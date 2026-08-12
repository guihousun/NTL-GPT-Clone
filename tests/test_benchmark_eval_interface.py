from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmark_runtime import (
    CASE_SCHEMA,
    EVAL_PACKET_SCHEMA,
    EVAL_RESULT_SCHEMA,
    EVAL_SPEC_SCHEMA,
    RUN_SCHEMA,
    SUMMARY_SCHEMA,
)
from benchmark_runtime.contracts import (
    ContractError,
    DuplicateRecordError,
    UnsafePathError,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_sha256,
    load_case_records,
    validate_case_record,
    validate_eval_spec_record,
    validate_eval_result,
    validate_run_batch,
    validate_run_record,
)
from benchmark_runtime.cli import main as cli_main
from benchmark_runtime.eval_packets import (
    build_eval_packets,
    load_eval_packet,
    verified_packet_paths,
)
from benchmark_runtime.summary import FormalSummaryBlocked, aggregate_metrics


NOW = "2026-08-09T08:00:00+00:00"
LATER = "2026-08-09T08:00:02+00:00"


def _case(case_id: str = "case-alpha") -> dict:
    return {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "prompt": "请检查夜间灯光结果。",
        "inputs": [
            {
                "source_path": "fixtures/source.csv",
                "target_path": "inputs/source.csv",
                "sha256": "a" * 64,
            }
        ],
        "metadata": {},
    }


def _eval_spec(case_id: str = "case-alpha", *, mode: str = "gold_compare") -> dict:
    return {
        "schema_version": EVAL_SPEC_SCHEMA,
        "case_id": case_id,
        "mode": mode,
        "mandatory_criteria": [
            {"criterion_id": "answer-correct", "description": "Answer is correct."},
            {"criterion_id": "artifact-valid", "description": "Artifact is valid."},
        ],
        "reference": {"expected": 42} if mode == "gold_compare" else {"date": "{{TEST_DATE}}"},
        "authoritative_sources": [] if mode == "gold_compare" else ["https://authority.example/data"],
        "notes": "",
    }


