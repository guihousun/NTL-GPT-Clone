import numpy as np
import geopandas as gpd
import rasterio
import rasterio.mask
from shapely.geometry import mapping
import pandas as pd
from tqdm import tqdm
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from shapely.ops import unary_union
import os
from storage_manager import storage_manager

class NTL_raster_statistics_input(BaseModel):
    ntl_tif_path: str = Field(..., description="Filename of the NTL GeoTIFF in 'inputs/' (e.g. 'ntl_2023.tif')")
    shapefile_path: str = Field(..., description="Filename of the boundary Shapefile in 'inputs/' (e.g. 'city.shp')")
    output_csv_path: str = Field(..., description="Target filename for results in 'outputs/' (e.g. 'stats.csv')")
    selected_indices: list[str] = Field(
        default=None,
        description="Optional list of indices to calculate: ['TNTL', 'LArea', 'ANTL', '3DPLand', '3DED', '3DLPI', 'MaxNTL', 'MinNTL', 'SDNTL']"
    )
    only_global: bool = Field(
        default=False, 
        description="If True, only calculates the aggregate summary for the entire shapefile and skips individual region statistics."
    )


# --- 指数计算核心函数 (保持逻辑不变) ---

def calc_TNTL(ntl_array):
    return np.nansum(ntl_array)

def calc_LArea(ntl_array, pixel_area):
    lit_mask = ntl_array > 0
    return np.sum(lit_mask) * pixel_area

def calc_3DPLand(ntl_array):
    max_ntl = np.nanmax(ntl_array)
    n_pixels = np.sum(~np.isnan(ntl_array))
    if max_ntl == 0 or n_pixels == 0:
        return np.nan
    return np.nansum(ntl_array) / (max_ntl * n_pixels)

def calc_3DED(ntl_array):
    from scipy import ndimage
    lit_mask = ntl_array > 0
    labeled, num_features = ndimage.label(lit_mask)
    perimeter = 0
    total_intensity = np.nansum(ntl_array)
    for region_label in range(1, num_features + 1):
        region = (labeled == region_label)
        edges = ndimage.binary_dilation(region) ^ region
        perimeter += np.sum(edges)
    return perimeter / total_intensity if total_intensity != 0 else np.nan

def calc_3DLPI(ntl_array):
    from scipy import ndimage
    lit_mask = ntl_array > 0
    labeled, num_features = ndimage.label(lit_mask)
    region_intensities = [np.nansum(ntl_array[labeled == i]) for i in range(1, num_features + 1)]
    if not region_intensities: return np.nan
    return np.nanmax(region_intensities) / np.nansum(ntl_array)

def calc_ANTL(ntl_array):
    valid_pixels = np.sum(~np.isnan(ntl_array))
    return np.nansum(ntl_array) / valid_pixels if valid_pixels != 0 else np.nan

def calc_indices_per_polygon(ntl_array, mask_array, pixel_area, hist_bins=10, selected_indices=None):
    masked_ntl = np.where(mask_array, ntl_array, np.nan)
    index_dict = {}
    
    def is_selected(name):
        return (selected_indices is None) or (name in selected_indices)

    # 统计指标计算
    if is_selected("MaxNTL"): index_dict["MaxNTL"] = np.nanmax(masked_ntl)
    if is_selected("MinNTL"): index_dict["MinNTL"] = np.nanmin(masked_ntl)
    if is_selected("SDNTL"): index_dict["SDNTL"] = np.nanstd(masked_ntl)
    if is_selected("TNTL"): index_dict["TNTL"] = calc_TNTL(masked_ntl)
    if is_selected("LArea"): index_dict["LArea"] = calc_LArea(masked_ntl, pixel_area)
    if is_selected("3DPLand"): index_dict["3DPLand"] = calc_3DPLand(masked_ntl)
    if is_selected("3DED"): index_dict["3DED"] = calc_3DED(masked_ntl)
    if is_selected("3DLPI"): index_dict["3DLPI"] = calc_3DLPI(masked_ntl)
    if is_selected("ANTL"): index_dict["ANTL"] = calc_ANTL(masked_ntl)
    
    return index_dict

# --- 主逻辑函数 (路径重构 & 英文版) ---

