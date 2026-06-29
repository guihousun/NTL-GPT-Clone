from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.errors import RasterioError
from rasterio.mask import raster_geometry_mask
from scipy import ndimage
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ntl_toolkit.runtime import (
    require_input_path,
    reserve_output_path,
    resolve_local_path,
    runtime_workdir,
)
from ntl_toolkit.schemas import OutputArtifact, ToolError, ToolResult

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
_RASTER_TOOL = "calculate_ntl_metrics_for_raster"
_ZONAL_TOOL = "calculate_zonal_statistics"


class _KnownNTLFailure(Exception):
    def __init__(self, error: ToolError) -> None:
        super().__init__(error.message)
        self.error = error


def _fail(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    suggestion: str | None = None,
) -> None:
    raise _KnownNTLFailure(
        ToolError(
            code=code,
            message=message,
            details=details or {},
            suggestion=suggestion,
        )
    )


def _tool_failure(tool: str, error: ToolError) -> ToolResult:
    return ToolResult.failed(tool=tool, error=error)


def _resolve_input_path(path: str | Path) -> Path:
    return require_input_path(path, runtime_workdir())


def _resolve_output_path(path: str | Path) -> Path:
    requested = resolve_local_path(path, runtime_workdir())
    return reserve_output_path(requested)


def _resolve_tool_input_path(path: str | Path, *, parameter: str) -> Path:
    try:
        return _resolve_input_path(path)
    except ValueError as exc:
        _fail(
            "INVALID_PARAMETER",
            f"Invalid path for '{parameter}'.",
            details={"parameter": parameter, "path": str(path), "reason": str(exc)},
            suggestion="Use an ordinary relative path or a fully qualified absolute Windows path.",
        )


def _resolve_tool_output_path(path: str | Path, *, parameter: str) -> Path:
    try:
        return _resolve_output_path(path)
    except ValueError as exc:
        _fail(
            "INVALID_PARAMETER",
            f"Invalid path for '{parameter}'.",
            details={"parameter": parameter, "path": str(path), "reason": str(exc)},
            suggestion="Use an ordinary relative path or a fully qualified absolute Windows path.",
        )


def _normalize_selected(selected: Sequence[str] | None) -> list[str]:
    if selected is None:
        return list(_METRIC_ORDER)
    if isinstance(selected, (str, bytes)):
        raise ValueError("selected must be a sequence of metric names.")

    selected_list = [str(name) for name in selected]
    if not selected_list:
        return []

    unknown = [name for name in selected_list if name not in _METRIC_ORDER]
    if unknown:
        raise ValueError(f"Unknown metric name(s): {', '.join(unknown)}")

    selected_set = set(selected_list)
    return [name for name in _METRIC_ORDER if name in selected_set]


def _normalize_pixel_area(pixel_area: Any) -> float:
    try:
        value = float(pixel_area)
    except (TypeError, ValueError) as exc:
        raise ValueError("pixel_area must be a finite number greater than zero.") from exc

    if not np.isfinite(value) or value <= 0:
        raise ValueError("pixel_area must be a finite number greater than zero.")
    return value


def _normalize_band(band: Any) -> int:
    if isinstance(band, bool):
        raise ValueError("band must be an integer between 1 and the raster band count.")

    try:
        value = int(band)
    except (TypeError, ValueError) as exc:
        raise ValueError("band must be an integer between 1 and the raster band count.") from exc

    if value < 1:
        raise ValueError("band must be an integer between 1 and the raster band count.")
    return value


def _normalize_only_global(only_global: Any) -> bool:
    if not isinstance(only_global, bool):
        raise ValueError("only_global must be a boolean value.")
    return only_global


def _sanitize_array(values: Any) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    array[~np.isfinite(array)] = np.nan
    return array


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    scalar = float(value)
    if not np.isfinite(scalar):
        return None
    return scalar


def _pixel_area_for(dataset: rasterio.io.DatasetReader) -> float:
    transform = dataset.transform
    return abs(float(transform.a * transform.e - transform.b * transform.d))


