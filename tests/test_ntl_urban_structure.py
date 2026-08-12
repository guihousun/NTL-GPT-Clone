from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The Deep Agents compatibility venv inherits geospatial wheels from the
# NTL-GPT conda environment, but Windows venv activation does not propagate the
# corresponding PROJ/GDAL data directories. Resolve them from sys.base_prefix
# before geopandas/rasterio import so the synthetic tests exercise the branch's
# implementation instead of failing during CRS construction.
_CONDA_SHARE = Path(sys.base_prefix) / "Library" / "share"
if (_CONDA_SHARE / "proj").is_dir():
    os.environ.setdefault("PROJ_DATA", str(_CONDA_SHARE / "proj"))
if (_CONDA_SHARE / "gdal").is_dir():
    os.environ.setdefault("GDAL_DATA", str(_CONDA_SHARE / "gdal"))

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "packages" / "ntl_toolkit" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from ntl_toolkit.core.urban_structure import (  # noqa: E402
    ContourNode,
    CHEN2017_SHANGHAI_2014_CONFIG,
    build_localized_contour_tree,
    detect_urban_centres,
    simplify_contour_tree,
)


def _write_aoi(path: Path, bounds: tuple[float, float, float, float]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"name": ["synthetic_aoi"]},
        geometry=[box(*bounds)],
        crs="EPSG:3857",
    ).to_file(path, driver="GeoJSON")
    return path


