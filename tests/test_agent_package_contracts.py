from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError
import pytest

import orchestration.contract_tools as contract_tools
from contracts.agent_packages import (
    AgentRole,
    AnalysisPackage,
    ArtifactRecord,
    AssignmentEnvelope,
    ContractStatus,
    EngineerDecision,
    ErrorCode,
    EventContext,
    EvidenceReport,
    HandoffEnvelope,
    ObservationPackage,
    PackageRef,
    RevisionRequest,
    TaskPlan,
    canonical_json,
    contract_sha256,
)
from orchestration.contract_tools import (
    CONTRACT_TOOLS,
    record_handoff_decision,
    record_route_transition,
    save_task_plan,
    validate_contract,
)
from orchestration.observation_runtime import (
    observation_tool_started_at,
    record_observation_tool_success,
)
from orchestration.contracts_io import (
    ContractIOError,
    load_contract,
    persist_handoff_decision,
    save_contract,
    validate_contract_payload,
)
from orchestration.route_state import RouteState, RouteStateMachine, RouteStatus
from storage_manager import current_thread_id, storage_manager


UTC = timezone.utc
NOW = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
TOOL_EXECUTED_AT = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
TASK_SUBMITTED_AT = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)


@pytest.fixture()
def isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base_dir = tmp_path / "user_data"
    shared_dir = tmp_path / "base_data"
    base_dir.mkdir()
    shared_dir.mkdir()
    monkeypatch.setattr(storage_manager, "base_dir", base_dir)
    monkeypatch.setattr(storage_manager, "shared_dir", shared_dir)
    token = current_thread_id.set("contract-thread")
    try:
        yield storage_manager.get_workspace("contract-thread")
    finally:
        current_thread_id.reset(token)


def _task_plan(**updates) -> TaskPlan:
    payload = {
        "artifact_id": "plan-1",
        "run_id": "run-1",
        "task_id": "case-1",
        "created_at_utc": NOW,
        "as_of_utc": NOW,
        "status": ContractStatus.READY,
        "original_request": "Analyze a prepared raster.",
        "normalized_objective": "Analyze the prepared raster.",
        "aoi_contract": {"name": "test-aoi", "crs": "EPSG:4326"},
        "time_contract": {"as_of": "2026-08-11T08:00:00Z"},
    }
    payload.update(updates)
    return TaskPlan(**payload)


def _package_ref(result: dict) -> PackageRef:
    return PackageRef.model_validate(result["package_ref"])


def _persisted_contract_path(
    workspace: Path,
    *,
    run_id: str,
    artifact_id: str,
) -> Path:
    matches = list((workspace / "outputs" / "runs" / run_id / "contracts").glob(f"*__{artifact_id}.json"))
    assert len(matches) == 1
    return matches[0]


def test_all_five_contracts_validate_with_versioned_envelopes() -> None:
    plan = _task_plan()
    plan_ref = PackageRef(
        artifact_id=plan.artifact_id,
        artifact_type=plan.artifact_type,
        path="/data/processed/runs/run-1/contracts/task_plan__plan-1.json",
        sha256=contract_sha256(plan),
    )
    models = [
        plan,
        EventContext(
            artifact_id="event-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            retrieval_executed_at_utc=NOW,
            status=ContractStatus.READY,
            source_policy={"allowed": ["official"]},
            event={"type": "earthquake", "place": "test-aoi"},
            sources=[{"source_record_id": "source-1", "url": "https://example.test/event"}],
            non_attribution_boundary="Observed light changes are not causal proof.",
        ),
        ObservationPackage(
            artifact_id="observation-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            query_executed_at_utc=NOW,
            status=ContractStatus.READY,
            product={"collection_id": "projects/example/ntl", "band": "radiance"},
            availability={"coverage_status": "available"},
            validation={"status": "passed"},
        ),
        AnalysisPackage(
            artifact_id="analysis-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            status=ContractStatus.READY,
            linked_contracts=[plan_ref],
            scientific_question="What changed?",
            analysis_unit="AOI mean radiance",
            method={"name": "difference"},
            validation={"status": "passed"},
        ),
        EvidenceReport(
            artifact_id="report-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            status=ContractStatus.READY,
            final_status="completed",
            direct_answer="The requested workflow completed.",
            validation_summary={"status": "passed"},
        ),
    ]
    for model in models:
        restored = validate_contract_payload(json.loads(model.model_dump_json()))
        assert type(restored) is type(model)
        assert restored.schema_version == "ntl.contract.v1"


def test_task_plan_roundtrip_and_hash_are_deterministic() -> None:
    plan = _task_plan()
    restored = TaskPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert contract_sha256(restored) == contract_sha256(plan)
    assert canonical_json({"b": 1, "a": NOW}) == canonical_json({"a": NOW, "b": 1})


def test_blocked_contract_requires_error() -> None:
    with pytest.raises(ValidationError):
        EventContext(
            run_id="run-1",
            task_id="case-1",
            as_of_utc=NOW,
            retrieval_executed_at_utc=NOW,
            status=ContractStatus.BLOCKED,
            non_attribution_boundary="No causal claim.",
        )