def _read_raster_band(
    path: Path,
    *,
    band: int,
) -> tuple[np.ndarray, rasterio.io.DatasetReader, list[str]]:
    try:
        dataset = rasterio.open(path)
    except RasterioError as exc:
        _fail(
            "RASTER_READ_FAILED",
            f"Unable to read raster '{path}'.",
            details={"path": str(path), "reason": str(exc)},
        )

    warnings: list[str] = []
    try:
        if dataset.crs is None:
            _fail(
                "CRS_MISSING",
                f"Raster dataset '{path}' does not define a CRS.",
                details={"path": str(path)},
            )
        if band > dataset.count:
            _fail(
                "INVALID_PARAMETER",
                f"band must be between 1 and {dataset.count}.",
                details={"parameter": "band", "value": band, "band_count": dataset.count},
            )

        masked = dataset.read(band, masked=True)
        array = np.asarray(masked.filled(np.nan), dtype=float)
        array[~np.isfinite(array)] = np.nan
        if dataset.crs.is_geographic:
            warnings.append("GEOGRAPHIC_PIXEL_AREA")
        return array, dataset, warnings
    except Exception:
        dataset.close()
        raise


def _validate_geometry(gdf: gpd.GeoDataFrame, path: Path) -> None:
    if gdf.crs is None:
        _fail(
            "CRS_MISSING",
            f"Vector dataset '{path}' does not define a CRS.",
            details={"path": str(path)},
        )
    if gdf.empty:
        _fail(
            "EMPTY_DATASET",
            f"Vector dataset '{path}' contains no features.",
            details={"path": str(path)},
        )

    for index, geometry in enumerate(gdf.geometry):
        problem = _geometry_problem(geometry)
        if problem is not None:
            _fail(
                "INVALID_GEOMETRY",
                f"Vector dataset '{path}' contains {problem} geometry.",
                details={"path": str(path), "feature_index": index, "reason": problem},
            )


def _geometry_problem(geometry: BaseGeometry | None) -> str | None:
    if geometry is None:
        return "missing"
    if geometry.is_empty:
        return "empty"
    if not geometry.is_valid:
        return "invalid"
    return None


def _read_vector(path: Path) -> gpd.GeoDataFrame:
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:  # pragma: no cover - driver-specific failures
        _fail(
            "VECTOR_READ_FAILED",
            f"Unable to read vector dataset '{path}'.",
            details={"path": str(path), "reason": str(exc)},
        )

    _validate_geometry(gdf, path)
    return gdf


def _region_label_series(gdf: gpd.GeoDataFrame) -> pd.Series:
    if "name" in gdf.columns:
        return gdf["name"].astype(str)

    non_geometry_columns = [column for column in gdf.columns if column != gdf.geometry.name]
    if non_geometry_columns:
        return gdf[non_geometry_columns[0]].astype(str)

    return pd.Series(
        [f"feature_{index}" for index in range(len(gdf))],
        index=gdf.index,
        dtype="object",
    )


def _extract_year_from_name(name: str) -> int | None:
    matches = re.findall(r"(19\d{2}|20\d{2})", name or "")
    return int(matches[-1]) if matches else None


def _masked_values_for_geometry(
    dataset: rasterio.io.DatasetReader,
    values: np.ndarray,
    geometry: BaseGeometry,
) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="shapes are outside bounds of raster.*",
            category=UserWarning,
        )
        geometry_mask, _, _ = raster_geometry_mask(
            dataset,
            [geometry],
            invert=False,
        )
    return np.where(~geometry_mask, values, np.nan)


