from __future__ import annotations

import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from tools import _EXPORTS, _GROUPS, dmsp_viirs_harmonization_tool


def _write_raster(path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(0, 4, 1, 1)
    profile = {
        "driver": "GTiff",
        "height": int(array.shape[0]),
        "width": int(array.shape[1]),
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype(np.float32), 1)


def test_tool_is_registered_with_expected_contract():
    name = "dmsp_viirs_harmonization_tool"
    assert name in _EXPORTS
    assert name in _GROUPS["analyst_tools"]
    assert name in _GROUPS["specialized_tool_catalog"]
    assert dmsp_viirs_harmonization_tool.name == "DMSP_VIIRS_Harmonization"
    assert "DMSP" in dmsp_viirs_harmonization_tool.description
    assert "VIIRS-like" in dmsp_viirs_harmonization_tool.description


def test_cubic_dmsp_to_viirs_like_series_is_deterministic(tmp_path, monkeypatch):
    dmsp_dir = tmp_path / "dmsp"
    viirs_dir = tmp_path / "viirs"
    output_dir = tmp_path / "outputs"

    overlap_dmsp = np.arange(1, 17, dtype=np.float32).reshape(4, 4)
    overlap_viirs = 4.0 + 1.5 * overlap_dmsp - 0.02 * overlap_dmsp**2
    historical_dmsp = overlap_dmsp * 0.75
    later_viirs = overlap_viirs + 5.0

    _write_raster(dmsp_dir / "DMSP_2000.tif", historical_dmsp)
    _write_raster(dmsp_dir / "DMSP_2001.tif", overlap_dmsp)
    _write_raster(viirs_dir / "VIIRS_2001.tif", overlap_viirs)
    _write_raster(viirs_dir / "VIIRS_2002.tif", later_viirs)

    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(
        "tools.NTL_cross_sensor_harmonization.storage_manager.resolve_input_path",
        lambda folder: str({"dmsp": dmsp_dir, "viirs": viirs_dir}[folder]),
    )
    monkeypatch.setattr(
        "tools.NTL_cross_sensor_harmonization.storage_manager.resolve_output_path",
        lambda _: str(output_dir),
    )

    result = dmsp_viirs_harmonization_tool.invoke(
        {
            "dmsp_folder": "dmsp",
            "viirs_folder": "viirs",
            "output_folder": "dmsp_viirs_first_version",
            "start_year": 2000,
            "overlap_year": 2001,
            "end_year": 2002,
            "degree": 3,
        }
    )

    assert result["status"] == "success"
    assert result["direction"] == "DMSP_to_VIIRS_like"
    assert result["annual_output_count"] == 3
    assert result["overlap_diagnostics"]["rmse"] < 1e-4

    with rasterio.open(output_dir / "viirs_like_2000.tif") as src:
        historical_output = src.read(1)
    with rasterio.open(output_dir / "viirs_like_2001.tif") as src:
        overlap_output = src.read(1)
    with rasterio.open(output_dir / "viirs_like_2002.tif") as src:
        later_output = src.read(1)

    expected_historical = 4.0 + 1.5 * historical_dmsp - 0.02 * historical_dmsp**2
    np.testing.assert_allclose(historical_output, expected_historical, rtol=0, atol=1e-4)
    np.testing.assert_allclose(overlap_output, overlap_viirs, rtol=0, atol=1e-6)
    np.testing.assert_allclose(later_output, later_viirs, rtol=0, atol=1e-6)

    manifest = json.loads((output_dir / "harmonization_manifest.json").read_text(encoding="utf-8"))
    assert manifest["method"] == "overlap_period_polynomial_calibration"
    assert manifest["historical_years"] == [2000]
    assert manifest["observed_viirs_years"] == [2001, 2002]
    assert (output_dir / "annual_statistics.csv").is_file()


def test_missing_input_is_reported_without_writing_outputs(tmp_path, monkeypatch):
    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(
        "tools.NTL_cross_sensor_harmonization.storage_manager.resolve_input_path",
        lambda _: str(tmp_path / "missing"),
    )
    monkeypatch.setattr(
        "tools.NTL_cross_sensor_harmonization.storage_manager.resolve_output_path",
        lambda _: str(output_dir),
    )

    result = dmsp_viirs_harmonization_tool.invoke(
        {
            "dmsp_folder": "missing",
            "viirs_folder": "missing",
            "output_folder": "dmsp_viirs_first_version",
            "start_year": 2000,
            "overlap_year": 2001,
            "end_year": 2002,
        }
    )

    assert result["status"] == "error"
    assert result["error_type"] == "FileNotFoundError"
    assert "Input folder not found" in result["message"]
    assert not output_dir.exists()