def test_runtime_contract_rejects_evaluator_only_fields() -> None:
    payload = _task_plan().model_dump(mode="json")
    payload["budget"] = {"judge_packet": {"gold_answer": "secret"}}
    with pytest.raises(ContractIOError, match="evaluator-only"):
        validate_contract_payload(payload)


def test_path_and_identifier_traversal_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _task_plan(run_id="../escape")
    with pytest.raises(ValidationError):
        ArtifactRecord(path="../outside.txt", sha256="a" * 64, bytes=1)


def test_assignment_target_must_match_output_contract() -> None:
    with pytest.raises(ValidationError):
        AssignmentEnvelope(
            run_id="run-1",
            task_id="case-1",
            target_agent=AgentRole.ANALYST,
            objective="Prepare observations",
            required_output_type="ObservationPackage",
        )


def test_assignment_accepts_a_matching_specialist_contract() -> None:
    assignment = AssignmentEnvelope(
        run_id="run-1",
        task_id="case-1",
        target_agent=AgentRole.DATA_SEARCHER,
        objective="Prepare observations",
        required_output_type="ObservationPackage",
        accepted_parent_contracts=[
            PackageRef(
                artifact_id="plan-1",
                artifact_type="TaskPlan",
                path="/data/processed/runs/run-1/contracts/task_plan__plan-1.json",
                sha256="a" * 64,
            )
        ],
        allowed_inputs=["/data/raw/aoi.geojson", "/shared/reference.tif"],
    )
    assert assignment.source_agent == AgentRole.ENGINEER


def test_specialists_cannot_request_each_other_directly() -> None:
    with pytest.raises(ValidationError, match="specialists cannot"):
        RevisionRequest(
            run_id="run-1",
            task_id="case-1",
            source_agent=AgentRole.ANALYST,
            target_agent=AgentRole.DATA_SEARCHER,
            reason="Observation metadata is incomplete.",
            required_changes=["Add QA policy."],
            revision_number=1,
        )


def test_contract_save_is_canonical_scoped_atomic_and_immutable(isolated_workspace: Path) -> None:
    plan = _task_plan()
    result = save_contract(plan, thread_id="contract-thread")
    assert result["status"] == "success"
    assert result["path"] == "/data/processed/runs/run-1/contracts/task_plan__plan-1.json"
    path = isolated_workspace / "outputs" / "runs" / "run-1" / "contracts" / "task_plan__plan-1.json"
    assert path.read_text(encoding="utf-8") == canonical_json(plan)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == result["sha256"] == contract_sha256(plan)
    assert save_contract(plan, thread_id="contract-thread")["sha256"] == result["sha256"]
    assert not list(path.parent.glob("*.tmp"))

    changed = _task_plan(normalized_objective="A different objective.")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        save_contract(changed, thread_id="contract-thread")


def test_load_contract_is_restricted_to_current_run_tree(isolated_workspace: Path) -> None:
    result = save_contract(_task_plan(), thread_id="contract-thread")
    restored = load_contract(result["path"], thread_id="contract-thread", require_run_id="run-1")
    assert isinstance(restored, TaskPlan)
    with pytest.raises(ContractIOError, match="outputs/runs/run-2"):
        load_contract(result["path"], thread_id="contract-thread", require_run_id="run-2")
    with pytest.raises(ContractIOError):
        load_contract("/data/processed/../inputs/secret.json", thread_id="contract-thread")


def test_tool_surface_saves_and_validates_without_exposing_thread_id(isolated_workspace: Path) -> None:
    assert [tool.name for tool in CONTRACT_TOOLS] == [
        "save_task_plan",
        "save_event_context",
        "save_observation_package",
        "save_analysis_package",
        "save_evidence_report",
        "validate_contract",
        "record_handoff_decision",
        "record_route_transition",
    ]
    assert "thread_id" not in CONTRACT_TOOLS[0].args_schema.model_fields
    saved = save_task_plan(_task_plan().model_dump(mode="json"))
    assert saved["status"] == "success"
    checked = validate_contract(contract_path=saved["path"])
    assert checked["status"] == "success"
    assert checked["sha256"] == saved["sha256"]


def test_each_save_tool_exposes_its_exact_nested_contract_schema() -> None:
    expected_required = {
        "save_task_plan": {
            "status",
            "original_request",
            "normalized_objective",
        },
        "save_event_context": {
            "status",
            "retrieval_executed_at_utc",
            "non_attribution_boundary",
        },
        "save_observation_package": {
            "status",
        },
        "save_analysis_package": {
            "status",
            "scientific_question",
            "analysis_unit",
        },
        "save_evidence_report": {
            "status",
            "final_status",
            "direct_answer",
        },
    }
    expected_artifact_type = {
        "save_task_plan": "TaskPlan",
        "save_event_context": "EventContext",
        "save_observation_package": "ObservationPackage",
        "save_analysis_package": "AnalysisPackage",
        "save_evidence_report": "EvidenceReport",
    }

    save_tools = {tool.name: tool for tool in CONTRACT_TOOLS[:5]}
    assert set(save_tools) == set(expected_required)
    for name, tool in save_tools.items():
        openai_schema = convert_to_openai_tool(tool)["function"]["parameters"]
        assert openai_schema["required"] == ["contract"]
        contract_schema = openai_schema["properties"]["contract"]
        assert contract_schema["type"] == "object"
        assert contract_schema["additionalProperties"] is False
        assert "anyOf" not in contract_schema
        assert set(contract_schema["required"]) == expected_required[name]
        assert contract_schema["properties"]["artifact_type"]["const"] == expected_artifact_type[name]
        assert contract_schema["properties"]["schema_version"]["const"] == "ntl.contract.v1"
        assert "producer" in contract_schema["properties"]
        assert {"run_id", "task_id", "case_id", "created_at_utc"}.isdisjoint(
            contract_schema["properties"]
        )


