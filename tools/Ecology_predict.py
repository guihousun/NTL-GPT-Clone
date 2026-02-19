from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import os
import pandas as pd
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask

# 文件路径
base_path = r"C:\NTL-CHAT\tool\GDP\test\\"
geojson_path = os.path.join(base_path, "中国_省 (1).geojson")

# 参数和阈值
params = {
    2000: (0.0221, 1360.76), 2001: (0.0185, 1642.64), 2002: (0.0230, 813.29),
    2003: (0.0196, 1485.76), 2004: (0.0237, 1360.78), 2005: (0.0264, 1207.83),
    2006: (0.0297, 1063.79), 2007: (0.0316, 1368.72), 2008: (0.0370, 909.52),
    2009: (0.0368, 1205.12), 2010: (0.0434, 978.93), 2011: (0.0463, 1351.84),
    2012: (0.0469, 1253.63), 2013: (0.0502, 1279.73), 2014: (0.0514, 1272.24),
    2015: (0.0508, 1209.69), 2016: (0.0514, 1353.13), 2017: (0.0553, 1285.67),
    2018: (0.0572, 1201.84), 2019: (0.0575, 1278.31), 2020: (0.0614, 1304.78),
    2021: (0.0633, 1408.47), 2022: (0.0651, 1376.85), 2023: (0.0665, 1297.19)
}
MIN_TNL_THRESHOLD = 100
MIN_GDP_THRESHOLD = 0


# 定义输入模型
class GDPToolInput(BaseModel):
    years: list = Field(..., description="用户选择的年份列表，格式如 [2000, 2001, 2023]")


# 定义 GDP 计算函数
def calculate_gdp(years: list) -> str:
    # 检查 GeoJSON 文件
    if not os.path.exists(geojson_path):
        return "GeoJSON文件不存在，请检查路径。"

    # 读取中国省份边界
    china_provinces = gpd.read_file(geojson_path)

    all_results = []
    for year in years:
        nighttime_image_path = os.path.join(base_path, f"LongNTL_{year}.tif")

        # 检查影像文件
        if not os.path.exists(nighttime_image_path):
            return f"影像文件 {nighttime_image_path} 不存在，请检查路径。"

        # 获取年份参数
        w, c = params.get(year, (0, 0))

        # 打开影像文件并裁剪各省影像
        with rasterio.open(nighttime_image_path) as src:
            results = []
            for _, row in china_provinces.iterrows():
                province_name = row["name"]
                if any(region in province_name for region in ["台湾", "香港", "澳门", "境界线"]):
                    continue

                geometry = [row["geometry"]]
                try:
                    out_image, out_transform = mask(src, geometry, crop=True)
                    out_image = out_image[0].astype(np.float64)
                    out_image = np.where((out_image >= 0) & (out_image <= 255), out_image, np.nan)

                    # 计算 TNL 和 GDP
                    province_tnl = np.nansum(out_image)
                    province_gdp = max(MIN_GDP_THRESHOLD,
                                       w * province_tnl + c) if province_tnl >= MIN_TNL_THRESHOLD else 0

                    results.append({"省份": province_name, "TNL": province_tnl, "估算GDP(亿人民币)": province_gdp})

                except Exception as e:
                    print(f"无法处理 {province_name}: {e}")

            # 结果保存
            output_path = os.path.join(base_path, f"GDP_estimates_{year}.csv")
            if os.path.exists(output_path):
                output_path = os.path.join(base_path, f"GDP_estimates_{year}_new.csv")

            df = pd.DataFrame(results)
            df.to_csv(output_path, index=False)
            all_results.append(f"{year} 年的结果已保存至: {output_path}")

    return "\n".join(all_results)


# 将 GDP 计算工具转为 LangChain 的 `StructuredTool`
gdp_tool = StructuredTool.from_function(
    calculate_gdp,
    name="gdp_estimation_tool",
    description=(
        "计算给定年份的中国各省份 GDP。输入一个年份列表（如 [2000, 2001, 2023]），"
        "工具将使用夜间灯光影像和线性回归模型估算 GDP，并保存结果到 CSV 文件中。"
    ),
    input_type=GDPToolInput,
)

# result = gdp_tool.func([2010,2020])
# print(result)