def _workspace(tmp_path: Path, case_id: str) -> tuple[Path, dict]:
    workspace = tmp_path / "workspaces" / case_id
    output = workspace / "outputs" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text(f"artifact for {case_id}\n", encoding="utf-8")
    data = output.read_bytes()
    artifact = {
        "relative_path": "outputs/result.txt",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    return workspace.resolve(), artifact


def _run_record(
    tmp_path: Path,
    case_id: str = "case-alpha",
    *,
    task_run_id: str | None = None,
    terminal_state: str = "succeeded",
    usage_complete: bool = True,
    llm_calls: int = 2,
    input_tokens: int = 20,
    output_tokens: int = 10,
    total_tokens: int = 30,
    wall_time: float = 2.0,
) -> dict:
    workspace, artifact = _workspace(tmp_path, case_id)
    input_parts = [input_tokens // llm_calls] * llm_calls if llm_calls else []
    output_parts = [output_tokens // llm_calls] * llm_calls if llm_calls else []
    for index in range(input_tokens % llm_calls if llm_calls else 0):
        input_parts[index] += 1
    for index in range(output_tokens % llm_calls if llm_calls else 0):
        output_parts[index] += 1
    calls = [
        {
            "sequence": index + 1,
            "status": "completed",
            "requested_model_id": "test-model",
            "provider_reported_model_id": "test-model-202608",
            "provider_request_id": f"request-{index + 1}",
            "model_identity_matches_tested": True,
            "input_tokens": input_parts[index],
            "output_tokens": output_parts[index],
            "total_tokens": input_parts[index] + output_parts[index],
            "usage_complete": True,
        }
        for index in range(llm_calls)
    ]
    return {
        "schema_version": RUN_SCHEMA,
        "batch_run_id": "batch-one",
        "task_run_id": task_run_id or f"run-{case_id}",
        "case_id": case_id,
        "thread_id": f"thread-{case_id}",
        "started_at": NOW,
        "ended_at": LATER,
        "wall_clock_seconds": wall_time,
        "terminal_state": terminal_state,
        "final_answer": "The answer is 42." if terminal_state == "succeeded" else None,
        "artifacts": [artifact],
        "tool_trace": [{"tool": "inspect", "status": "completed"}],
        "model_usage": {
            "llm_call_count": llm_calls,
            "calls": calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "usage_complete": usage_complete,
        },
        "errors": [] if terminal_state == "succeeded" else [{"code": "TIMEOUT", "message": "timed out"}],
        "environment": {
            "workspace": str(workspace),
            "python": "test",
            "model": "test-model",
            "architecture_mode": "full",
            "request_timeout_seconds": 120,
            "task_timeout_seconds": 1800.0,
            "recursion_limit": 200,
            "system_git_sha": "a" * 40,
            "system_git_dirty": False,
            "system_git_status_sha256": "b" * 64,
            "cases_sha256": "c" * 64,
            "case_sha256": canonical_json_sha256(_case(case_id)),
            "python_version": "3.11-test",
            "platform": "windows-test",
            "wall_clock_scope": "parent_process_start_to_worker_exit",
        },
    }


def _eval_result(
    case_id: str = "case-alpha",
    *,
    task_run_id: str | None = None,
    passed: bool = True,
    status: str = "completed",
    resolved_reference: object = None,
    artifact_absolute_path: str = "C:/benchmark-fixture/outputs/result.txt",
    mode: str = "gold_compare",
) -> dict:
    criteria = [
        {
            "criterion_id": "answer-correct",
            "passed": passed,
            "reason": "checked answer",
            "evidence": [
                {"kind": "answer", "location": "final_answer", "observation": "checked"}
            ],
        },
        {
            "criterion_id": "artifact-valid",
            "passed": passed,
            "reason": "checked artifact",
            "evidence": [
                {
                    "kind": "artifact",
                    "location": artifact_absolute_path,
                    "observation": "checked",
                }
            ],
        },
    ]
    return {
        "schema_version": EVAL_RESULT_SCHEMA,
        "batch_run_id": "batch-one",
        "case_id": case_id,
        "task_run_id": task_run_id or f"run-{case_id}",
        "eval_spec_sha256": canonical_json_sha256(_eval_spec(case_id, mode=mode)),
        "status": status,
        "pass": passed if status == "completed" else None,
        "mandatory_criteria": criteria if status == "completed" else [],
        "resolved_reference": resolved_reference,
        "source_checks": [],
        "artifacts_checked": [
            {
                "relative_path": "outputs/result.txt",
                "absolute_path": artifact_absolute_path,
                "status": "checked",
                "evidence": "artifact content inspected",
            }
        ],
        "summary": "evaluation complete" if status == "completed" else "evaluator failed",
        "worker": {"role": "luna_worker", "model": "gpt-5.6-luna", "attempt": 1},
        "timestamps": {"started_at": NOW, "ended_at": LATER},
        "errors": [] if status == "completed" else [{"code": "TOOL_ERROR", "message": "source unavailable"}],
    }


def test_case_jsonl_is_utf8_and_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    atomic_write_jsonl(path, [_case()])

    assert "夜间灯光" in path.read_text(encoding="utf-8")
    assert load_case_records(path)[0]["case_id"] == "case-alpha"

    atomic_write_jsonl(path, [_case(), _case()])
    with pytest.raises(DuplicateRecordError, match="duplicate case_id"):
        load_case_records(path)

    atomic_write_jsonl(path, [_case("Case-A"), _case("case-a")])
    with pytest.raises(DuplicateRecordError, match="duplicate case_id"):
        load_case_records(path)


@pytest.mark.parametrize("unsafe", ["../escape.csv", "/absolute.csv", "C:\\escape.csv", "inputs/../escape.csv"])
def test_case_target_path_rejects_traversal_and_absolute_paths(unsafe: str) -> None:
    case = _case()
    case["inputs"][0]["target_path"] = unsafe
    with pytest.raises(UnsafePathError):
        validate_case_record(case)


def test_run_record_validates_generic_usage_and_artifact_fields(tmp_path: Path) -> None:
    record = _run_record(tmp_path)
    assert validate_run_record(record)["model_usage"]["total_tokens"] == 30

    record["model_usage"]["llm_call_count"] = 1
    with pytest.raises(ContractError, match="must equal len"):
        validate_run_record(record)

    record = _run_record(tmp_path, case_id="bad-terminal")
    record["terminal_state"] = "maybe"
    with pytest.raises(ContractError, match="terminal_state"):
        validate_run_record(record)


def test_build_eval_packet_inspects_real_artifact_and_stays_outside_workspace(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_paths = build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=tmp_path / "eval" / "packets",
        result_dir=tmp_path / "eval" / "results",
        created_at=NOW,
    )

    assert len(packet_paths) == 1
    assert (tmp_path / "eval" / "results").is_dir()
    assert (tmp_path / "eval" / "packets" / "packet-manifest.json").is_file()
    packet = load_eval_packet(packet_paths[0])
    assert packet["schema_version"] == EVAL_PACKET_SCHEMA
    assert packet["read_only_rules"]["must_not_modify_tested_files"] is True
    assert packet["final_answer"] == run["final_answer"]
    assert packet["tool_trace"] == run["tool_trace"]
    assert packet["artifacts"][0]["verified_at_packet_build"] is True
    assert Path(packet["artifacts"][0]["absolute_path"]).is_file()
    assert Path(packet["artifact_root"]) == Path(run["environment"]["workspace"]) / "outputs"
    assert not Path(packet["result_path"]).is_relative_to(Path(run["environment"]["workspace"]))
    artifact_path = packet["artifacts"][0]["absolute_path"]
    assert (
        validate_eval_result(
            _eval_result(artifact_absolute_path=artifact_path), eval_packet=packet
        )["pass"]
        is True
    )

    unchecked = _eval_result(artifact_absolute_path=artifact_path)
    unchecked["artifacts_checked"] = []
    with pytest.raises(ContractError, match="account for every packet artifact"):
        validate_eval_result(unchecked, eval_packet=packet)

    unsafe_result = Path(run["environment"]["workspace"]) / "outputs" / "forbidden.json"
    packet["result_path"] = str(unsafe_result)
    packet["read_only_rules"]["allowed_write_paths"] = [str(unsafe_result)]
    atomic_write_json(packet_paths[0], packet)
    with pytest.raises(UnsafePathError, match="result_path must be outside"):
        load_eval_packet(packet_paths[0])


def test_build_eval_packet_rejects_tampered_artifact_and_workspace_result_path(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    artifact_path = Path(run["environment"]["workspace"]) / "outputs" / "result.txt"
    artifact_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ContractError, match="artifact (size|sha256) changed"):
        build_eval_packets(
            [_case()],
            [_eval_spec()],
            [run],
            packet_dir=tmp_path / "eval" / "packets",
            result_dir=tmp_path / "eval" / "results",
        )


def test_packet_and_workspace_mutation_are_rejected_before_collection(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "results"
    packet_path = build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=packet_dir,
        result_dir=result_dir,
        created_at=NOW,
    )[0]
    packet = load_eval_packet(packet_path)
    Path(run["environment"]["workspace"], "inputs", "unexpected.txt").parent.mkdir(
        parents=True, exist_ok=True
    )
    Path(run["environment"]["workspace"], "inputs", "unexpected.txt").write_text(
        "mutation", encoding="utf-8"
    )
    with pytest.raises(ContractError, match="workspace changed"):
        load_eval_packet(packet_path)

    # Rebuild in a separate fixture, then prove the manifest catches packet edits.
    run_two = _run_record(tmp_path, case_id="case-delta")
    packet_dir_two = tmp_path / "evaluation-two" / "packets"
    result_dir_two = tmp_path / "evaluation-two" / "results"
    packet_path_two = build_eval_packets(
        [_case("case-delta")],
        [_eval_spec("case-delta")],
        [run_two],
        packet_dir=packet_dir_two,
        result_dir=result_dir_two,
        created_at=NOW,
    )[0]
    tampered_packet = json.loads(packet_path_two.read_text(encoding="utf-8"))
    tampered_packet["final_answer"] = "tampered"
    atomic_write_json(packet_path_two, tampered_packet)
    with pytest.raises(ContractError, match="packet checksum changed"):
        cli_main(
            [
                "collect-eval",
                "--packet-dir",
                str(packet_dir_two),
                "--result-dir",
                str(result_dir_two),
                "--output",
                str(tmp_path / "never-written.jsonl"),
            ]
        )

    run = _run_record(tmp_path, case_id="case-beta")
    workspace = Path(run["environment"]["workspace"])
    with pytest.raises(UnsafePathError, match="must be outside"):
        build_eval_packets(
            [_case("case-beta")],
            [_eval_spec("case-beta")],
            [run],
            packet_dir=tmp_path / "eval" / "packets",
            result_dir=workspace / "eval-results",
        )

    run = _run_record(tmp_path, case_id="case-gamma")
    workspace = Path(run["environment"]["workspace"])
    (workspace / "outputs" / "unrecorded.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ContractError, match="does not exactly match"):
        build_eval_packets(
            [_case("case-gamma")],
            [_eval_spec("case-gamma")],
            [run],
            packet_dir=tmp_path / "eval" / "packets",
            result_dir=tmp_path / "eval" / "results",
        )


def test_packet_directory_rejects_unmanifested_files_and_directories(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_dir = tmp_path / "evaluation" / "packets"
    build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=packet_dir,
        result_dir=tmp_path / "evaluation" / "results",
        created_at=NOW,
    )
    (packet_dir / "notes.txt").write_text("unauthorized", encoding="utf-8")
    with pytest.raises(ContractError, match="exactly match packet manifest"):
        verified_packet_paths(packet_dir)


def test_eval_packet_rejects_case_identity_mismatch_with_nested_run(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_path = build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=tmp_path / "evaluation" / "packets",
        result_dir=tmp_path / "evaluation" / "results",
        created_at=NOW,
    )[0]
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["run_record"]["case_id"] = "case-other"
    atomic_write_json(packet_path, packet)
    with pytest.raises(ContractError, match="case identifiers are inconsistent"):
        load_eval_packet(packet_path)


def test_formal_batch_requires_clean_git_and_bound_provider_model(tmp_path: Path) -> None:
    dirty = _run_record(tmp_path, case_id="case-dirty")
    dirty["environment"]["system_git_dirty"] = True
    with pytest.raises(ContractError, match="clean Git worktree"):
        validate_run_batch([dirty], require_clean_git=True)

    mismatched = _run_record(tmp_path, case_id="case-model")
    mismatched["model_usage"]["calls"][0]["provider_reported_model_id"] = "other-model"
    with pytest.raises(ContractError, match="does not match.*environment.model"):
        validate_run_batch([mismatched])

    invalid_mode = _run_record(tmp_path, case_id="case-invalid-mode")
    invalid_mode["environment"]["architecture_mode"] = "multi"
    with pytest.raises(ContractError, match="architecture_mode"):
        validate_run_batch([invalid_mode])


def test_collect_rejects_any_file_beyond_authorized_luna_results(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "results"
    packet_path = build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=packet_dir,
        result_dir=result_dir,
        created_at=NOW,
    )[0]
    packet = load_eval_packet(packet_path)
    atomic_write_json(
        packet["result_path"],
        _eval_result(artifact_absolute_path=packet["artifacts"][0]["absolute_path"]),
    )
    (result_dir / "notes.txt").write_text("unauthorized", encoding="utf-8")
    with pytest.raises(ContractError, match="exactly match authorized"):
        cli_main(
            [
                "collect-eval",
                "--packet-dir",
                str(packet_dir),
                "--result-dir",
                str(result_dir),
                "--output",
                str(tmp_path / "eval-results.jsonl"),
            ]
        )


def test_prepare_requires_separate_fresh_packet_and_result_directories(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    shared = tmp_path / "shared-eval-dir"
    with pytest.raises(UnsafePathError, match="separate, non-nested"):
        build_eval_packets(
            [_case()],
            [_eval_spec()],
            [run],
            packet_dir=shared,
            result_dir=shared,
        )

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "notes.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(FileExistsError, match="completely empty"):
        build_eval_packets(
            [_case()],
            [_eval_spec()],
            [run],
            packet_dir=tmp_path / "packets",
            result_dir=result_dir,
        )


def test_collect_output_cannot_overwrite_packet_or_tested_workspace(tmp_path: Path) -> None:
    run = _run_record(tmp_path)
    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "results"
    packet_path = build_eval_packets(
        [_case()],
        [_eval_spec()],
        [run],
        packet_dir=packet_dir,
        result_dir=result_dir,
        created_at=NOW,
    )[0]
    packet = load_eval_packet(packet_path)
    atomic_write_json(
        packet["result_path"],
        _eval_result(artifact_absolute_path=packet["artifacts"][0]["absolute_path"]),
    )
    for unsafe_output in (
        packet_path,
        Path(run["environment"]["workspace"]) / "forbidden-eval-results.jsonl",
    ):
        with pytest.raises(UnsafePathError, match="outside packet, result, and tested-workspace"):
            cli_main(
                [
                    "collect-eval",
                    "--packet-dir",
                    str(packet_dir),
                    "--result-dir",
                    str(result_dir),
                    "--output",
                    str(unsafe_output),
                ]
            )


def test_eval_result_requires_all_criteria_and_live_resolution() -> None:
    result = _eval_result()
    result["mandatory_criteria"][1]["passed"] = False
    with pytest.raises(ContractError, match="must equal all"):
        validate_eval_result(result, eval_spec=_eval_spec())

    live = _eval_result(resolved_reference=None, mode="live_verify")
    with pytest.raises(ContractError, match="resolved_reference"):
        validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))

    live["resolved_reference"] = {"date": "2026-08-09", "value": 42}
    live["source_checks"] = [
        {
            "declared_source": "https://authority.example/data",
            "source": "https://authority.example/data",
            "checked_at": NOW,
            "status": "verified",
            "evidence": "dated value was verified",
        }
    ]
    assert validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))["pass"] is True

    live["source_checks"][0].pop("checked_at")
    with pytest.raises(ContractError, match="checked_at"):
        validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))