def _all_schema_property_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(str(key) for key in properties)
        for nested in value.values():
            names.update(_all_schema_property_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_all_schema_property_names(nested))
    return names


def test_model_facing_contract_tools_hide_all_runtime_identity_fields() -> None:
    forbidden = {
        "run_id",
        "task_id",
        "case_id",
        "created_at_utc",
        "query_executed_at_utc",
    }
    for tool in [*CONTRACT_TOOLS[:5], CONTRACT_TOOLS[6], CONTRACT_TOOLS[7]]:
        schema = convert_to_openai_tool(tool)["function"]["parameters"]
        assert forbidden.isdisjoint(_all_schema_property_names(schema)), tool.name

    route_schema = convert_to_openai_tool(CONTRACT_TOOLS[7])["function"]["parameters"]
    assert {"target_status", "reason"}.issubset(route_schema["required"])
    assert {"run_id", "task_id"}.isdisjoint(route_schema["properties"])

    handoff_schema = convert_to_openai_tool(CONTRACT_TOOLS[6])["function"]["parameters"]
    assert handoff_schema["required"] == ["handoff", "decision"]
    validate_schema = convert_to_openai_tool(CONTRACT_TOOLS[5])["function"]["parameters"]
    assert validate_schema["required"] == ["contract_path"]
    assert "contract" not in validate_schema["properties"]
    with pytest.raises(ValidationError):
        CONTRACT_TOOLS[5].args_schema.model_validate(
            {"contract_path": "/data/processed/runs/secret/contracts/package.json"}
        )


def test_all_save_tools_accept_and_persist_their_parsed_nested_models(
    isolated_workspace: Path,
) -> None:
    models = {
        "save_task_plan": _task_plan(),
        "save_event_context": EventContext(
            artifact_id="event-tool-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            retrieval_executed_at_utc=NOW,
            status=ContractStatus.READY,
            sources=[{"source_record_id": "source-1", "url": "https://example.test/event"}],
            non_attribution_boundary="Observed light changes are not causal proof.",
        ),
        "save_observation_package": ObservationPackage(
            artifact_id="observation-tool-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            query_executed_at_utc=NOW,
            status=ContractStatus.READY,
            product={"collection_id": "projects/example/ntl"},
            validation={"status": "passed"},
        ),
        "save_analysis_package": AnalysisPackage(
            artifact_id="analysis-tool-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            status=ContractStatus.READY,
            scientific_question="What changed?",
            analysis_unit="AOI mean radiance",
        ),
        "save_evidence_report": EvidenceReport(
            artifact_id="report-tool-1",
            run_id="run-1",
            task_id="case-1",
            created_at_utc=NOW,
            as_of_utc=NOW,
            status=ContractStatus.READY,
            final_status="completed",
            direct_answer="The deterministic contract test completed.",
        ),
    }

    for tool in CONTRACT_TOOLS[:5]:
        model = models[tool.name]
        draft = model.model_dump(mode="json")
        for system_field in ("run_id", "task_id", "created_at_utc"):
            draft.pop(system_field)
        config = {
            "configurable": {"thread_id": "contract-thread"},
            "metadata": {
                "task_run_id": "run-1",
                "case_id": "case-1",
                "task_submitted_at": NOW.isoformat(),
            },
        }
        if tool.name == "save_observation_package":
            draft.pop("query_executed_at_utc")
            record_observation_tool_success(
                tool_name="geodata_inspector_tool",
                mode="full",
                started_at_utc=observation_tool_started_at(),
                config=config,
            )
        parsed = tool.args_schema.model_validate({"contract": draft})
        assert parsed.contract.__class__.__name__ == f"{model.artifact_type}Draft"
        result = tool.invoke(
            {"contract": draft},
            config=config,
        )
        assert result["status"] == "success"
        assert result["artifact_type"] == model.artifact_type
        assert result["artifact_id"] == model.artifact_id
        assert {"run_id", "task_id"}.isdisjoint(result)


def test_contract_tool_injects_runtime_identity_when_model_omits_it(
    isolated_workspace: Path,
) -> None:
    payload = _task_plan().model_dump(mode="json")
    payload.pop("run_id")
    payload.pop("task_id")
    saved = save_task_plan(
        payload,
        config={
            "configurable": {"thread_id": "contract-thread"},
            "metadata": {"task_run_id": "runtime-run", "case_id": "runtime-case"},
        },
    )
    assert {"run_id", "task_id"}.isdisjoint(saved)
    assert saved["path"].startswith("package/")
    checked = validate_contract(
        contract_path=saved["path"],
        config={"configurable": {"thread_id": "contract-thread"}},
    )
    assert checked["status"] == "success"
    assert checked["contract"]["normalized_objective"] == payload["normalized_objective"]
    assert {"run_id", "task_id", "created_at_utc"}.isdisjoint(checked["contract"])
    assert "runtime-run" not in json.dumps(checked["contract"], sort_keys=True)
    persisted = TaskPlan.model_validate_json(
        _persisted_contract_path(
            isolated_workspace,
            run_id="runtime-run",
            artifact_id="plan-1",
        ).read_text(encoding="utf-8")
    )
    assert persisted.run_id == "runtime-run"
    assert persisted.task_id == "runtime-case"


