#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


def _load_case_result(case_dir: Path) -> Dict:
    case_json = case_dir / "case_result.json"
    if case_json.exists():
        try:
            return json.loads(case_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    attempt_files = sorted(case_dir.glob("attempt_*.json"))
    if not attempt_files:
        return {}

    attempts: List[Dict] = []
    for fp in attempt_files:
        try:
            attempts.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue

    if not attempts:
        return {}

    success = any(bool(a.get("success", False)) for a in attempts)
    hallucination = any(bool(a.get("hallucination", False)) for a in attempts)
    exec_error = any(bool(a.get("execution_error", False)) for a in attempts)

    first_success_at = None
    for i, a in enumerate(attempts, start=1):
        if bool(a.get("success", False)):
            first_success_at = i
            break

    base = attempts[-1].copy()
    base.update(
        {
            "success": success,
            "hallucination": hallucination,
            "execution_error": exec_error,
            "attempts_used": first_success_at or len(attempts),
            "attempt_count": len(attempts),
        }
    )
    return base


def collect_results(root: Path) -> pd.DataFrame:
    rows: List[Dict] = []
    # Expected: runs/<exp_id>/<model>/<worker>/case_xxx/
    for case_dir in root.glob("*/*/*/case_*"):
        if not case_dir.is_dir():
            continue
        exp_id = case_dir.parents[2].name
        model = case_dir.parents[1].name
        worker = case_dir.parents[0].name
        case_id = case_dir.name.replace("case_", "")

        record = _load_case_result(case_dir)
        if not record:
            continue

        record["exp_id"] = record.get("exp_id", exp_id)
        record["model"] = record.get("model", model)
        record["worker"] = record.get("worker", worker)
        record["case_id"] = int(record.get("case_id", case_id))
        record["category"] = record.get("category", "")
        record["success"] = bool(record.get("success", False))
        record["hallucination"] = bool(record.get("hallucination", False))
        record["execution_error"] = bool(record.get("execution_error", False))
        record["attempts_used"] = int(record.get("attempts_used", record.get("attempt_count", 1)))
        record["runtime_s"] = float(record.get("runtime_s", 0.0))
        rows.append(record)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values(["exp_id", "model", "case_id"]).reset_index(drop=True)


def summarize(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    overall = (
        df.groupby(["exp_id", "model"], as_index=False)
        .agg(
            total_cases=("case_id", "nunique"),
            success_cases=("success", "sum"),
            hallucination_cases=("hallucination", "sum"),
            execution_error_cases=("execution_error", "sum"),
            avg_attempts=("attempts_used", "mean"),
            avg_runtime_s=("runtime_s", "mean"),
        )
    )
    overall["success_rate"] = overall["success_cases"] / overall["total_cases"]

    by_category = (
        df.groupby(["exp_id", "model", "category"], as_index=False)
        .agg(
            total_cases=("case_id", "nunique"),
            success_cases=("success", "sum"),
            hallucination_cases=("hallucination", "sum"),
            execution_error_cases=("execution_error", "sum"),
            avg_attempts=("attempts_used", "mean"),
        )
    )
    by_category["success_rate"] = by_category["success_cases"] / by_category["total_cases"]

    by_case = df[[
        "exp_id",
        "model",
        "case_id",
        "category",
        "success",
        "hallucination",
        "execution_error",
        "attempts_used",
        "runtime_s",
    ]].copy()

    return {
        "overall": overall.sort_values(["exp_id", "success_rate"], ascending=[True, False]),
        "by_category": by_category.sort_values(["exp_id", "model", "category"]),
        "by_case": by_case.sort_values(["exp_id", "model", "case_id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate parallel experiment results for NTL-GPT/Codex runs.")
    parser.add_argument("--runs-root", default="experiments/parallel_eval/runs")
    parser.add_argument("--out-dir", default="experiments/parallel_eval/analysis")
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = collect_results(runs_root)
    if df.empty:
        print("No results found under", runs_root)
        return

    summary = summarize(df)
    df.to_csv(out_dir / "all_case_results.csv", index=False, encoding="utf-8-sig")
    summary["overall"].to_csv(out_dir / "summary_overall.csv", index=False, encoding="utf-8-sig")
    summary["by_category"].to_csv(out_dir / "summary_by_category.csv", index=False, encoding="utf-8-sig")
    summary["by_case"].to_csv(out_dir / "summary_by_case.csv", index=False, encoding="utf-8-sig")

    print("Analysis written to", out_dir)
    print(summary["overall"].to_string(index=False))


if __name__ == "__main__":
    main()
