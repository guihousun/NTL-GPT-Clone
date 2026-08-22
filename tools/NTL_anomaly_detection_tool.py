from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import numpy as np
import rasterio
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from rasterio.features import geometry_mask

# 导入你的存储管理器
from storage_manager import storage_manager
from ntl_toolkit.runtime import reserve_output_path

# ===== Input Schema =====
class SimpleAnomalyDetectionInput(BaseModel):
    raster_files: List[str] = Field(
        ...,
        description="Time-series NTL raster file names (at least two images, e.g., ['NTL_2022.tif', 'NTL_2023.tif']). Files should be located in the workspace 'inputs/' folder."
    )
    target_index: Optional[int] = Field(
        None,
        description="Index of the specific image to be detected (0-based). Default is the latest image."
    )
    k_sigma: float = Field(
        3.0,
        description="Threshold: pixels with a Z-score > k_sigma are flagged as anomalies."
    )
    save_filename: Optional[str] = Field(
        "NTL_anomaly_mask.tif",
        description="The filename for the generated anomaly mask. Saved to the 'outputs/' folder."
    )
    vector_file: Optional[str] = Field(
        None,
        description=(
            "Optional AOI boundary filename in 'inputs/'. When supplied, pixels outside the "
            "AOI are emitted as NoData rather than evaluated."
        ),
    )


def _resolve_target_index(target_index: Optional[int], raster_count: int) -> int:
    if target_index is None:
        return raster_count - 1
    if isinstance(target_index, bool) or not isinstance(target_index, int):
        raise ValueError("target_index must be an integer or omitted.")
    if target_index < 0 or target_index >= raster_count:
        raise ValueError(f"target_index must be in [0, {raster_count - 1}].")
    return target_index


def _load_common_grid(raster_paths: List[str]) -> tuple[np.ndarray, dict, object]:
    """Load a chronologically ordered stack and reject non-identical grids."""

    arrays: list[np.ndarray] = []
    profile: dict | None = None
    reference_crs = None
    reference_transform = None
    reference_shape: tuple[int, int] | None = None

    for path in raster_paths:
        with rasterio.open(path) as dataset:
            current_shape = (dataset.height, dataset.width)
            if profile is None:
                profile = dataset.profile.copy()
                reference_crs = dataset.crs
                reference_transform = dataset.transform
                reference_shape = current_shape
            elif (
                dataset.crs != reference_crs
                or dataset.transform != reference_transform
                or current_shape != reference_shape
            ):
                raise ValueError("All anomaly rasters must share the same CRS, grid, and shape.")

            values = np.asarray(dataset.read(1, masked=True).filled(np.nan), dtype=np.float64)
            values[~np.isfinite(values)] = np.nan
            arrays.append(values)

    assert profile is not None and reference_shape is not None
    return np.stack(arrays, axis=0), profile, reference_transform


def _aoi_mask(vector_file: Optional[str], profile: dict, transform: object) -> np.ndarray:
    shape = (int(profile["height"]), int(profile["width"]))
    if not vector_file:
        return np.ones(shape, dtype=bool)

    vector_path = storage_manager.resolve_input_path(vector_file)
    boundary = gpd.read_file(vector_path)
    if boundary.empty or boundary.crs is None:
        raise ValueError("vector_file must contain a non-empty boundary with a declared CRS.")
    raster_crs = profile.get("crs")
    if raster_crs is None:
        raise ValueError("Anomaly raster has no CRS; cannot apply vector_file.")
    if boundary.crs != raster_crs:
        boundary = boundary.to_crs(raster_crs)
    geometries = [geometry for geometry in boundary.geometry if geometry is not None and not geometry.is_empty]
    if not geometries:
        raise ValueError("vector_file contains no valid geometries.")
    return geometry_mask(geometries, out_shape=shape, transform=transform, invert=True)