def test_eval_contract_rejects_untrusted_luna_evidence_and_sources() -> None:
    with pytest.raises(ContractError, match="must not be empty"):
        validate_eval_spec_record({**_eval_spec(mode="live_verify"), "authoritative_sources": []})

    wrong_worker = _eval_result()
    wrong_worker["worker"]["role"] = "judge"
    with pytest.raises(ContractError, match="luna_worker"):
        validate_eval_result(wrong_worker, eval_spec=_eval_spec())

    wrong_model = _eval_result()
    wrong_model["worker"]["model"] = "some-other-model"
    with pytest.raises(ContractError, match="gpt-5.6-luna"):
        validate_eval_result(wrong_model, eval_spec=_eval_spec())

    completed_with_error = _eval_result()
    completed_with_error["errors"] = [{"code": "SOURCE_TIMEOUT", "message": "not resolved"}]
    with pytest.raises(ContractError, match="must be empty"):
        validate_eval_result(completed_with_error, eval_spec=_eval_spec())

    wrong_spec_hash = _eval_result()
    wrong_spec_hash["eval_spec_sha256"] = "0" * 64
    with pytest.raises(ContractError, match="does not match eval_spec"):
        validate_eval_result(wrong_spec_hash, eval_spec=_eval_spec())

    no_evidence = _eval_result()
    no_evidence["mandatory_criteria"][0]["evidence"] = []
    with pytest.raises(ContractError, match="non-empty"):
        validate_eval_result(no_evidence, eval_spec=_eval_spec())

    live = _eval_result(resolved_reference={"date": "2026-08-09"}, mode="live_verify")
    live["source_checks"] = [
        {
            "declared_source": "https://untrusted.example/data",
            "source": "https://untrusted.example/data",
            "checked_at": NOW,
            "status": "verified",
            "evidence": "untrusted observation",
        }
    ]
    with pytest.raises(ContractError, match="declared authoritative sources"):
        validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))

    live["source_checks"][0]["declared_source"] = "https://authority.example/data"
    with pytest.raises(ContractError, match="not the declared authority"):
        validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))

    live["source_checks"][0]["source"] = "https://authority.example/data/resolved-observation"
    live["source_checks"][0]["checked_at"] = "2026-08-09T09:00:00+00:00"
    with pytest.raises(ContractError, match="within worker timestamps"):
        validate_eval_result(live, eval_spec=_eval_spec(mode="live_verify"))

    empty_reference = _eval_result(resolved_reference={}, mode="live_verify")
    with pytest.raises(ContractError, match="non-empty resolved_reference"):
        validate_eval_result(empty_reference, eval_spec=_eval_spec(mode="live_verify"))


