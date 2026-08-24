"""Engineer-side independent verification of the Q19 Analyst recovery outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


WINDOWS = [
    ("baseline", "w1", "2026-01-01", "2026-02-27"),
    ("conflict", "w2", "2026-02-28", "2026-04-07"),
    ("ceasefire_evaluation", "w3", "2026-04-08", "2026-04-21"),
    ("extended_monitoring", "w4", "2026-04-22", "2026-07-31"),
]
TOLERANCE = 1e-9


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected(source_rows: list[dict[str, str]], mode: str, start: str, end: str) -> tuple[int, float]:
    selected = [
        float(row["mean"])
        for row in source_rows
        if row["qa_mode"] == mode
        and row["qualified"] == "true"
        and start <= row["date_utc"] <= end
    ]
    return len(selected), sum(selected) / len(selected)


def approx(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-daily", type=Path, required=True)
    parser.add_argument("--analyst-dir", type=Path, required=True)
    parser.add_argument("--crosscheck-dir", type=Path, required=True)
    parser.add_argument("--event-selection", type=Path, required=True)
    parser.add_argument("--figure-input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = rows(args.source_daily)
    analyst_summary = rows(args.analyst_dir / "q19-window-summary.csv")
    analyst_map = {(row["qa_mode"], row["window_id"]): row for row in analyst_summary}
    crosscheck_map = {(row["qa_mode"], row["window"]): row for row in rows(args.crosscheck_dir / "crosscheck.csv")}
    checks: list[dict[str, object]] = []

    recomputed: dict[str, dict[str, dict[str, float | int]]] = {}
    for mode in ("strict", "permissive"):
        recomputed[mode] = {}
        baseline_count, baseline_mean = expected(source, mode, WINDOWS[0][2], WINDOWS[0][3])
        for window, cross_id, start, end in WINDOWS:
            count, mean = expected(source, mode, start, end)
            change = (mean - baseline_mean) / baseline_mean * 100
            recomputed[mode][window] = {"qualified_days": count, "mean": mean, "relative_pct": change}
            analyst = analyst_map[(mode, window)]
            cross = crosscheck_map[(mode, cross_id)]
            passed = (
                int(analyst["qualified_days"]) == count
                and approx(float(analyst["mean_of_daily_means"]), mean)
                and approx(float(analyst["relative_change_vs_baseline_percent"]), change)
                and int(cross["n"]) == count
                and approx(float(cross["mean_mean"]), mean)
                and approx(float(cross["relative_to_first_pct"]), change)
            )
            checks.append(
                {
                    "check_id": f"{mode}_{window}_three_way_recompute",
                    "passed": passed,
                    "source": {"qualified_days": count, "mean": mean, "relative_pct": change},
                }
            )

    event_selection = json.loads(args.event_selection.read_text(encoding="utf-8"))
    checks.append(
        {
            "check_id": "event_overall_ranking_indeterminate",
            "passed": event_selection.get("verdict") == "indeterminate",
            "observed": event_selection.get("verdict"),
        }
    )
    figure_rows = rows(args.figure_input)
    post_cutoff = [row["date_utc"] for row in figure_rows if row["date_utc"] > "2026-07-31"]
    bad_rolling = [
        row["date_utc"]
        for row in figure_rows
        if row["qa_mode"] == "strict"
        and row["strict_centered_14day_mean_nw_cm2_sr"]
        and int(row["strict_centered_14day_actual_sample_count"]) < 3
    ]
    checks.extend(
        [
            {"check_id": "figure_input_cutoff", "passed": not post_cutoff, "post_cutoff_dates": post_cutoff},
            {"check_id": "figure_input_no_low_sample_rolling", "passed": not bad_rolling, "dates": bad_rolling},
        ]
    )

    payload = {
        "schema_version": "codex-subagent-q19-engineer-validation.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "simulation_scope": "Codex-subagent case-evidence simulation; not deployed NTL-GPT runtime or benchmark evidence.",
        "sources": {
            "daily_csv_sha256": sha256(args.source_daily),
            "analyst_summary_sha256": sha256(args.analyst_dir / "q19-window-summary.csv"),
            "crosscheck_sha256": sha256(args.crosscheck_dir / "crosscheck.csv"),
            "figure_input_sha256": sha256(args.figure_input),
        },
        "recomputed": recomputed,
        "checks": checks,
        "overall_pass": all(bool(check["passed"]) for check in checks),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
