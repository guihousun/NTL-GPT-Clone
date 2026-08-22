from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from tools import _EXPORTS, _GROUPS
from tools.VNP46A2_persistence import (
    CLASS_BACKGROUND,
    CLASS_PERSISTENT,
    CLASS_TRANSIENT,
    CLASS_UNCERTAIN,
    OUTPUT_NODATA,
    RULE_ID,
    VNP46A2_persistence_classification_tool,
    classify_persistence_files,
    classify_vnp46a2_persistence,
)


def _write_stack(
    path: Path,
    data: np.ndarray,
    *,
    nodata: float,
    transform=None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=str(data.dtype),
        crs="EPSG:4326",
        transform=transform or from_origin(120.0, 32.0, 0.01, 0.01),
        nodata=nodata,
    ) as destination:
        destination.write(data)


def _stacks(valid_counts: list[int], lit_counts: list[int]) -> tuple[np.ndarray, np.ndarray]:
    radiance = np.full((30, 1, len(valid_counts)), -9999.0, dtype=np.float32)
    qa = np.zeros((30, 1, len(valid_counts)), dtype=np.uint8)
    for column, (valid_count, lit_count) in enumerate(zip(valid_counts, lit_counts, strict=True)):
        qa[:valid_count, 0, column] = 1
        radiance[:valid_count, 0, column] = 0.0
        radiance[:lit_count, 0, column] = 1.0
    return radiance, qa


def test_fixed_rule_classifies_all_classes_and_writes_auditable_outputs(tmp_path):
    radiance, qa = _stacks([30, 24, 30, 23], [24, 23, 0, 23])
    radiance_path = tmp_path / "radiance.tif"
    qa_path = tmp_path / "qa.tif"
    _write_stack(radiance_path, radiance, nodata=-9999.0)
    _write_stack(qa_path, qa, nodata=255)

    lit_path = tmp_path / "lit.tif"
    class_path = tmp_path / "class.tif"
    uncertainty_path = tmp_path / "uncertainty.tif"
    summary_path = tmp_path / "summary.json"
    result = classify_persistence_files(
        radiance_path,
        qa_path,
        lit_path,
        class_path,
        uncertainty_path,
        summary_path,
    )

    assert result["status"] == "success"
    assert result["rule"]["id"] == RULE_ID
    assert result["rule"]["adaptive_threshold"] is False
    assert result["counts"]["class_pixels"] == {
        "background": 1,
        "transient": 1,
        "persistent": 1,
        "uncertain": 1,
    }
    with rasterio.open(lit_path) as source:
        assert source.nodata == OUTPUT_NODATA
        assert source.read(1).tolist() == [[24, 23, 0, 23]]
    with rasterio.open(class_path) as source:
        assert source.read(1).tolist() == [[
            CLASS_PERSISTENT,
            CLASS_TRANSIENT,
            CLASS_BACKGROUND,
            CLASS_UNCERTAIN,
        ]]
        assert source.tags()["adaptive_threshold"] == "false"
    with rasterio.open(uncertainty_path) as source:
        assert source.read(1).tolist() == [[0, 0, 0, 1]]
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert persisted["inputs"]["radiance"]["sha256"]
    assert persisted["outputs"]["class"]["sha256"]


def test_qa_and_radiance_validity_both_gate_observations(tmp_path):
    radiance, qa = _stacks([30], [30])
    qa[0, 0, 0] = 0
    radiance[1, 0, 0] = -9999.0
    radiance_path = tmp_path / "radiance.tif"
    qa_path = tmp_path / "qa.tif"
    _write_stack(radiance_path, radiance, nodata=-9999.0)
    _write_stack(qa_path, qa, nodata=255)

    result = classify_persistence_files(
        radiance_path,
        qa_path,
        tmp_path / "lit.tif",
        tmp_path / "class.tif",
        tmp_path / "uncertainty.tif",
        tmp_path / "summary.json",
    )
    assert result["counts"]["valid_observation_count_min"] == 28
    assert result["counts"]["illuminated_night_count_min"] == 28
    assert result["counts"]["class_pixels"]["persistent"] == 1


def test_tool_fails_closed_when_stack_does_not_have_exactly_30_nights(tmp_path, monkeypatch):
    radiance = np.ones((29, 1, 1), dtype=np.float32)
    qa = np.ones((29, 1, 1), dtype=np.uint8)
    radiance_path = tmp_path / "inputs" / "radiance.tif"
    qa_path = tmp_path / "inputs" / "qa.tif"
    _write_stack(radiance_path, radiance, nodata=-9999.0)
    _write_stack(qa_path, qa, nodata=255)

    inputs = {"radiance.tif": radiance_path, "qa.tif": qa_path}
    monkeypatch.setattr(
        "tools.VNP46A2_persistence.storage_manager.resolve_input_path",
        lambda value, _thread=None: str(inputs[Path(value).name]),
    )
    monkeypatch.setattr(
        "tools.VNP46A2_persistence.storage_manager.resolve_output_path",
        lambda value, _thread=None: str(tmp_path / "outputs" / Path(value).name),
    )
    result = classify_vnp46a2_persistence("radiance.tif", "qa.tif")
    assert result["status"] == "error"
    assert "exactly 30 bands/nights" in result["message"]


def test_structured_tool_uses_confirmed_public_name():
    assert VNP46A2_persistence_classification_tool.name == "VNP46A2_persistence_classification_tool"
    assert "without an adaptive threshold" in VNP46A2_persistence_classification_tool.description
    assert _EXPORTS["VNP46A2_persistence_classification_tool"] == (
        ".VNP46A2_persistence",
        "VNP46A2_persistence_classification_tool",
    )
    assert "VNP46A2_persistence_classification_tool" in _GROUPS["Engineer_tools"]
    assert "VNP46A2_persistence_classification_tool" in _GROUPS["specialized_tool_catalog"]
