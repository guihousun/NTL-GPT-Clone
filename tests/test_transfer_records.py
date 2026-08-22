from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from contracts.agent_packages import (
    ContractStatus,
    EngineerDecision,
    EngineerValidation,
    HandoffEnvelope,
    ObservationPackage,
    PackageRef,
    canonical_json,
    contract_sha256,
)
from orchestration.run_evidence import (
    collect_internal_evidence,
    validate_internal_evidence,
)
from orchestration.transfer_records import (
    AssignmentRecordV2,
    HandoffRecordV2,
    TRANSFER_PACKAGE_LINK_INVALID,
    TRANSFER_TASK_ROLE_INVALID,
    reconcile_transfer_records,
)


RUN_ID = "run-transfer"
TASK_ID = "case-transfer"
CALL_ID = "task-call-transfer"


def _stable_hash(value: object) -> tuple[str, int]:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _task_row(
    *,
    target: str = "NTL_Data_Searcher",
    source: str = "NTL_Engineer",
    description: str = "Inspect the staged raster and return ordinary prose; this is not JSON {.",
    response: str = "Completed in plain text; no JSON envelope was returned.",
) -> dict[str, object]:
    arguments = {"description": description, "subagent_type": target}
    arguments_sha256, _ = _stable_hash(arguments)
    response_sha256, response_bytes = _stable_hash(response)
    return {
        "sequence": 1,
        "tool_call_id": CALL_ID,
        "parent_run_id": None,
        "tool_name": "task",
        "status": "succeeded",
        "started_at": "2026-08-13T01:00:01+00:00",
        "ended_at": "2026-08-13T01:00:05+00:00",
        "arguments": arguments,
        "arguments_sha256": arguments_sha256,
        "result_observed": True,
        "result_sha256": response_sha256,
        "result_bytes": response_bytes,
        "error": None,
        "metadata": {
            "task_run_id": RUN_ID,
            "case_id": TASK_ID,
            "lc_agent_name": source,
        },
        "ancestor_tool_call_ids": [],
    }


def _persist_observation_and_legacy_pair(outputs: Path) -> None:
    run_root = outputs / "runs" / RUN_ID
    contract_dir = run_root / "contracts"
    handoff_dir = run_root / "handoffs"
    decision_dir = run_root / "decisions"
    contract_dir.mkdir(parents=True)
    handoff_dir.mkdir()
    decision_dir.mkdir()

    package = ObservationPackage(
        artifact_id="observation-transfer",
        run_id=RUN_ID,
        task_id=TASK_ID,
        created_at_utc=datetime(2026, 8, 13, 1, 0, 3, tzinfo=timezone.utc),
        query_executed_at_utc=datetime(2026, 8, 13, 1, 0, 2, tzinfo=timezone.utc),
        status=ContractStatus.READY,
        product={"kind": "synthetic fixture"},
        validation={"verdict": "passed"},
    )
    package_name = "observation_package__observation-transfer.json"
    package_path = contract_dir / package_name
    package_text = canonical_json(package)
    package_path.write_text(package_text, encoding="utf-8")
    package_ref = PackageRef(
        artifact_id=package.artifact_id,
        artifact_type=package.artifact_type,
        path=f"/data/processed/runs/{RUN_ID}/contracts/{package_name}",
        sha256=hashlib.sha256(package_text.encode("utf-8")).hexdigest(),
    )
    handoff = HandoffEnvelope(
        handoff_id="legacy-handoff-transfer",
        assignment_id="legacy-assignment-transfer",
        run_id=RUN_ID,
        task_id=TASK_ID,
        producer="NTL_Data_Searcher",
        status=ContractStatus.READY,
        package=package_ref,
        summary=["package saved", "validation passed", "limitations recorded"],
        validation_verdict="passed",
    )
    decision = EngineerDecision(
        decision_id="legacy-decision-transfer",
        run_id=RUN_ID,
        task_id=TASK_ID,
        assignment_id=handoff.assignment_id,
        handoff_id=handoff.handoff_id,
        handoff_sha256=contract_sha256(handoff),
        decision="accepted",
        package=package_ref,
        validation=EngineerValidation(
            schema_valid=True,
            artifact_exists=True,
            checksum_valid=True,
            assignment_scope_valid=True,
            semantic_consistency_valid=True,
            producer_validation_passed=True,
        ),
        reason="Legacy compatibility link only.",
    )
    (handoff_dir / "handoff__legacy-handoff-transfer.json").write_text(
        canonical_json(handoff), encoding="utf-8"
    )
    (decision_dir / "engineer_decision__legacy-decision-transfer.json").write_text(
        canonical_json(decision), encoding="utf-8"
    )