@pytest.mark.parametrize(
    ("save_name", "artifact_type", "extra"),
    [
        (
            "save_task_plan",
            "TaskPlan",
            {
                "original_request": "Use the prepared fixture.",
                "normalized_objective": "Use the prepared fixture.",
            },
        ),
        (
            "save_event_context",
            "EventContext",
            {
                "retrieval_executed_at_utc": NOW.isoformat(),
                "sources": [{"url": "https://example.test/event"}],
                "non_attribution_boundary": "Observed change is not causal proof.",
            },
        ),
        (
            "save_observation_package",
            "ObservationPackage",
            {
                "query_executed_at_utc": NOW.isoformat(),
                "product": {"collection_id": "projects/example/ntl"},
                "validation": {"status": "passed"},
            },
        ),
        (
            "save_analysis_package",
            "AnalysisPackage",
            {
                "scientific_question": "What changed?",
                "analysis_unit": "AOI mean radiance",
            },
        ),
        (
            "save_evidence_report",
            "EvidenceReport",
            {
                "final_status": "completed",
                "direct_answer": "The fixture contract completed.",
            },
        ),
    ],
)
def test_all_typed_save_tools_override_model_identity_and_creation_time_in_benchmark_runs(
    isolated_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    save_name: str,
    artifact_type: str,
    extra: dict,
) -> None:
    monkeypatch.setattr(contract_tools, "_utc_now", lambda: TOOL_EXECUTED_AT)
    payload = {
        "artifact_type": artifact_type,
        "artifact_id": f"{artifact_type.lower()}-runtime-binding",
        "run_id": "model-guessed-run",
        "task_id": "model-guessed-task",
        "created_at_utc": "2026-03-02T00:00:00Z",
        "as_of_utc": NOW.isoformat(),
        "status": "ready",
        **extra,
    }
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {
            "task_run_id": "runtime-run",
            "case_id": "runtime-case",
            "task_submitted_at": TOOL_EXECUTED_AT.isoformat(),
        },
    }
    if artifact_type == "ObservationPackage":
        record_observation_tool_success(
            tool_name="geodata_inspector_tool",
            mode="full",
            started_at_utc=observation_tool_started_at(),
            config=config,
        )

    saved = getattr(contract_tools, save_name)(payload, config=config)

    assert saved["status"] == "success"
    assert {"run_id", "task_id"}.isdisjoint(saved)
    assert saved["path"].startswith("package/")
    assert saved["package_ref"]["path"] == saved["path"] == saved["package_handle"]
    persisted = validate_contract_payload(
        json.loads(
            _persisted_contract_path(
                isolated_workspace,
                run_id="runtime-run",
                artifact_id=payload["artifact_id"],
            ).read_text(encoding="utf-8")
        ),
        expected_artifact_type=artifact_type,
    )
    assert persisted.run_id == "runtime-run"
    assert persisted.task_id == "runtime-case"
    assert persisted.created_at_utc == TOOL_EXECUTED_AT
    assert persisted.as_of_utc == NOW


def test_non_benchmark_save_tool_preserves_explicit_identity_and_creation_time(
    isolated_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_tools, "_utc_now", lambda: TOOL_EXECUTED_AT)
    saved = save_task_plan(_task_plan().model_dump(mode="json"))
    persisted = TaskPlan.model_validate_json(
        _persisted_contract_path(
            isolated_workspace,
            run_id="run-1",
            artifact_id="plan-1",
        ).read_text(encoding="utf-8")
    )
    assert persisted.run_id == "run-1"
    assert persisted.task_id == "case-1"
    assert persisted.created_at_utc == NOW


def test_structured_save_tool_receives_authoritative_identity_from_runnable_config(
    isolated_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_tools, "_utc_now", lambda: TOOL_EXECUTED_AT)
    payload = _task_plan(
        artifact_id="plan-structured-runtime-binding",
    ).model_dump(mode="json")
    for system_field in ("run_id", "task_id", "created_at_utc"):
        payload.pop(system_field)
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {
            "task_run_id": "runtime-run",
            "case_id": "runtime-case",
            "task_submitted_at": TASK_SUBMITTED_AT.isoformat(),
        },
    }
    result = contract_tools.save_task_plan_tool.invoke({"contract": payload}, config=config)
    assert result["status"] == "success"
    assert {"run_id", "task_id"}.isdisjoint(result)
    assert result["path"].startswith("package/")
    persisted = TaskPlan.model_validate_json(
        _persisted_contract_path(
            isolated_workspace,
            run_id="runtime-run",
            artifact_id="plan-structured-runtime-binding",
        ).read_text(encoding="utf-8")
    )
    assert persisted.created_at_utc == TASK_SUBMITTED_AT
    # The stable runner timestamp keeps retries of an immutable artifact byte-idempotent.
    retried = contract_tools.save_task_plan_tool.invoke({"contract": payload}, config=config)
    assert retried["status"] == "success"
    assert retried["sha256"] == result["sha256"]
    assert retried["package_handle"] == result["package_handle"]

    forbidden_payload = dict(payload)
    forbidden_payload["run_id"] = "model-must-not-control-this"
    forbidden_payload["task_id"] = "model-must-not-control-this"
    forbidden_payload["created_at_utc"] = "2026-03-02T00:00:00Z"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract_tools.save_task_plan_tool.args_schema.model_validate(
            {"contract": forbidden_payload}
        )


