from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
import numpy as np
from pydantic import ValidationError
import pytest
import rasterio
from rasterio.transform import from_origin

import orchestration.contract_tools as contract_tools
import orchestration.observation_runtime as observation_runtime
from contracts.agent_packages import ObservationPackage
from storage_manager import current_thread_id, storage_manager


UTC = timezone.utc
SUBMITTED = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
COMPLETED = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)


def _config(
    *,
    thread_id: str = "observation-thread",
    run_id: str = "observation-run",
    case_id: str = "observation-case",
    submitted_at: datetime = SUBMITTED,
) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "task_run_id": run_id,
            "case_id": case_id,
            "task_submitted_at": submitted_at.isoformat(),
        },
    }


def _draft(artifact_id: str = "observation-system-time") -> dict:
    return {
        "artifact_id": artifact_id,
        "as_of_utc": SUBMITTED.isoformat(),
        "status": "ready",
        "product": {"collection_id": "staged/synthetic-ntl"},
        "validation": {"status": "passed"},
    }


@pytest.fixture(autouse=True)
def _isolated_observation_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base_dir = tmp_path / "user_data"
    shared_dir = tmp_path / "base_data"
    base_dir.mkdir()
    shared_dir.mkdir()
    monkeypatch.setattr(storage_manager, "base_dir", base_dir)
    monkeypatch.setattr(storage_manager, "shared_dir", shared_dir)
    monkeypatch.setattr(observation_runtime, "_utc_now", lambda: COMPLETED)
    observation_runtime.clear_observation_evidence_for_tests()
    token = current_thread_id.set("observation-thread")
    try:
        yield
    finally:
        current_thread_id.reset(token)
        observation_runtime.clear_observation_evidence_for_tests()


def _inspector_module():
    return importlib.import_module("tools.geodata_inspector_tool")


def _persisted_observation(*, run_id: str, artifact_id: str) -> ObservationPackage:
    root = storage_manager.get_workspace("observation-thread")
    matches = list(
        (root / "outputs" / "runs" / run_id / "contracts").glob(
            f"observation_package__{artifact_id}.json"
        )
    )
    assert len(matches) == 1
    return ObservationPackage.model_validate_json(matches[0].read_text(encoding="utf-8"))


def _stage_raster(
    *,
    thread_id: str = "observation-thread",
    filename: str = "synthetic_ntl.tif",
) -> str:
    path = storage_manager.get_workspace(thread_id) / "inputs" / filename
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.array([[1.0, 2.0], [3.0, -9999.0]], dtype="float32"), 1)
    return filename


def test_observation_schema_hides_query_time_and_runtime_overwrites_direct_value() -> None:
    inspector = _inspector_module()
    config = _config()
    raster_name = _stage_raster()
    report = inspector.geodata_inspector_tool.invoke(
        {"mode": "full", "raster_paths": [raster_name]}, config=config
    )
    assert '"mode": "full"' in report

    schema = convert_to_openai_tool(contract_tools.save_observation_package_tool)["function"][
        "parameters"
    ]
    encoded_properties = schema["properties"]["contract"]["properties"]
    assert "query_executed_at_utc" not in encoded_properties
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract_tools.save_observation_package_tool.args_schema.model_validate(
            {
                "contract": {
                    **_draft(),
                    "query_executed_at_utc": "2099-01-01T00:00:00Z",
                }
            }
        )

    # Even a trusted Python caller bypassing the draft schema cannot select the
    # timestamp: the system consumes the full-inspector completion time.
    result = contract_tools.save_observation_package(
        {
            **_draft(),
            "query_executed_at_utc": "2099-01-01T00:00:00Z",
            "validation": {
                "status": "passed",
                "query_executed_at_utc": "2098-01-01T00:00:00Z",
            },
        },
        config=config,
    )
    assert result["status"] == "success"
    persisted = _persisted_observation(
        run_id="observation-run",
        artifact_id="observation-system-time",
    )
    assert persisted.query_executed_at_utc == COMPLETED
    assert "2098-01-01" not in persisted.model_dump_json()
    assert "2099-01-01" not in persisted.model_dump_json()


