from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from scipy.stats import kendalltau, theilslopes
from shapely.geometry import box

from storage_manager import current_thread_id, storage_manager
from tools.NTL_anomaly_detection_tool import _detect_ntl_anomaly_with_optional_aoi
from tools.NTL_trend_detection_tool import analyze_ntl_trend_masked_logic


def _write_raster(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0.0, float(values.shape[0]), 1.0, 1.0),
        nodata=None,
    ) as destination:
        destination.write(values.astype(np.float32), 1)


def _configure_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, thread_id: str) -> Path:
    monkeypatch.setattr(storage_manager, "base_dir", tmp_path)
    return tmp_path / thread_id


def test_anomaly_tool_uses_population_sd_strict_threshold_common_support_and_aoi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reusable anomaly tool must encode the BV1-052 statistical contract."""

    thread_id = "time-series-anomaly-contract"
    workspace = _configure_workspace(tmp_path, monkeypatch, thread_id)
    token = current_thread_id.set(thread_id)
    try:
        inputs = workspace / "inputs"
        _write_raster(
            inputs / "year_1.tif",
            np.array([[1.0, 5.0, 1.0], [1.0, 2.0, 1.0]], dtype=np.float32),
        )
        _write_raster(
            inputs / "year_2.tif",
            np.array([[2.0, 5.0, 2.0], [np.nan, 4.0, 2.0]], dtype=np.float32),
        )
        _write_raster(
            inputs / "target.tif",
            np.array([[2.6, 30.0, 3.0], [4.0, 5.0, 3.0]], dtype=np.float32),
        )
        boundary = gpd.GeoDataFrame(
            {"name": ["roi"]}, geometry=[box(0.0, 0.0, 2.0, 2.0)], crs="EPSG:4326"
        )
        boundary.to_file(inputs / "boundary.geojson", driver="GeoJSON")

        response = _detect_ntl_anomaly_with_optional_aoi(
            ["year_1.tif", "year_2.tif", "target.tif"],
            target_index=2,
            k_sigma=2.0,
            save_filename="strict_mask.tif",
            vector_file="boundary.geojson",
        )

        assert "population baseline SD (ddof=0)" in response
        assert "common-valid pixels" in response
        outputs = workspace / "outputs"
        with rasterio.open(outputs / "strict_mask.tif") as source:
            assert source.nodata == 255
            np.testing.assert_array_equal(
                source.read(1),
                np.array([[1, 0, 255], [255, 0, 255]], dtype=np.uint8),
            )

        summary = json.loads((outputs / "strict_mask_summary.json").read_text(encoding="utf-8"))
        assert summary["method"]["baseline_standard_deviation"] == "population standard deviation (ddof=0)"
        assert summary["method"]["threshold_rule"] == "positive z-score strictly greater than k_sigma"
        assert summary["common_valid_pixel_count"] == 3
        assert summary["evaluated_pixel_count"] == 3
        assert summary["nonzero_baseline_sd_pixel_count"] == 2
        assert summary["zero_baseline_sd_pixel_count"] == 1
        assert summary["positive_anomaly_pixel_count"] == 1
    finally:
        current_thread_id.reset(token)


def test_trend_wrapper_retains_theil_sen_and_kendall_tau_b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-linear/outlier series distinguishes the registered method from OLS."""

    thread_id = "time-series-trend-contract"
    workspace = _configure_workspace(tmp_path, monkeypatch, thread_id)
    token = current_thread_id.set(thread_id)
    try:
        inputs = workspace / "inputs"
        values = [0.0, 0.0, 0.0, 100.0, 1.0]
        names: list[str] = []
        for index, value in enumerate(values):
            name = f"year_{index:02d}.tif"
            names.append(name)
            _write_raster(inputs / name, np.array([[value]], dtype=np.float32))
        boundary = gpd.GeoDataFrame(
            {"name": ["roi"]}, geometry=[box(0.0, 0.0, 1.0, 1.0)], crs="EPSG:4326"
        )
        boundary.to_file(inputs / "boundary.geojson", driver="GeoJSON")

        response = analyze_ntl_trend_masked_logic(names, "boundary.geojson", "theil_sen")
        assert "Slope Map" in response
        with rasterio.open(workspace / "outputs" / "theil_sen_slope_trend.tif") as source:
            observed_slope = float(source.read(1, masked=True)[0, 0])
        with rasterio.open(workspace / "outputs" / "theil_sen_pvalue_map.tif") as source:
            observed_pvalue = float(source.read(1, masked=True)[0, 0])

        time_index = np.arange(len(values), dtype=float)
        assert observed_slope == pytest.approx(theilslopes(values, time_index).slope)
        assert observed_pvalue == pytest.approx(kendalltau(time_index, values).pvalue)
        assert observed_slope != pytest.approx(np.polyfit(time_index, values, 1)[0])
    finally:
        current_thread_id.reset(token)


def test_analyst_prompt_and_skill_preserve_time_series_method_contracts() -> None:
    from agents.NTL_Analyst import system_prompt_analyst

    repository = Path(__file__).resolve().parents[1]
    skill_text = (repository / ".ntl-gpt" / "skills" / "analyst" / "ntl-statistics-and-time-series" / "SKILL.md").read_text(encoding="utf-8")
    prompt_text = str(system_prompt_analyst.content)
    for text in (skill_text, prompt_text):
        normalized = text.lower()
        assert "ddof=0" in normalized
        assert "z > threshold" in normalized or "z > k_sigma" in normalized
        assert "common-valid" in normalized or "common valid" in normalized
        assert "theil-sen" in normalized
        assert "kendall tau-b" in normalized
        assert "ols" in normalized
        assert "matched-valid" in normalized or "matched valid" in normalized
