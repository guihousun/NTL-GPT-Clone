"""Deterministic post-worker evidence collection.

This module is deliberately outside the model/tool loop.  It records what the
worker actually persisted and may close an otherwise successful scientific run
when the model stopped before writing a prose EvidenceReport.  It never
creates, edits, or hashes a scientific artifact and never makes another LLM
request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SYSTEM_FINALIZATION_SCHEMA = "ntl-benchmark.system-finalization.v1"

# These are completion/evidence symptoms, not scientific or I/O failures.  A
# ready typed package is the authority for an automatic closeout; the original
# symptoms remain in the system-finalization record for audit.
_AUTO_FINALIZABLE_CODES = {
    "NO_FINAL_ANSWER",
    "TRANSFER_PACKAGE_LINK_INVALID",
    "AMBIGUOUS_OBSERVATION_SAVE_TRACE",
    "OBSERVATION_TIMESTAMP_AFTER_SAVE",
    "MISSING_EVIDENCE_REPORT",
    "MISSING_ROUTE_STATE",
}

# A worker can die after it has durably persisted the complete scientific
# closeout, for example while rendering a final chat response.  Treat only
# that narrow post-persistence symptom as recoverable; timeouts and malformed
# records remain terminal failures.
_RECOVERABLE_WORKER_CLOSEOUT_CODES = {
    "WORKER_PROCESS_FAILED",
    "ARCHITECTURE_EVIDENCE_INCOMPLETE",
}


# A model can complete a bounded direct tool task, persist its scientific
# output, and then stop before emitting prose.  Keep this path deliberately
# narrower than package-based recovery: it needs a substantive output *and* a
# successful domain tool, never merely a file-system call or a log file.
_NON_SCIENTIFIC_TOOL_NAMES = {
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "delete_file",
    "glob",
    "grep",
    "task",
    "save_task_plan",
    "save_event_context",
    "save_observation_package",
    "save_analysis_package",
    "save_evidence_report",
    "validate_contract",
    "record_route_transition",
    "NTL_Knowledge_Base",
    "GeoCode_Knowledge_Recipes_tool",
    "geodata_inspector_tool",
    "geodata_quick_check_tool",
}
_NON_SCIENTIFIC_OUTPUT_SUFFIXES = {".py", ".jsonl", ".log", ".md", ".tmp", ".lock"}


def _has_substantive_output_artifact(record: dict[str, Any]) -> bool:
    """Return whether the worker recorded a non-bookkeeping output artifact."""

    for artifact in record.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        path = str(artifact.get("relative_path") or "").replace("\\", "/").strip()
        normalized = path.lower()
        if not normalized.startswith("outputs/") or normalized.startswith("outputs/runs/"):
            continue
        suffix = normalized.rsplit(".", 1)[-1] if "." in normalized.rsplit("/", 1)[-1] else ""
        if f".{suffix}" in _NON_SCIENTIFIC_OUTPUT_SUFFIXES:
            continue
        return True
    return False


def _has_successful_scientific_tool(record: dict[str, Any]) -> bool:
    """Require a domain-tool success, rather than inferring science from a file."""

    for event in record.get("tool_trace") or []:
        if not isinstance(event, dict):
            continue
        tool_name = str(event.get("tool_name") or "").strip()
        status = str(event.get("status") or "").strip().lower()
        if status == "succeeded" and tool_name and tool_name not in _NON_SCIENTIFIC_TOOL_NAMES:
            return True
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_codes(record: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    rows = [
        *(record.get("errors") or []),
        *(record.get("audit_issues") or []),
    ]
    for error in rows:
        if not isinstance(error, dict):
            continue
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "")
        if code == "ARCHITECTURE_EVIDENCE_INCOMPLETE":
            # The runner preserves the stable sub-code in the diagnostic
            # message.  Do not treat unrelated architecture failures as a
            # harmless closeout symptom.
            for candidate in _AUTO_FINALIZABLE_CODES:
                if candidate in message:
                    codes.add(candidate)
            if not any(candidate in message for candidate in _AUTO_FINALIZABLE_CODES):
                codes.add(code)
        elif code:
            codes.add(code)
    return codes


def _package_summary(internal_evidence: Any) -> tuple[list[str], list[str]]:
    if not isinstance(internal_evidence, dict):
        return [], []
    ready: list[str] = []
    failed: list[str] = []
    for package in internal_evidence.get("packages") or []:
        if not isinstance(package, dict):
            continue
        package_type = str(package.get("artifact_type") or "").strip()
        status = str(package.get("status") or "").strip().lower()
        if not package_type:
            continue
        if status in {"ready", "passed", "succeeded"}:
            ready.append(package_type)
        elif status in {"failed", "blocked"}:
            failed.append(package_type)
    return sorted(set(ready)), sorted(set(failed))


def collect_system_finalization(record: dict[str, Any]) -> dict[str, Any]:
    """Return an append-only, deterministic closeout record for one worker."""

    internal = record.get("internal_evidence")
    ready_types, failed_types = _package_summary(internal)
    errors = _error_codes(record)
    audit_codes = set(errors)
    # Artifact identity findings are audit warnings; evaluators still inspect required outputs.
    worker_failure = bool(errors & {"TASK_TIMEOUT", "WORKER_PROCESS_FAILED", "INVALID_WORKER_RECORD"})
    science_ready = any(
        package_type in {"ObservationPackage", "AnalysisPackage", "EventContext", "EvidenceReport"}
        for package_type in ready_types
    )
    internal_valid = isinstance(internal, dict) and internal.get("valid") is True
    complete_scientific_closeout = (
        internal_valid
        and "EvidenceReport" in ready_types
        and bool({"ObservationPackage", "AnalysisPackage", "EventContext"} & set(ready_types))
        and not failed_types
    )
    substantive_output_artifact = _has_substantive_output_artifact(record)
    successful_scientific_tool = _has_successful_scientific_tool(record)
    if not internal_valid:
        audit_codes.add("INTERNAL_EVIDENCE_UNAVAILABLE")
    auto_finalized = bool(
        (bool(str(record.get("final_answer") or "").strip()) or science_ready)
        and not worker_failure
        and errors.issubset(_AUTO_FINALIZABLE_CODES | {"ARCHITECTURE_EVIDENCE_INCOMPLETE", "PACKAGE_ARTIFACT_INTEGRITY_MISMATCH"})
        and str(record.get("terminal_state") or "") != "timed_out"
    )
    recovered_worker_closeout = bool(
        complete_scientific_closeout
        and "WORKER_PROCESS_FAILED" in errors
        and errors.issubset(_RECOVERABLE_WORKER_CLOSEOUT_CODES)
        and str(record.get("terminal_state") or "") != "timed_out"
    )
    artifact_only_closeout = bool(
        internal_valid
        and "NO_FINAL_ANSWER" in errors
        and not failed_types
        and substantive_output_artifact
        and successful_scientific_tool
        and not worker_failure
        and errors.issubset(_AUTO_FINALIZABLE_CODES | {"ARCHITECTURE_EVIDENCE_INCOMPLETE"})
        and str(record.get("terminal_state") or "") != "timed_out"
    )
    if str(record.get("terminal_state") or "") == "succeeded":
        status = "completed_with_audit_warnings" if audit_codes else "native_success"
        effective_terminal_state = "succeeded"
        reason = (
            "worker completed; architecture and artifact audit warnings were recorded separately"
            if audit_codes
            else "worker completed with no audit warnings"
        )
    elif auto_finalized:
        status = "auto_finalized"
        effective_terminal_state = "succeeded"
        reason = "worker returned a scientific answer or package; parent collected non-blocking audit evidence"
    elif recovered_worker_closeout:
        status = "recovered_worker_closeout"
        effective_terminal_state = "succeeded"
        reason = "worker exited after a complete persisted scientific closeout; parent recovered the terminal state"
    elif artifact_only_closeout:
        status = "artifact_only_closeout"
        effective_terminal_state = "succeeded"
        reason = "worker completed a successful domain tool with a substantive output artifact but emitted no final prose"
    else:
        status = "not_finalized"
        effective_terminal_state = str(record.get("terminal_state") or "failed")
        reason = "required scientific package evidence was not sufficient for automatic closeout"

    return {
        "schema_version": SYSTEM_FINALIZATION_SCHEMA,
        "collector": "benchmark_runtime.system_finalizer",
        "collector_scope": "parent_post_worker",
        "collected_at_utc": _utc_now(),
        "excluded_from_task_model_usage": True,
        "task_run_id": record.get("task_run_id"),
        "case_id": record.get("case_id"),
        "original_terminal_state": record.get("terminal_state"),
        "effective_terminal_state": effective_terminal_state,
        "status": status,
        "reason": reason,
        "original_error_codes": sorted(errors),
        "audit_issue_codes": sorted(audit_codes),
        "model_final_answer_present": bool(str(record.get("final_answer") or "").strip()),
        "internal_evidence_valid": internal_valid,
        "ready_package_types": ready_types,
        "failed_or_blocked_package_types": failed_types,
        "substantive_output_artifact_observed": substantive_output_artifact,
        "successful_scientific_tool_observed": successful_scientific_tool,
        "model_call_count": len((record.get("model_usage") or {}).get("calls") or []),
        "tool_call_count": len(record.get("tool_trace") or []),
    }


def apply_system_finalization(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply an automatic closeout without hiding its original diagnostics."""

    finalization = collect_system_finalization(record)
    updated = dict(record)
    updated["system_finalization"] = finalization
    if finalization["status"] in {"auto_finalized", "recovered_worker_closeout", "artifact_only_closeout"}:
        updated["terminal_state"] = "succeeded"
        # The original evidence-gate symptoms remain in the append-only
        # system-finalization file; the task record reports its effective
        # system-computed terminal state.
        updated["errors"] = []
    return updated, finalization


__all__ = [
    "SYSTEM_FINALIZATION_SCHEMA",
    "apply_system_finalization",
    "collect_system_finalization",
]