def test_aggregate_metrics_keeps_failed_and_timed_out_runs_in_denominator(tmp_path: Path) -> None:
    successful_run = _run_record(
        tmp_path,
        "case-alpha",
        task_run_id="run-alpha",
        llm_calls=2,
        input_tokens=20,
        output_tokens=10,
        total_tokens=30,
        wall_time=2.0,
    )
    timed_out_run = _run_record(
        tmp_path,
        "case-beta",
        task_run_id="run-beta",
        terminal_state="timed_out",
        llm_calls=1,
        input_tokens=4,
        output_tokens=2,
        total_tokens=6,
        wall_time=6.0,
    )
    summary = aggregate_metrics(
        [successful_run, timed_out_run],
        [
            _eval_result("case-alpha", task_run_id="run-alpha", passed=True),
            _eval_result("case-beta", task_run_id="run-beta", passed=False),
        ],
        eval_specs=[_eval_spec("case-alpha"), _eval_spec("case-beta")],
        generated_at=NOW,
    )

    assert summary["schema_version"] == SUMMARY_SCHEMA
    assert summary["task_run_count"] == 2
    assert summary["passed_task_runs"] == 1
    assert summary["final_task_success_rate"] == 0.5
    assert summary["mean_llm_calls_per_task_run"] == 1.5
    assert summary["mean_input_tokens_per_task_run"] == 12.0
    assert summary["mean_output_tokens_per_task_run"] == 6.0
    assert summary["mean_total_tokens_per_task_run"] == 18.0
    assert summary["mean_wall_time_seconds_per_task_run"] == 4.0


