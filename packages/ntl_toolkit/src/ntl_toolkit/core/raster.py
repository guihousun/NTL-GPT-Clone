from __future__ import annotations

from numbers import Integral
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.errors import RasterioError
from rasterio.warp import transform_bounds

from ntl_toolkit.runtime import require_input_path, runtime_workdir
from ntl_toolkit.schemas import ToolError, ToolResult

_RASTER_TOOL_NAME = {
    "inspect": "inspect_raster",
    "validate": "validate_geodata",
}
_VALID_MODES = {"basic", "full"}
_GRID_TOLERANCE = 1e-15


class _KnownRasterFailure(Exception):
    def __init__(self, error: ToolError) -> None:
        super().__init__(error.message)
        self.error = error


def _fail(code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
    raise _KnownRasterFailure(
        ToolError(
            code=code,
            message=message,
            details=details or {},
        )
    )


def _tool_failure(tool: str, error: ToolError) -> ToolResult:
    return ToolResult.failed(tool=tool, error=error)


def _resolve_input_path(path: str | Path) -> Path:
    return require_input_path(path, runtime_workdir())


def _normalize_mode(mode: str) -> str:
    if mode not in _VALID_MODES:
        _fail(
            "INVALID_PARAMETER",
            "mode must be either 'basic' or 'full'.",
            details={"parameter": "mode", "value": mode},
        )
    return mode


def _normalize_sample_pixels(sample_pixels: Any) -> int:
    if isinstance(sample_pixels, bool) or not isinstance(sample_pixels, Integral):
        _fail(
            "INVALID_PARAMETER",
            "sample_pixels must be an integer greater than or equal to zero.",
            details={"parameter": "sample_pixels", "value": sample_pixels},
        )

    value = int(sample_pixels)
    if value < 0:
        _fail(
            "INVALID_PARAMETER",
            "sample_pixels must be an integer greater than or equal to zero.",
            details={"parameter": "sample_pixels", "value": sample_pixels},
        )
    return value


def _transform_to_list(transform: Any) -> list[float]:
    return [float(value) for value in tuple(transform)]


def _bounds_to_list(bounds: Any) -> list[float]:
    return [float(bounds.left), float(bounds.bottom), float(bounds.right), float(bounds.top)]


def _resolution(transform: Any) -> list[float]:
    return [abs(float(transform.a)), abs(float(transform.e))]


def _grid_signature(
    *,
    crs: str | None,
    width: int,
    height: int,
    resolution: list[float],
    transform: list[float],
) -> str:
    parts = [crs or "None", str(width), str(height), str(resolution[0]), str(resolution[1])]
    parts.extend(str(value) for value in transform)
    return "|".join(parts)


def _empty_stats() -> dict[str, Any]:
    return {
        "valid_count": 0,
        "min": None,
        "max": None,
        "mean": None,
        "std": None,
    }


def _finite_bounds(bounds: Iterable[Any] | None) -> list[float] | None:
    if bounds is None:
        return None

    values = [float(value) for value in bounds]
    if len(values) != 4 or not np.all(np.isfinite(values)):
        return None
    return values


def _sample_band(band: np.ndarray, sample_pixels: int) -> np.ndarray:
    if sample_pixels <= 0 or band.size <= sample_pixels:
        return band

    step = max(1, int(np.sqrt(band.size / sample_pixels)))
    return band[::step, ::step]


def _band_statistics(band: np.ndarray, nodata: float | None) -> dict[str, Any]:
    if nodata is None:
        valid_mask = np.isfinite(band)
    else:
        valid_mask = np.isfinite(band) & (band != nodata)

    valid = band[valid_mask]
    if valid.size == 0:
        return _empty_stats()

    return {
        "valid_count": int(valid.size),
        "min": float(np.nanmin(valid)),
        "max": float(np.nanmax(valid)),
        "mean": float(np.nanmean(valid)),
        "std": float(np.nanstd(valid)),
    }


def _stat_hints(stats: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    minimum = stats.get("min")
    maximum = stats.get("max")
    if minimum is not None and minimum < -1e-6:
        hints.append("Contains negative values; verify nodata and sensor units.")
    if maximum is not None and maximum > 1e6:
        hints.append("Very large max; check radiance units or scale.")
    return hints


def _inspect_raster_metrics(path: Path, *, mode: str, sample_pixels: int) -> dict[str, Any]:
    with rasterio.open(path) as dataset:
        transform = _transform_to_list(dataset.transform)
        resolution = _resolution(dataset.transform)
        metrics: dict[str, Any] = {
            "path": str(path.resolve(strict=False)),
            "driver": dataset.driver,
            "crs": str(dataset.crs) if dataset.crs else None,
            "width": int(dataset.width),
            "height": int(dataset.height),
            "band_count": int(dataset.count),
            "dtype": dataset.dtypes[0] if dataset.count > 0 and dataset.dtypes else None,
            "resolution": resolution,
            "nodata": None if dataset.nodata is None else float(dataset.nodata),
            "bounds": _bounds_to_list(dataset.bounds),
            "transform": transform,
            "grid_signature": _grid_signature(
                crs=str(dataset.crs) if dataset.crs else None,
                width=int(dataset.width),
                height=int(dataset.height),
                resolution=resolution,
                transform=transform,
            ),
            "readable": True,
        }

        if mode == "basic":
            return metrics

        if dataset.count < 1:
            metrics.update(_empty_stats())
            metrics["sample_pixels"] = int(sample_pixels)
            metrics["hints"] = []
            return metrics

        sampled = _sample_band(dataset.read(1), sample_pixels)
        stats = _band_statistics(sampled, dataset.nodata)
        metrics.update(stats)
        metrics["sample_pixels"] = int(sample_pixels)
        metrics["hints"] = _stat_hints(stats)
        return metrics


def _normalize_paths(paths: Iterable[str | Path] | str | Path | None) -> list[str | Path]:
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        return [paths]
    return list(paths)


def _raster_validation_report(path: str | Path) -> dict[str, Any]:
    requested_path = str(path)
    try:
        resolved = _resolve_input_path(path)
    except FileNotFoundError as exc:
        return {
            "requested_path": requested_path,
            "path": str(exc),
            "exists": False,
            "readable": False,
            "warning_codes": ["UNREADABLE"],
            "error_code": "INPUT_NOT_FOUND",
        }

    try:
        metrics = _inspect_raster_metrics(resolved, mode="basic", sample_pixels=0)
    except (RasterioError, ValueError, OSError) as exc:
        return {
            "requested_path": requested_path,
            "path": str(resolved.resolve(strict=False)),
            "exists": True,
            "readable": False,
            "warning_codes": ["UNREADABLE"],
            "error_code": "RASTER_READ_FAILED",
            "error_message": str(exc),
        }

    warning_codes: list[str] = []
    empty_dataset = bool(
        metrics["band_count"] < 1 or metrics["width"] == 0 or metrics["height"] == 0
    )
    if empty_dataset:
        warning_codes.append("EMPTY_DATASET")

    metrics.update(
        {
            "requested_path": requested_path,
            "exists": True,
            "empty_dataset": empty_dataset,
            "warning_codes": warning_codes,
        }
    )
    return metrics


def _geometry_problem(geometry: Any) -> str | None:
    if geometry is None:
        return "missing"
    if geometry.is_empty:
        return "empty"
    if not geometry.is_valid:
        return "invalid"
    return None


def _vector_validation_report(path: str | Path) -> tuple[dict[str, Any], gpd.GeoDataFrame | None]:
    requested_path = str(path)
    try:
        resolved = _resolve_input_path(path)
    except FileNotFoundError as exc:
        return (
            {
                "requested_path": requested_path,
                "path": str(exc),
                "exists": False,
                "readable": False,
                "warning_codes": ["UNREADABLE"],
                "error_code": "INPUT_NOT_FOUND",
            },
            None,
        )

    try:
        gdf = gpd.read_file(resolved)
    except Exception as exc:  # noqa: BLE001
        return (
            {
                "requested_path": requested_path,
                "path": str(resolved.resolve(strict=False)),
                "exists": True,
                "readable": False,
                "warning_codes": ["UNREADABLE"],
                "error_code": "VECTOR_READ_FAILED",
                "error_message": str(exc),
            },
            None,
        )

    warning_codes: list[str] = []
    empty_dataset = gdf.empty
    invalid_geometry = False
    if empty_dataset:
        warning_codes.append("EMPTY_DATASET")
    else:
        invalid_geometry = any(
            _geometry_problem(geometry) is not None for geometry in gdf.geometry
        )
        if invalid_geometry:
            warning_codes.append("INVALID_GEOMETRY")

    raw_bounds = None if empty_dataset else _finite_bounds(gdf.total_bounds)
    if raw_bounds is None and not empty_dataset and "INVALID_GEOMETRY" not in warning_codes:
        warning_codes.append("INVALID_GEOMETRY")
        invalid_geometry = True

    report = {
        "requested_path": requested_path,
        "path": str(resolved.resolve(strict=False)),
        "exists": True,
        "readable": True,
        "crs": str(gdf.crs) if gdf.crs else None,
        "feature_count": int(len(gdf)),
        "geometry_types": sorted(str(value) for value in gdf.geometry.geom_type.dropna().unique()),
        "bounds": raw_bounds,
        "empty_dataset": empty_dataset,
        "invalid_geometry": invalid_geometry,
        "warning_codes": warning_codes,
    }
    return report, gdf


def _warning_union(*code_groups: list[str]) -> list[str]:
    ordered: list[str] = []
    for group in code_groups:
        for code in group:
            if code not in ordered:
                ordered.append(code)
    return ordered


def _crs_object(raw_crs: Any) -> CRS | None:
    if raw_crs in {None, ""}:
        return None
    try:
        return CRS.from_user_input(raw_crs)
    except Exception:  # noqa: BLE001
        return None


def _crs_equal(left: Any, right: Any) -> bool:
    left_crs = _crs_object(left)
    right_crs = _crs_object(right)
    if left_crs is None or right_crs is None:
        return False
    return left_crs == right_crs


def _transform_object(raw_transform: Any) -> Affine | None:
    if raw_transform is None:
        return None
    try:
        values = tuple(float(value) for value in raw_transform)
    except (TypeError, ValueError):
        return None
    if len(values) != 9 or not np.all(np.isfinite(values)):
        return None
    return Affine(*values[:6])


def _float_lists_close(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    try:
        left_values = np.asarray(left, dtype=float)
        right_values = np.asarray(right, dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(
        left_values.shape == right_values.shape
        and np.all(np.isfinite(left_values))
        and np.all(np.isfinite(right_values))
        and np.allclose(
            left_values,
            right_values,
            rtol=_GRID_TOLERANCE,
            atol=_GRID_TOLERANCE,
        )
    )


def _grid_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_transform = _transform_object(left.get("transform"))
    right_transform = _transform_object(right.get("transform"))
    return (
        _crs_equal(left.get("crs"), right.get("crs"))
        and left.get("width") == right.get("width")
        and left.get("height") == right.get("height")
        and _float_lists_close(left.get("resolution"), right.get("resolution"))
        and left_transform is not None
        and right_transform is not None
        and left_transform.almost_equals(right_transform, precision=_GRID_TOLERANCE)
    )


def _bbox_intersects(raster_bounds: list[float], vector_bounds: list[float]) -> bool:
    left, bottom, right, top = raster_bounds
    minx, miny, maxx, maxy = vector_bounds
    return not (
        right <= minx
        or left >= maxx
        or top <= miny
        or bottom >= maxy
    )


def _transform_bounds_safe(
    source_crs: Any,
    target_crs: Any,
    bounds: Iterable[Any] | None,
) -> list[float] | None:
    normalized_bounds = _finite_bounds(bounds)
    source = _crs_object(source_crs)
    target = _crs_object(target_crs)
    if normalized_bounds is None or source is None or target is None:
        return None
    try:
        transformed = transform_bounds(
            source,
            target,
            *normalized_bounds,
            densify_pts=21,
        )
    except Exception:  # noqa: BLE001
        return None
    return _finite_bounds(transformed)


def inspect_raster(
    path: str | Path,
    *,
    mode: str = "full",
    sample_pixels: int = 0,
) -> ToolResult:
    """Return metadata and optional band statistics for a raster dataset."""
    tool = _RASTER_TOOL_NAME["inspect"]
    try:
        normalized_mode = _normalize_mode(mode)
        normalized_sample_pixels = _normalize_sample_pixels(sample_pixels)
        input_path = _resolve_input_path(path)
        metrics = _inspect_raster_metrics(
            input_path,
            mode=normalized_mode,
            sample_pixels=normalized_sample_pixels,
        )
    except FileNotFoundError as exc:
        return _tool_failure(
            tool,
            ToolError(
                code="INPUT_NOT_FOUND",
                message=f"Input raster was not found: {exc}.",
                details={"path": str(exc)},
            ),
        )
    except _KnownRasterFailure as exc:
        return _tool_failure(tool, exc.error)
    except (RasterioError, ValueError, OSError) as exc:
        resolved_path = Path(path).expanduser().resolve(strict=False)
        return _tool_failure(
            tool,
            ToolError(
                code="RASTER_READ_FAILED",
                message=f"Failed to read raster '{resolved_path}'.",
                details={"path": str(resolved_path), "reason": str(exc)},
            ),
        )

    summary = f"Inspected raster {metrics['width']}x{metrics['height']}."
    return ToolResult.succeeded(
        tool=tool,
        summary=summary,
        metrics=metrics,
    )


def validate_geodata(
    *,
    raster_paths: Iterable[str | Path] | str | Path | None = None,
    vector_paths: Iterable[str | Path] | str | Path | None = None,
) -> ToolResult:
    """Validate raster and vector inputs without mutating caller-provided sequences."""
    tool = _RASTER_TOOL_NAME["validate"]
    raster_items = _normalize_paths(raster_paths)
    vector_items = _normalize_paths(vector_paths)

    raster_reports = [_raster_validation_report(path) for path in raster_items]
    vector_results = [_vector_validation_report(path) for path in vector_items]
    vector_reports = [report for report, _ in vector_results]

    warnings = _warning_union(
        *[report["warning_codes"] for report in raster_reports],
        *[report["warning_codes"] for report in vector_reports],
    )

    readable_rasters = [report for report in raster_reports if report.get("readable")]
    raster_pair_reports: list[dict[str, Any]] = []
    for index, left in enumerate(readable_rasters):
        for right in readable_rasters[index + 1 :]:
            warning_codes: list[str] = []
            grid_compatible = _grid_compatible(left, right)
            if not grid_compatible:
                warning_codes.append("GRID_MISMATCH")
            raster_pair_reports.append(
                {
                    "left_path": left["path"],
                    "right_path": right["path"],
                    "grid_compatible": grid_compatible,
                    "warning_codes": warning_codes,
                }
            )
            warnings = _warning_union(warnings, warning_codes)

    raster_vector_reports: list[dict[str, Any]] = []
    readable_vector_results = [
        (report, gdf)
        for report, gdf in vector_results
        if report.get("readable") and gdf is not None
    ]
    for raster_report in readable_rasters:
        raster_crs = raster_report.get("crs")
        raster_bounds = raster_report.get("bounds")
        for vector_report, vector_gdf in readable_vector_results:
            warning_codes: list[str] = []
            warning_codes = _warning_union(
                warning_codes,
                [code for code in vector_report["warning_codes"] if code in {"INVALID_GEOMETRY", "EMPTY_DATASET"}],
            )
            crs_match = _crs_equal(raster_crs, vector_report.get("crs"))
            comparison_bounds = _finite_bounds(vector_report.get("bounds"))
            if not crs_match:
                warning_codes.append("CRS_MISMATCH")
                comparison_bounds = _transform_bounds_safe(
                    vector_report.get("crs"),
                    raster_crs,
                    comparison_bounds,
                )

            bbox_intersects = (
                _bbox_intersects(raster_bounds, comparison_bounds)
                if raster_bounds is not None and comparison_bounds is not None
                else None
            )
            if bbox_intersects is False:
                warning_codes.append("NO_BBOX_INTERSECTION")

            raster_vector_reports.append(
                {
                    "raster_path": raster_report["path"],
                    "vector_path": vector_report["path"],
                    "crs_match": bool(crs_match),
                    "bbox_intersects": bbox_intersects,
                    "warning_codes": warning_codes,
                }
            )
            warnings = _warning_union(warnings, warning_codes)

    metrics = {
        "raster_count": len(raster_items),
        "vector_count": len(vector_items),
        "readable_raster_count": sum(1 for report in raster_reports if report.get("readable")),
        "readable_vector_count": sum(1 for report in vector_reports if report.get("readable")),
        "raster_reports": raster_reports,
        "vector_reports": vector_reports,
        "raster_pair_reports": raster_pair_reports,
        "raster_vector_reports": raster_vector_reports,
    }
    return ToolResult.succeeded(
        tool=tool,
        summary=f"Validated {len(raster_items)} raster(s) and {len(vector_items)} vector(s).",
        metrics=metrics,
        warnings=warnings,
    )
