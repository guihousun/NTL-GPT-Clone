from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError
import pytest

import orchestration.contract_tools as contract_tools
from contracts.agent_packages import EventContext, EvidenceReport
from orchestration.artifact_runtime import (
    bind_artifact_scope,
    strip_model_facing_local_artifact_identity,
)
from storage_manager import current_thread_id, storage_manager


NOW = datetime(2026, 8, 13, 4, 21, 48, tzinfo=timezone.utc)


@pytest.fixture()
def artifact_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base_dir = tmp_path / "user_data"
    shared_dir = tmp_path / "base_data"
    base_dir.mkdir()
    shared_dir.mkdir()
    monkeypatch.setattr(storage_manager, "base_dir", base_dir)
    monkeypatch.setattr(storage_manager, "shared_dir", shared_dir)
    token = current_thread_id.set("artifact-thread")
    try:
        yield storage_manager.get_workspace("artifact-thread")
    finally:
        current_thread_id.reset(token)


def _config(
    *,
    thread_id: str = "artifact-thread",
    run_id: str = "runtime-run",
    task_id: str = "runtime-case",
) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "task_run_id": run_id,
            "case_id": task_id,
            "task_submitted_at": NOW.isoformat(),
        },
    }


def _event_draft(*, source_policy: dict) -> dict:
    return {
        "schema_version": "ntl.contract.v1",
        "artifact_type": "EventContext",
        "artifact_id": "event-artifact-identity",
        "producer": "NTL_Event_Tracker",
        "as_of_utc": NOW.isoformat(),
        "status": "ready",
        "retrieval_executed_at_utc": NOW.isoformat(),
        "source_policy": source_policy,
        "sources": [{"url": "https://example.test/event"}],
        "non_attribution_boundary": "Event evidence does not prove impact or causality.",
    }


def _report_draft(*, artifact: dict) -> dict:
    return {
        "schema_version": "ntl.contract.v1",
        "artifact_type": "EvidenceReport",
        "artifact_id": "report-artifact-identity",
        "producer": "NTL_Engineer",
        "status": "ready",
        "final_status": "completed",
        "direct_answer": "The local artifact was produced and verified.",
        "representative_artifacts": [artifact],
    }


def _persisted_contract(workspace: Path, stem: str, artifact_id: str) -> Path:
    path = (
        workspace
        / "outputs"
        / "runs"
        / "runtime-run"
        / "contracts"
        / f"{stem}__{artifact_id}.json"
    )
    assert path.is_file()
    return path


def test_staged_input_identity_is_injected_and_hidden_from_model_view(
    artifact_workspace: Path,
) -> None:
    staged = artifact_workspace / "inputs" / "event" / "source.json"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b'{"source":"trusted"}')
    digest = hashlib.sha256(staged.read_bytes()).hexdigest()
    registry = [
        {
            "relative_path": "inputs/event/source.json",
            "sha256": digest,
            "bytes": staged.stat().st_size,
        }
    ]
    config = _config()
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=registry,
    ):
        result = contract_tools.save_event_context_tool.invoke(
            {
                "contract": _event_draft(
                    source_policy={
                        "snapshot": {
                            "path": "inputs/event/source.json",
                            "role": "official_source_snapshot",
                        }
                    }
                )
            },
            config=config,
        )
        assert result["status"] == "success"
        checked = contract_tools.validate_contract_tool.invoke(
            {"contract_path": result["path"], "expected_artifact_type": "EventContext"},
            config=config,
        )

    raw = json.loads(
        _persisted_contract(
            artifact_workspace, "event_context", "event-artifact-identity"
        ).read_text(encoding="utf-8")
    )
    snapshot = raw["source_policy"]["snapshot"]
    assert snapshot["sha256"] == digest
    assert snapshot["bytes"] == staged.stat().st_size
    public_snapshot = checked["contract"]["source_policy"]["snapshot"]
    assert {"sha256", "bytes"}.isdisjoint(public_snapshot)


def test_output_identity_is_computed_inside_bound_workspace(
    artifact_workspace: Path,
) -> None:
    output = artifact_workspace / "outputs" / "event" / "timeline.json"
    output.parent.mkdir(parents=True)
    output.write_bytes(b'{"timeline":[]}')
    config = _config()
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=[],
    ):
        result = contract_tools.save_evidence_report_tool.invoke(
            {
                "contract": _report_draft(
                    artifact={
                        "path": "outputs/event/timeline.json",
                        "media_type": "application/json",
                        "role": "normalized_timeline",
                    }
                )
            },
            config=config,
        )
    assert result["status"] == "success"
    report = EvidenceReport.model_validate_json(
        _persisted_contract(
            artifact_workspace, "evidence_report", "report-artifact-identity"
        ).read_text(encoding="utf-8")
    )
    assert report.representative_artifacts[0].sha256 == hashlib.sha256(
        output.read_bytes()
    ).hexdigest()
    assert report.representative_artifacts[0].bytes == output.stat().st_size