@pytest.mark.parametrize("problem", ["missing", "eval_error", "incomplete_usage"])
def test_aggregate_metrics_blocks_nonformal_result_sets(tmp_path: Path, problem: str) -> None:
    run = _run_record(tmp_path, usage_complete=problem != "incomplete_usage")
    results = [] if problem == "missing" else [_eval_result(status="eval_error" if problem == "eval_error" else "completed")]
    with pytest.raises(FormalSummaryBlocked):
        aggregate_metrics([run], results, eval_specs=[_eval_spec()])

    zero_call_run = _run_record(
        tmp_path,
        case_id="zero-call",
        llm_calls=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )
    with pytest.raises(FormalSummaryBlocked, match="at least one tested-model call"):
        aggregate_metrics(
            [zero_call_run],
            [_eval_result("zero-call")],
            eval_specs=[_eval_spec("zero-call")],
        )


def test_mixed_batch_or_runtime_context_is_rejected(tmp_path: Path) -> None:
    run_a = _run_record(tmp_path, "case-alpha", task_run_id="run-alpha")
    run_b = _run_record(tmp_path, "case-beta", task_run_id="run-beta")
    run_b["batch_run_id"] = "batch-two"
    with pytest.raises(ContractError, match="same batch_run_id"):
        build_eval_packets(
            [_case("case-alpha"), _case("case-beta")],
            [_eval_spec("case-alpha"), _eval_spec("case-beta")],
            [run_a, run_b],
            packet_dir=tmp_path / "packets",
            result_dir=tmp_path / "results",
        )
    with pytest.raises(FormalSummaryBlocked, match="same batch_run_id"):
        aggregate_metrics(
            [run_a, run_b],
            [
                _eval_result("case-alpha", task_run_id="run-alpha"),
                _eval_result("case-beta", task_run_id="run-beta"),
            ],
            eval_specs=[_eval_spec("case-alpha"), _eval_spec("case-beta")],
        )

    run_b["batch_run_id"] = "batch-one"
    run_b["environment"]["architecture_mode"] = "single_agent"
    with pytest.raises(FormalSummaryBlocked, match="same architecture_mode"):
        aggregate_metrics(
            [run_a, run_b],
            [
                _eval_result("case-alpha", task_run_id="run-alpha"),
                _eval_result("case-beta", task_run_id="run-beta"),
            ],
            eval_specs=[_eval_spec("case-alpha"), _eval_spec("case-beta")],
        )
    with pytest.raises(FormalSummaryBlocked, match="same architecture_mode"):
        aggregate_metrics(
            [run_a, run_b],
            [_eval_result("case-alpha", task_run_id="run-alpha")],
            eval_specs=[_eval_spec("case-alpha")],
            case_ids=["case-alpha"],
        )

    run_b["environment"]["architecture_mode"] = "full"
    run_a["environment"]["model"] = "model-a"
    run_b["environment"]["model"] = "model-b"
    with pytest.raises(FormalSummaryBlocked, match="runtime context"):
        aggregate_metrics(
            [run_a, run_b],
            [
                _eval_result("case-alpha", task_run_id="run-alpha"),
                _eval_result("case-beta", task_run_id="run-beta"),
            ],
            eval_specs=[_eval_spec("case-alpha"), _eval_spec("case-beta")],
        )

    run_a = _run_record(tmp_path, "context-alpha", task_run_id="context-run")
    run_a["environment"].pop("model")
    with pytest.raises(FormalSummaryBlocked, match="missing required fields"):
        aggregate_metrics(
            [run_a],
            [_eval_result("context-alpha", task_run_id="context-run")],
            eval_specs=[_eval_spec("context-alpha")],
        )


