"""Scientific contract regressions for the public zonal-statistics tool.

The verified benchmark fixture is intentionally a test-only oracle.  Runtime
code does not import it, inspect task IDs, or select a case-specific path.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from pyproj import Geod
from rasterio.transform import from_origin
from shapely.geometry import box

from tools import NTL_raster_stats as stats


_DEFAULT_REFERENCE_ROOT = Path(
    r"D:\Research_vault\work\projects\ntl-gpt\data\benchmark-v1\fixtures\verified-reference"
)
_REFERENCE_ROOT = Path(os.environ.get("NTL_BENCHMARK_REFERENCE_ROOT", _DEFAULT_REFERENCE_ROOT))
_METRIC_BY_TASK = {
    "BV1-040": "LArea",
    "BV1-041": "3DPLand",
    "BV1-042": "3DED",
    "BV1-043": "3DLPI",
}
_GOLD_KEY_BY_TASK = {
    "BV1-040": "lit_area_km2",
    "BV1-041": "three_d_pland_percent",
    "BV1-042": "three_d_edge_density_km2_per_ntl",
    "BV1-043": "three_d_lpi_fraction",
}


def test_landscape_metrics_use_valid_zeroes_weighted_area_and_four_neighbours() -> None:
    """Unit-level check independent of any benchmark fixture or target value."""

    values = np.array(
        [[5.0, 0.0, 4.0], [0.0, 2.0, 0.0], [3.0, 0.0, np.nan]],
        dtype=np.float64,
    )
    pixel_areas = np.array(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
        dtype=np.float64,
    )
    result = stats.calc_indices_per_polygon(
        values,
        np.ones(values.shape, dtype=bool),
        pixel_areas,
        selected_indices=["LArea", "3DPLand", "3DED", "3DLPI"],
    )

    # Four isolated positive pixels: areas 1 + 3 + 5 + 7 and largest patch 5.
    assert result["LArea"] == pytest.approx(16.0)
    assert result["3DPLand"] == pytest.approx(14.0 / (5.0 * 8.0) * 100.0)
    assert result["3DED"] == pytest.approx(16.0 / 14.0)
    assert result["3DLPI"] == pytest.approx(5.0 / 14.0)


def test_public_tool_writes_geodesic_landscape_csv(tmp_path: Path, monkeypatch) -> None:
    """The public workspace entry point preserves the same scientific contract."""

    import storage_manager as storage_module

    data_root = tmp_path / "user_data"
    monkeypatch.setattr(storage_module.storage_manager, "base_dir", data_root)
    monkeypatch.setattr(storage_module.storage_manager, "shared_dir", tmp_path / "shared_data")
    token = storage_module.current_thread_id.set("stats-contract")
    try:
        workspace = storage_module.storage_manager.get_workspace()
        raster_path = workspace / "inputs" / "ntl_2020.tif"
        values = np.array([[5.0, 0.0], [3.0, -9999.0]], dtype=np.float32)
        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            height=2,
            width=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0.0, 2.0, 1.0, 1.0),
            nodata=-9999.0,
        ) as destination:
            destination.write(values, 1)
        gpd.GeoDataFrame(
            {"name": ["roi"]},
            geometry=[box(0.0, 0.0, 2.0, 2.0)],
            crs="EPSG:4326",
        ).to_file(workspace / "inputs" / "boundary.geojson", driver="GeoJSON")

        response = stats.NTL_raster_statistics(
            shapefile_path="boundary.geojson",
            output_csv_path="metrics.csv",
            ntl_tif_path="ntl_2020.tif",
            selected_indices=["LArea", "3DPLand", "3DED", "3DLPI"],
        )
        assert response.startswith("Success:")
        output = pd.read_csv(workspace / "outputs" / "metrics.csv")
        row = output.loc[output["Region"] == "roi"].iloc[0]

        geod = Geod(ellps="WGS84")
        row_areas = []
        for top, bottom in ((2.0, 1.0), (1.0, 0.0)):
            area_m2, _ = geod.polygon_area_perimeter(
                [0.0, 1.0, 1.0, 0.0], [top, top, bottom, bottom]
            )
            row_areas.append(abs(area_m2) / 1_000_000.0)
        lit_area = row_areas[0] + row_areas[1]
        assert row["LArea"] == pytest.approx(lit_area)
        assert row["3DPLand"] == pytest.approx(8.0 / (5.0 * 3.0) * 100.0)
        assert row["3DED"] == pytest.approx(lit_area / 8.0)
        assert row["3DLPI"] == pytest.approx(1.0)
    finally:
        storage_module.current_thread_id.reset(token)


@pytest.mark.parametrize("task_id", tuple(_METRIC_BY_TASK))
def test_verified_fixture_regression_for_landscape_metrics(task_id: str) -> None:
    """Compare the general tool algorithm against frozen, independently built evidence."""

    package = _REFERENCE_ROOT / task_id
    if not package.is_dir():
        pytest.skip("verified local benchmark fixture is not available in this environment")

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    expected_rows = manifest["gold_answer"]["result"]["rows"]
    metric_name = _METRIC_BY_TASK[task_id]
    gold_key = _GOLD_KEY_BY_TASK[task_id]
    raster_path = package / "inputs" / "NTL_Shanghai_2000_2020_2020.tif"
    boundary_path = package / "inputs" / "shanghai_districts_boundary.shp"

    actual_rows, _ = stats._compute_for_single_raster(
        str(raster_path),
        raster_path.name,
        str(boundary_path),
        [metric_name],
        only_global=False,
    )
    actual_rows = [row for row in actual_rows if row["Region"] != "Global_Summary"]
    boundary = gpd.read_file(boundary_path)

    # The runtime CSV preserves boundary feature order.  The frozen reference
    # is ordered by the stable administrative ID, so establish that mapping
    # from the input itself instead of injecting benchmark labels into runtime.
    assert list(boundary["AdCode"].astype(int)) == [row["adcode"] for row in expected_rows]
    assert len(actual_rows) == len(expected_rows)
    for actual, expected in zip(actual_rows, expected_rows):
        assert math.isclose(
            float(actual[metric_name]),
            float(expected[gold_key]),
            rel_tol=1e-10,
            abs_tol=1e-10,
        )
