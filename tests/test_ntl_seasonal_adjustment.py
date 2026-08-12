from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from tools import VNP46A2_seasonal_adjustment_tool
from tools import _EXPORTS, _GROUPS
from tools.NTL_seasonal_adjustment import _adjust_frame, run_vnp46a2_seasonal_adjustment


def _synthetic_daily_series() -> pd.DataFrame:
    dates = pd.date_range("2019-01-01", "2024-12-31", freq="D")
    t = np.arange(len(dates), dtype=float)
    seasonal = 8.0 * np.cos(2 * np.pi * t / 365.25) + 3.0 * np.sin(2 * np.pi * t / 365.25)
    trend = 100.0 + 0.01 * t
    noise = 0.05 * np.sin(2 * np.pi * t / 17.0)
    frame = pd.DataFrame(
        {
            "date": dates,
            "antl": trend + seasonal + noise,
            "Mandatory_Quality_Flag": 0,
            "QF_Cloud_Mask": 0,
            "Snow_Flag": 0,
        }
    )
    frame.loc[frame["date"] == "2021-03-01", "Mandatory_Quality_Flag"] = 1
    frame.loc[frame["date"] == "2024-05-05", "antl"] += 80.0
    return frame[frame["date"] != "2020-06-01"].reset_index(drop=True)


def test_tool_is_registered_with_expected_contract():
    name = "VNP46A2_seasonal_adjustment_tool"
    assert name in _EXPORTS
    assert name in _GROUPS["analyst_tools"]
    assert name in _GROUPS["specialized_tool_catalog"]
    assert VNP46A2_seasonal_adjustment_tool.name == name
    assert "365.25" in VNP46A2_seasonal_adjustment_tool.description
    assert "viewing-angle correction" in VNP46A2_seasonal_adjustment_tool.description


def test_harmonic_adjustment_handles_gap_quality_and_outlier():
    source = _synthetic_daily_series()
    output, metadata = _adjust_frame(
        source,
        date_column="date",
        value_column="antl",
        fit_start_date="2019-01-01",
        fit_end_date="2023-12-31",
        output_start_date="2024-01-01",
        output_end_date="2024-12-31",
        period_days=365.25,
        outlier_threshold=3.0,
        min_valid_days=730,
        fill_missing=True,
    )

    assert len(output) == 366
    assert output["date"].min() == pd.Timestamp("2024-01-01")
    assert output["date"].max() == pd.Timestamp("2024-12-31")
    assert int(output["is_missing_date"].sum()) == 0
    assert metadata["reference_valid_count"] > 1800
    assert metadata["output_outlier_count"] == 1

    outlier = output.loc[output["date"] == pd.Timestamp("2024-05-05")].iloc[0]
    assert bool(outlier["is_outlier"])
    assert bool(outlier["is_filled"])
    assert abs(float(outlier["adjusted_antl"]) - float(outlier["trend"])) < 1e-9

    # The quality-invalid reference date is excluded from fitting.
    quality_output, _ = _adjust_frame(
        source,
        date_column="date",
        value_column="antl",
        fit_start_date="2019-01-01",
        fit_end_date="2023-12-31",
        output_start_date="2021-03-01",
        output_end_date="2021-03-01",
        period_days=365.25,
        outlier_threshold=3.0,
        min_valid_days=730,
        fill_missing=True,
    )
    quality_invalid = quality_output.iloc[0]
    assert not bool(quality_invalid["is_quality_valid"])
    assert bool(quality_invalid["is_filled"])

    # The missing 2020-06-01 row is created by the complete daily calendar.
    gap_output, _ = _adjust_frame(
        source,
        date_column="date",
        value_column="antl",
        fit_start_date="2019-01-01",
        fit_end_date="2023-12-31",
        output_start_date="2020-05-31",
        output_end_date="2020-06-02",
        period_days=365.25,
        outlier_threshold=3.0,
        min_valid_days=730,
        fill_missing=True,
    )
    gap_row = gap_output.loc[gap_output["date"] == pd.Timestamp("2020-06-01")].iloc[0]
    assert bool(gap_row["is_missing_date"])
    assert not bool(gap_row["is_quality_valid"])
    assert bool(gap_row["is_filled"])


def test_public_tool_writes_csv_and_metadata(tmp_path, monkeypatch):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    _synthetic_daily_series().to_csv(input_path, index=False)
    # The tool wrapper is exercised without sending this deterministic unit test to LangSmith.
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setattr(
        "tools.NTL_seasonal_adjustment.storage_manager.resolve_input_path",
        lambda _: str(input_path),
    )
    monkeypatch.setattr(
        "tools.NTL_seasonal_adjustment.storage_manager.resolve_output_path",
        lambda _: str(output_path),
    )

    result = VNP46A2_seasonal_adjustment_tool.invoke(
        {
            "input_csv_path": "inputs/input.csv",
            "output_csv_path": "outputs/output.csv",
            "fit_start_date": "2019-01-01",
            "fit_end_date": "2023-12-31",
            "output_start_date": "2024-01-01",
            "output_end_date": "2024-12-31",
        }
    )
    assert result["status"] == "success"
    assert result["reference_doi"] == "https://doi.org/10.1016/j.rse.2022.113269"
    assert output_path.is_file()
    assert output_path.with_suffix(".json").is_file()
    checked = pd.read_csv(output_path)
    assert len(checked) == 366
    assert {"seasonal_component", "trend", "adjusted_antl", "is_outlier", "is_filled"} <= set(checked.columns)


def test_q20_fixture_reviews_public_tool(tmp_path, monkeypatch):
    """The checked-in Q20 fixture exercises the public tool contract end to end."""
    fixture_path = Path(__file__).parents[1] / "example" / "Q20" / "inputs" / "vnp46a2_seasonal_fixture.csv"
    output_path = tmp_path / "q20_adjusted.csv"
    monkeypatch.setattr(
        "tools.NTL_seasonal_adjustment.storage_manager.resolve_input_path",
        lambda _: str(fixture_path),
    )
    monkeypatch.setattr(
        "tools.NTL_seasonal_adjustment.storage_manager.resolve_output_path",
        lambda _: str(output_path),
    )

    result = run_vnp46a2_seasonal_adjustment(
        "inputs/vnp46a2_seasonal_fixture.csv",
        "outputs/q20_adjusted.csv",
        fit_start_date="2019-01-01",
        fit_end_date="2023-12-31",
        output_start_date="2024-01-01",
        output_end_date="2024-12-31",
    )
    assert result["status"] == "success"
    assert output_path.is_file()
    assert output_path.with_suffix(".json").is_file()

    checked = pd.read_csv(output_path, parse_dates=["date"])
    assert len(checked) == 366
    assert checked["date"].is_unique
    assert checked["date"].min() == pd.Timestamp("2024-01-01")
    assert checked["date"].max() == pd.Timestamp("2024-12-31")

    spike = checked.loc[checked["date"] == "2024-05-05"].iloc[0]
    assert bool(spike["is_outlier"])
    assert bool(spike["is_filled"])

    missing = checked.loc[checked["date"] == "2024-06-01"].iloc[0]
    assert bool(missing["is_missing_date"])
    assert not bool(missing["is_quality_valid"])
    assert bool(missing["is_filled"])

    low_quality = checked.loc[checked["date"] == "2024-08-01"].iloc[0]
    assert not bool(low_quality["is_quality_valid"])
    assert bool(low_quality["is_filled"])
