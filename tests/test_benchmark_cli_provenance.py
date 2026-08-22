from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmark_runtime import CASE_SCHEMA, EVAL_RESULT_SCHEMA, EVAL_SPEC_SCHEMA, RUN_SCHEMA
from benchmark_runtime.cli import build_parser, main as cli_main
from benchmark_runtime.contracts import (
    ContractError,
    UnsafePathError,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_sha256,
)
from benchmark_runtime.eval_packets import build_eval_packets, load_eval_packet


NOW = "2026-08-09T08:00:00+00:00"
LATER = "2026-08-09T08:00:01+00:00"


def _case(case_id: str) -> dict[str, object]:
    return {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "prompt": f"Complete {case_id}.",
        "inputs": [],
        "metadata": {},
    }


def _eval_spec(case_id: str) -> dict[str, object]:
    return {
        "schema_version": EVAL_SPEC_SCHEMA,
        "case_id": case_id,
        "mode": "gold_compare",
        "mandatory_criteria": [
            {"criterion_id": "answer-correct", "description": "The answer is correct."}
        ],
        "reference": {"expected": "done"},
        "authoritative_sources": [],
        "notes": "",
    }


def _run_record(
    tmp_path: Path,
    case: dict[str, object],
    *,
    cases_sha256: str,
) -> dict[str, object]:
    case_id = str(case["case_id"])
    workspace = (tmp_path / "workspaces" / case_id).resolve()
    (workspace / "outputs").mkdir(parents=True)
    return {
        "schema_version": RUN_SCHEMA,
        "batch_run_id": "batch-provenance",
        "task_run_id": f"run-{case_id}",
        "case_id": case_id,
        "thread_id": f"thread-{case_id}",
        "started_at": NOW,
        "ended_at": LATER,
        "wall_clock_seconds": 1.0,
        "terminal_state": "succeeded",
        "final_answer": "done",
        "artifacts": [],
        "tool_trace": [],
        "model_usage": {
            "llm_call_count": 1,
            "calls": [
                {
                    "sequence": 1,
                    "status": "completed",
                    "requested_model_id": "test-model",
                    "provider_reported_model_id": "test-model",
                    "provider_request_id": f"request-{case_id}",
                    "model_identity_matches_tested": True,
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                    "usage_complete": True,
                }
            ],
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 3,
            "usage_complete": True,
            "incomplete_reasons": [],
        },
        "errors": [],
        "environment": {
            "workspace": str(workspace),
            "model": "test-model",
            "request_timeout_seconds": 120,
            "task_timeout_seconds": 1800.0,
            "recursion_limit": 200,
            "system_git_sha": "a" * 40,
            "system_git_dirty": False,
            "system_git_status_sha256": "b" * 64,
            "cases_sha256": cases_sha256,
            "case_sha256": canonical_json_sha256(case),
            "python_version": "3.11-test",
            "platform": "windows-test",
            "wall_clock_scope": "parent_process_start_to_worker_exit",
        },
    }


def _eval_result(packet: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": EVAL_RESULT_SCHEMA,
        "batch_run_id": packet["batch_run_id"],
        "case_id": packet["case_id"],
        "task_run_id": packet["task_run_id"],
        "eval_spec_sha256": packet["eval_spec_sha256"],
        "status": "completed",
        "pass": True,
        "mandatory_criteria": [
            {
                "criterion_id": "answer-correct",
                "passed": True,
                "reason": "The final answer matches the reference.",
                "evidence": [
                    {
                        "kind": "answer",
                        "location": "final_answer",
                        "observation": "done",
                    }
                ],
            }
        ],
        "resolved_reference": None,
        "source_checks": [],
        "artifacts_checked": [],
        "summary": "passed",
        "worker": {"role": "luna_worker", "model": "gpt-5.6-luna", "attempt": 1},
        "timestamps": {"started_at": NOW, "ended_at": LATER},
        "errors": [],
    }