def test_quick_check_cannot_authorize_full_package_and_full_evidence_is_one_shot() -> None:
    inspector = _inspector_module()
    config = _config()
    raster_name = _stage_raster()
    inspector.geodata_quick_check_tool.invoke(
        {"raster_paths": [raster_name]}, config=config
    )
    quick_only = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("quick-only")},
        config=config,
    )
    assert quick_only["status"] == "failed"

    inspector.geodata_inspector_tool.invoke(
        {"mode": "full", "raster_paths": [raster_name]}, config=config
    )
    accepted = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("full-once")},
        config=config,
    )
    assert accepted["status"] == "success"
    reused = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("full-reused")},
        config=config,
    )
    assert reused["status"] == "failed"


def test_invalid_save_restores_evidence_for_one_corrected_retry() -> None:
    inspector = _inspector_module()
    config = _config()
    raster_name = _stage_raster()
    inspector.geodata_inspector_tool.invoke(
        {"mode": "full", "raster_paths": [raster_name]}, config=config
    )

    invalid = _draft("repairable-observation")
    invalid["validation"] = {}
    first = contract_tools.save_observation_package_tool.invoke(
        {"contract": invalid}, config=config
    )
    assert first["status"] == "failed"

    corrected = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("repairable-observation")}, config=config
    )
    assert corrected["status"] == "success"
    third = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("evidence-already-finalized")}, config=config
    )
    assert third["status"] == "failed"


def test_full_inspector_evidence_is_thread_task_and_submission_scoped() -> None:
    inspector = _inspector_module()
    original = _config()
    raster_name = _stage_raster()
    inspector.geodata_inspector_tool.invoke(
        {"mode": "full", "raster_paths": [raster_name]}, config=original
    )

    other_thread = _config(thread_id="other-thread")
    assert contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("other-thread")}, config=other_thread
    )["status"] == "failed"

    newer_submission = _config(submitted_at=datetime(2026, 8, 12, 9, 15, tzinfo=UTC))
    assert contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("newer-submission")}, config=newer_submission
    )["status"] == "failed"

    # Failed mismatched attempts do not steal the correctly scoped record.
    assert contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("original-scope")}, config=original
    )["status"] == "success"


def test_inspector_exception_records_no_success_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    inspector = _inspector_module()
    config = _config()
    raster_name = _stage_raster()

    def _fail(**_kwargs):
        raise RuntimeError("synthetic inspector failure")

    monkeypatch.setattr(inspector, "_inspect_geospatial_assets_core", _fail)
    with pytest.raises(RuntimeError, match="synthetic inspector failure"):
        inspector.geodata_inspector_tool.invoke(
            {"mode": "full", "raster_paths": [raster_name]}, config=config
        )
    result = contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("after-error")},
        config=config,
    )
    assert result["status"] == "failed"


@pytest.mark.parametrize(
    "tool_args",
    [
        {"mode": "full"},
        {"mode": "full", "raster_paths": ["missing.tif"]},
    ],
)
def test_empty_or_failed_full_report_does_not_authorize_package(tool_args: dict) -> None:
    inspector = _inspector_module()
    config = _config()
    inspector.geodata_inspector_tool.invoke(tool_args, config=config)
    assert contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft("invalid-inspection")}, config=config
    )["status"] == "failed"


@pytest.mark.parametrize("missing_key", ["task_run_id", "case_id", "task_submitted_at"])
def test_incomplete_benchmark_scope_does_not_record_authorizing_evidence(
    missing_key: str,
) -> None:
    inspector = _inspector_module()
    raster_name = _stage_raster()
    config = _config()
    del config["metadata"][missing_key]
    inspector.geodata_inspector_tool.invoke(
        {"mode": "full", "raster_paths": [raster_name]}, config=config
    )
    assert contract_tools.save_observation_package_tool.invoke(
        {"contract": _draft(f"missing-{missing_key}")}, config=config
    )["status"] == "failed"


def test_observation_evidence_registry_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observation_runtime, "_EVIDENCE_LIMIT", 3)
    started = observation_runtime.observation_tool_started_at()
    for index in range(5):
        observation_runtime.record_observation_tool_success(
            tool_name="geodata_inspector_tool",
            mode="full",
            started_at_utc=started,
            config=_config(
                thread_id=f"thread-{index}",
                run_id=f"run-{index}",
                case_id=f"case-{index}",
            ),
        )
    assert len(observation_runtime._EVIDENCE) == 3