def _strict_positive_anomaly(
    raster_files: List[str],
    target_index: Optional[int],
    k_sigma: float,
    save_filename: str,
    vector_file: Optional[str],
) -> tuple[Path, Path, dict]:
    """Implement the reproducible population-SD, common-support anomaly contract."""

    if len(raster_files) < 2:
        raise ValueError("Anomaly detection requires at least two chronologically ordered rasters.")
    if isinstance(k_sigma, bool):
        raise ValueError("k_sigma must be a finite positive number.")
    try:
        threshold = float(k_sigma)
    except (TypeError, ValueError) as exc:
        raise ValueError("k_sigma must be a finite positive number.") from exc
    if not np.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("k_sigma must be a finite positive number.")

    input_paths = [storage_manager.resolve_input_path(path) for path in raster_files]
    target_position = _resolve_target_index(target_index, len(input_paths))
    stack, profile, transform = _load_common_grid(input_paths)
    aoi = _aoi_mask(vector_file, profile, transform)

    baseline = np.delete(stack, target_position, axis=0)
    # A comparison day/pixel is eligible only when every baseline and target
    # observation is valid. This makes support identical across the statistic.
    common_valid = np.all(np.isfinite(stack), axis=0) & aoi
    baseline_mean = np.mean(baseline, axis=0)
    baseline_std = np.std(baseline, axis=0, ddof=0)
    nonzero_baseline_sd = common_valid & np.isfinite(baseline_std) & (baseline_std > 0.0)
    z_score = np.full(baseline_mean.shape, np.nan, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        z_score[nonzero_baseline_sd] = (
            (stack[target_position][nonzero_baseline_sd] - baseline_mean[nonzero_baseline_sd])
            / baseline_std[nonzero_baseline_sd]
        )

    mask = np.full(baseline_mean.shape, 255, dtype=np.uint8)
    # A zero-variance baseline is a valid, stable comparison but cannot produce
    # a z-score anomaly. Preserve it as an explicit non-anomaly rather than
    # manufacturing a very large value with an epsilon denominator.
    mask[common_valid] = 0
    mask[nonzero_baseline_sd & (z_score > threshold)] = 1

    requested_output = Path(storage_manager.resolve_output_path(save_filename or "NTL_anomaly_mask.tif"))
    output_path = reserve_output_path(requested_output)
    profile.update(count=1, dtype="uint8", nodata=255)
    with rasterio.open(output_path, "w", **profile) as destination:
        destination.write(mask, 1)

    summary = {
        "schema": "ntl_gpt.anomaly_summary.v1",
        "target_index": int(target_position),
        "target_file": Path(input_paths[target_position]).name,
        "raster_count": int(len(input_paths)),
        "baseline_count": int(len(input_paths) - 1),
        "threshold": threshold,
        "method": {
            "baseline_standard_deviation": "population standard deviation (ddof=0)",
            "threshold_rule": "positive z-score strictly greater than k_sigma",
            "validity_rule": "common finite support across every baseline and target raster, intersected with optional AOI",
            "zero_baseline_sd_rule": "valid non-anomaly; excluded from z-score division",
        },
        "aoi_file": vector_file or None,
        "common_valid_pixel_count": int(np.sum(common_valid)),
        "evaluated_pixel_count": int(np.sum(common_valid)),
        "nonzero_baseline_sd_pixel_count": int(np.sum(nonzero_baseline_sd)),
        "zero_baseline_sd_pixel_count": int(np.sum(common_valid & (baseline_std == 0.0))),
        "positive_anomaly_pixel_count": int(np.sum(mask == 1)),
    }
    summary_path = reserve_output_path(output_path.with_name(f"{output_path.stem}_summary.json"))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path, summary_path, summary

# ===== Tool Logic =====
def detect_ntl_anomaly(
    raster_files: List[str],
    target_index: Optional[int] = None,
    k_sigma: float = 3.0,
    save_filename: str = "NTL_anomaly_mask.tif"
) -> str:
    """
    Core function for detecting anomalies in NTL time-series using standardized workspace paths.
    """
    return _detect_ntl_anomaly_with_optional_aoi(
        raster_files=raster_files,
        target_index=target_index,
        k_sigma=k_sigma,
        save_filename=save_filename,
        vector_file=None,
    )


def _detect_ntl_anomaly_with_optional_aoi(
    raster_files: List[str],
    target_index: Optional[int] = None,
    k_sigma: float = 3.0,
    save_filename: str = "NTL_anomaly_mask.tif",
    vector_file: Optional[str] = None,
) -> str:
    try:
        output_path, summary_path, summary = _strict_positive_anomaly(
            raster_files,
            target_index,
            k_sigma,
            save_filename,
            vector_file,
        )
    except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
        return f"Error: {exc}"

    return (
        "Anomaly Detection Task Completed.\n"
        f"- **Target Image**: {summary['target_file']}\n"
        f"- **Method**: Pixel-wise positive Z-score; population baseline SD (ddof=0); z > {float(k_sigma)}\n"
        "- **Support**: common-valid pixels across all baseline and target rasters; zero baseline-SD pixels cannot be anomalies\n"
        f"- **Positive Anomalies**: {summary['positive_anomaly_pixel_count']}\n"
        f"- **Result Saved**: `outputs/{output_path.name}`\n"
        f"- **Summary Saved**: `outputs/{summary_path.name}`"
    )

# ===== Tool Registration =====
detect_ntl_anomaly_tool = StructuredTool.from_function(
    func=_detect_ntl_anomaly_with_optional_aoi,
    name="Detect_NTL_anomaly",
    description=(
        "Identifies sudden brightness spikes or significant fluctuations in nighttime light (NTL) time-series data. "
        "The tool uses a positive Z-Score (K-Sigma) method to compare a target image against a historical baseline: "
        "population SD (ddof=0), strictly z > threshold, common valid support, and zero-SD pixels excluded from z-score anomalies. "
        "It automatically reads inputs from the workspace 'inputs/' folder and saves results to 'outputs/'. "
        "Useful for detecting post-disaster recovery, large-scale construction, or unexpected economic activity."
    ),
    input_type=SimpleAnomalyDetectionInput,
)