def test_opaque_package_handle_is_thread_scoped_and_hides_runtime_identity(
    isolated_workspace: Path,
) -> None:
    draft = _task_plan(artifact_id="plan-opaque-handle").model_dump(mode="json")
    for system_field in ("run_id", "task_id", "created_at_utc"):
        draft.pop(system_field)
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {"task_run_id": "secret-runtime-run", "case_id": "secret-runtime-case"},
    }
    saved = contract_tools.save_task_plan_tool.invoke({"contract": draft}, config=config)
    serialized = json.dumps(saved, sort_keys=True)
    assert saved["path"].startswith("package/")
    assert "secret-runtime-run" not in serialized
    assert "secret-runtime-case" not in serialized
    assert validate_contract(contract_path=saved["path"], config=config)["status"] == "success"

    other_thread = validate_contract(
        contract_path=saved["path"],
        config={"configurable": {"thread_id": "different-thread"}},
    )
    assert other_thread["status"] == "failed"
    assert other_thread["error"]["code"] == "CONTRACT_VALIDATION_OR_IO_FAILED"
    assert "unknown package handle" not in other_thread["error"]["message"]


def test_route_tool_expands_opaque_contract_refs_before_internal_checkpoint(
    isolated_workspace: Path,
) -> None:
    draft = _task_plan(artifact_id="plan-route-opaque").model_dump(mode="json")
    for system_field in ("run_id", "task_id", "created_at_utc"):
        draft.pop(system_field)
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {"task_run_id": "runtime-run", "case_id": "runtime-case"},
    }
    saved = contract_tools.save_task_plan_tool.invoke({"contract": draft}, config=config)
    result = contract_tools.record_route_transition_tool.invoke(
        {
            "target_status": "planning",
            "reason": "Use the persisted TaskPlan.",
            "contract_refs": [saved["package_ref"]],
        },
        config=config,
    )
    assert result["status"] == "success"
    assert "runtime-run" not in json.dumps(result, sort_keys=True)
    checkpoint = isolated_workspace / "outputs" / "runs" / "runtime-run" / "route" / "route_state.json"
    state = RouteState.model_validate_json(checkpoint.read_text(encoding="utf-8"))
    assert state.events[0].contract_refs[0].path == (
        "/data/processed/runs/runtime-run/contracts/task_plan__plan-route-opaque.json"
    )


