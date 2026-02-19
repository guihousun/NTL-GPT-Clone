# GEE_download.py
import os
import json
import tempfile
import ee
import sys
import os
from storage_manager import storage_manager
project_id = 'empyrean-caster-430308-m2'
ee.Initialize(project=project_id)

_PROJECT_ID = 'empyrean-caster-430308-m2'
_EE_READY = False

def _init_ee_if_needed():
    """Lazy init: 优先服务账号，其次本地交互式认证；只初始化一次。"""
    global _EE_READY
    if _EE_READY:
        return
    try:
        # 尝试直接使用已有持久凭证（本地开发时可能有效）
        ee.Initialize(project=_PROJECT_ID)
        _EE_READY = True
        return
    except Exception:
        pass

    # 1) 服务账号路径：用于云端/Streamlit 等非交互环境（推荐）
    sa_email = (
        os.getenv("EE_SERVICE_ACCOUNT") or
        getattr(__import__("builtins"), "st", None) and __import__("builtins").st.secrets.get("EE_SERVICE_ACCOUNT")
    )
    sa_key_json = (
        os.getenv("EE_PRIVATE_KEY_JSON") or
        getattr(__import__("builtins"), "st", None) and __import__("builtins").st.secrets.get("EE_PRIVATE_KEY_JSON")
    )

    if sa_email and sa_key_json:
        # 将 JSON 写入临时文件（ee 旧版只接受文件路径最稳妥）
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            if isinstance(sa_key_json, dict):
                f.write(json.dumps(sa_key_json).encode("utf-8"))
            else:
                f.write(sa_key_json.encode("utf-8"))
            key_path = f.name
        creds = ee.ServiceAccountCredentials(sa_email, key_path)
        ee.Initialize(credentials=creds, project=_PROJECT_ID)
        _EE_READY = True
        return

    # 2) 本地开发（可交互）：退回到 OAuth
    # 注意：云端/容器里这一步会卡/失败，所以只在本地使用
    ee.Authenticate()           # 需要在本地浏览器完成一次授权
    ee.Initialize(project=_PROJECT_ID)
    _EE_READY = True

from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

class NightlightDataInput(BaseModel):
    study_area: str = Field(..., description="Name of the study area of interest. Example: 'Nanjing'")
    scale_level: Literal['country', 'province', 'city', 'county'] = Field(..., description="Administrative scale level.")
    temporal_resolution: Literal['annual', 'monthly', 'daily'] = Field(..., description="Temporal resolution: 'annual', 'monthly', or 'daily'.")
    time_range_input: str = Field(..., description="Time range. Annual: 'YYYY to YYYY' or 'YYYY'. Monthly: 'YYYY-MM to YYYY-MM'. Daily: 'YYYY-MM-DD to YYYY-MM-DD'.")
    out_name: str = Field(..., description="Output filename ONLY (e.g., 'NTL_Nanjing_VNP46A2_2021-05.tif'), no path, will be saved to your workspace's 'inputs/' directory.")
    dataset_name: Optional[str] = Field(None, description=(
        "Further dataset selection. "
        "For annual: 'NPP-VIIRS-Like' (default), 'NPP-VIIRS', 'DMSP-OLS'. "
        "For monthly: 'NOAA_VCMSLCFG' (fixed). "
        "For daily: 'VNP46A2' (default), 'VNP46A1'."
    ))
    collection_name: Optional[str] = Field(None, description="Optional logical name for the exported collection.")
    is_in_China: Optional[bool] = Field(
        None,
        description=(
            "Whether the study area is located in China. "
            "If True, uses domestic administrative boundary datasets. "
            "If False, uses international boundary datasets (e.g., GAUL, GADM). "
        )
    )