def _save_row(*, artifact_id: str = "observation-transfer") -> dict[str, object]:
    return {
        "sequence": 2,
        "tool_call_id": "save-call-transfer",
        "tool_name": "save_observation_package",
        "status": "succeeded",
        "result_observed": True,
        "arguments": {
            "contract": {
                "artifact_id": artifact_id,
                "artifact_type": "ObservationPackage",
            }
        },
        "metadata": {
            "task_run_id": RUN_ID,
            "case_id": TASK_ID,
            "lc_agent_name": "NTL_Data_Searcher",
        },
        "ancestor_tool_call_ids": [CALL_ID],
    }


def _save_row_system_managed_identity() -> dict[str, object]:
    """Model-facing typed saves omit identity; runtime binds it on persist."""
    row = _save_row()
    row["arguments"] = {"contract": {}}
    return row


def _structured_failed_save_row() -> dict[str, object]:
    row = _save_row_system_managed_identity()
    row["status"] = "error"
    row["error"] = {"code": "CONTRACT_SCHEMA_INVALID", "message": "missing field"}
    return row


def _downstream_analysis_save_row() -> dict[str, object]:
    """A later specialist save may still carry the supervisor task as an ancestor."""
    return {
        "sequence": 3,
        "tool_call_id": "analysis-save-call-transfer",
        "tool_name": "save_analysis_package",
        "status": "succeeded",
        "result_observed": True,
        "arguments": {"contract": {"artifact_id": "analysis-transfer", "artifact_type": "AnalysisPackage"}},
        "metadata": {
            "task_run_id": RUN_ID,
            "case_id": TASK_ID,
            "lc_agent_name": "NTL_Analyst",
        },
        "ancestor_tool_call_ids": [CALL_ID],
    }