@pytest.mark.parametrize(
    "supplied",
    [
        {"sha256": None, "bytes": None},
        {"sha256": "0" * 64, "bytes": 0},
    ],
)
def test_model_supplied_local_identity_is_rejected_even_when_null(
    artifact_workspace: Path,
    supplied: dict,
) -> None:
    staged = artifact_workspace / "inputs" / "event" / "source.json"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"trusted")
    registry = [
        {
            "relative_path": "inputs/event/source.json",
            "sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
            "bytes": staged.stat().st_size,
        }
    ]
    config = _config()
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=registry,
    ):
        result = contract_tools.save_event_context(
            _event_draft(
                source_policy={
                    "snapshot": {
                        "path": "inputs/event/source.json",
                        "role": "official_source_snapshot",
                        **supplied,
                    }
                }
            ),
            config=config,
        )
    assert result["status"] == "failed"
    assert not (artifact_workspace / "outputs" / "runs" / "runtime-run").exists()


def test_package_shaped_free_dict_cannot_bypass_local_identity_binding(
    artifact_workspace: Path,
) -> None:
    staged = artifact_workspace / "inputs" / "event" / "source.json"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"trusted")
    registry = [
        {
            "relative_path": "inputs/event/source.json",
            "sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
            "bytes": staged.stat().st_size,
        }
    ]
    package_shaped_local = {
        "artifact_id": "forged-local-package",
        "artifact_type": "EventContext",
        "path": "inputs/event/source.json",
        "sha256": "0" * 64,
        "bytes": 0,
        "role": "official_source_snapshot",
    }
    config = _config()
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=registry,
    ):
        result = contract_tools.save_event_context_tool.invoke(
            {
                "contract": _event_draft(
                    source_policy={"snapshot": package_shaped_local}
                )
            },
            config=config,
        )

    assert result["status"] == "failed"
    assert not (artifact_workspace / "outputs" / "runs" / "runtime-run").exists()
    public = strip_model_facing_local_artifact_identity(
        {"source_policy": {"snapshot": package_shaped_local}}
    )
    assert {"sha256", "bytes"}.isdisjoint(
        public["source_policy"]["snapshot"]
    )


def test_typed_artifact_draft_schema_rejects_model_identity_fields() -> None:
    schema = convert_to_openai_tool(contract_tools.save_evidence_report_tool)["function"][
        "parameters"
    ]
    artifact_schema = schema["properties"]["contract"]["properties"][
        "representative_artifacts"
    ]
    properties = artifact_schema["items"]["properties"]
    assert {"sha256", "bytes"}.isdisjoint(properties)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract_tools.save_evidence_report_tool.args_schema.model_validate(
            {
                "contract": _report_draft(
                    artifact={
                        "path": "outputs/event/timeline.json",
                        "sha256": None,
                        "bytes": None,
                    }
                )
            }
        )


def test_staged_input_registry_cannot_be_reused_across_run_or_case_scope(
    artifact_workspace: Path,
) -> None:
    staged = artifact_workspace / "inputs" / "event" / "source.json"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"trusted")
    registry = [
        {
            "relative_path": "inputs/event/source.json",
            "sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
            "bytes": staged.stat().st_size,
        }
    ]
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=registry,
    ):
        wrong_run = contract_tools.save_event_context(
            _event_draft(
                source_policy={"snapshot": {"path": "inputs/event/source.json"}}
            ),
            config=_config(run_id="different-run"),
        )
        wrong_case = contract_tools.save_event_context(
            _event_draft(
                source_policy={"snapshot": {"path": "inputs/event/source.json"}}
            ),
            config=_config(task_id="different-case"),
        )
    assert wrong_run["status"] == "failed"
    assert wrong_case["status"] == "failed"


def test_unknown_staged_input_and_missing_output_paths_fail_closed(
    artifact_workspace: Path,
) -> None:
    config = _config()
    with bind_artifact_scope(
        thread_id="artifact-thread",
        run_id="runtime-run",
        task_id="runtime-case",
        workspace=artifact_workspace,
        staged_inputs=[],
    ):
        unknown_input = contract_tools.save_event_context(
            _event_draft(
                source_policy={"snapshot": {"path": "inputs/event/unknown.json"}}
            ),
            config=config,
        )
        missing_output = contract_tools.save_evidence_report(
            _report_draft(
                artifact={"path": "outputs/event/missing.json", "role": "missing"}
            ),
            config=config,
        )
    assert unknown_input["status"] == "failed"
    assert missing_output["status"] == "failed"


def test_opaque_package_binding_is_not_reinterpreted_as_local_artifact(
    artifact_workspace: Path,
) -> None:
    del artifact_workspace
    config = _config()
    opaque = {
        "artifact_id": "event-package",
        "artifact_type": "EventContext",
        "path": "package/0123456789abcdef0123456789abcdef",
        "sha256": "a" * 64,
        "bytes": 123,
        "role": "event_context_package",
    }
    hydrated = contract_tools._hydrate_contract_identity(
        _report_draft(artifact=opaque),
        config,
    )
    assert hydrated["representative_artifacts"][0] == opaque
