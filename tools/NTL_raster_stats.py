import os
import re
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from rasterio.errors import RasterioIOError
from shapely.geometry import mapping
from shapely.ops import unary_union
from tqdm import tqdm

from storage_manager import storage_manager


class NTL_raster_statistics_input(BaseModel):
    ntl_tif_path: Optional[str] = Field(
        default=None,
        description="Single NTL GeoTIFF filename in 'inputs/' (e.g. 'ntl_2023.tif').",
    )
    ntl_tif_paths: Optional[List[str]] = Field(
        default=None,
        description="Optional batch input: multiple NTL GeoTIFF filenames in 'inputs/' for multi-year processing.",
    )
    shapefile_path: str = Field(..., description="Filename of the boundary Shapefile in 'inputs/' (e.g. 'city.shp')")
    output_csv_path: str = Field(..., description="Target filename for results in 'outputs/' (e.g. 'stats.csv')")
    selected_indices: Optional[List[str]] = Field(
        default=None,
        description="Optional list of indices to calculate: ['TNTL', 'LArea', 'ANTL', '3DPLand', '3DED', '3DLPI', 'MaxNTL', 'MinNTL', 'SDNTL']",
    )
    only_global: bool = Field(
        default=False,
        description="If True, only calculates aggregate summary for each raster and skips sub-region statistics.",
    )


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
        region = labeled == region_label
        edges = ndimage.binary_dilation(region) ^ region
        perimeter += np.sum(edges)
    return perimeter / total_intensity if total_intensity != 0 else np.nan


def calc_3DLPI(ntl_array):
    from scipy import ndimage

    lit_mask = ntl_array > 0
    labeled, num_features = ndimage.label(lit_mask)
    region_intensities = [np.nansum(ntl_array[labeled == i]) for i in range(1, num_features + 1)]
    if not region_intensities:
        return np.nan
    return np.nanmax(region_intensities) / np.nansum(ntl_array)


def calc_ANTL(ntl_array):
    valid_pixels = np.sum(~np.isnan(ntl_array))
    return np.nansum(ntl_array) / valid_pixels if valid_pixels != 0 else np.nan


def calc_indices_per_polygon(ntl_array, mask_array, pixel_area, selected_indices=None):
    masked_ntl = np.where(mask_array, ntl_array, np.nan)
    index_dict = {}

    def is_selected(name):
        return (selected_indices is None) or (name in selected_indices)

    if is_selected("MaxNTL"):
        index_dict["MaxNTL"] = np.nanmax(masked_ntl)
    if is_selected("MinNTL"):
        index_dict["MinNTL"] = np.nanmin(masked_ntl)
    if is_selected("SDNTL"):
        index_dict["SDNTL"] = np.nanstd(masked_ntl)
    if is_selected("TNTL"):
        index_dict["TNTL"] = calc_TNTL(masked_ntl)
    if is_selected("LArea"):
        index_dict["LArea"] = calc_LArea(masked_ntl, pixel_area)
    if is_selected("3DPLand"):
        index_dict["3DPLand"] = calc_3DPLand(masked_ntl)
    if is_selected("3DED"):
        index_dict["3DED"] = calc_3DED(masked_ntl)
    if is_selected("3DLPI"):
        index_dict["3DLPI"] = calc_3DLPI(masked_ntl)
    if is_selected("ANTL"):
        index_dict["ANTL"] = calc_ANTL(masked_ntl)

    return index_dict