def _materialize_evaluation(
    tmp_path: Path, case_ids: list[str]
) -> dict[str, object]:
    cases = [_case(case_id) for case_id in case_ids]
    specs = [_eval_spec(case_id) for case_id in case_ids]
    cases_path = tmp_path / "cases.jsonl"
    specs_path = tmp_path / "eval-specs.jsonl"
    runs_path = tmp_path / "task-runs.jsonl"
    atomic_write_jsonl(cases_path, cases)
    atomic_write_jsonl(specs_path, specs)
    cases_sha256 = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    runs = [_run_record(tmp_path, case, cases_sha256=cases_sha256) for case in cases]
    atomic_write_jsonl(runs_path, runs)

    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "luna-results"
    packet_paths = build_eval_packets(
        cases_path,
        specs_path,
        runs_path,
        packet_dir=packet_dir,
        result_dir=result_dir,
        created_at=NOW,
    )
    packets = [load_eval_packet(path) for path in packet_paths]
    for packet in packets:
        atomic_write_json(packet["result_path"], _eval_result(packet))

    collected_path = tmp_path / "evaluation" / "eval-results.jsonl"
    assert (
        cli_main(
            [
                "collect-eval",
                "--packet-dir",
                str(packet_dir),
                "--result-dir",
                str(result_dir),
                "--output",
                str(collected_path),
            ]
        )
        == 0
    )
    return {
        "cases": cases,
        "specs_path": specs_path,
        "runs": runs,
        "runs_path": runs_path,
        "packets": packets,
        "packet_dir": packet_dir,
        "collected_path": collected_path,
    }