def ntl_download_tool(
        study_area: str,
        scale_level: str,
        temporal_resolution: str,
        time_range_input: str,
        out_name: str,
        dataset_name: Optional[str] = None,
        is_in_China: Optional[bool] = None,
):
    import os
    import re
    import ee
    import geemap
    import calendar
    from datetime import datetime, timedelta

    # ---------- Admin boundary sources ----------
    national_collection = ee.FeatureCollection("projects/empyrean-caster-430308-m2/assets/World_countries")
    province_collection = ee.FeatureCollection("projects/empyrean-caster-430308-m2/assets/province")
    city_collection = ee.FeatureCollection("projects/empyrean-caster-430308-m2/assets/city")
    county_collection = ee.FeatureCollection("projects/empyrean-caster-430308-m2/assets/county")
    international_collection = ee.FeatureCollection("FAO/GAUL/2015/level1")
    def get_administrative_boundaries(scale_level: str, study_area: str, is_in_China: bool):
        if is_in_China:
            directly_governed_cities = ['北京市', '天津市', '上海市', '重庆市']
            if scale_level == 'province' or (scale_level == 'city' and study_area in directly_governed_cities):
                admin_boundary = province_collection
                name_property = 'name'
            elif scale_level == 'country':
                admin_boundary = national_collection
                name_property = 'NAME'
            elif scale_level == 'city':
                admin_boundary = city_collection
                name_property = 'name'
            elif scale_level == 'county':
                admin_boundary = county_collection
                name_property = 'name'
            else:
                raise ValueError("Unknown scale level. Options are 'country', 'province', 'city', 'county'.")
        else:
            admin_boundary = international_collection
            if scale_level == 'country':
                name_property = 'ADM0_NAME'
            elif scale_level == 'province':
                name_property = 'ADM1_NAME'
            else:
                raise ValueError("only support scale 'country' and 'province'。")
        return admin_boundary, name_property

    admin_boundary, name_property = get_administrative_boundaries(scale_level, study_area, is_in_China)
    region = admin_boundary.filter(ee.Filter.eq(name_property, study_area))

    if region.size().getInfo() == 0:
        raise ValueError(f"No area named '{study_area}' found under scale level '{scale_level}'.")

    # ---------- Temporal parsing ----------
    def parse_time_range(time_range_input: str, temporal_resolution: str):
        tr = time_range_input.replace(' ', '')
        if 'to' in tr:
            start_str, end_str = [s.strip() for s in tr.split('to')]
        else:
            start_str = end_str = tr

        if temporal_resolution == 'annual':
            if re.fullmatch(r'\d{4}-01-01', start_str) and re.fullmatch(r'\d{4}-12-31', end_str):
                start_str = start_str[:4]
                end_str = end_str[:4]   

            if not re.fullmatch(r'\d{4}', start_str) or not re.fullmatch(r'\d{4}', end_str):
                raise ValueError("Annual format must be 'YYYY' or 'YYYY to YYYY'.")
            start_date, end_date = f"{start_str}-01-01", f"{end_str}-12-31"
        elif temporal_resolution == 'monthly':
            if not re.fullmatch(r'\d{4}-\d{2}', start_str) or not re.fullmatch(r'\d{4}-\d{2}', end_str):
                raise ValueError("Monthly format must be 'YYYY-MM' or 'YYYY-MM to YYYY-MM'.")
            sy, sm = map(int, start_str.split('-'))
            ey, em = map(int, end_str.split('-'))
            start_date = f"{sy}-{sm:02d}-01"
            end_date = f"{ey}-{em:02d}-{calendar.monthrange(ey, em)[1]}"
        elif temporal_resolution == 'daily':
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start_str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', end_str):
                raise ValueError("Daily format must be 'YYYY-MM-DD' or 'YYYY-MM-DD to YYYY-MM-DD'.")
            start_date, end_date = start_str, end_str
        else:
            raise ValueError("temporal_resolution must be one of: 'annual', 'monthly', 'daily'.")

        if datetime.strptime(start_date, '%Y-%m-%d') > datetime.strptime(end_date, '%Y-%m-%d'):
            raise ValueError("Start date cannot be later than end date.")

        return start_date, end_date

    start_date, end_date = parse_time_range(time_range_input, temporal_resolution)

    # ---------- Dataset routing ----------
    # Defaults
    # ---------- Dataset routing: ANNUAL ----------
    if temporal_resolution == 'annual':
        dataset_name = dataset_name or 'NPP-VIIRS-Like'

        # 配置与有效年限
        annual_like_cfg = {'id': 'projects/sat-io/open-datasets/npp-viirs-ntl', 'band': 'b1', 'valid_from': 2000,
                           'valid_to': 2024}
        dmsp_cfg = {'id': 'NOAA/DMSP-OLS/NIGHTTIME_LIGHTS', 'band': 'avg_vis', 'valid_from': 1992, 'valid_to': 2013}

        start_year, end_year = int(start_date[:4]), int(end_date[:4])

        if dataset_name == 'NPP-VIIRS-Like':
            if start_year < annual_like_cfg['valid_from'] or end_year > annual_like_cfg['valid_to']:
                raise ValueError(
                    f"NPP-VIIRS-Like valid year range: {annual_like_cfg['valid_from']}–{annual_like_cfg['valid_to']}.")
            col_id, band = annual_like_cfg['id'], annual_like_cfg['band']
            images = []
            for y in range(start_year, end_year + 1):
                y_start, y_end = f"{y}-01-01", f"{y + 1}-01-01"
                col = ee.ImageCollection(col_id).filterDate(y_start, y_end).select(band).filterBounds(region.geometry())
                img = col.map(lambda i: i.clip(region)).mean().set('system:time_start', ee.Date(y_start).millis())
                images.append(img)
            if not images:
                return "No images found for the specified date range and region."
            NTL_collection = ee.ImageCollection(images)

        elif dataset_name == 'NPP-VIIRS':
            # 2012–2021: V21；2022-2023: V22；
            V21_ID, V22_ID, BAND = 'NOAA/VIIRS/DNB/ANNUAL_V21', 'NOAA/VIIRS/DNB/ANNUAL_V22', 'average'
            valid_from, valid_to = 2012, 2023
            if start_year < valid_from or end_year > valid_to:
                raise ValueError(
                    f"NPP-VIIRS valid year range: {valid_from}–{valid_to}. (2012–2021 from V21, 2022-2023 from V22)")

            images = []
            for y in range(start_year, end_year + 1):
                y_start, y_end = f"{y}-01-01", f"{y + 1}-01-01"
                src_id = V21_ID if y <= 2021 else V22_ID
                col = ee.ImageCollection(src_id).filterDate(y_start, y_end).select(BAND).filterBounds(region.geometry())
                img = col.map(lambda i: i.clip(region)).mean().set('system:time_start', ee.Date(y_start).millis())
                images.append(img)

            if not images:
                return "No images found for the specified date range and region."
            NTL_collection = ee.ImageCollection(images)

        elif dataset_name == 'DMSP-OLS':
            if start_year < dmsp_cfg['valid_from'] or end_year > dmsp_cfg['valid_to']:
                raise ValueError(f"DMSP-OLS valid year range: {dmsp_cfg['valid_from']}–{dmsp_cfg['valid_to']}.")
            col_id, band = dmsp_cfg['id'], dmsp_cfg['band']
            images = []
            for y in range(start_year, end_year + 1):
                y_start, y_end = f"{y}-01-01", f"{y + 1}-01-01"
                col = ee.ImageCollection(col_id).filterDate(y_start, y_end).select(band).filterBounds(region.geometry())
                img = col.map(lambda i: i.clip(region)).mean().set('system:time_start', ee.Date(y_start).millis())
                images.append(img)
            if not images:
                return "No images found for the specified date range and region."
            NTL_collection = ee.ImageCollection(images)

        else:
            raise ValueError(
                "For annual, dataset_name must be one of: 'NPP-VIIRS-Like' (default), 'NPP-VIIRS', 'DMSP-OLS'.")



    elif temporal_resolution == 'monthly':
        # Fixed monthly dataset
        col_id = 'NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG'
        band = 'avg_rad'
        sy, sm = map(int, start_date[:7].split('-'))
        ey, em = map(int, end_date[:7].split('-'))

        if sy < 2014:
            raise ValueError("Monthly VIIRS is available from 2014-01 onwards.")
        images = []
        for y in range(sy, ey + 1):
            m_start = sm if y == sy else 1
            m_end = em if y == ey else 12
            for m in range(m_start, m_end + 1):
                s_day = f"{y}-{m:02d}-01"
                e_day = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]}"
                collection = ee.ImageCollection(col_id).filterDate(s_day, e_day).select(band).filterBounds(region.geometry())
                image = collection.map(lambda img: img.clip(region)).mean().set('system:time_start', ee.Date(s_day).millis())
                images.append(image)
        if not images:
            return "No images found for the specified date range and region."
        NTL_collection = ee.ImageCollection(images)

    elif temporal_resolution == 'daily':
        dataset_name = dataset_name or 'VNP46A2'
        daily_map = {
            'VNP46A2': {'id': 'NASA/VIIRS/002/VNP46A2', 'band': 'DNB_BRDF_Corrected_NTL'},
            'VNP46A1': {'id': 'NOAA/VIIRS/001/VNP46A1', 'band': 'DNB_At_Sensor_Radiance_500m'},
        }
        if dataset_name not in daily_map:
            raise ValueError("For daily, dataset_name must be one of: 'VNP46A2' (default), 'VNP46A1'.")
        col_id, band = daily_map[dataset_name]['id'], daily_map[dataset_name]['band']
        if int(start_date[:4]) < 2014:
            raise ValueError("Daily VIIRS is available from 2014-01 onwards.")
        NTL_collection = (
            ee.ImageCollection(col_id)
            .filterDate(start_date, (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d'))
            .select(band)
            .filterBounds(region.geometry())
            .map(lambda img: img.clip(region))
        )

    else:
        raise ValueError("temporal_resolution must be 'annual', 'monthly', or 'daily'.")

    
    # ---------- Export ----------
    images_list = NTL_collection.toList(NTL_collection.size())
    num_images = NTL_collection.size().getInfo()

    exported_files = []
        # 多文件输出情况下动态生成唯一names
    for i in range(num_images):
        image = ee.Image(images_list.get(i))
        if num_images == 1:
            filename = out_name
        else:
            # 动态加上 image_date
            if temporal_resolution == "annual":
                image_date = image.date().format('YYYY').getInfo()
            elif temporal_resolution == "monthly":
                image_date = image.date().format('YYYY-MM').getInfo()
            else:
                image_date = image.date().format('YYYY-MM-dd').getInfo()
            name_no_ext, ext = os.path.splitext(out_name)
            filename = f"{name_no_ext}_{image_date}{ext}"
        # 路径必须用 resolve_path
        abs_input = storage_manager.resolve_input_path(filename)

        os.makedirs(os.path.dirname(abs_input), exist_ok=True)  # 确保inputs/存在

        try:
            geemap.ee_export_image(
                ee_object=image,
                filename=abs_input,
                scale=500,
                region=region.geometry(),
                crs='EPSG:4326',
                file_per_band=False
            )
            exported_files.append(filename)  # 只返回逻辑文件名，后续工具用 inputs/filename
            print(f"Exported to: {abs_input}")
        except Exception as e:
            print(f"Failed to export {abs_input}: {e}")
            continue

    return {
        "output_files": exported_files  # 列出每个输出逻辑文件名
    }






# Update the nightlight_download_tool
NTL_download_tool = StructuredTool.from_function(
    ntl_download_tool,
    name="NTL_download_tool",
    description=(
        """
        This tool downloads NTL data from GEE
        CRITICAL LANGUAGE RULE: 
        - For regions in CHINA, the 'study_area' MUST be in **Chinese** (e.g., use '南京市' instead of 'Nanjing'). 
        - For regions OUTSIDE China, use **English** (e.g., 'New York').

        Parameters include region name, spatial level (country/province/city/county), temporal resolution (annual/monthly/daily), optional dataset name, and time range.

        EFFICIENCY & QUOTA RULE (IMPORTANT):
        - Do NOT automatically download a large number of daily images (e.g., >31 days) without justification.
        - If the user's request covers a long period, you MUST suggest or prioritize monthly composites ('NOAA_VCMSLCFG') or annual composites ('NPP-VIIRS-Like') instead of daily data ('VNP46A2').
        - Before downloading a massive daily dataset, ask the user like this: "Downloading daily data for [X] months will result in [N] images. Would you prefer a monthly composite product to save time and storage?"

        Dataset selection:
        - Annual: 'NPP-VIIRS-Like' (default), 'NPP-VIIRS', 'DMSP-OLS'
        - Monthly: fixed to 'NOAA_VCMSLCFG'
        - Daily: 'VNP46A2' (default), 'VNP46A1'

        # Output protocol
        - Only specify the output file name (e.g., out_name="NTL_Nanjing_VNP46A2_2021-05.tif"); do not include any folder or path. 
        - The tool will automatically save the downloaded file into your session's isolated 'inputs/' folder.

        Example Input:
        (
            study_area='南京市',
            scale_level='city',
            temporal_resolution='monthly',
            dataset_name='VNP46A2',
            time_range_input='2021-05 to 2021-07',
            out_name='NTL_Nanjing_VNP46A2_2021-05.tif'
            is_in_China=True
        )
        or
        (
            study_area='上海市',
            scale_level='province',
            temporal_resolution='annual',
            dataset_name='NPP-VIIRS-Like',
            time_range_input='2000 to 2023',
            out_name='NTL_Shanghai_NPP-VIIRS-Like_2020.tif'
            is_in_China=True
        )
        or
        (
            study_area='定日县',
            scale_level='county',
            temporal_resolution='daily',
            time_range_input='2020-01-01 to 2020-02-01',
            out_name='NTL_Dingri_VNP46A2_2020-01-01.tif'
            is_in_China=True
        )
        """
    )
    ,
    input_type=NightlightDataInput,
)

#
result = NTL_download_tool.func(study_area='上海市',
    scale_level='city',
    temporal_resolution = 'daily',
    dataset_name='VNP46A1',
    time_range_input='2026-01-18 to 2026-01-23',
    out_name='NTL_Shanghai_VNP46A2_2026-01-20.tif',
    is_in_China=True,)

# result2 = NDVI_download_tool.func(study_area='南京市',
#     scale_level='city',
#     time_range_input='2018 to 2020',
#     out_name='./NTL_Agent/NDVI_data/Nanjing')

# result2 = NDVI_download_tool.func(study_area='南京市',
#     scale_level='city',
#     time_range_input='2018 to 2020',
#     out_name='./NTL_Agent/NDVI_data/Nanjing')

