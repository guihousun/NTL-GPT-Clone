from __future__ import annotations

from pathlib import Path

import pytest

from tools import VNP46A2_angular_correction_tool, _EXPORTS, _GROUPS
from tools.VNP46A2_angular_correction import (
    STATISTICS_BATCH_SIZE,
    _qa_rule,
    _statistics_batch_ranges,
    _validate_dates,
    run_vnp46a2_angular_correction,
)


def test_angular_tool_is_registered_in_independent_module():
    assert _EXPORTS["VNP46A2_angular_correction_tool"] == (
        ".VNP46A2_angular_correction",
        "VNP46A2_angular_correction_tool",
    )
    assert "VNP46A2_angular_correction_tool" in _GROUPS["Engineer_tools"]
    assert "VNP46A2_angular_correction_tool" in _GROUPS["specialized_tool_catalog"]
    assert VNP46A2_angular_correction_tool.name == "VNP46A2_angular_correction_tool"
    assert "entirely in Google Earth Engine" in VNP46A2_angular_correction_tool.description


def test_fixed_contract_and_qa_rule_are_explicit():
    rule = _qa_rule()
    assert rule["radiance_band"] == "DNB_BRDF_Corrected_NTL"
    assert rule["use_gap_filled_band"] is False
    assert rule["Mandatory_Quality_Flag"] == [0, 1]
    assert rule["QF_Cloud_Mask_bits_4_5_minimum_quality"] == 2
    assert rule["QF_Cloud_Mask_bits_6_7_allowed_cloud_classes"] == [0, 1]
    assert rule["Snow_Flag"] == 0
    _validate_dates("2024-01-01", "2025-01-01", "2024-01-01")
    with pytest.raises(ValueError, match="later"):
        _validate_dates("2024-01-01", "2024-01-01", "2024-01-01")
    with pytest.raises(ValueError, match="on or before"):
        _validate_dates("2024-01-01", "2025-01-01", "2024-01-02")


def test_module_has_no_interactive_auth_or_local_raster_download():
    source = Path(__file__).parents[1].joinpath("tools", "VNP46A2_angular_correction.py").read_text(
        encoding="utf-8"
    )
    assert "ee.Authenticate" not in source
    assert "geemap" not in source
    assert "ee_export_image" not in source
    assert "ee_export_image_collection" not in source
    assert "Export.image.toAsset" in source


def test_daily_statistics_are_split_into_small_batches():
    assert STATISTICS_BATCH_SIZE == 8
    ranges = _statistics_batch_ranges(366)
    assert ranges[0] == (0, 8)
    assert ranges[-1] == (360, 6)
    assert sum(count for _offset, count in ranges) == 366
    assert max(count for _offset, count in ranges) <= 8
    with pytest.raises(ValueError, match="positive"):
        _statistics_batch_ranges(10, 0)


def test_initialization_failure_writes_fail_closed_metadata(tmp_path, monkeypatch):
    metadata_path = tmp_path / "angular.metadata.json"
    statistics_path = tmp_path / "daily.csv"
    monkeypatch.setattr(
        "tools.VNP46A2_angular_correction.storage_manager.resolve_output_path",
        lambda value, _thread=None: str(metadata_path if value.endswith("json") else statistics_path),
    )
    monkeypatch.setattr(
        "tools.VNP46A2_angular_correction._load_ee",
        lambda _project: (_ for _ in ()).throw(RuntimeError("no Earth Engine credentials")),
    )
    result = run_vnp46a2_angular_correction(
        output_asset_id="projects/example/assets/q19_output",
        wait_for_completion=False,
    )
    assert result["status"] == "error"
    assert result["error_type"] == "RuntimeError"
    assert result["local_raster_download_performed"] is False
    assert metadata_path.is_file()
