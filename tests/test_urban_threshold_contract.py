"""Regression tests for the public thresholded built-up extraction tool.

The frozen benchmark package below is a test-only oracle.  The runtime tool
does not inspect task identifiers, reference output paths, or expected values.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from pyproj import Geod
from rasterio.transform import from_origin
from shapely.geometry import box

import storage_manager as storage_module
from tools import NTL_urban_structure_extract as urban


_DEFAULT_REFERENCE_ROOT = Path(
    r"D:\Research_vault\work\projects\ntl-gpt\data\benchmark-v1\fixtures\verified-reference"
)
_REFERENCE_ROOT = Path(os.environ.get("NTL_BENCHMARK_REFERENCE_ROOT", _DEFAULT_REFERENCE_ROOT))


def _use_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, thread_id: str) -> Path:
    monkeypatch.setattr(storage_module.storage_manager, "base_dir", tmp_path / "user_data")
    monkeypatch.setattr(storage_module.storage_manager, "shared_dir", tmp_path / "shared_data")
    token = storage_module.current_thread_id.set(thread_id)
    workspace = storage_module.storage_manager.get_workspace()
    return workspace, token


def _wgs84_pixel_area_km2(left: float, right: float, top: float, bottom: float) -> float:
    area_m2, _ = Geod(ellps="WGS84").polygon_area_perimeter(
        [left, right, right, left], [top, top, bottom, bottom]
    )
    return abs(area_m2) / 1_000_000.0


def test_public_tool_threshold_contract_handles_aoi_valid_zero_and_nonfinite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A general synthetic fixture checks the stated pixel and area semantics."""

    workspace, token = _use_workspace(monkeypatch, tmp_path, "threshold-contract")
    try:
        raster_path = workspace / "inputs" / "ntl.tif"
        values = np.array(
            [[0.0, 10.0, 20.0], [np.nan, 5.0, np.inf], [-9999.0, 11.0, 0.0]],
            dtype=np.float32,
        )
        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            height=3,
            width=3,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0.0, 3.0, 1.0, 1.0),
            nodata=-9999.0,
        ) as destination:
            destination.write(values, 1)

        # Centres in columns 0 and 1 fall inside; centres in column 2 do not.
        gpd.GeoDataFrame(
            {"name": ["roi"]}, geometry=[box(0.0, 0.0, 2.0, 3.0)], crs="EPSG:4326"
        ).to_file(workspace / "inputs" / "roi.geojson", driver="GeoJSON")

        response = urban.extract_urban_area_by_thresholding(
            tif_filename="ntl.tif",
            output_filename="built.tif",
            threshold=10.0,
            aoi_boundary="roi.geojson",
            statistics_filename="built.json",
        )
        assert response.startswith("✅ Success!")

        with rasterio.open(workspace / "outputs" / "built.tif") as result:
            output = result.read(1)
            assert result.nodata == 255
            assert result.crs.to_string() == "EPSG:4326"
            assert result.transform == from_origin(0.0, 3.0, 1.0, 1.0)
        assert np.array_equal(
            output,
            np.array(
                [[0, 1, 255], [255, 0, 255], [255, 1, 255]], dtype=np.uint8
            ),
        )

        statistics = json.loads((workspace / "outputs" / "built.json").read_text(encoding="utf-8"))
        assert statistics["method"]["threshold"] == 10.0
        assert statistics["method"]["comparison"] == "NTL >= 10"
        assert statistics["aoi"]["all_touched"] is False
        assert statistics["result"] == {
            "aoi_valid_pixel_count": 4,
            "built_up_pixel_count": 2,
            "non_built_pixel_count": 2,
            "built_up_fraction": 0.5,
            "built_up_area_km2": pytest.approx(
                _wgs84_pixel_area_km2(1.0, 2.0, 3.0, 2.0)
                + _wgs84_pixel_area_km2(1.0, 2.0, 1.0, 0.0)
            ),
        }
    finally:
        storage_module.current_thread_id.reset(token)


def test_verified_fixture_regression_has_no_runtime_case_specific_logic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generic tool reproduces the frozen threshold semantics on an external fixture."""

    package = _REFERENCE_ROOT / "BV1-056"
    if not package.is_dir():
        pytest.skip("verified local benchmark fixture is not available in this environment")

    workspace, token = _use_workspace(monkeypatch, tmp_path, "threshold-reference")
    try:
        for source in (package / "inputs").iterdir():
            shutil.copy2(source, workspace / "inputs" / source.name)
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        expected = manifest["gold_answer"]["result"]

        response = urban.extract_urban_area_by_thresholding(
            tif_filename="NTL_Shanghai_2000_2020_2018.tif",
            output_filename="built_up.tif",
            threshold=10.0,
            aoi_boundary="shanghai_districts_boundary.shp",
            statistics_filename="built_up_statistics.json",
        )
        assert response.startswith("✅ Success!")

        with rasterio.open(workspace / "outputs" / "built_up.tif") as actual, rasterio.open(
            package / "outputs" / "BV1-056_built_up_threshold10.tif"
        ) as reference:
            assert actual.crs == reference.crs
            assert actual.transform == reference.transform
            assert actual.nodata == 255
            assert np.array_equal(actual.read(1), reference.read(1))

        statistics = json.loads(
            (workspace / "outputs" / "built_up_statistics.json").read_text(encoding="utf-8")
        )
        result = statistics["result"]
        assert result["aoi_valid_pixel_count"] == expected["aoi_valid_pixel_count"]
        assert result["built_up_pixel_count"] == expected["built_up_pixel_count"]
        assert result["non_built_pixel_count"] == expected["non_built_pixel_count"]
        assert result["built_up_fraction"] == pytest.approx(expected["built_up_fraction"], rel=1e-10)
        assert result["built_up_area_km2"] == pytest.approx(expected["built_up_area_km2"], rel=1e-10)
    finally:
        storage_module.current_thread_id.reset(token)
