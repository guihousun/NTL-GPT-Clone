from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import ARCHITECTURE_MODES
from .runner import MAX_BATCH_WORKERS, run_batch, worker_main


def _inside_or_equal(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def prepare_eval(args: argparse.Namespace) -> int:
    from .eval_packets import build_eval_packets

    paths = build_eval_packets(
        args.cases,
        args.eval_specs,
        args.run_records,
        packet_dir=args.packet_dir,
        result_dir=args.result_dir,
        case_ids=args.case_id,
    )
    print(
        json.dumps(
            {"packet_count": len(paths), "packet_paths": [str(path) for path in paths]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def collect_eval(args: argparse.Namespace) -> int:
    """Validate one Luna JSON per packet, then atomically write JSONL."""

    from .contracts import (
        ContractError,
        UnsafePathError,
        atomic_write_jsonl,
        path_is_linklike,
        unique_index,
        validate_eval_result,
    )
    from .eval_packets import load_eval_packet, verified_packet_paths

    declared_packet_dir = Path(args.packet_dir).expanduser()
    declared_result_dir = Path(args.result_dir).expanduser()
    if path_is_linklike(declared_packet_dir) or path_is_linklike(declared_result_dir):
        raise UnsafePathError("packet_dir and result_dir must not be links or junctions")
    packet_dir = declared_packet_dir.resolve()
    result_dir = declared_result_dir.resolve()
    if not packet_dir.is_dir():
        raise FileNotFoundError(packet_dir)
    if not result_dir.is_dir():
        raise FileNotFoundError(result_dir)
    packet_paths = verified_packet_paths(declared_packet_dir)
    packets = [load_eval_packet(path) for path in packet_paths]
    packets_by_case = unique_index(packets, "case_id", "eval_packets")
    expected_result_paths = {
        Path(packet["result_path"]).expanduser().resolve() for packet in packets
    }
    if any(path.parent != result_dir for path in expected_result_paths):
        raise ContractError("packet-authorized result paths must be direct children of result_dir")
    actual_entries = list(result_dir.iterdir())
    if any(
        not entry.is_file()
        or path_is_linklike(entry)
        or entry.stat().st_nlink > 1
        for entry in actual_entries
    ):
        raise ContractError("result_dir must contain only the authorized result files")
    actual_result_paths = {entry.absolute() for entry in actual_entries}
    if actual_result_paths != expected_result_paths:
        missing = sorted(str(path) for path in expected_result_paths - actual_result_paths)
        extra = sorted(str(path) for path in actual_result_paths - expected_result_paths)
        raise ContractError(
            f"result_dir does not exactly match authorized result paths; missing={missing}, extra={extra}"
        )
    result_paths = sorted(expected_result_paths, key=lambda path: path.name.casefold())
    results: list[dict[str, object]] = []
    for result_path in result_paths:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        preliminary = validate_eval_result(payload)
        case_id = preliminary["case_id"]
        packet = packets_by_case.get(case_id)
        if packet is None:
            raise ContractError(f"eval result has no matching packet: {case_id}")
        declared_result_path = Path(packet["result_path"]).expanduser().resolve()
        if result_path.resolve() != declared_result_path:
            raise ContractError(
                f"eval result is not at the packet-authorized write path for {case_id}: {result_path}"
            )
        results.append(validate_eval_result(preliminary, eval_packet=packet))

    results_by_case = unique_index(results, "case_id", "eval_results")
    missing = sorted(set(packets_by_case) - set(results_by_case))
    extra = sorted(set(results_by_case) - set(packets_by_case))
    if missing or extra:
        raise ContractError(
            f"eval results do not exactly match packets; missing={missing}, extra={extra}"
        )
    ordered = [results_by_case[packet["case_id"]] for packet in packets]
    output_path = Path(args.output).expanduser().resolve(strict=False)
    tested_workspaces = {
        Path(workspace_path).expanduser().resolve(strict=False)
        for packet in packets
        for workspace_path in packet["protected_workspace_paths"]
    }
    forbidden_roots = {packet_dir, result_dir, *tested_workspaces}
    if any(_inside_or_equal(output_path, root) for root in forbidden_roots):
        raise UnsafePathError("collect-eval output must be outside packet, result, and tested-workspace roots")
    if output_path.exists():
        raise FileExistsError(f"collect-eval output must be new: {output_path}")
    output = atomic_write_jsonl(output_path, ordered)
    print(json.dumps({"result_count": len(ordered), "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def summarize(args: argparse.Namespace) -> int:
    from .contracts import (
        ContractError,
        UnsafePathError,
        canonical_json_sha256,
        load_eval_result_records,
        load_eval_spec_records,
        load_run_records,
        unique_index,
        validate_eval_result,
    )
    from .eval_packets import load_eval_packet, verified_packet_paths
    from .summary import aggregate_metrics

    declared_packet_dir = Path(args.packet_dir).expanduser()
    packet_paths = verified_packet_paths(declared_packet_dir)
    packet_dir = declared_packet_dir.resolve()
    packets = [load_eval_packet(path) for path in packet_paths]
    packets_by_case = unique_index(packets, "case_id", "eval_packets")
    packets_by_task = unique_index(packets, "task_run_id", "eval_packets")

    eval_results = load_eval_result_records(args.eval_results)
    results_by_case = unique_index(eval_results, "case_id", "eval_results")
    results_by_task = unique_index(eval_results, "task_run_id", "eval_results")
    missing_cases = sorted(set(packets_by_case) - set(results_by_case))
    extra_cases = sorted(set(results_by_case) - set(packets_by_case))
    missing_tasks = sorted(set(packets_by_task) - set(results_by_task))
    extra_tasks = sorted(set(results_by_task) - set(packets_by_task))
    if missing_cases or extra_cases or missing_tasks or extra_tasks:
        raise ContractError(
            "eval results do not exactly match the verified packet manifest; "
            f"missing_cases={missing_cases}, extra_cases={extra_cases}, "
            f"missing_tasks={missing_tasks}, extra_tasks={extra_tasks}"
        )

    # Re-run the same packet-bound validation used by collect-eval.  Passing the
    # validated in-memory records to aggregation prevents a manually assembled
    # JSONL from bypassing artifact, source, task, batch, or eval-spec checks.
    validated_results: list[dict[str, object]] = []
    for packet in packets:
        result = results_by_case[packet["case_id"]]
        validated_results.append(validate_eval_result(result, eval_packet=packet))

    run_records = load_run_records(args.run_records)
    eval_specs = load_eval_spec_records(args.eval_specs)

    requested_ids = [str(value) for value in (args.case_id or [])]
    if len({value.casefold() for value in requested_ids}) != len(requested_ids):
        raise ContractError("selected case IDs must be unique ignoring case")

    def selected_by_case(
        records: list[dict[str, object]], label: str
    ) -> list[dict[str, object]]:
        if not requested_ids:
            return records
        indexed = unique_index(records, "case_id", label)
        missing = [case_id for case_id in requested_ids if case_id not in indexed]
        if missing:
            raise ContractError(f"selected case IDs are absent from {label}: {missing}")
        return [dict(indexed[case_id]) for case_id in requested_ids]

    selected_packets = selected_by_case(packets, "eval_packets")
    selected_runs = selected_by_case(run_records, "run_records")
    selected_specs = selected_by_case(eval_specs, "eval_specs")
    selected_results = selected_by_case(validated_results, "eval_results")
    selected_case_sets = {
        label: {record["case_id"] for record in records}
        for label, records in (
            ("eval_packets", selected_packets),
            ("run_records", selected_runs),
            ("eval_specs", selected_specs),
            ("eval_results", selected_results),
        )
    }
    expected_cases = selected_case_sets["eval_packets"]
    if any(case_ids != expected_cases for case_ids in selected_case_sets.values()):
        raise ContractError(
            "selected packet, run, eval-spec, and eval-result case sets must match exactly: "
            + repr(selected_case_sets)
        )

    selected_runs_by_case = unique_index(selected_runs, "case_id", "run_records")
    selected_specs_by_case = unique_index(selected_specs, "case_id", "eval_specs")
    for packet in selected_packets:
        case_id = packet["case_id"]
        run_record = selected_runs_by_case[case_id]
        eval_spec = selected_specs_by_case[case_id]
        if canonical_json_sha256(run_record) != canonical_json_sha256(packet["run_record"]):
            raise ContractError(f"run record changed after evaluation packet creation: {case_id}")
        if canonical_json_sha256(eval_spec) != packet["eval_spec_sha256"]:
            raise ContractError(f"eval spec changed after evaluation packet creation: {case_id}")
        if canonical_json_sha256(packet["case"]) != packet["run_record"]["environment"].get(
            "case_sha256"
        ):
            raise ContractError(f"packet case content does not match its recorded case hash: {case_id}")

    input_paths = {
        Path(args.run_records).expanduser().resolve(),
        Path(args.eval_results).expanduser().resolve(),
        Path(args.eval_specs).expanduser().resolve(),
        *packet_paths,
    }
    output_path = Path(args.output).expanduser().resolve(strict=False)
    if output_path in input_paths:
        raise UnsafePathError(
            "summary output must not overwrite a run, eval-result, eval-spec, or packet input"
        )
    # Use every packet in the verified manifest here, even for a --case-id
    # subset.  A subset summary must never be able to write into an unselected
    # task's tested workspace or evaluator result directory.
    workspaces = {
        Path(workspace_path).expanduser().resolve(strict=False)
        for packet in packets
        for workspace_path in packet["protected_workspace_paths"]
    }
    result_roots = {
        Path(packet["result_path"]).expanduser().resolve(strict=False).parent
        for packet in packets
    }
    forbidden_roots = {packet_dir, *result_roots, *workspaces}
    if any(_inside_or_equal(output_path, root) for root in forbidden_roots):
        raise UnsafePathError(
            "summary output must be outside packet, result, and every tested-workspace root"
        )
    if output_path.exists():
        raise FileExistsError(f"summary output must be new: {output_path}")

    summary = aggregate_metrics(
        run_records,
        validated_results,
        eval_specs=eval_specs,
        output_path=output_path,
        case_ids=args.case_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch_run.py",
        description="Case-agnostic NTL-GPT benchmark runner (evaluation is external).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run cases in fresh isolated worker processes.")
    run_parser.add_argument("--cases", required=True, help="ntl-benchmark.case.v1 JSONL file")
    run_parser.add_argument("--output-dir", required=True, help="new batch output directory")
    run_parser.add_argument("--model", required=True, help="NTL-GPT frontend model name")
    run_parser.add_argument(
        "--architecture-mode",
        required=True,
        choices=ARCHITECTURE_MODES,
        help="tested architecture: hierarchical Full system or matched Single-Agent",
    )
    run_parser.add_argument(
        "--resource-profile",
        choices=("standard", "tools_prompt_only"),
        default="standard",
        help="runtime resources: standard, or prompts plus registered tools only",
    )
    run_parser.add_argument(
        "--max-workers",
        type=int,
        default=MAX_BATCH_WORKERS,
        help=f"parallel task subprocesses (default and hard maximum: {MAX_BATCH_WORKERS})",
    )
    run_parser.add_argument("--task-timeout-seconds", type=float, default=1800.0)
    run_parser.add_argument("--request-timeout-seconds", type=int, default=120)
    run_parser.add_argument("--recursion-limit", type=int, default=200)
    run_parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="run only this case id; repeat the option for multiple cases",
    )
    run_parser.set_defaults(handler=run_batch)

    packet_parser = subparsers.add_parser(
        "prepare-eval", help="Build one read-only external-evaluation packet per task run."
    )
    packet_parser.add_argument("--cases", required=True)
    packet_parser.add_argument("--eval-specs", required=True)
    packet_parser.add_argument("--run-records", required=True)
    packet_parser.add_argument("--packet-dir", required=True)
    packet_parser.add_argument("--result-dir", required=True)
    packet_parser.add_argument(
        "--case-id", action="append", default=[], help="prepare only this selected case ID"
    )
    packet_parser.set_defaults(handler=prepare_eval)

    collect_parser = subparsers.add_parser(
        "collect-eval", help="Validate per-case Luna JSON files and atomically collect JSONL."
    )
    collect_parser.add_argument("--packet-dir", required=True)
    collect_parser.add_argument("--result-dir", required=True)
    collect_parser.add_argument("--output", required=True)
    collect_parser.set_defaults(handler=collect_eval)

    summary_parser = subparsers.add_parser(
        "summarize", help="Aggregate the four formal metrics after external evaluation."
    )
    summary_parser.add_argument("--run-records", required=True)
    summary_parser.add_argument("--eval-results", required=True)
    summary_parser.add_argument("--eval-specs", required=True)
    summary_parser.add_argument(
        "--packet-dir",
        required=True,
        help="verified packet directory used to bind formal results to their provenance",
    )
    summary_parser.add_argument("--output", required=True)
    summary_parser.add_argument(
        "--case-id", action="append", default=[], help="summarize only this selected case ID"
    )
    summary_parser.set_defaults(handler=summarize)

    worker_parser = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("payload", type=Path)
    worker_parser.set_defaults(handler=lambda args: worker_main(args.payload))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
