from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box


@pytest.fixture
def runtime_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    (workspace / "outputs").mkdir(parents=True)
    monkeypatch.setenv("NTL_MCP_WORKDIR", str(workspace))
    return workspace


def _write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> Path:
    gdf.to_file(path, driver="GeoJSON")
    return path


@pytest.fixture
def admin_polygons_path(runtime_workspace: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "shapeName": ["west", "east"],
            "iso3": ["TST", "TST"],
        },
        geometry=[
            box(0.0, 0.0, 1.0, 1.0),
            box(1.0, 0.0, 2.0, 1.0),
        ],
        crs="EPSG:4326",
    )
    return _write_geojson(runtime_workspace / "inputs" / "admin.geojson", gdf)


@pytest.fixture
def point_features_geojson_path(runtime_workspace: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3],
            "longitude": [0.5, 1.5, 3.0],
            "latitude": [0.5, 0.5, 3.0],
        },
        geometry=[
            Point(0.5, 0.5),
            Point(1.5, 0.5),
            Point(3.0, 3.0),
        ],
        crs="EPSG:4326",
    )
    return _write_geojson(runtime_workspace / "inputs" / "points.geojson", gdf)


@pytest.fixture
def point_features_csv_path(runtime_workspace: Path) -> Path:
    path = runtime_workspace / "inputs" / "points.csv"
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "longitude": [0.5, 1.5, 3.0],
            "latitude": [0.5, 0.5, 3.0],
        }
    ).to_csv(path, index=False, encoding="utf-8")
    return path