def test_route_tool_checkpoints_and_restores_current_thread_state(isolated_workspace: Path) -> None:
    first = record_route_transition(
        run_id="run-tool-1",
        task_id="case-1",
        target_status="planning",
        reason="Create the TaskPlan.",
    )
    assert first["status"] == "success"
    assert first["route_status"] == "planning"
    second = record_route_transition(
        run_id="run-tool-1",
        task_id="case-1",
        target_status="direct_execution",
        reason="Fast-path gates passed.",
    )
    assert second["route_status"] == "direct_execution"
    checkpoint = isolated_workspace / "outputs" / "runs" / "run-tool-1" / "route" / "route_state.json"
    restored = RouteState.model_validate_json(checkpoint.read_text(encoding="utf-8"))
    assert len(restored.events) == 2
    assert second["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()


def test_route_tool_injects_authoritative_benchmark_identity_outside_model_input(
    isolated_workspace: Path,
) -> None:
    result = contract_tools.record_route_transition_tool.invoke(
        {
            "target_status": "planning",
            "reason": "Create the authoritative TaskPlan.",
        },
        config={
            "configurable": {"thread_id": "contract-thread"},
            "metadata": {"task_run_id": "runtime-run", "case_id": "runtime-case"},
        },
    )
    assert result["status"] == "success"
    assert {"run_id", "task_id"}.isdisjoint(result)
    checkpoint = isolated_workspace / "outputs" / "runs" / "runtime-run" / "route" / "route_state.json"
    restored = RouteState.model_validate_json(checkpoint.read_text(encoding="utf-8"))
    assert restored.run_id == "runtime-run"
    assert restored.task_id == "runtime-case"
    assert not (isolated_workspace / "outputs" / "runs" / "model-guessed-run").exists()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract_tools.record_route_transition_tool.args_schema.model_validate(
            {
                "run_id": "model-guessed-run",
                "task_id": "model-guessed-task",
                "target_status": "planning",
                "reason": "IDs are forbidden model input.",
            }
        )


def test_engineer_acceptance_verifies_package_and_declared_artifacts(isolated_workspace: Path) -> None:
    artifact_path = isolated_workspace / "outputs" / "runs" / "run-1" / "artifacts" / "summary.csv"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"date,value\n2026-08-11,1\n")
    artifact_ref = ArtifactRecord(
        path="/data/processed/runs/run-1/artifacts/summary.csv",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        bytes=artifact_path.stat().st_size,
        media_type="text/csv",
    )
    observation = ObservationPackage(
        artifact_id="observation-1",
        run_id="run-1",
        task_id="case-1",
        created_at_utc=NOW,
        as_of_utc=NOW,
        query_executed_at_utc=NOW,
        status=ContractStatus.READY,
        product={"collection_id": "projects/example/ntl", "band": "radiance"},
        validation={"status": "passed"},
        analysis_ready_artifacts=[artifact_ref],
    )
    saved = save_contract(observation, thread_id="contract-thread")
    ref = _package_ref(saved)
    handoff = HandoffEnvelope(
        handoff_id="handoff-1",
        assignment_id="assignment-1",
        run_id="run-1",
        task_id="case-1",
        producer=AgentRole.DATA_SEARCHER,
        status=ContractStatus.READY,
        package=ref,
        summary=["Product fixed.", "QA checked.", "Artifact verified."],
        validation_verdict="passed",
    )
    decision = EngineerDecision(
        decision_id="decision-1",
        run_id="run-1",
        task_id="case-1",
        assignment_id="assignment-1",
        handoff_id="handoff-1",
        handoff_sha256=contract_sha256(handoff),
        decision="accepted",
        package=ref,
        validation={
            "schema_valid": True,
            "artifact_exists": True,
            "checksum_valid": True,
            "assignment_scope_valid": True,
            "semantic_consistency_valid": True,
            "producer_validation_passed": True,
        },
        reason="The package meets the assignment contract.",
    )
    result = persist_handoff_decision(handoff, decision, thread_id="contract-thread")
    assert result["status"] == "success"
    assert result["handoff"]["sha256"] == contract_sha256(handoff)
    assert result["decision"]["path"].startswith("/data/processed/runs/run-1/decisions/")

    artifact_path.write_text("tampered", encoding="utf-8")
    changed_decision = decision.model_copy(update={"decision_id": "decision-2"})
    with pytest.raises(ContractIOError, match="byte-size mismatch|checksum mismatch"):
        persist_handoff_decision(handoff, changed_decision, thread_id="contract-thread")


def test_engineer_acceptance_allows_checksum_bound_staged_input_artifact(
    isolated_workspace: Path,
) -> None:
    artifact_path = isolated_workspace / "inputs" / "observation" / "synthetic.tif"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"synthetic-raster")
    artifact_ref = ArtifactRecord(
        path="inputs/observation/synthetic.tif",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        bytes=artifact_path.stat().st_size,
        media_type="image/tiff",
    )
    observation = ObservationPackage(
        artifact_id="observation-staged-input",
        run_id="run-input",
        task_id="case-input",
        created_at_utc=NOW,
        query_executed_at_utc=NOW,
        status=ContractStatus.READY,
        product={"product_type": "synthetic fixture"},
        validation={"status": "passed"},
        analysis_ready_artifacts=[artifact_ref],
    )
    ref = _package_ref(save_contract(observation, thread_id="contract-thread"))
    handoff = HandoffEnvelope(
        handoff_id="handoff-input",
        assignment_id="assignment-input",
        run_id="run-input",
        task_id="case-input",
        producer=AgentRole.DATA_SEARCHER,
        status=ContractStatus.READY,
        package=ref,
        summary=["Staged input inspected.", "Checksum verified.", "Package ready."],
        validation_verdict="passed",
    )
    decision = EngineerDecision(
        decision_id="decision-input",
        run_id="run-input",
        task_id="case-input",
        assignment_id="assignment-input",
        handoff_id="handoff-input",
        handoff_sha256=contract_sha256(handoff),
        decision="accepted",
        package=ref,
        validation={
            "schema_valid": True,
            "artifact_exists": True,
            "checksum_valid": True,
            "assignment_scope_valid": True,
            "semantic_consistency_valid": True,
            "producer_validation_passed": True,
        },
        reason="The staged observation is immutable and checksum-bound.",
    )
    assert persist_handoff_decision(handoff, decision, thread_id="contract-thread")[
        "status"
    ] == "success"

    artifact_path.write_bytes(b"changed")
    changed = decision.model_copy(update={"decision_id": "decision-input-changed"})
    with pytest.raises(ContractIOError, match="byte-size mismatch|checksum mismatch"):
        persist_handoff_decision(handoff, changed, thread_id="contract-thread")


def test_workspace_artifact_paths_reject_input_traversal() -> None:
    with pytest.raises(ValidationError, match="artifact path"):
        ArtifactRecord(
            path="inputs/../secret.tif",
            sha256="0" * 64,
            bytes=1,
        )