def _write_raster(
    path: Path,
    values: np.ndarray,
    *,
    unit: str | None = "nW/cm^2/sr",
    nodata: float | None = -9999.0,
    crs: CRS | str | None = "EPSG:3857",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(values, dtype=np.float32)
    encoded = np.where(np.isfinite(array), array, nodata if nodata is not None else np.nan)
    transform = from_origin(0.0, 60_000.0, 500.0, 500.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(encoded.astype(np.float32), 1)
        if unit is not None:
            dataset.update_tags(units=unit)
    return path


def _hill_values(*, peaks: list[tuple[float, float, float, float]] | None = None) -> np.ndarray:
    y, x = np.mgrid[0:120, 0:120]
    world_x = (x + 0.5) * 500.0
    world_y = 60_000.0 - (y + 0.5) * 500.0
    values = np.full((120, 120), 2.0, dtype=np.float64)
    for peak_x, peak_y, amplitude, radius in peaks or [(30_000.0, 30_000.0, 85.0, 6_000.0)]:
        values += amplitude * np.exp(
            -((world_x - peak_x) ** 2 + (world_y - peak_y) ** 2) / (2.0 * radius**2)
        )
    return values


def _run_synthetic(
    root: Path,
    *,
    values: np.ndarray,
    min_area_km2: float = 5.0,
    unit: str | None = "nW/cm^2/sr",
    nodata: float | None = -9999.0,
    crs: CRS | str | None = "EPSG:3857",
):
    inputs = root / "inputs"
    outputs = root / "outputs"
    raster = _write_raster(inputs / "synthetic_ntl.tif", values, unit=unit, nodata=nodata, crs=crs)
    aoi = _write_aoi(inputs / "aoi.geojson", (10_000.0, 10_000.0, 50_000.0, 50_000.0))
    return detect_urban_centres(
        raster,
        aoi,
        outputs / "urban_centres.geojson",
        outputs / "urban_centres.csv",
        outputs / "urban_centres.metadata.json",
        base_threshold=34.0,
        contour_interval=1.0,
        min_area_km2=min_area_km2,
        gaussian_kernel=3,
        gaussian_sigma=1.0,
        aoi_buffer_km=10.0,
        parameter_profile=None,
    )


def _result_error_code(result) -> str:
    assert result.error is not None
    return result.error.code


def test_single_double_nested_and_single_node_trees() -> None:
    single = build_localized_contour_tree(
        [ContourNode("single", box(0, 0, 2, 2), 40.0, has_local_peak=True)]
    )
    assert single["single"].level == 1
    assert simplify_contour_tree(single)["single"].members == ("single",)

    double = build_localized_contour_tree(
        [
            ContourNode("left", box(0, 0, 2, 2), 50.0, has_local_peak=True),
            ContourNode("right", box(4, 0, 6, 2), 50.0, has_local_peak=True),
            ContourNode("merge", box(-1, -1, 7, 3), 34.0, has_local_peak=False),
        ]
    )
    assert double["merge"].children_ids == ["left", "right"]
    assert double["merge"].level == 2
    simplified_double = simplify_contour_tree(double)
    assert simplified_double["left"].parent_id == "merge"
    assert simplified_double["right"].parent_id == "merge"
    assert simplified_double["merge"].children_ids == ["left", "right"]

    nested = build_localized_contour_tree(
        [
            ContourNode("seed", box(1, 1, 2, 2), 60.0, has_local_peak=True),
            ContourNode("middle", box(0, 0, 3, 3), 45.0, has_local_peak=False),
            ContourNode("outer", box(-1, -1, 4, 4), 34.0, has_local_peak=False),
        ]
    )
    assert [nested[node_id].level for node_id in ("seed", "middle", "outer")] == [1, 1, 1]
    simplified_nested = simplify_contour_tree(nested)
    assert list(simplified_nested) == ["outer"]
    assert simplified_nested["outer"].members == ("middle", "outer", "seed")


def test_tree_drops_unseeded_branch_and_preserves_parent_relationships() -> None:
    nodes = build_localized_contour_tree(
        [
            ContourNode("seed", box(0, 0, 2, 2), 55.0, has_local_peak=True),
            ContourNode("noise", box(4, 0, 6, 2), 55.0, has_local_peak=False),
            ContourNode("root", box(-1, -1, 7, 3), 34.0, has_local_peak=False),
        ]
    )
    assert set(nodes) == {"seed", "root"}
    assert nodes["seed"].parent_id == "root"
    assert nodes["root"].children_ids == ["seed"]


def test_validation_rejects_multiband_missing_unit_geographic_crs_and_bad_coverage(tmp_path: Path) -> None:
    root = tmp_path / "validation"
    values = _hill_values()
    raster = _write_raster(root / "inputs" / "multiband.tif", values)
    # Recreate the multiband input because rasterio cannot change count in place.
    raster.unlink()
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        height=120,
        width=120,
        count=2,
        dtype="float32",
        crs="EPSG:3857",
        transform=from_origin(0.0, 60_000.0, 500.0, 500.0),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.stack([values, values]))
        dataset.update_tags(units="nW/cm^2/sr")
    aoi = _write_aoi(root / "inputs" / "aoi.geojson", (10_000.0, 10_000.0, 50_000.0, 50_000.0))
    result = detect_urban_centres(raster, aoi, root / "outputs" / "a.geojson", root / "outputs" / "a.csv")
    assert _result_error_code(result) == "INVALID_RASTER"

    missing_unit_root = tmp_path / "missing_unit"
    result = _run_synthetic(missing_unit_root, values=values, unit=None)
    assert _result_error_code(result) == "UNIT_MISSING"

    geographic_root = tmp_path / "geographic"
    result = _run_synthetic(geographic_root, values=values, crs="EPSG:4326")
    assert _result_error_code(result) == "CRS_NOT_PROJECTED_METRIC"

    coverage_root = tmp_path / "coverage"
    raster = _write_raster(coverage_root / "inputs" / "small.tif", values)
    aoi = _write_aoi(coverage_root / "inputs" / "large_aoi.geojson", (-20_000.0, -20_000.0, 80_000.0, 80_000.0))
    result = detect_urban_centres(
        raster,
        aoi,
        coverage_root / "outputs" / "a.geojson",
        coverage_root / "outputs" / "a.csv",
        parameter_profile=None,
    )
    assert _result_error_code(result) == "INPUT_COVERAGE_INSUFFICIENT"

    invalid_aoi_root = tmp_path / "invalid_aoi"
    invalid_aoi_raster = _write_raster(invalid_aoi_root / "inputs" / "invalid_aoi.tif", values)
    invalid_aoi_path = invalid_aoi_root / "inputs" / "invalid.geojson"
    gpd.GeoDataFrame(
        {"name": ["bowtie"]},
        geometry=[Polygon([(10_000, 10_000), (50_000, 50_000), (10_000, 50_000), (50_000, 10_000), (10_000, 10_000)])],
        crs="EPSG:3857",
    ).to_file(invalid_aoi_path, driver="GeoJSON")
    result = detect_urban_centres(
        invalid_aoi_raster,
        invalid_aoi_path,
        invalid_aoi_root / "outputs" / "a.geojson",
        invalid_aoi_root / "outputs" / "a.csv",
        parameter_profile=None,
    )
    assert result.status == "failed"


def test_area_threshold_nodata_open_contour_and_no_valid_centre(tmp_path: Path) -> None:
    values = _hill_values()
    successful = _run_synthetic(tmp_path / "area_low", values=values, min_area_km2=5.0)
    assert successful.status == "succeeded"
    too_large = _run_synthetic(tmp_path / "area_high", values=values, min_area_km2=500.0)
    assert _result_error_code(too_large) == "NO_CLOSED_CONTOURS"

    no_data_values = values.copy()
    no_data_values[52:68, 52:68] = np.nan
    nodata_result = _run_synthetic(tmp_path / "nodata_hole", values=no_data_values)
    assert nodata_result.status == "failed"
    assert _result_error_code(nodata_result) in {"NO_CLOSED_CONTOURS", "NO_VALID_CENTERS"}

    edge_values = np.full((120, 120), 2.0, dtype=np.float64)
    edge_values[:, :12] += 100.0
    open_result = _run_synthetic(tmp_path / "open", values=edge_values)
    assert _result_error_code(open_result) == "NO_CLOSED_CONTOURS"

    below_threshold = _run_synthetic(tmp_path / "below", values=np.full((120, 120), 5.0, dtype=np.float64))
    assert _result_error_code(below_threshold) == "NO_CLOSED_CONTOURS"


def test_outputs_are_real_valid_and_deterministic(tmp_path: Path) -> None:
    values = _hill_values(
        peaks=[
            (24_000.0, 30_000.0, 85.0, 5_000.0),
            (36_000.0, 30_000.0, 80.0, 5_000.0),
        ]
    )
    first = _run_synthetic(tmp_path / "first", values=values)
    second = _run_synthetic(tmp_path / "second", values=values)
    assert first.status == second.status == "succeeded"
    assert first.metrics == second.metrics

    first_csv = tmp_path / "first" / "outputs" / "urban_centres.csv"
    second_csv = tmp_path / "second" / "outputs" / "urban_centres.csv"
    assert first_csv.read_bytes() == second_csv.read_bytes()
    first_metadata = json.loads((tmp_path / "first" / "outputs" / "urban_centres.metadata.json").read_text(encoding="utf-8"))
    second_metadata = json.loads((tmp_path / "second" / "outputs" / "urban_centres.metadata.json").read_text(encoding="utf-8"))
    assert first_metadata == second_metadata

    first_vector = gpd.read_file(tmp_path / "first" / "outputs" / "urban_centres.geojson")
    second_vector = gpd.read_file(tmp_path / "second" / "outputs" / "urban_centres.geojson")
    assert first_vector["center_id"].tolist() == second_vector["center_id"].tolist()
    assert first_vector.geometry.to_wkb().tolist() == second_vector.geometry.to_wkb().tolist()
    assert all(geometry.is_valid and not geometry.is_empty for geometry in first_vector.geometry)
    csv_frame = pd.read_csv(first_csv, dtype={"center_id": str}, keep_default_na=False)
    assert set(csv_frame["center_id"]) == set(first_vector["center_id"].astype(str))
    assert len(csv_frame) == len(first_vector) == first.metrics["centre_count"]
    vector_by_id = first_vector.set_index(first_vector["center_id"].astype(str))
    csv_by_id = csv_frame.set_index("center_id")
    for column in ("parent_id", "child_ids", "level", "type", "main"):
        vector_values = vector_by_id[column].map(lambda value: "" if pd.isna(value) else str(value)).to_dict()
        csv_values = csv_by_id[column].map(lambda value: "" if pd.isna(value) else str(value)).to_dict()
        assert vector_values == csv_values


def test_tool_registration_and_default_are_compatible() -> None:
    import tools
    from tools.NTL_urban_structure_extract import (  # noqa: PLC0415
        UrbanStructureInput,
        detect_urban_centres_logic,
        detect_urban_centres_tool,
    )

    assert tools._EXPORTS["detect_urban_centres_tool"] == (
        ".NTL_urban_structure_extract",
        "detect_urban_centres_tool",
    )
    assert "detect_urban_centres_tool" in tools._GROUPS["analyst_tools"]
    assert "detect_urban_centres_tool" not in tools._GROUPS["engineer_tools"]
    assert "detect_urban_centres_tool" in tools._GROUPS["specialized_tool_catalog"]
    assert UrbanStructureInput.__fields__["min_area_km2"].default == 5.0
    assert CHEN2017_SHANGHAI_2014_CONFIG["profile"] == "chen2017_shanghai_2014"
    assert CHEN2017_SHANGHAI_2014_CONFIG["min_area_km2"] == 5.0
    assert "centre_count" not in CHEN2017_SHANGHAI_2014_CONFIG
    assert detect_urban_centres_logic.__name__ == "detect_urban_centres_logic"
    assert detect_urban_centres_tool.name == "Detect_Urban_Centres_and_Spatial_Structure"


def test_q70_frozen_input_end_to_end_against_reference(tmp_path: Path) -> None:
    root = REPO_ROOT / "example" / "Q70"
    raster = root / "inputs" / "ntl_shanghai_2014_12_v1_albers_500m.tif"
    aoi = root / "inputs" / "shanghai_boundary.geojson"
    reference_metadata_path = root / "reference_output" / "urban_centres.metadata.json"
    if not raster.exists() or not aoi.exists() or not reference_metadata_path.exists():
        pytest.skip("Q70's external frozen fixture is not stored in this worktree")

    output_dir = tmp_path / "test_output"
    result = detect_urban_centres(
        raster,
        aoi,
        output_dir / "urban_centres.geojson",
        output_dir / "urban_centres.csv",
        output_dir / "urban_centres.metadata.json",
        parameter_profile=CHEN2017_SHANGHAI_2014_CONFIG["profile"],
    )
    assert result.status == "succeeded", result.summary
    reference_metadata = json.loads(reference_metadata_path.read_text(encoding="utf-8"))
    assert result.metrics["centre_count"] == reference_metadata["centres"]["total"]
    assert result.metrics["tree_count"] == reference_metadata["tree"]["tree_count"]
    output_vector = gpd.read_file(output_dir / "urban_centres.geojson")
    output_csv = pd.read_csv(output_dir / "urban_centres.csv", dtype={"center_id": str})
    assert len(output_vector) == len(output_csv) == result.metrics["centre_count"]
    assert set(output_vector["center_id"].astype(str)) == set(output_csv["center_id"])
    assert all(geometry.is_valid and not geometry.is_empty for geometry in output_vector.geometry)
