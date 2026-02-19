#!/usr/bin/env python
"""Aggregate NTL-VLM benchmark reports into parallel_eval analysis format."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate NTL-VLM benchmark report CSVs.")
    parser.add_argument("--benchmark-root", default="benchmarks/ntl_vlm_mvp")
    parser.add_argument("--out-dir", default="experiments/parallel_eval/analysis")
    args = parser.parse_args()

    benchmark_root = Path(args.benchmark_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    overall_path = benchmark_root / "reports" / "overall.csv"
    by_task_path = benchmark_root / "reports" / "by_task.csv"
    by_split_path = benchmark_root / "reports" / "by_split.csv"

    if not overall_path.exists():
        raise FileNotFoundError(f"overall report not found: {overall_path}")
    if not by_task_path.exists():
        raise FileNotFoundError(f"by_task report not found: {by_task_path}")

    overall = pd.read_csv(overall_path)
    by_task = pd.read_csv(by_task_path)
    by_split = pd.read_csv(by_split_path) if by_split_path.exists() else pd.DataFrame()

    overall_out = out_dir / "ntl_vlm_summary_overall.csv"
    by_task_out = out_dir / "ntl_vlm_summary_by_task.csv"
    by_split_out = out_dir / "ntl_vlm_summary_by_split.csv"

    overall.to_csv(overall_out, index=False, encoding="utf-8-sig")
    by_task.to_csv(by_task_out, index=False, encoding="utf-8-sig")
    if not by_split.empty:
        by_split.to_csv(by_split_out, index=False, encoding="utf-8-sig")

    print("Wrote:")
    print(overall_out)
    print(by_task_out)
    if by_split_path.exists():
        print(by_split_out)


if __name__ == "__main__":
    main()