def test_handoff_tool_normalizes_benchmark_envelopes_but_still_verifies_package_identity(
    isolated_workspace: Path,
) -> None:
    observation = ObservationPackage(
        artifact_id="observation-runtime-binding",
        run_id="runtime-run",
        task_id="runtime-case",
        created_at_utc=NOW,
        as_of_utc=NOW,
        query_executed_at_utc=NOW,
        status=ContractStatus.READY,
        product={"collection_id": "projects/example/ntl"},
        validation={"status": "passed"},
    )
    ref = _package_ref(save_contract(observation, thread_id="contract-thread"))
    handoff = {
        "handoff_id": "handoff-runtime-binding",
        "assignment_id": "assignment-runtime-binding",
        "run_id": "model-guessed-run",
        "task_id": "model-guessed-task",
        "producer": "NTL_Data_Searcher",
        "status": "ready",
        "package": ref.model_dump(mode="json"),
        "summary": ["Product fixed.", "QA checked.", "Package referenced."],
        "validation_verdict": "passed",
    }
    decision = {
        "decision_id": "decision-runtime-binding",
        "run_id": "another-guessed-run",
        "task_id": "another-guessed-task",
        "assignment_id": "wrong-assignment",
        "handoff_id": "wrong-handoff",
        "handoff_sha256": "0" * 64,
        "decision": "accepted",
        "package": {
            "artifact_id": "model-guessed-package",
            "artifact_type": "ObservationPackage",
            "path": "/data/processed/runs/runtime-run/contracts/model-guessed-package.json",
            "sha256": "0" * 64,
        },
        "validation": {
            "schema_valid": True,
            "artifact_exists": True,
            "checksum_valid": True,
            "assignment_scope_valid": True,
            "semantic_consistency_valid": True,
            "producer_validation_passed": True,
        },
        "reason": "The verified package meets the assignment contract.",
    }
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {"task_run_id": "runtime-run", "case_id": "runtime-case"},
    }

    result = record_handoff_decision(handoff, decision, config=config)

    assert result["status"] == "success"
    assert {"run_id", "task_id"}.isdisjoint(result["handoff"])
    assert {"run_id", "task_id"}.isdisjoint(result["decision"])
    handoff_path = (
        isolated_workspace
        / "outputs"
        / "runs"
        / "runtime-run"
        / "handoffs"
        / "handoff__handoff-runtime-binding.json"
    )
    decision_path = (
        isolated_workspace
        / "outputs"
        / "runs"
        / "runtime-run"
        / "decisions"
        / "engineer_decision__decision-runtime-binding.json"
    )
    persisted_handoff = HandoffEnvelope.model_validate_json(handoff_path.read_text(encoding="utf-8"))
    persisted_decision = EngineerDecision.model_validate_json(decision_path.read_text(encoding="utf-8"))
    assert persisted_handoff.package == ref
    assert persisted_decision.assignment_id == persisted_handoff.assignment_id
    assert persisted_decision.handoff_id == persisted_handoff.handoff_id
    assert persisted_decision.handoff_sha256 == contract_sha256(persisted_handoff)
    assert persisted_decision.package == ref

    bad_handoff = dict(handoff)
    bad_handoff["handoff_id"] = "handoff-bad-checksum"
    bad_ref = ref.model_copy(update={"sha256": "f" * 64})
    bad_handoff["package"] = bad_ref.model_dump(mode="json")
    bad_decision = dict(decision)
    bad_decision["decision_id"] = "decision-bad-checksum"
    failed = record_handoff_decision(bad_handoff, bad_decision, config=config)
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "CONTRACT_VALIDATION_OR_IO_FAILED"
    assert "checksum mismatch" not in failed["error"]["message"]


def test_handoff_tool_normalizes_nested_revision_request_identity(
    isolated_workspace: Path,
) -> None:
    observation = ObservationPackage(
        artifact_id="observation-revision-binding",
        run_id="runtime-run",
        task_id="runtime-case",
        created_at_utc=NOW,
        as_of_utc=NOW,
        query_executed_at_utc=NOW,
        status=ContractStatus.READY,
        product={"collection_id": "projects/example/ntl"},
        validation={"status": "passed"},
    )
    config = {
        "configurable": {"thread_id": "contract-thread"},
        "metadata": {
            "task_run_id": "runtime-run",
            "case_id": "runtime-case",
            "task_submitted_at": NOW.isoformat(),
        },
    }
    draft = observation.model_dump(mode="json")
    for system_field in ("run_id", "task_id", "created_at_utc", "query_executed_at_utc"):
        draft.pop(system_field)
    record_observation_tool_success(
        tool_name="geodata_inspector_tool",
        mode="full",
        started_at_utc=observation_tool_started_at(),
        config=config,
    )
    saved = contract_tools.save_observation_package_tool.invoke(
        {"contract": draft},
        config=config,
    )
    ref = _package_ref(saved)
    assert ref.path.startswith("package/")
    actual_ref = ref.model_copy(
        update={
            "path": (
                "/data/processed/runs/runtime-run/contracts/"
                "observation_package__observation-revision-binding.json"
            )
        }
    )
    handoff = {
        "handoff_id": "handoff-revision-binding",
        "assignment_id": "assignment-revision-binding",
        "producer": "NTL_Data_Searcher",
        "status": "ready",
        "package": ref.model_dump(mode="json"),
        "summary": ["Product fixed.", "QA checked.", "Revision needed."],
        "validation_verdict": "passed",
    }
    decision = {
        "decision_id": "decision-revision-binding",
        "decision": "revision_requested",
        "validation": {
            "schema_valid": True,
            "artifact_exists": True,
            "checksum_valid": True,
            "assignment_scope_valid": False,
            "semantic_consistency_valid": True,
            "producer_validation_passed": True,
        },
        "reason": "Add the missing assignment-scoped provenance.",
        "revision_request": {
            "revision_id": "revision-runtime-binding",
            "source_agent": "NTL_Engineer",
            "target_agent": "NTL_Data_Searcher",
            "related_package": ref.model_dump(mode="json"),
            "reason": "Assignment-scoped provenance is incomplete.",
            "required_changes": ["Add the missing provenance record."],
            "revision_number": 1,
        },
    }
    result = contract_tools.record_handoff_decision_tool.invoke(
        {"handoff": handoff, "decision": decision},
        config=config,
    )
    assert result["status"] == "success"
    decision_path = (
        isolated_workspace
        / "outputs"
        / "runs"
        / "runtime-run"
        / "decisions"
        / "engineer_decision__decision-revision-binding.json"
    )
    persisted = EngineerDecision.model_validate_json(decision_path.read_text(encoding="utf-8"))
    assert persisted.revision_request is not None
    assert persisted.revision_request.run_id == "runtime-run"
    assert persisted.revision_request.task_id == "runtime-case"
    assert persisted.package == actual_ref
    assert persisted.revision_request.related_package == actual_ref

    forbidden_handoff = dict(handoff)
    forbidden_handoff["run_id"] = "model-guessed-run"
    forbidden_handoff["task_id"] = "model-guessed-task"
    forbidden_decision = dict(decision)
    forbidden_decision["run_id"] = "model-guessed-run"
    forbidden_decision["task_id"] = "model-guessed-task"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract_tools.record_handoff_decision_tool.args_schema.model_validate(
            {"handoff": forbidden_handoff, "decision": forbidden_decision}
        )