def test_summarize_requires_verified_packets_and_rejects_forged_result_jsonl(
    tmp_path: Path,
) -> None:
    fixture = _materialize_evaluation(tmp_path, ["case-alpha"])
    valid_summary = tmp_path / "evaluation" / "summary.json"
    assert (
        cli_main(
            [
                "summarize",
                "--run-records",
                str(fixture["runs_path"]),
                "--eval-results",
                str(fixture["collected_path"]),
                "--eval-specs",
                str(fixture["specs_path"]),
                "--packet-dir",
                str(fixture["packet_dir"]),
                "--output",
                str(valid_summary),
            ]
        )
        == 0
    )

    forged = [
        json.loads(line)
        for line in Path(fixture["collected_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    forged[0]["eval_spec_sha256"] = "f" * 64
    forged_path = tmp_path / "evaluation" / "forged-eval-results.jsonl"
    atomic_write_jsonl(forged_path, forged)
    with pytest.raises(ContractError, match="eval_spec_sha256 does not match eval_spec"):
        cli_main(
            [
                "summarize",
                "--run-records",
                str(fixture["runs_path"]),
                "--eval-results",
                str(forged_path),
                "--eval-specs",
                str(fixture["specs_path"]),
                "--packet-dir",
                str(fixture["packet_dir"]),
                "--output",
                str(tmp_path / "evaluation" / "forged-summary.json"),
            ]
        )


def test_subset_summary_protects_every_manifest_workspace(tmp_path: Path) -> None:
    fixture = _materialize_evaluation(tmp_path, ["case-alpha", "case-beta"])
    unselected_workspace = Path(fixture["runs"][1]["environment"]["workspace"])
    result_root = Path(fixture["packets"][0]["result_path"]).parent
    unsafe_outputs = [
        Path(fixture["packet_dir"]) / "forbidden-summary.json",
        result_root / "forbidden-summary.json",
        unselected_workspace / "forbidden-summary.json",
    ]
    for unsafe_output in unsafe_outputs:
        with pytest.raises(UnsafePathError, match="every tested-workspace"):
            cli_main(
                [
                    "summarize",
                    "--run-records",
                    str(fixture["runs_path"]),
                    "--eval-results",
                    str(fixture["collected_path"]),
                    "--eval-specs",
                    str(fixture["specs_path"]),
                    "--packet-dir",
                    str(fixture["packet_dir"]),
                    "--case-id",
                    "case-alpha",
                    "--output",
                    str(unsafe_output),
                ]
            )


def test_subset_prepare_and_collect_protect_unselected_batch_workspace(
    tmp_path: Path,
) -> None:
    cases = [_case("case-alpha"), _case("case-beta")]
    specs = [_eval_spec("case-alpha"), _eval_spec("case-beta")]
    cases_path = tmp_path / "cases.jsonl"
    specs_path = tmp_path / "eval-specs.jsonl"
    runs_path = tmp_path / "task-runs.jsonl"
    atomic_write_jsonl(cases_path, cases)
    atomic_write_jsonl(specs_path, specs)
    cases_sha256 = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    runs = [_run_record(tmp_path, case, cases_sha256=cases_sha256) for case in cases]
    atomic_write_jsonl(runs_path, runs)
    unselected_workspace = Path(runs[1]["environment"]["workspace"])

    with pytest.raises(UnsafePathError, match="outside every batch workspace"):
        build_eval_packets(
            cases_path,
            specs_path,
            runs_path,
            packet_dir=unselected_workspace / "packets",
            result_dir=unselected_workspace / "results",
            created_at=NOW,
            case_ids=["case-alpha"],
        )

    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "results"
    packet_path = build_eval_packets(
        cases_path,
        specs_path,
        runs_path,
        packet_dir=packet_dir,
        result_dir=result_dir,
        created_at=NOW,
        case_ids=["case-alpha"],
    )[0]
    packet = load_eval_packet(packet_path)
    assert str(unselected_workspace.resolve()) in packet["protected_workspace_paths"]
    atomic_write_json(packet["result_path"], _eval_result(packet))
    with pytest.raises(UnsafePathError, match="tested-workspace roots"):
        cli_main(
            [
                "collect-eval",
                "--packet-dir",
                str(packet_dir),
                "--result-dir",
                str(result_dir),
                "--output",
                str(unselected_workspace / "forbidden-eval-results.jsonl"),
            ]
        )


def test_summarize_rejects_run_and_spec_changes_after_packet_creation(tmp_path: Path) -> None:
    fixture = _materialize_evaluation(tmp_path, ["case-alpha"])

    tampered_runs = json.loads(json.dumps(fixture["runs"]))
    tampered_runs[0]["model_usage"]["calls"][0].update(
        {"input_tokens": 3, "total_tokens": 4}
    )
    tampered_runs[0]["model_usage"].update({"input_tokens": 3, "total_tokens": 4})
    tampered_runs_path = tmp_path / "tampered-runs.jsonl"
    atomic_write_jsonl(tampered_runs_path, tampered_runs)
    with pytest.raises(ContractError, match="run record changed after evaluation packet creation"):
        cli_main(
            [
                "summarize",
                "--run-records",
                str(tampered_runs_path),
                "--eval-results",
                str(fixture["collected_path"]),
                "--eval-specs",
                str(fixture["specs_path"]),
                "--packet-dir",
                str(fixture["packet_dir"]),
                "--output",
                str(tmp_path / "run-tamper-summary.json"),
            ]
        )

    tampered_specs = [_eval_spec("case-alpha")]
    tampered_specs[0]["reference"] = {"expected": "different"}
    tampered_specs_path = tmp_path / "tampered-specs.jsonl"
    atomic_write_jsonl(tampered_specs_path, tampered_specs)
    with pytest.raises(ContractError, match="eval spec changed after evaluation packet creation"):
        cli_main(
            [
                "summarize",
                "--run-records",
                str(fixture["runs_path"]),
                "--eval-results",
                str(fixture["collected_path"]),
                "--eval-specs",
                str(tampered_specs_path),
                "--packet-dir",
                str(fixture["packet_dir"]),
                "--output",
                str(tmp_path / "spec-tamper-summary.json"),
            ]
        )


def test_summarize_parser_requires_packet_dir() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "summarize",
                "--run-records",
                "runs.jsonl",
                "--eval-results",
                "eval-results.jsonl",
                "--eval-specs",
                "eval-specs.jsonl",
                "--output",
                "summary.json",
            ]
        )