def NTL_raster_statistics(ntl_tif_path, shapefile_path, output_csv_path, selected_indices=None, only_global=False):


    # 1. Resolve Paths using storage_manager
    abs_ntl_path = storage_manager.resolve_input_path(ntl_tif_path)
    abs_shp_path = storage_manager.resolve_input_path(shapefile_path)
    abs_out_path = storage_manager.resolve_output_path(output_csv_path)

    if not os.path.exists(abs_ntl_path):
        return f"Error: Raster file not found at {abs_ntl_path}"
    if not os.path.exists(abs_shp_path):
        return f"Error: Shapefile not found at {abs_shp_path}"

    with rasterio.open(abs_ntl_path) as src:
        ntl_data = src.read(1).astype(np.float32)
        ntl_data[ntl_data == src.nodata] = np.nan
        ntl_profile = src.profile
        pixel_area = abs(src.transform.a * src.transform.e)

        # Step 1: Global Summary
        gdf = gpd.read_file(abs_shp_path).to_crs(ntl_profile['crs'])
        global_geom = unary_union(gdf.geometry)
        mask_global, _, _ = rasterio.mask.raster_geometry_mask(src, [mapping(global_geom)], invert=False)
        global_indices = calc_indices_per_polygon(ntl_data, ~mask_global, pixel_area, selected_indices=selected_indices)

        # Step 2: Per Region Calculation
        results = []
        # Try to find a name column in English
        name_col = 'name' if 'name' in gdf.columns else (gdf.columns[0] if len(gdf.columns) > 0 else 'ID')
        if not only_global:
            for _, row in tqdm(gdf.iterrows(), total=len(gdf), desc="Calculating NTL Indices"):
                if row.geometry.is_empty: continue
                mask_local, _, _ = rasterio.mask.raster_geometry_mask(src, [mapping(row.geometry)], invert=False)
                local_indices = calc_indices_per_polygon(ntl_data, ~mask_local, pixel_area, selected_indices=selected_indices)
                
                results.append({
                    'Region': row[name_col],
                    **local_indices
                })

        # Step 3: Append Global Result
        results.append({
            'Region': 'Global_Summary',
            **global_indices
        })

    # Save to CSV
    df = pd.DataFrame(results)
    df.to_csv(abs_out_path, index=False, encoding='utf-8', float_format="%.4f")
    
    # 提取全域汇总数据（即 global_indices）
    summary_lines = []
    for k, v in global_indices.items():
        summary_lines.append(f"- {k}: {v:.4f}")
    summary_str = "\n".join(summary_lines)


    # 返回给 Agent 的消息
    return (
        f"Success: Analysis completed for {len(results)-1} regions.\n"
        f"Results saved to: {output_csv_path}\n\n"
        f"**Global Summary (Total ROI):**\n{summary_str}\n"
        f"Note: Detailed statistics for each sub-region are available in the generated CSV file."
    )

# --- Tool Definition ---


NTL_raster_statistics_tool = StructuredTool.from_function(
    func=NTL_raster_statistics,
    name="NTL_raster_statistics",
    description=(
    "Calculates Nighttime Light (NTL) landscape indices for a given region defined by a shapefile. "
    "By default, it computes statistics for each individual feature (e.g., city, district) AND a global summary for the entire area. "
    "If `only_global=True`, it skips per-feature calculations and returns ONLY the aggregate summary for the whole shapefile. "
    "Inputs must be filenames within the workspace. "
    "Outputs a CSV file containing the results in the outputs directory. "
    "Common indices include TNTL, LArea, ANTL, MaxNTL, SDNTL, 3DPLand, 3DED, 3DLPI, etc. "
    ),
    args_schema=NTL_raster_statistics_input,
)
# 示例调用：计算武汉市的 NTL 统计
# 假设你的 NTL GeoTIFF 文件名为 "wuhan_ntl_2020.tif"，位于 inputs/ 文件夹中
# 如果文件名不同，请替换 ntl_tif_path

result = NTL_raster_statistics_tool.run({
    "ntl_tif_path": "NTL_Wuhan_2020_Lockdown_2020-04.tif",  # 替换为你的实际 NTL 文件名
    "shapefile_path": "wuhan_boundary.shp",  # 使用之前下载的武汉边界
    "output_csv_path": "wuhan_ntl_stats.csv",  # 输出文件名
    "selected_indices": ["TNTL", "LArea", "ANTL", "3DPLand"],  # 选择要计算的指标（可选）
    "only_global": False  # 如果只想全局汇总，设为 True
})

print(result)
# result = NTL_raster_statistics.run({
#     "ntl_tif_path": "./NTL_Agent/Night_data/Shanghai/NTL_上海市_VIIRS_2020.tif",
#     "shapefile_path": "./NTL_Agent/report/shp/Shanghai/上海.shp",
#     "output_csv_path": "shanghai_TNTL_only.csv",
#     "selected_indices": ["TNTL", "LArea", "3DPLand"]
#     })