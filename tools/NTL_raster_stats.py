"""Thread-workspace NTL zonal landscape statistics.

The historical implementation delegated this public tool to the generic
``ntl_toolkit`` metric adapter. That adapter intentionally keeps a compact
legacy surface, but treats the affine determinant as an area even for a
geographic grid and retained an older perimeter-based interpretation of
``3DED``. This wrapper owns the richer, scientifically explicit semantics
needed by the runtime tool:

* pixels are selected by centre containment (``all_touched=False``);
* declared NoData and non-finite values are excluded while valid zeroes remain;
* area metrics use WGS84 geodesic source-pixel area in km2; and
* the 3D landscape measures use four-neighbour lit patches.

The public function and its original parameters remain stable so existing
tool calls continue to work.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import StructuredTool
from pydantic.v1 import BaseModel, Field
from pyproj import CRS, Geod, Transformer
from rasterio.features import geometry_mask
from scipy import ndimage
from shapely.geometry import mapping
from shapely.ops import unary_union

from storage_manager import current_thread_id, storage_manager


_METRIC_ORDER = (
    "MaxNTL",
    "MinNTL",
    "SDNTL",
    "TNTL",
    "LArea",
    "3DPLand",
    "3DED",
    "3DLPI",
    "ANTL",
)
_FOUR_NEIGHBOUR_STRUCTURE = np.array(
    [[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8
)
_WGS84 = CRS.from_epsg(4326)


class NTL_raster_statistics_input(BaseModel):
    ntl_tif_path: Optional[str] = Field(
        default=None,
        description=(
            "Single NTL GeoTIFF input. Supports local workspace filename in 'inputs/' "
            "(e.g. 'ntl_2023.tif') or shared virtual path (e.g. '/shared/Q11/inputs/ntl_2023.tif')."
        ),
    )
    ntl_tif_paths: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional batch input list. Each item supports local 'inputs/' filename "
            "or shared virtual path '/shared/...'."
        ),
    )
    shapefile_path: str = Field(
        ...,
        description=(
            "Boundary Shapefile input. Supports local 'inputs/' filename "
            "or shared virtual path (e.g. '/shared/Q11/inputs/city.shp')."
        ),
    )
    output_csv_path: str = Field(
        ...,
        description=(
            "Target output filename in current-thread workspace 'outputs/' (e.g. 'stats.csv'). "
            "Do not use '/shared/...'; shared paths are read-only."
        ),
    )
    selected_indices: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional list of indices to calculate: ['TNTL', 'LArea', 'ANTL', "
            "'3DPLand', '3DED', '3DLPI', 'MaxNTL', 'MinNTL', 'SDNTL']. "
            "LArea is km2, 3DPLand is percent, 3DED is lit-patch geodesic area "
            "per summed NTL, and 3DLPI is a fraction."
        ),
    )
    only_global: bool = Field(
        default=False,
        description="If True, only calculates aggregate summary for each raster and skips sub-region statistics.",
    )


def _normalize_selected_indices(selected_indices: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if selected_indices is None:
        return _METRIC_ORDER
    if isinstance(selected_indices, (str, bytes)):
        raise ValueError("selected_indices must be a list of metric names.")

    selected = [str(name) for name in selected_indices]
    unknown = [name for name in selected if name not in _METRIC_ORDER]
    if unknown:
        raise ValueError(f"Unknown metric name(s): {', '.join(unknown)}")
    selected_set = set(selected)
    return tuple(name for name in _METRIC_ORDER if name in selected_set)


def _float_or_nan(value: object) -> float:
    try:
        scalar = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return scalar if np.isfinite(scalar) else float("nan")


def _safe_nanmax(array: np.ndarray) -> float:
    return _float_or_nan(np.nanmax(array)) if np.any(np.isfinite(array)) else float("nan")


def _safe_nanmin(array: np.ndarray) -> float:
    return _float_or_nan(np.nanmin(array)) if np.any(np.isfinite(array)) else float("nan")


def _validate_grid_for_area(source: rasterio.io.DatasetReader) -> None:
    if source.crs is None:
        raise ValueError("Raster has no CRS; WGS84 ground-area metrics cannot be calculated.")
    transform = source.transform
    determinant = float(transform.a * transform.e - transform.b * transform.d)
    if not np.isfinite(determinant) or determinant == 0.0:
        raise ValueError("Raster has a non-invertible affine transform.")


def _pixel_area_grid_km2(source: rasterio.io.DatasetReader) -> np.ndarray:
    """Return WGS84 geodesic area (km2) for every source-grid pixel.

    North-up EPSG:4326 grids are common for NTL products. Their pixels share
    one exact geodesic area per latitude row, so that path is both fast and
    stable. Other valid grids use their four transformed pixel corners, which
    keeps the same WGS84 ground-area interpretation instead of assuming that a
    projected affine determinant is a physical area.
    """

    _validate_grid_for_area(source)
    source_crs = CRS.from_user_input(source.crs)
    transform = source.transform
    height, width = int(source.height), int(source.width)
    geod = Geod(ellps="WGS84")

    if source_crs == _WGS84 and transform.b == 0.0 and transform.d == 0.0:
        left = float(transform.c)
        right = float(transform.c + transform.a)
        row_areas = np.empty(height, dtype=np.float64)
        for row_index in range(height):
            top = float(transform.f + row_index * transform.e)
            bottom = float(transform.f + (row_index + 1) * transform.e)
            area_m2, _ = geod.polygon_area_perimeter(
                [left, right, right, left],
                [top, top, bottom, bottom],
            )
            row_areas[row_index] = abs(float(area_m2)) / 1_000_000.0
        if not np.all(np.isfinite(row_areas)) or np.any(row_areas <= 0.0):
            raise ValueError("Could not derive finite positive WGS84 pixel areas.")
        return np.broadcast_to(row_areas[:, None], (height, width))

    transformer = Transformer.from_crs(source_crs, _WGS84, always_xy=True)
    areas = np.empty((height, width), dtype=np.float64)
    for row_index in range(height):
        for column_index in range(width):
            corners = (
                transform * (column_index, row_index),
                transform * (column_index + 1, row_index),
                transform * (column_index + 1, row_index + 1),
                transform * (column_index, row_index + 1),
            )
            x_values, y_values = zip(*corners)
            lon_values, lat_values = transformer.transform(x_values, y_values)
            area_m2, _ = geod.polygon_area_perimeter(lon_values, lat_values)
            areas[row_index, column_index] = abs(float(area_m2)) / 1_000_000.0

    if not np.all(np.isfinite(areas)) or np.any(areas <= 0.0):
        raise ValueError("Could not derive finite positive WGS84 pixel areas.")
    return areas


def calc_TNTL(ntl_array: np.ndarray) -> float:
    if not np.any(np.isfinite(ntl_array)):
        return float("nan")
    return _float_or_nan(np.nansum(ntl_array, dtype=np.float64))


def calc_LArea(ntl_array: np.ndarray, pixel_area_km2: np.ndarray | float) -> float:
    lit_mask = np.isfinite(ntl_array) & (ntl_array > 0.0)
    if not np.any(np.isfinite(ntl_array)):
        return float("nan")
    areas = np.asarray(pixel_area_km2, dtype=np.float64)
    if areas.ndim == 0:
        return _float_or_nan(np.count_nonzero(lit_mask) * float(areas))
    if areas.shape != ntl_array.shape:
        raise ValueError("Pixel-area grid must match the NTL array shape.")
    return _float_or_nan(np.sum(areas[lit_mask], dtype=np.float64))


def calc_3DPLand(ntl_array: np.ndarray) -> float:
    valid_mask = np.isfinite(ntl_array)
    valid_count = int(np.count_nonzero(valid_mask))
    if valid_count == 0:
        return float("nan")
    maximum = float(np.nanmax(ntl_array))
    total_intensity = float(np.nansum(ntl_array, dtype=np.float64))
    if maximum == 0.0:
        return 0.0 if total_intensity == 0.0 else float("nan")
    if maximum < 0.0:
        return float("nan")
    return _float_or_nan(total_intensity / (maximum * valid_count) * 100.0)


def _label_lit_patches(ntl_array: np.ndarray) -> Tuple[np.ndarray, int, np.ndarray]:
    lit_mask = np.isfinite(ntl_array) & (ntl_array > 0.0)
    labels, patch_count = ndimage.label(lit_mask, structure=_FOUR_NEIGHBOUR_STRUCTURE)
    return labels, int(patch_count), lit_mask


def calc_3DED(ntl_array: np.ndarray, pixel_area_km2: np.ndarray | float = 1.0) -> float:
    """3D edge density: total four-neighbour lit-patch area / district TNTL."""

    total_intensity = float(np.nansum(ntl_array, dtype=np.float64))
    labels, patch_count, lit_mask = _label_lit_patches(ntl_array)
    if total_intensity <= 0.0 or patch_count == 0:
        return float("nan")
    areas = np.asarray(pixel_area_km2, dtype=np.float64)
    if areas.ndim == 0:
        areas = np.broadcast_to(areas, ntl_array.shape)
    if areas.shape != ntl_array.shape:
        raise ValueError("Pixel-area grid must match the NTL array shape.")
    patch_areas = np.bincount(
        labels.ravel(),
        weights=np.where(lit_mask, pixel_area_km2, 0.0).ravel(),
        minlength=patch_count + 1,
    )[1:]
    return _float_or_nan(np.sum(patch_areas, dtype=np.float64) / total_intensity)


def calc_3DLPI(ntl_array: np.ndarray) -> float:
    """3D largest patch index: max four-neighbour lit-patch TNTL / district TNTL."""

    total_intensity = float(np.nansum(ntl_array, dtype=np.float64))
    labels, patch_count, lit_mask = _label_lit_patches(ntl_array)
    if total_intensity <= 0.0 or patch_count == 0:
        return float("nan")
    patch_tntl = np.bincount(
        labels.ravel(),
        weights=np.where(lit_mask, ntl_array, 0.0).ravel(),
        minlength=patch_count + 1,
    )[1:]
    return _float_or_nan(np.max(patch_tntl) / total_intensity)


def calc_ANTL(ntl_array: np.ndarray) -> float:
    valid_pixels = int(np.count_nonzero(np.isfinite(ntl_array)))
    return _float_or_nan(np.nansum(ntl_array, dtype=np.float64) / valid_pixels) if valid_pixels else float("nan")


def calc_indices_per_polygon(
    ntl_array: np.ndarray,
    include_mask: np.ndarray,
    pixel_area_km2: np.ndarray | float,
    selected_indices: Optional[Sequence[str]] = None,
) -> Dict[str, float]:
    """Calculate requested metrics for a centre-inclusion raster mask."""

    selected = _normalize_selected_indices(selected_indices)
    areas = np.asarray(pixel_area_km2, dtype=np.float64)
    if include_mask.shape != ntl_array.shape:
        raise ValueError("Raster values and inclusion mask must share one shape.")
    if areas.ndim == 0:
        areas = np.broadcast_to(areas, ntl_array.shape)
    if areas.shape != ntl_array.shape:
        raise ValueError("Raster values, inclusion mask, and pixel-area grid must share one shape.")
    masked_ntl = np.where(include_mask, ntl_array, np.nan)
    index_dict: Dict[str, float] = {}

    if "MaxNTL" in selected:
        index_dict["MaxNTL"] = _safe_nanmax(masked_ntl)
    if "MinNTL" in selected:
        index_dict["MinNTL"] = _safe_nanmin(masked_ntl)
    if "SDNTL" in selected:
        index_dict["SDNTL"] = _float_or_nan(np.nanstd(masked_ntl)) if np.any(np.isfinite(masked_ntl)) else float("nan")
    if "TNTL" in selected:
        index_dict["TNTL"] = calc_TNTL(masked_ntl)
    if "LArea" in selected:
        index_dict["LArea"] = calc_LArea(masked_ntl, areas)
    if "3DPLand" in selected:
        index_dict["3DPLand"] = calc_3DPLand(masked_ntl)
    if "3DED" in selected:
        index_dict["3DED"] = calc_3DED(masked_ntl, areas)
    if "3DLPI" in selected:
        index_dict["3DLPI"] = calc_3DLPI(masked_ntl)
    if "ANTL" in selected:
        index_dict["ANTL"] = calc_ANTL(masked_ntl)
    return index_dict


def _collect_ntl_inputs(ntl_tif_path: Optional[str], ntl_tif_paths: Optional[List[str]]) -> List[str]:
    values: List[str] = []
    if isinstance(ntl_tif_path, str) and ntl_tif_path.strip():
        values.append(ntl_tif_path.strip())
    if isinstance(ntl_tif_paths, list):
        values.extend(path.strip() for path in ntl_tif_paths if isinstance(path, str) and path.strip())

    seen = set()
    deduplicated: List[str] = []
    for path in values:
        if path not in seen:
            deduplicated.append(path)
            seen.add(path)
    return deduplicated


def _extract_year_from_filename(name: str) -> Optional[int]:
    matches = re.findall(r"(19\d{2}|20\d{2})", name or "")
    return int(matches[-1]) if matches else None


def _resolve_thread_id_from_config(config: Optional[RunnableConfig] = None) -> str:
    runtime_config: Optional[RunnableConfig] = config if isinstance(config, dict) else None
    if runtime_config is None:
        inherited = var_child_runnable_config.get()
        runtime_config = inherited if isinstance(inherited, dict) else None

    configurable = runtime_config.get("configurable", {}) if isinstance(runtime_config, dict) else {}
    thread_id = str(configurable.get("thread_id", "") or "").strip()
    if thread_id:
        return thread_id
    return str(current_thread_id.get() or "debug").strip() or "debug"


def _normalized_output_reference(output_csv_path: str) -> str:
    name = os.path.basename(str(output_csv_path or "").strip())
    return f"outputs/{name}" if name else "outputs/result.csv"


def _region_label_column(gdf: gpd.GeoDataFrame) -> str:
    columns_by_casefold = {
        str(column).casefold(): column
        for column in gdf.columns
        if column != gdf.geometry.name
    }
    for preferred in ("name", "shapename", "adm_name", "admin_name", "region"):
        candidate = columns_by_casefold.get(preferred)
        if candidate is not None:
            return candidate
    non_geometry_columns = [column for column in gdf.columns if column != gdf.geometry.name]
    if not non_geometry_columns:
        raise ValueError("Boundary has no non-geometry attribute to identify regions.")
    return non_geometry_columns[0]


def _read_valid_ntl(source: rasterio.io.DatasetReader) -> np.ndarray:
    if source.count < 1:
        raise ValueError("Raster contains no bands.")
    masked = source.read(1, masked=True).astype(np.float64)
    values = np.asarray(masked.filled(np.nan), dtype=np.float64)
    values[~np.isfinite(values)] = np.nan
    return values


def _mask_for_geometry(source: rasterio.io.DatasetReader, geometry) -> np.ndarray:
    return geometry_mask(
        [mapping(geometry)],
        out_shape=(source.height, source.width),
        transform=source.transform,
        invert=True,
        all_touched=False,
    )


def _compute_for_single_raster(
    abs_ntl_path: str,
    ntl_label: str,
    abs_shp_path: str,
    selected_indices: Optional[Sequence[str]],
    only_global: bool,
) -> Tuple[List[dict], Dict[str, float]]:
    with rasterio.open(abs_ntl_path) as source:
        values = _read_valid_ntl(source)
        selected = _normalize_selected_indices(selected_indices)
        area_grid_km2: np.ndarray | float = (
            _pixel_area_grid_km2(source)
            if {"LArea", "3DED"}.intersection(selected)
            else 1.0
        )

        gdf = gpd.read_file(abs_shp_path)
        if gdf.empty:
            raise ValueError("Boundary file contains no features.")
        if gdf.crs is None:
            raise ValueError("Boundary file has no CRS.")
        if source.crs is None:
            raise ValueError("Raster has no CRS.")
        if gdf.crs != source.crs:
            gdf = gdf.to_crs(source.crs)
        if gdf.geometry.isna().any() or gdf.geometry.is_empty.any() or not bool(gdf.geometry.is_valid.all()):
            raise ValueError("Boundary file contains missing, empty, or invalid geometry.")

        global_geometry = unary_union(gdf.geometry)
        global_mask = _mask_for_geometry(source, global_geometry)
        global_indices = calc_indices_per_polygon(
            values,
            global_mask,
            area_grid_km2,
            selected_indices=selected_indices,
        )

        results: List[dict] = []
        name_col = _region_label_column(gdf)
        year_val = _extract_year_from_filename(ntl_label)
        if not only_global:
            for _, row in gdf.iterrows():
                feature_mask = _mask_for_geometry(source, row.geometry)
                local_indices = calc_indices_per_polygon(
                    values,
                    feature_mask,
                    area_grid_km2,
                    selected_indices=selected_indices,
                )
                results.append(
                    {
                        "Raster_file": ntl_label,
                        "Year": year_val,
                        "Region": str(row[name_col]),
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


def _render_success(
    *,
    output_ref: str,
    feature_rows: int,
    global_metrics: Sequence[Tuple[str, Dict[str, float]]],
) -> str:
    summaries: List[str] = []
    for raster_label, metrics in global_metrics:
        formatted = [
            f"- {name}: {value:.8g}" if np.isfinite(value) else f"- {name}: None"
            for name, value in metrics.items()
        ]
        summaries.append(f"[{raster_label}]\n" + "\n".join(formatted))
    global_summary = "\n\n".join(summaries) or "(no selected metrics)"
    return (
        f"Success: Analysis completed for {feature_rows} region rows.\n"
        f"Results saved to: {output_ref}\n\n"
        f"**Global Summary (Total ROI):**\n{global_summary}\n"
        "Area metrics use WGS84 geodesic source-pixel area; masks use pixel-centre inclusion."
    )


def NTL_raster_statistics(
    shapefile_path,
    output_csv_path,
    ntl_tif_path=None,
    ntl_tif_paths=None,
    selected_indices=None,
    only_global=False,
    config: Optional[RunnableConfig] = None,
):
    """Calculate per-feature and union NTL metrics for local or shared inputs."""

    try:
        if not isinstance(only_global, bool):
            raise ValueError("only_global must be a boolean value.")
        selected = _normalize_selected_indices(selected_indices)
        ntl_inputs = _collect_ntl_inputs(ntl_tif_path=ntl_tif_path, ntl_tif_paths=ntl_tif_paths)
        if not ntl_inputs:
            raise ValueError("Provide 'ntl_tif_path' or 'ntl_tif_paths' with at least one raster filename.")

        thread_id = _resolve_thread_id_from_config(config)
        abs_shp_path = storage_manager.resolve_input_path(shapefile_path, thread_id=thread_id)
        abs_out_path = storage_manager.resolve_output_path(output_csv_path, thread_id=thread_id)
        abs_ntl_paths = [
            storage_manager.resolve_input_path(tif_name, thread_id=thread_id)
            for tif_name in ntl_inputs
        ]
        missing_paths = [path for path in [abs_shp_path, *abs_ntl_paths] if not os.path.isfile(path)]
        if missing_paths:
            raise FileNotFoundError(", ".join(missing_paths))

        all_rows: List[dict] = []
        summaries: List[Tuple[str, Dict[str, float]]] = []
        for abs_ntl_path, ntl_label in zip(abs_ntl_paths, ntl_inputs):
            rows, global_indices = _compute_for_single_raster(
                abs_ntl_path=abs_ntl_path,
                ntl_label=os.path.basename(ntl_label),
                abs_shp_path=abs_shp_path,
                selected_indices=selected,
                only_global=only_global,
            )
            all_rows.extend(rows)
            summaries.append((os.path.basename(ntl_label), global_indices))

        pd.DataFrame(all_rows).to_csv(abs_out_path, index=False, encoding="utf-8")
        feature_rows = int(sum(row["Region"] != "Global_Summary" for row in all_rows))
        return _render_success(
            output_ref=_normalized_output_reference(output_csv_path),
            feature_rows=feature_rows,
            global_metrics=summaries,
        )
    except Exception as exc:
        return f"Error: {exc}"


NTL_raster_statistics_tool = StructuredTool.from_function(
    func=NTL_raster_statistics,
    name="NTL_raster_statistics",
    description=(
        "Calculates NTL landscape metrics for one or multiple rasters over a boundary. "
        "Uses pixel-centre containment, excludes declared NoData/non-finite values while retaining valid zeroes, "
        "and reports WGS84-geodesic area metrics. Use `LArea` for lit area (km2), `3DPLand` for percent, "
        "`3DED` for four-neighbour lit-patch area per summed NTL, and `3DLPI` for the largest-patch fraction. "
        "Outputs a CSV in outputs/."
    ),
    args_schema=NTL_raster_statistics_input,
)
