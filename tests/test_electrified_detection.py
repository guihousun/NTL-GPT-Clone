from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tools import _EXPORTS, _GROUPS, electrified_detection_tool
from tools.electrified_detection import (
    METHOD_DOI,
    OUTPUT_NODATA,
    detect_electrified_areas_by_thresholding,
)


def _write_raster(path: Path, data: np.ndarray, *, nodata: float, transform=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=str(data.dtype),
        crs="EPSG:4326",
        transform=transform or from_origin(120.0, 32.0, 0.01, 0.01),
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)


def test_electrified_tool_is_registered_in_lightweight_module():
    assert _EXPORTS["electrified_detection_tool"] == (
        ".electrified_detection",
        "electrified_detection_tool",
    )
    assert "electrified_detection_tool" in _GROUPS["Engineer_tools"]
    assert "electrified_detection_tool" in _GROUPS["specialized_tool_catalog"]
    assert electrified_detection_tool.name == "Detect_Electrified_Areas_by_Thresholding"
    assert "midpoint threshold" in electrified_detection_tool.description


def test_paper_threshold_mask_and_population_aggregation(tmp_path, monkeypatch):
    ntl_path = tmp_path / "inputs" / "ntl.tif"
    labels_path = tmp_path / "inputs" / "labels.tif"
    population_path = tmp_path / "inputs" / "population.tif"
    _write_raster(
        ntl_path,
        np.array([[0.0, 0.2, 0.4], [0.6, 0.8, -999.0]], dtype=np.float32),
        nodata=-999.0,
    )
    _write_raster(
        labels_path,
        np.array([[0, 0, 255], [255, 1, 1]], dtype=np.uint8),
        nodata=255,
    )
    _write_raster(
        population_path,
        np.array([[10.0, 20.0, 30.0], [40.0, 50.0, -999.0]], dtype=np.float32),
        nodata=-999.0,
    )

    inputs = {
        "ntl.tif": ntl_path,
        "labels.tif": labels_path,
        "population.tif": population_path,
    }
    monkeypatch.setattr(
        "tools.electrified_detection.storage_manager.resolve_input_path",
        lambda value, _thread=None: str(inputs[Path(value).name]),
    )
    monkeypatch.setattr(
        "tools.electrified_detection.storage_manager.resolve_output_path",
        lambda value, _thread=None: str(tmp_path / "outputs" / Path(value).name),
    )

    result = detect_electrified_areas_by_thresholding(
        "ntl.tif",
        "labels.tif",
        "population.tif",
    )
    assert result["status"] == "success"
    assert result["method"]["reference"] == METHOD_DOI
    assert result["calibration"]["threshold"] == pytest.approx(0.5)
    assert result["calibration"]["maximum_non_electrified_ntl"] == pytest.approx(0.2)
    assert result["calibration"]["minimum_electrified_ntl"] == pytest.approx(0.8)
    assert result["population"]["total_population"] == 150.0
    assert result["population"]["population_with_electricity_access_proxy"] == 90.0
    assert result["population"]["population_access_proxy_share"] == 0.6

    mask_path = tmp_path / "outputs" / "electrified_mask.tif"
    with rasterio.open(mask_path) as src:
        assert src.nodata == OUTPUT_NODATA
        assert src.read(1).tolist() == [[0, 0, 0], [1, 1, OUTPUT_NODATA]]
    metadata = json.loads(
        (tmp_path / "outputs" / "electrified_population.metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["inputs"]["ntl"]["sha256"]
    assert metadata["outputs"]["electricity_mask"].endswith("electrified_mask.tif")


def test_calibration_grid_mismatch_fails_closed(tmp_path, monkeypatch):
    ntl_path = tmp_path / "inputs" / "ntl.tif"
    labels_path = tmp_path / "inputs" / "labels.tif"
    population_path = tmp_path / "inputs" / "population.tif"
    _write_raster(ntl_path, np.ones((2, 2), dtype=np.float32), nodata=-999.0)
    _write_raster(
        labels_path,
        np.array([[0, 1], [0, 1]], dtype=np.uint8),
        nodata=255,
        transform=from_origin(120.1, 32.0, 0.01, 0.01),
    )
    _write_raster(population_path, np.ones((2, 2), dtype=np.float32), nodata=-999.0)
    inputs = {"ntl.tif": ntl_path, "labels.tif": labels_path, "population.tif": population_path}
    monkeypatch.setattr(
        "tools.electrified_detection.storage_manager.resolve_input_path",
        lambda value, _thread=None: str(inputs[Path(value).name]),
    )
    monkeypatch.setattr(
        "tools.electrified_detection.storage_manager.resolve_output_path",
        lambda value, _thread=None: str(tmp_path / "outputs" / Path(value).name),
    )
    result = detect_electrified_areas_by_thresholding("ntl.tif", "labels.tif", "population.tif")
    assert result["status"] == "error"
    assert "exact CRS, transform" in result["message"]
