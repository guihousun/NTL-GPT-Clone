"""Formal aggregation for externally evaluated benchmark task runs."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import SUMMARY_SCHEMA
from .contracts import (
    ContractError,
    atomic_write_json,
    load_eval_result_records,
    load_eval_spec_records,
    load_run_records,
    unique_index,
    validate_eval_result,
    validate_eval_spec_record,
    validate_run_batch,
    validate_run_record,
)


RecordSource = str | os.PathLike[str] | Sequence[Mapping[str, Any]]


class FormalSummaryBlocked(ContractError):
    """Raised when missing, invalid, or technical-error data forbids a summary."""


def _records(source: RecordSource, *, loader: Any, validator: Any) -> list[dict[str, Any]]:
    if isinstance(source, (str, os.PathLike)):
        return loader(source)
    if not isinstance(source, Sequence):
        raise ContractError("record source must be a JSONL path or a sequence of records")
    return [validator(record) for record in source]


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def _select_case_records(
    records: list[dict[str, Any]], requested: Sequence[str] | None, label: str
) -> list[dict[str, Any]]:
    requested_ids = [str(value) for value in (requested or [])]
    if not requested_ids:
        return records
    if len({value.casefold() for value in requested_ids}) != len(requested_ids):
        raise FormalSummaryBlocked("selected case IDs must be unique ignoring case")
    indexed = unique_index(records, "case_id", label)
    missing = [case_id for case_id in requested_ids if case_id not in indexed]
    if missing:
        raise FormalSummaryBlocked(f"selected case IDs are absent from {label}: {missing}")
    return [dict(indexed[case_id]) for case_id in requested_ids]


def aggregate_metrics(
    run_records: RecordSource,
    eval_results: RecordSource,
    *,
    eval_specs: RecordSource | None = None,
    output_path: str | os.PathLike[str] | None = None,
    generated_at: str | None = None,
    case_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a complete one-result-per-run set and aggregate four metrics.

    A task run remains in the denominator regardless of whether its runtime
    terminal state is success, failure, or timeout.  Incomplete evaluator output,
    ``eval_error``, or incomplete provider usage raises ``FormalSummaryBlocked``
    instead of being counted as a tested-model failure.
    """

    all_runs = _records(run_records, loader=load_run_records, validator=validate_run_record)
    results = _records(eval_results, loader=load_eval_result_records, validator=validate_eval_result)
    if not all_runs:
        raise FormalSummaryBlocked("formal summary requires at least one task run")
    # Validate the complete declared batch before applying an optional reporting
    # subset. Otherwise a caller could hide mixed Full/Single-Agent provenance
    # by selecting only records from one architecture.
    try:
        batch_context = validate_run_batch(all_runs, require_clean_git=True)
    except ContractError as exc:
        raise FormalSummaryBlocked(str(exc)) from exc
    runs = _select_case_records(all_runs, case_ids, "run_records")
    results = _select_case_records(results, case_ids, "eval_results")
    if eval_specs is None:
        raise FormalSummaryBlocked("formal summary requires the bound evaluation specifications")

    runs_by_task = unique_index(runs, "task_run_id", "run_records")
    results_by_task = unique_index(results, "task_run_id", "eval_results")
    unique_index(runs, "case_id", "run_records")
    unique_index(results, "case_id", "eval_results")

    run_ids = set(runs_by_task)
    result_ids = set(results_by_task)
    missing = sorted(run_ids - result_ids)
    extra = sorted(result_ids - run_ids)
    if missing or extra:
        raise FormalSummaryBlocked(
            f"eval result task_run_ids do not exactly match run records; missing={missing}, extra={extra}"
        )

    specs = _records(eval_specs, loader=load_eval_spec_records, validator=validate_eval_spec_record)
    specs = _select_case_records(specs, case_ids, "eval_specs")
    specs_by_case = unique_index(specs, "case_id", "eval_specs")
    run_case_ids = {run["case_id"] for run in runs}
    missing_specs = sorted(run_case_ids - set(specs_by_case))
    extra_specs = sorted(set(specs_by_case) - run_case_ids)
    if missing_specs or extra_specs:
        raise FormalSummaryBlocked(
            f"eval spec case IDs do not exactly match run records; missing={missing_specs}, extra={extra_specs}"
        )

    ordered_results: list[dict[str, Any]] = []
    eval_error_cases: list[str] = []
    incomplete_usage_cases: list[str] = []
    zero_call_cases: list[str] = []
    for run in runs:
        result = results_by_task[run["task_run_id"]]
        if result["case_id"] != run["case_id"]:
            raise FormalSummaryBlocked(
                f"task_run_id {run['task_run_id']} has mismatched case IDs in run and eval result"
            )
        if result["batch_run_id"] != run["batch_run_id"]:
            raise FormalSummaryBlocked(
                f"task_run_id {run['task_run_id']} has mismatched batch_run_id in run and eval result"
            )
        spec = specs_by_case[run["case_id"]]
        try:
            validated_result = validate_eval_result(result, eval_spec=spec)
        except ContractError as exc:
            raise FormalSummaryBlocked(f"invalid eval result for {run['case_id']}: {exc}") from exc
        if validated_result["status"] != "completed":
            eval_error_cases.append(run["case_id"])
        if not run["model_usage"]["usage_complete"]:
            incomplete_usage_cases.append(run["case_id"])
        if run["model_usage"]["llm_call_count"] == 0:
            zero_call_cases.append(run["case_id"])
        ordered_results.append(validated_result)

    if eval_error_cases:
        raise FormalSummaryBlocked(
            "technical evaluator failures must be retried or resolved before formal summary: "
            + ", ".join(eval_error_cases)
        )
    if incomplete_usage_cases:
        raise FormalSummaryBlocked(
            "provider usage is incomplete; formal token/call metrics cannot be reported: "
            + ", ".join(incomplete_usage_cases)
        )
    if zero_call_cases:
        raise FormalSummaryBlocked(
            "formal task runs must contain at least one tested-model call: "
            + ", ".join(zero_call_cases)
        )

    task_count = len(runs)
    passed_count = sum(1 for result in ordered_results if result["pass"] is True)
    failed_count = task_count - passed_count
    success_rate = passed_count / task_count
    mean_llm_calls = _mean([float(run["model_usage"]["llm_call_count"]) for run in runs])
    mean_input_tokens = _mean([float(run["model_usage"]["input_tokens"]) for run in runs])
    mean_output_tokens = _mean([float(run["model_usage"]["output_tokens"]) for run in runs])
    mean_total_tokens = _mean([float(run["model_usage"]["total_tokens"]) for run in runs])
    mean_wall_time = _mean([float(run["wall_clock_seconds"]) for run in runs])
    internal_evidence_rows = [
        run.get("internal_evidence")
        for run in runs
        if isinstance(run.get("internal_evidence"), Mapping)
    ]
    package_types = (
        "TaskPlan",
        "EventContext",
        "ObservationPackage",
        "AnalysisPackage",
        "EvidenceReport",
    )
    package_counts = {
        package_type: sum(
            int(row.get("package_counts", {}).get(package_type, 0))
            for row in internal_evidence_rows
        )
        for package_type in package_types
    }

    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "status": "completed",
        "batch_run_id": batch_context["batch_run_id"],
        "architecture_mode": batch_context["environment"]["architecture_mode"],
        "system_snapshot_sha256": batch_context["environment"].get(
            "system_snapshot_sha256"
        ),
        "generated_at": timestamp,
        "task_run_count": task_count,
        "passed_task_runs": passed_count,
        "failed_task_runs": failed_count,
        "metrics": {
            "final_task_success_rate": success_rate,
            "mean_llm_calls_per_task_run": mean_llm_calls,
            "mean_tokens_per_task_run": {
                "input": mean_input_tokens,
                "output": mean_output_tokens,
                "total": mean_total_tokens,
            },
            "mean_wall_time_seconds_per_task_run": mean_wall_time,
        },
        # Flat fields keep tabular exports straightforward while ``metrics``
        # preserves the four conceptual paper metrics.
        "final_task_success_rate": success_rate,
        "final_task_success_rate_percent": success_rate * 100.0,
        "mean_llm_calls_per_task_run": mean_llm_calls,
        "mean_input_tokens_per_task_run": mean_input_tokens,
        "mean_output_tokens_per_task_run": mean_output_tokens,
        "mean_total_tokens_per_task_run": mean_total_tokens,
        "mean_wall_time_seconds_per_task_run": mean_wall_time,
        "provider_usage_complete_for_all_runs": True,
        "internal_evidence": {
            "present_for_all_runs": len(internal_evidence_rows) == task_count,
            "valid_for_all_present_runs": all(
                row.get("valid") is True for row in internal_evidence_rows
            ),
            "package_counts": package_counts,
        },
    }
    if output_path is not None:
        atomic_write_json(Path(output_path), summary)
    return summary