def test_plain_text_native_task_materializes_and_links_v2_records(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _persist_observation_and_legacy_pair(outputs)
    trace = [_task_row(), _save_row(), _downstream_analysis_save_row()]

    first = reconcile_transfer_records(
        outputs,
        tool_trace=trace,
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert first["issues"] == []
    assert len(first["assignment_records"]) == 1
    assert len(first["handoff_records"]) == 1

    assignment_path = (
        outputs / "runs" / RUN_ID / "assignment_records" / f"assignment_record__{CALL_ID}.json"
    )
    handoff_path = (
        outputs / "runs" / RUN_ID / "handoff_records" / f"handoff_record__{CALL_ID}.json"
    )
    assignment = AssignmentRecordV2.model_validate_json(assignment_path.read_text(encoding="utf-8"))
    handoff = HandoffRecordV2.model_validate_json(handoff_path.read_text(encoding="utf-8"))
    description = trace[0]["arguments"]["description"]
    assert assignment.description_sha256 == hashlib.sha256(description.encode("utf-8")).hexdigest()
    assert handoff.response_sha256 == trace[0]["result_sha256"]
    assert handoff.producer_role == "NTL_Data_Searcher"
    assert handoff.recipient_role == "NTL_Engineer"
    assert handoff.package_association == "linked"
    assert handoff.package is not None
    assert handoff.package.artifact_id == "observation-transfer"
    assert handoff.legacy_handoff is not None
    assert handoff.legacy_decision is not None
    assert description not in assignment_path.read_text(encoding="utf-8")
    assert "Completed in plain text" not in handoff_path.read_text(encoding="utf-8")

    # Reconciliation is append-only and idempotent: identical facts reuse the
    # same immutable files instead of overwriting or adding copies.
    second = reconcile_transfer_records(
        outputs,
        tool_trace=trace,
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert second == first
    assert len(list((outputs / "runs" / RUN_ID / "assignment_records").glob("*.json"))) == 1
    assert len(list((outputs / "runs" / RUN_ID / "handoff_records").glob("*.json"))) == 1

    evidence = collect_internal_evidence(outputs)
    validate_internal_evidence(evidence)
    assert len(evidence["assignment_records"]) == 1
    assert len(evidence["handoff_records"]) == 1


def test_downstream_specialist_save_does_not_break_parent_transfer_link(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _persist_observation_and_legacy_pair(outputs)
    reconciled = reconcile_transfer_records(
        outputs,
        tool_trace=[_task_row(), _save_row(), _downstream_analysis_save_row()],
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert reconciled["issues"] == []
    assert len(reconciled["handoff_records"]) == 1


def test_system_managed_package_identity_links_unique_ready_package(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _persist_observation_and_legacy_pair(outputs)
    reconciled = reconcile_transfer_records(
        outputs,
        tool_trace=[_task_row(), _save_row_system_managed_identity()],
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert reconciled["issues"] == []
    handoff_path = (
        outputs
        / "runs"
        / RUN_ID
        / "handoff_records"
        / f"handoff_record__{CALL_ID}.json"
    )
    handoff = HandoffRecordV2.model_validate_json(handoff_path.read_text(encoding="utf-8"))
    assert handoff.package_association == "linked"


def test_structured_failed_save_never_links_an_unrelated_ready_package(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _persist_observation_and_legacy_pair(outputs)
    # The ready package exists, but the current native save failed. The v2
    # transfer must inventory the handoff without claiming that failed save
    # persisted this package.
    reconciled = reconcile_transfer_records(
        outputs,
        tool_trace=[_task_row(), _structured_failed_save_row()],
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    handoff_path = (
        outputs / "runs" / RUN_ID / "handoff_records" / f"handoff_record__{CALL_ID}.json"
    )
    handoff = HandoffRecordV2.model_validate_json(handoff_path.read_text(encoding="utf-8"))
    assert handoff.package_association == "none"
    assert handoff.package is None
    # The legacy compatibility pair is intentionally not re-linked; its
    # existing audit issue is finalizer-recoverable rather than scientific.
    assert reconciled["issues"] == [TRANSFER_PACKAGE_LINK_INVALID]


def test_collector_inventories_unlinked_native_transfer(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    trace = [_task_row(target="NTL_Analyst")]

    reconciled = reconcile_transfer_records(
        outputs,
        tool_trace=trace,
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert reconciled["issues"] == []
    evidence = collect_internal_evidence(outputs)
    assert len(evidence["assignment_records"]) == 1
    assert len(evidence["handoff_records"]) == 1
    assert evidence["handoff_records"][0]["package_association"] == "none"


def test_transfer_record_hard_gates_role_and_package_call_consistency(tmp_path: Path) -> None:
    wrong_role_outputs = tmp_path / "wrong-role" / "outputs"
    wrong_role_outputs.mkdir(parents=True)
    wrong_role = reconcile_transfer_records(
        wrong_role_outputs,
        tool_trace=[_task_row(source="NTL_Analyst")],
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert wrong_role["issues"] == [TRANSFER_TASK_ROLE_INVALID]
    assert wrong_role["assignment_records"] == []
    assert wrong_role["handoff_records"] == []

    missing_package_outputs = tmp_path / "missing-package" / "outputs"
    missing_package_outputs.mkdir(parents=True)
    missing_package = reconcile_transfer_records(
        missing_package_outputs,
        tool_trace=[_task_row(), _save_row(artifact_id="does-not-exist")],
        expected_run_id=RUN_ID,
        expected_task_id=TASK_ID,
    )
    assert missing_package["issues"] == [TRANSFER_PACKAGE_LINK_INVALID]
    assert missing_package["assignment_records"] == []
    assert missing_package["handoff_records"] == []