def _collect_ntl_inputs(ntl_tif_path: Optional[str], ntl_tif_paths: Optional[List[str]]) -> List[str]:
    values: List[str] = []
    if isinstance(ntl_tif_path, str) and ntl_tif_path.strip():
        values.append(ntl_tif_path.strip())
    if isinstance(ntl_tif_paths, list):
        for path in ntl_tif_paths:
            if isinstance(path, str) and path.strip():
                values.append(path.strip())

    seen = set()
    deduped: List[str] = []
    for path in values:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def _extract_year_from_filename(name: str) -> Optional[int]:
    matches = re.findall(r"(19\d{2}|20\d{2})", name or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except Exception:
        return None


def _compute_for_single_raster(
    abs_ntl_path: str,
    ntl_label: str,
    abs_shp_path: str,
    selected_indices: Optional[List[str]],
    only_global: bool,
) -> Tuple[List[dict], Dict[str, float]]:
    with rasterio.open(abs_ntl_path) as src:
        ntl_data = src.read(1).astype(np.float32)
        ntl_data[ntl_data == src.nodata] = np.nan
        ntl_profile = src.profile
        pixel_area = abs(src.transform.a * src.transform.e)

        gdf = gpd.read_file(abs_shp_path)
        if gdf.empty:
            raise ValueError("Boundary file contains no features.")
        gdf = gdf.to_crs(ntl_profile["crs"])

        global_geom = unary_union(gdf.geometry)
        mask_global, _, _ = rasterio.mask.raster_geometry_mask(src, [mapping(global_geom)], invert=False)
        global_indices = calc_indices_per_polygon(ntl_data, ~mask_global, pixel_area, selected_indices=selected_indices)

        results: List[dict] = []
        name_col = "name" if "name" in gdf.columns else (gdf.columns[0] if len(gdf.columns) > 0 else "ID")
        year_val = _extract_year_from_filename(ntl_label)

        if not only_global:
            for _, row in tqdm(gdf.iterrows(), total=len(gdf), desc=f"Calculating NTL ({ntl_label})"):
                if row.geometry.is_empty:
                    continue
                mask_local, _, _ = rasterio.mask.raster_geometry_mask(src, [mapping(row.geometry)], invert=False)
                local_indices = calc_indices_per_polygon(ntl_data, ~mask_local, pixel_area, selected_indices=selected_indices)
                results.append(
                    {
                        "Raster_file": ntl_label,
                        "Year": year_val,
                        "Region": row[name_col],
                        **local_indices,
                    }
                )

        results.append(
            {
                "Raster_file": ntl_label,
                "Year": year_val,
                "Region": "Global_Summary",
                **global_indices,
            }
        )
        return results, global_indices


def NTL_raster_statistics(
    shapefile_path,
    output_csv_path,
    ntl_tif_path=None,
    ntl_tif_paths=None,
    selected_indices=None,
    only_global=False,
):
    ntl_inputs = _collect_ntl_inputs(ntl_tif_path=ntl_tif_path, ntl_tif_paths=ntl_tif_paths)
    if not ntl_inputs:
        return "Error: Provide 'ntl_tif_path' or 'ntl_tif_paths' with at least one raster filename."

    abs_shp_path = storage_manager.resolve_input_path(shapefile_path)
    abs_out_path = storage_manager.resolve_output_path(output_csv_path)

    if not os.path.exists(abs_shp_path):
        return f"Error: Shapefile not found at {abs_shp_path}"

    all_results: List[dict] = []
    global_summaries: List[Tuple[str, Dict[str, float]]] = []

    for tif_name in ntl_inputs:
        abs_ntl_path = storage_manager.resolve_input_path(tif_name)
        if not os.path.exists(abs_ntl_path):
            return f"Error: Raster file not found at {abs_ntl_path}"

        try:
            rows, global_indices = _compute_for_single_raster(
                abs_ntl_path=abs_ntl_path,
                ntl_label=tif_name,
                abs_shp_path=abs_shp_path,
                selected_indices=selected_indices,
                only_global=only_global,
            )
            all_results.extend(rows)
            global_summaries.append((tif_name, global_indices))
        except RasterioIOError as e:
            return f"Error: Failed to open raster '{tif_name}'. Details: {str(e)}"
        except Exception as e:
            return f"Error: Failed during NTL raster statistics calculation for '{tif_name}'. Details: {str(e)}"

    df = pd.DataFrame(all_results)
    df.to_csv(abs_out_path, index=False, encoding="utf-8", float_format="%.4f")

    total_feature_rows = len([r for r in all_results if r.get("Region") != "Global_Summary"])
    summary_blocks = []
    for tif_name, global_indices in global_summaries:
        lines = [f"- {k}: {v:.4f}" for k, v in global_indices.items()]
        summary_blocks.append(f"[{tif_name}]\n" + "\n".join(lines))
    summary_str = "\n\n".join(summary_blocks)

    if len(ntl_inputs) == 1:
        if total_feature_rows <= 0:
            return (
                f"Results saved to: {output_csv_path}\n\n"
                f"**Global Summary (Total ROI):**\n{summary_str}\n"
                "Note: Detailed statistics for each sub-region are available in the generated CSV file."
            )
        return (
            f"Success: Analysis completed for {total_feature_rows} region rows.\n"
            f"Results saved to: {output_csv_path}\n\n"
            f"**Global Summary (Total ROI):**\n{summary_str}\n"
            "Note: Detailed statistics for each sub-region are available in the generated CSV file."
        )

    return (
        f"Success: Batch analysis completed for {len(ntl_inputs)} rasters.\n"
        f"Feature rows: {total_feature_rows}\n"
        f"Results saved to: {output_csv_path}\n\n"
        f"**Global Summary (Per Raster):**\n{summary_str}"
    )


NTL_raster_statistics_tool = StructuredTool.from_function(
    func=NTL_raster_statistics,
    name="NTL_raster_statistics",
    description=(
        "Calculates Nighttime Light (NTL) landscape indices for one or multiple rasters over a boundary shapefile. "
        "Use `ntl_tif_path` for single-year input or `ntl_tif_paths` for multi-year batch processing in one call. "
        "By default, it computes per-feature statistics plus a global summary; set `only_global=True` to skip per-feature rows. "
        "Outputs a CSV in outputs/."
    ),
    args_schema=NTL_raster_statistics_input,
)