def test_handoff_rejects_package_type_inconsistent_with_producer() -> None:
    with pytest.raises(ValidationError, match="package type"):
        HandoffEnvelope(
            assignment_id="assignment-1",
            run_id="run-1",
            task_id="case-1",
            producer=AgentRole.ANALYST,
            status=ContractStatus.READY,
            package=PackageRef(
                artifact_id="observation-1",
                artifact_type="ObservationPackage",
                path="/data/processed/runs/run-1/contracts/observation.json",
                sha256="a" * 64,
            ),
            summary=["One", "Two", "Three"],
            validation_verdict="passed",
        )


def test_route_state_machine_enforces_revision_budget_and_is_replayable() -> None:
    machine = RouteStateMachine(RouteState(run_id="run-1", task_id="case-1", max_revisions=1))
    machine.transition(RouteStatus.PLANNING, actor="NTL_Engineer", reason="start")
    machine.transition(RouteStatus.SPECIALIST_ROUTING, actor="NTL_Engineer", reason="needs data")
    machine.transition(RouteStatus.DATA_PREPARATION, actor="NTL_Engineer", reason="dispatch")
    machine.transition(RouteStatus.HANDOFF_VALIDATION, actor="NTL_Engineer", reason="validate")
    machine.request_revision_or_block(actor="NTL_Engineer", reason="missing provenance")
    machine.transition(RouteStatus.SPECIALIST_ROUTING, actor="NTL_Engineer", reason="retry")
    machine.transition(RouteStatus.DATA_PREPARATION, actor="NTL_Engineer", reason="dispatch")
    machine.transition(RouteStatus.HANDOFF_VALIDATION, actor="NTL_Engineer", reason="validate")
    state = machine.request_revision_or_block(actor="NTL_Engineer", reason="still invalid")
    assert state.status == RouteStatus.BLOCKED
    assert state.revision_count == 1
    assert state.events[-1].error_code == ErrorCode.BUDGET_EXCEEDED
    restored = RouteState.model_validate_json(state.model_dump_json())
    assert restored == state
    assert restored.terminal
    with pytest.raises(ValueError):
        machine.transition(RouteStatus.PLANNING, actor="NTL_Engineer", reason="illegal")


def test_route_state_rejects_tampered_event_chain() -> None:
    machine = RouteStateMachine(RouteState(run_id="run-1", task_id="case-1"))
    state = machine.transition(RouteStatus.PLANNING, actor="NTL_Engineer", reason="start")
    payload = state.model_dump(mode="json")
    payload["events"][0]["from_status"] = "analysis"
    with pytest.raises(ValidationError, match="discontinuous|illegal persisted"):
        RouteState.model_validate(payload)


def test_model_facing_contract_failures_do_not_echo_internal_identity_or_paths(
    isolated_workspace: Path,
) -> None:
    del isolated_workspace
    config = {
        "configurable": {"thread_id": "opaque-error-thread"},
        "metadata": {
            "task_run_id": "secret-runtime-run",
            "case_id": "secret-runtime-case",
        },
    }
    result = contract_tools.validate_contract_tool.invoke(
        {
            "contract_path": "package/ffffffffffffffffffffffffffffffff",
            "expected_artifact_type": "TaskPlan",
        },
        config=config,
    )
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["status"] == "failed"
    assert "secret-runtime-run" not in encoded
    assert "secret-runtime-case" not in encoded
    assert "/data/processed/runs" not in encoded