def calculate_ntl_metrics(
    values: Any,
    *,
    pixel_area: float,
    selected: Sequence[str] | None = None,
) -> dict[str, float | None]:
    ordered_metrics = _normalize_selected(selected)
    normalized_pixel_area = _normalize_pixel_area(pixel_area)
    if not ordered_metrics:
        return {}

    array = _sanitize_array(values)
    valid_mask = ~np.isnan(array)
    valid_count = int(np.sum(valid_mask))
    lit_mask = array > 0
    total_intensity = float(np.nansum(array))

    result: dict[str, float | None] = {}
    for metric in ordered_metrics:
        value: float | None
        if metric == "MaxNTL":
            value = None if valid_count == 0 else _float_or_none(np.nanmax(array))
        elif metric == "MinNTL":
            value = None if valid_count == 0 else _float_or_none(np.nanmin(array))
        elif metric == "SDNTL":
            value = None if valid_count == 0 else _float_or_none(np.nanstd(array))
        elif metric == "TNTL":
            value = _float_or_none(total_intensity)
        elif metric == "LArea":
            value = _float_or_none(np.sum(lit_mask) * normalized_pixel_area)
        elif metric == "3DPLand":
            if valid_count == 0:
                value = None
            else:
                max_ntl = float(np.nanmax(array))
                value = None if max_ntl == 0 else _float_or_none(total_intensity / (max_ntl * valid_count))
        elif metric == "3DED":
            labeled, num_features = ndimage.label(lit_mask)
            if total_intensity == 0 or num_features == 0:
                value = None
            else:
                perimeter = 0
                for region_label in range(1, num_features + 1):
                    region = labeled == region_label
                    edges = ndimage.binary_dilation(region) ^ region
                    perimeter += int(np.sum(edges))
                value = _float_or_none(perimeter / total_intensity)
        elif metric == "3DLPI":
            labeled, num_features = ndimage.label(lit_mask)
            if total_intensity == 0 or num_features == 0:
                value = None
            else:
                region_intensities = [
                    float(np.nansum(array[labeled == region_label]))
                    for region_label in range(1, num_features + 1)
                ]
                value = None if not region_intensities else _float_or_none(max(region_intensities) / total_intensity)
        else:  # ANTL
            value = None if valid_count == 0 else _float_or_none(total_intensity / valid_count)

        result[metric] = value

    return result


def calculate_ntl_metrics_for_raster(
    raster_path: str | Path,
    *,
    band: int = 1,
    selected: Sequence[str] | None = None,
) -> ToolResult:
    try:
        normalized_band = _normalize_band(band)
        ordered_metrics = _normalize_selected(selected)
        input_path = _resolve_tool_input_path(raster_path, parameter="raster_path")
    except FileNotFoundError as exc:
        return _tool_failure(
            _RASTER_TOOL,
            ToolError(
                code="INPUT_NOT_FOUND",
                message=f"Input raster was not found: {exc}.",
                details={"path": str(exc)},
            ),
        )
    except ValueError as exc:
        return _tool_failure(
            _RASTER_TOOL,
            ToolError(
                code="INVALID_PARAMETER",
                message=str(exc),
                details={"parameter": "band" if "band" in str(exc) else "selected"},
            ),
        )
    except _KnownNTLFailure as exc:
        return _tool_failure(_RASTER_TOOL, exc.error)

    try:
        values, dataset, warnings = _read_raster_band(input_path, band=normalized_band)
        with dataset:
            pixel_area = _pixel_area_for(dataset)
            metrics = calculate_ntl_metrics(values, pixel_area=pixel_area, selected=ordered_metrics)
            metrics.update(
                {
                    "band": normalized_band,
                    "pixel_area": pixel_area,
                    "crs": str(dataset.crs),
                    "width": int(dataset.width),
                    "height": int(dataset.height),
                }
            )
    except ValueError as exc:
        return _tool_failure(
            _RASTER_TOOL,
            ToolError(
                code="INVALID_PARAMETER",
                message=str(exc),
                details={"parameter": "selected"},
            ),
        )
    except _KnownNTLFailure as exc:
        return _tool_failure(_RASTER_TOOL, exc.error)

    return ToolResult.succeeded(
        tool=_RASTER_TOOL,
        summary=f"Calculated NTL metrics for '{input_path.name}'.",
        metrics=metrics,
        warnings=warnings,
    )