def test_atomic_json_write_preserves_utf8_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    atomic_write_json(path, {"text": "中文", "value": 1})
    assert json.loads(path.read_text(encoding="utf-8"))["text"] == "中文"
    assert list(tmp_path.glob(".result.json.*.tmp")) == []


def test_interface_contains_no_benchmark_specific_ids_or_case_counts() -> None:
    root = Path(__file__).parents[1] / "benchmark_runtime"
    sources = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix in {".py", ".md"}
    )
    sources.append(Path(__file__).parents[1] / "batch_run.py")
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    for forbidden in (
        "BV1-",
        "OLD70-",
        "EXPECTED_TASK_IDS",
        "EXPECTED_TASK_COUNT",
        "range(70)",
        "range(100)",
        "range(300)",
        "exactly_one_record_for_each_of_100",
    ):
        assert forbidden not in text


def test_cli_external_eval_workflow_is_provider_free_and_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise packet creation, Luna-result collection, and summarization.

    The test deliberately starts from an already materialized run record, so it
    verifies the complete external-evaluation boundary without calling an LLM
    provider or importing the production agent graph.
    """

    cases_path = tmp_path / "cases.jsonl"
    specs_path = tmp_path / "eval-specs.jsonl"
    runs_path = tmp_path / "run-records.jsonl"
    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "luna-results"
    collected_path = tmp_path / "evaluation" / "eval-results.jsonl"
    summary_path = tmp_path / "evaluation" / "summary.json"

    atomic_write_jsonl(cases_path, [_case()])
    atomic_write_jsonl(specs_path, [_eval_spec()])
    run_record = _run_record(tmp_path)
    run_record["environment"]["cases_sha256"] = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    atomic_write_jsonl(runs_path, [run_record])

    assert (
        cli_main(
            [
                "prepare-eval",
                "--cases",
                str(cases_path),
                "--eval-specs",
                str(specs_path),
                "--run-records",
                str(runs_path),
                "--packet-dir",
                str(packet_dir),
                "--result-dir",
                str(result_dir),
            ]
        )
        == 0
    )
    packet = load_eval_packet(packet_dir / "case-alpha.eval-packet.json")
    atomic_write_json(
        Path(packet["result_path"]),
        _eval_result(artifact_absolute_path=packet["artifacts"][0]["absolute_path"]),
    )

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
    with pytest.raises(UnsafePathError, match="must not overwrite"):
        cli_main(
            [
                "summarize",
                "--run-records",
                str(runs_path),
                "--eval-results",
                str(collected_path),
                "--eval-specs",
                str(specs_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(runs_path),
            ]
        )
    assert (
        cli_main(
            [
                "summarize",
                "--run-records",
                str(runs_path),
                "--eval-results",
                str(collected_path),
                "--eval-specs",
                str(specs_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(summary_path),
            ]
        )
        == 0
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "completed"
    assert summary["architecture_mode"] == "full"
    assert summary["task_run_count"] == 1
    assert summary["final_task_success_rate"] == 1.0
    assert summary["mean_llm_calls_per_task_run"] == 2.0
    assert summary["mean_total_tokens_per_task_run"] == 30.0
    assert summary["mean_wall_time_seconds_per_task_run"] == 2.0
    assert "summary" in capsys.readouterr().out


def test_case_filter_supports_four_case_style_pilots_without_subset_files(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    specs_path = tmp_path / "eval-specs.jsonl"
    runs_path = tmp_path / "task-runs.jsonl"
    cases = [_case("case-alpha"), _case("case-beta")]
    specs = [_eval_spec("case-alpha"), _eval_spec("case-beta")]
    atomic_write_jsonl(cases_path, cases)
    atomic_write_jsonl(specs_path, specs)
    cases_sha256 = hashlib.sha256(cases_path.read_bytes()).hexdigest()
    runs = [
        _run_record(tmp_path, "case-alpha", task_run_id="run-alpha"),
        _run_record(tmp_path, "case-beta", task_run_id="run-beta"),
    ]
    for run in runs:
        run["environment"]["cases_sha256"] = cases_sha256
    atomic_write_jsonl(runs_path, runs)

    packet_dir = tmp_path / "evaluation" / "packets"
    result_dir = tmp_path / "evaluation" / "results"
    collected_path = tmp_path / "evaluation" / "eval-results.jsonl"
    summary_path = tmp_path / "evaluation" / "summary.json"
    assert (
        cli_main(
            [
                "prepare-eval",
                "--cases",
                str(cases_path),
                "--eval-specs",
                str(specs_path),
                "--run-records",
                str(runs_path),
                "--packet-dir",
                str(packet_dir),
                "--result-dir",
                str(result_dir),
                "--case-id",
                "case-alpha",
            ]
        )
        == 0
    )
    packet = load_eval_packet(packet_dir / "case-alpha.eval-packet.json")
    atomic_write_json(
        packet["result_path"],
        _eval_result(
            "case-alpha",
            task_run_id="run-alpha",
            artifact_absolute_path=packet["artifacts"][0]["absolute_path"],
        ),
    )
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
    assert (
        cli_main(
            [
                "summarize",
                "--run-records",
                str(runs_path),
                "--eval-results",
                str(collected_path),
                "--eval-specs",
                str(specs_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(summary_path),
                "--case-id",
                "case-alpha",
            ]
        )
        == 0
    )
    assert json.loads(summary_path.read_text(encoding="utf-8"))["task_run_count"] == 1
