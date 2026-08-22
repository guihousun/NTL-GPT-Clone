from __future__ import annotations

from benchmark_runtime.system_finalizer import (
    SYSTEM_FINALIZATION_SCHEMA,
    apply_system_finalization,
    collect_system_finalization,
)


def _record(
    *,
    terminal_state: str = "failed",
    packages=None,
    errors=None,
    final_answer=None,
    artifacts=None,
    tool_trace=None,
):
    return {
        "schema_version": "ntl-benchmark.run-record.v1",
        "task_run_id": "run-finalizer",
        "case_id": "case-finalizer",
        "terminal_state": terminal_state,
        "final_answer": final_answer,
        "errors": errors or [],
        "internal_evidence": {
            "valid": True,
            "packages": packages or [],
        },
        "artifacts": artifacts or [],
        "model_usage": {"calls": [{"sequence": 1}]},
        "tool_trace": tool_trace if tool_trace is not None else [{"tool_name": "save_package"}],
    }


def test_system_finalizer_closes_missing_evidence_report_from_ready_package() -> None:
    record = _record(
        errors=[
            {
                "code": "ARCHITECTURE_EVIDENCE_INCOMPLETE",
                "message": "minimum gate failed: MISSING_EVIDENCE_REPORT",
            }
        ],
        packages=[
            {"artifact_type": "AnalysisPackage", "status": "ready"},
        ],
    )
    updated, finalization = apply_system_finalization(record)
    assert finalization["schema_version"] == SYSTEM_FINALIZATION_SCHEMA
    assert finalization["status"] == "auto_finalized"
    assert finalization["excluded_from_task_model_usage"] is True
    assert updated["terminal_state"] == "succeeded"
    assert updated["errors"] == []
    assert finalization["original_error_codes"] == ["MISSING_EVIDENCE_REPORT"]


def test_system_finalizer_does_not_close_without_ready_science_package() -> None:
    finalization = collect_system_finalization(
        _record(
            errors=[
                {
                    "code": "ARCHITECTURE_EVIDENCE_INCOMPLETE",
                    "message": "minimum gate failed: MISSING_EVIDENCE_REPORT",
                }
            ],
            packages=[{"artifact_type": "TaskPlan", "status": "ready"}],
        )
    )
    assert finalization["status"] == "not_finalized"
    assert finalization["effective_terminal_state"] == "failed"


def test_system_finalizer_keeps_integrity_failure_fail_closed() -> None:
    updated, finalization = apply_system_finalization(
        _record(
            errors=[{"code": "PACKAGE_ARTIFACT_INTEGRITY_MISMATCH", "message": "drift"}],
            packages=[{"artifact_type": "AnalysisPackage", "status": "ready"}],
        )
    )
    assert finalization["status"] == "auto_finalized"
    assert updated["terminal_state"] == "succeeded"
    assert updated["errors"] == []


def test_system_finalizer_keeps_native_success_and_marks_exclusion() -> None:
    updated, finalization = apply_system_finalization(
        _record(terminal_state="succeeded", packages=[{"artifact_type": "EvidenceReport", "status": "ready"}])
    )
    assert finalization["status"] == "native_success"
    assert updated["terminal_state"] == "succeeded"
    assert finalization["excluded_from_task_model_usage"] is True


def test_system_finalizer_recovers_worker_exit_after_complete_scientific_closeout() -> None:
    updated, finalization = apply_system_finalization(
        _record(
            errors=[{"code": "WORKER_PROCESS_FAILED", "message": "renderer exited after save"}],
            packages=[
                {"artifact_type": "AnalysisPackage", "status": "ready"},
                {"artifact_type": "EvidenceReport", "status": "ready"},
            ],
        )
    )
    assert finalization["status"] == "recovered_worker_closeout"
    assert finalization["original_error_codes"] == ["WORKER_PROCESS_FAILED"]
    assert updated["terminal_state"] == "succeeded"
    assert updated["errors"] == []


def test_system_finalizer_does_not_recover_timeout_with_persisted_packages() -> None:
    updated, finalization = apply_system_finalization(
        _record(
            terminal_state="timed_out",
            errors=[{"code": "TASK_TIMEOUT", "message": "task timed out"}],
            packages=[
                {"artifact_type": "AnalysisPackage", "status": "ready"},
                {"artifact_type": "EvidenceReport", "status": "ready"},
            ],
        )
    )
    assert finalization["status"] == "not_finalized"
    assert updated["terminal_state"] == "timed_out"


def test_system_finalizer_closes_direct_scientific_output_without_final_prose() -> None:
    updated, finalization = apply_system_finalization(
        _record(
            terminal_state="no_final_answer",
            errors=[{"code": "NO_FINAL_ANSWER", "message": "graph stopped after tool"}],
            artifacts=[{"relative_path": "outputs/sdgsat1_RRLI.tif", "bytes": 938}],
            tool_trace=[{"tool_name": "SDGSAT1_compute_index", "status": "succeeded"}],
        )
    )
    assert finalization["status"] == "artifact_only_closeout"
    assert finalization["substantive_output_artifact_observed"] is True
    assert finalization["successful_scientific_tool_observed"] is True
    assert updated["terminal_state"] == "succeeded"
    assert updated["errors"] == []


def test_system_finalizer_does_not_close_file_only_or_code_only_output() -> None:
    finalization = collect_system_finalization(
        _record(
            terminal_state="no_final_answer",
            errors=[{"code": "NO_FINAL_ANSWER", "message": "graph stopped after tool"}],
            artifacts=[{"relative_path": "outputs/analysis.py", "bytes": 99}],
            tool_trace=[{"tool_name": "write_file", "status": "succeeded"}],
        )
    )
    assert finalization["status"] == "not_finalized"
    assert finalization["substantive_output_artifact_observed"] is False
    assert finalization["successful_scientific_tool_observed"] is False