def calculate_zonal_statistics(
    *,
    raster_paths: Sequence[str | Path],
    vector_path: str | Path,
    output_path: str | Path,
    selected_indices: Sequence[str] | None = None,
    only_global: bool = False,
) -> ToolResult:
    try:
        if isinstance(raster_paths, (str, bytes)) or not raster_paths:
            raise ValueError("raster_paths must be a non-empty sequence.")

        raster_path_list = list(raster_paths)
        ordered_metrics = _normalize_selected(selected_indices)
        only_global_value = _normalize_only_global(only_global)
        resolved_vector_path = _resolve_tool_input_path(vector_path, parameter="vector_path")
        reserved_output = _resolve_tool_output_path(output_path, parameter="output_path")
    except FileNotFoundError as exc:
        return _tool_failure(
            _ZONAL_TOOL,
            ToolError(
                code="INPUT_NOT_FOUND",
                message=f"Input dataset was not found: {exc}.",
                details={"path": str(exc)},
            ),
        )
    except ValueError as exc:
        return _tool_failure(
            _ZONAL_TOOL,
            ToolError(
                code="INVALID_PARAMETER",
                message=str(exc),
            ),
        )
    except _KnownNTLFailure as exc:
        return _tool_failure(_ZONAL_TOOL, exc.error)

    try:
        source_vector = _read_vector(resolved_vector_path)
        region_labels = _region_label_series(source_vector)
    except _KnownNTLFailure as exc:
        return _tool_failure(_ZONAL_TOOL, exc.error)

    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    raster_count = len(raster_path_list)
    polygon_count = int(len(source_vector))

    try:
        resolved_raster_paths = [
            _resolve_tool_input_path(path, parameter="raster_paths")
            for path in raster_path_list
        ]
    except FileNotFoundError as exc:
        return _tool_failure(
            _ZONAL_TOOL,
            ToolError(
                code="INPUT_NOT_FOUND",
                message=f"Input raster was not found: {exc}.",
                details={"path": str(exc)},
            ),
        )
    except _KnownNTLFailure as exc:
        return _tool_failure(_ZONAL_TOOL, exc.error)

    for resolved_raster_path in resolved_raster_paths:
        try:
            values, dataset, raster_warnings = _read_raster_band(resolved_raster_path, band=1)
            with dataset:
                pixel_area = _pixel_area_for(dataset)
                if raster_warnings and "GEOGRAPHIC_PIXEL_AREA" not in warnings:
                    warnings.extend(raster_warnings)

                try:
                    vector_for_raster = (
                        source_vector.copy()
                        if source_vector.crs == dataset.crs
                        else source_vector.to_crs(dataset.crs)
                    )
                except Exception as exc:
                    _fail(
                        "VECTOR_READ_FAILED",
                        f"Unable to reproject vector dataset '{resolved_vector_path}'.",
                        details={"path": str(resolved_vector_path), "reason": str(exc)},
                    )

                _validate_geometry(vector_for_raster, resolved_vector_path)
                global_geometry = unary_union(vector_for_raster.geometry)
                raster_label = resolved_raster_path.name
                year = _extract_year_from_name(raster_label)

                if not only_global_value:
                    for feature_index, geometry in enumerate(vector_for_raster.geometry):
                        metrics = calculate_ntl_metrics(
                            _masked_values_for_geometry(dataset, values, geometry),
                            pixel_area=pixel_area,
                            selected=ordered_metrics,
                        )
                        rows.append(
                            {
                                "Raster_file": raster_label,
                                "Year": year,
                                "Region": region_labels.iloc[feature_index],
                                **metrics,
                            }
                        )

                global_metrics = calculate_ntl_metrics(
                    _masked_values_for_geometry(dataset, values, global_geometry),
                    pixel_area=pixel_area,
                    selected=ordered_metrics,
                )
                rows.append(
                    {
                        "Raster_file": raster_label,
                        "Year": year,
                        "Region": "Global_Summary",
                        **global_metrics,
                    }
                )
        except ValueError as exc:
            return _tool_failure(
                _ZONAL_TOOL,
                ToolError(
                    code="INVALID_PARAMETER",
                    message=str(exc),
                    details={"parameter": "selected_indices"},
                ),
            )
        except _KnownNTLFailure as exc:
            return _tool_failure(_ZONAL_TOOL, exc.error)

    frame = pd.DataFrame(rows)
    try:
        frame.to_csv(reserved_output, index=False, encoding="utf-8")
    except Exception as exc:
        if reserved_output.exists():
            reserved_output.unlink()
        return _tool_failure(
            _ZONAL_TOOL,
            ToolError(
                code="OUTPUT_WRITE_FAILED",
                message=f"Unable to write zonal statistics CSV '{reserved_output}'.",
                details={"path": str(reserved_output), "reason": str(exc)},
            ),
        )

    return ToolResult.succeeded(
        tool=_ZONAL_TOOL,
        summary=f"Calculated zonal statistics for {raster_count} raster(s).",
        outputs=[OutputArtifact(path=str(reserved_output), media_type="text/csv")],
        metrics={
            "polygon_count": polygon_count,
            "raster_count": raster_count,
            "row_count": int(len(rows)),
            "only_global": only_global_value,
        },
        warnings=warnings,
    )
