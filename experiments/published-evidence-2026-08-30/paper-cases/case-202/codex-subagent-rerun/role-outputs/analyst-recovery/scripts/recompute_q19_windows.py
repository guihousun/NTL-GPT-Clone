#!/usr/bin/env python3
"""Recompute the Q19 descriptive windows from the frozen daily source table.

This is intentionally a standard-library-only, local recovery script.  It
does not download data, call GEE, infer an event mechanism, or create figures.
The only writes are the five artifacts in this script's parent output
directory.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_PATH = Path(__file__).resolve()
OUTPUT_DIR = SCRIPT_PATH.parent.parent
PROJECT_ROOT = OUTPUT_DIR.parents[3]

SOURCE_CSV = (
    PROJECT_ROOT
    / "experiments"
    / "paper-case-multiagent-2026-08-13"
    / "Q19-tehran-city-longseries"
    / "daily-vnp46a2.csv"
)
RERUN_OUTPUTS = OUTPUT_DIR.parent
DATA_SEARCHER_AUDIT = RERUN_OUTPUTS / "data-searcher" / "daily-series-audit.json"
EVENT_SELECTION = RERUN_OUTPUTS / "event-tracker" / "event-selection.json"

CASE_ID = "Q19-tehran-city-longseries"
TIME_BASIS = "UTC"
ANALYSIS_CUTOFF = date(2026, 7, 31)
EXPECTED_SOURCE_CUTOFF = date(2026, 8, 2)
QA_MODES = ("strict", "permissive")
WINDOWS = (
    ("baseline", date(2026, 1, 1), date(2026, 2, 27)),
    ("conflict", date(2026, 2, 28), date(2026, 4, 7)),
    ("ceasefire_evaluation", date(2026, 4, 8), date(2026, 4, 21)),
    ("extended_monitoring", date(2026, 4, 22), date(2026, 7, 31)),
)

REQUIRED_CSV_FIELDS = {
    "date_utc",
    "qa_mode",
    "image_available",
    "qualified",
    "mean",
}


def project_relative(path: Path) -> str:
    """Return a stable project-relative path for provenance fields."""

    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def output_relative(path: Path) -> str:
    """Return a stable output-relative path for manifest entries."""

    return path.resolve().relative_to(OUTPUT_DIR).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return value


def parse_bool(value: str, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Row {row_number}: {field} must be true or false, got {value!r}")


def load_daily_rows(path: Path) -> list[dict[str, Any]]:
    """Read and minimally type-check the supplied UTC daily table."""

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_CSV_FIELDS - fieldnames
        if missing:
            raise ValueError(f"Daily table is missing required fields: {sorted(missing)}")

        for row_number, raw in enumerate(reader, start=2):
            date_text = (raw.get("date_utc") or "").strip()
            qa_mode = (raw.get("qa_mode") or "").strip()
            if not date_text or qa_mode not in QA_MODES:
                raise ValueError(f"Row {row_number}: invalid date_utc or qa_mode")
            date_utc = date.fromisoformat(date_text)
            qualified = parse_bool(raw.get("qualified") or "", "qualified", row_number)
            image_available = parse_bool(
                raw.get("image_available") or "", "image_available", row_number
            )
            mean_text = (raw.get("mean") or "").strip()
            daily_mean = float(mean_text) if mean_text else None
            if qualified and not image_available:
                raise ValueError(f"Row {row_number}: qualified row is not image_available")
            if qualified and daily_mean is None:
                raise ValueError(f"Row {row_number}: qualified row has a null mean")
            if not qualified and daily_mean is not None:
                raise ValueError(f"Row {row_number}: unqualified row must have a null mean")
            rows.append(
                {
                    "date_utc": date_utc,
                    "qa_mode": qa_mode,
                    "image_available": image_available,
                    "qualified": qualified,
                    "mean": daily_mean,
                }
            )

    if not rows:
        raise ValueError("Daily table is empty")
    keys = [(row["date_utc"], row["qa_mode"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Daily table contains duplicate date_utc/qa_mode rows")
    return rows


def qualified_rows_in_window(
    rows: Iterable[dict[str, Any]], qa_mode: str, start: date, end: date
) -> list[dict[str, Any]]:
    """Select only qualified daily means within an inclusive UTC window."""

    return [
        row
        for row in rows
        if row["qa_mode"] == qa_mode
        and start <= row["date_utc"] <= end
        and row["date_utc"] <= ANALYSIS_CUTOFF
        and row["qualified"] is True
    ]


def mean_of_daily_means(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    values = [float(row["mean"]) for row in rows]
    return sum(values) / len(values)


def relative_change(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    if baseline == 0:
        raise ZeroDivisionError("Baseline mean cannot be zero for relative change")
    return (value - baseline) / baseline * 100.0


def compute_window_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Compute the flat summary rows and nested result rows for both QA modes."""

    summaries: dict[str, list[dict[str, Any]]] = {qa_mode: [] for qa_mode in QA_MODES}
    for qa_mode in QA_MODES:
        baseline_start, baseline_end = WINDOWS[0][1:]
        baseline_rows = qualified_rows_in_window(rows, qa_mode, baseline_start, baseline_end)
        baseline_mean = mean_of_daily_means(baseline_rows)
        for window_id, start, end in WINDOWS:
            selected = qualified_rows_in_window(rows, qa_mode, start, end)
            window_mean = mean_of_daily_means(selected)
            summaries[qa_mode].append(
                {
                    "qa_mode": qa_mode,
                    "window_id": window_id,
                    "start_date_utc": start.isoformat(),
                    "end_date_utc": end.isoformat(),
                    "inclusive_calendar_days": (end - start).days + 1,
                    "qualified_days": len(selected),
                    "mean_of_daily_means": window_mean,
                    "baseline_mean_of_daily_means": baseline_mean,
                    "relative_change_vs_baseline_percent": relative_change(
                        window_mean, baseline_mean
                    ),
                    "qualified_dates_utc": [
                        row["date_utc"].isoformat() for row in selected
                    ],
                }
            )
    return summaries


def csv_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.12f}"


def write_window_csv(path: Path, summaries: dict[str, list[dict[str, Any]]]) -> None:
    fieldnames = [
        "qa_mode",
        "window_id",
        "start_date_utc",
        "end_date_utc",
        "inclusive_calendar_days",
        "qualified_days",
        "mean_of_daily_means",
        "baseline_mean_of_daily_means",
        "relative_change_vs_baseline_percent",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for qa_mode in QA_MODES:
            for row in summaries[qa_mode]:
                writer.writerow(
                    {
                        key: csv_number(row[key])
                        if key
                        in {
                            "inclusive_calendar_days",
                            "qualified_days",
                            "mean_of_daily_means",
                            "baseline_mean_of_daily_means",
                            "relative_change_vs_baseline_percent",
                        }
                        else row[key]
                        for key in fieldnames
                    }
                )


def check(
    checks: list[dict[str, Any]],
    check_id: str,
    expected: Any,
    observed: Any,
    note: str,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "expected": expected,
            "observed": observed,
            "passed": expected == observed,
            "note": note,
        }
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": output_relative(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def input_record(path: Path) -> dict[str, Any]:
    return {
        "path": project_relative(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}%"


def build_report(
    summaries: dict[str, list[dict[str, Any]]],
    rows: list[dict[str, Any]],
    source_max: date,
    event_verdict: str,
) -> str:
    strict = {row["window_id"]: row for row in summaries["strict"]}
    permissive = {row["window_id"]: row for row in summaries["permissive"]}
    lines = [
        f"# Q19 descriptive window analysis ({CASE_ID})",
        "",
        "## Scope and method",
        "",
        f"- Time basis: UTC product-day dates; inclusive windows end on the stated UTC date.",
        f"- Analysis cutoff: **{ANALYSIS_CUTOFF.isoformat()} UTC**. The supplied daily table extends through **{source_max.isoformat()} UTC**, and later rows are excluded.",
        "- A daily value is included only when `qualified == true`; no interpolation or imputation is applied.",
        "- `mean_of_daily_means` is the arithmetic mean of the retained daily `mean` values. Relative change is `(window mean - complete baseline mean) / complete baseline mean * 100`.",
        "- Strict is the primary QA mode; permissive is a sensitivity analysis.",
        "",
        "## Window summary",
        "",
        "| QA mode | Window | Qualified days | Mean of daily means | Relative change vs complete baseline |",
        "|---|---|---:|---:|---:|",
    ]
    for qa_mode, data in (("strict", strict), ("permissive", permissive)):
        for window_id, _, _ in WINDOWS:
            row = data[window_id]
            lines.append(
                f"| {qa_mode} | {window_id} | {row['qualified_days']} | {row['mean_of_daily_means']:.12f} | {format_pct(row['relative_change_vs_baseline_percent'])} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "These are descriptive radiance summaries only. They do not establish causal attribution, conflict effects, outage, damage, or recovery. The extended-monitoring window is not treated as a homogeneous ceasefire or recovery phase.",
            "",
            f"The Event Tracker overall-ranking verdict is `{event_verdict}`. Therefore, the analysis does not treat the target as an established highest-ranked complete event-census unit; any ranking support is limited to the qualified exact-coordinate subset described by the Event Tracker artifact.",
            "",
            f"Source rows read: {len(rows)}. The analysis uses only dates through {ANALYSIS_CUTOFF.isoformat()} UTC.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_daily_rows(SOURCE_CSV)
    data_searcher_audit = load_json(DATA_SEARCHER_AUDIT)
    event_selection = load_json(EVENT_SELECTION)

    source_dates = [row["date_utc"] for row in rows]
    source_min = min(source_dates)
    source_max = max(source_dates)
    analysis_rows = [row for row in rows if row["date_utc"] <= ANALYSIS_CUTOFF]
    later_rows = [row for row in rows if row["date_utc"] > ANALYSIS_CUTOFF]
    analysis_qualified_dates = [
        row["date_utc"] for row in analysis_rows if row["qualified"] is True
    ]
    analysis_max_qualified = max(analysis_qualified_dates)

    summaries = compute_window_rows(rows)
    window_csv = OUTPUT_DIR / "q19-window-summary.csv"
    write_window_csv(window_csv, summaries)

    event_verdict = event_selection.get("verdict")
    audit_source_snapshot = data_searcher_audit.get("source_snapshot", {})

    checks: list[dict[str, Any]] = []
    strict_baseline_days = summaries["strict"][0]["qualified_days"]
    permissive_baseline_days = summaries["permissive"][0]["qualified_days"]
    check(
        checks,
        "strict_baseline_qualified_days",
        47,
        strict_baseline_days,
        "Independent count of CSV rows with qa_mode=strict and qualified=true in the UTC baseline.",
    )
    check(
        checks,
        "permissive_baseline_qualified_days",
        48,
        permissive_baseline_days,
        "Independent count of CSV rows with qa_mode=permissive and qualified=true in the UTC baseline.",
    )
    check(
        checks,
        "source_daily_table_cutoff",
        EXPECTED_SOURCE_CUTOFF.isoformat(),
        source_max.isoformat(),
        "The supplied source daily table reaches 2026-08-02 UTC.",
    )
    check(
        checks,
        "analysis_qualified_upper_bound",
        True,
        analysis_max_qualified <= ANALYSIS_CUTOFF,
        "No qualified daily value used in the analysis is later than the 2026-07-31 UTC cutoff.",
    )
    check(
        checks,
        "source_has_rows_after_analysis_cutoff",
        True,
        bool(later_rows),
        "The source contains later rows that can demonstrate the cutoff was applied.",
    )
    check(
        checks,
        "event_tracker_overall_ranking_verdict",
        "indeterminate",
        event_verdict,
        "The Event Tracker top-level verdict is the overall-ranking verdict used for this limitation.",
    )
    check(
        checks,
        "audit_source_snapshot_cutoff_agrees",
        EXPECTED_SOURCE_CUTOFF.isoformat(),
        audit_source_snapshot.get("actual_image_cutoff_utc"),
        "The independent CSV result agrees with the supplied Data Searcher source snapshot metadata.",
    )

    validation = {
        "schema_version": "ntl.q19-analysis-validation.v1",
        "case_id": CASE_ID,
        "independent_recompute": {
            "source_csv": project_relative(SOURCE_CSV),
            "rows_read": len(rows),
            "source_date_min_utc": source_min.isoformat(),
            "source_date_max_utc": source_max.isoformat(),
            "analysis_cutoff_date_utc": ANALYSIS_CUTOFF.isoformat(),
            "analysis_max_qualified_date_utc": analysis_max_qualified.isoformat(),
            "rows_after_analysis_cutoff": len(later_rows),
            "dates_after_analysis_cutoff_utc": sorted(
                {row["date_utc"].isoformat() for row in later_rows}
            ),
            "qualified_baseline_days_by_qa_mode": {
                qa_mode: summaries[qa_mode][0]["qualified_days"] for qa_mode in QA_MODES
            },
        },
        "event_tracker": {
            "source_json": project_relative(EVENT_SELECTION),
            "field": "verdict",
            "overall_ranking_verdict": event_verdict,
        },
        "checks": checks,
        "overall_pass": all(item["passed"] for item in checks),
    }
    validation_path = OUTPUT_DIR / "validation.json"
    validation_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not validation["overall_pass"]:
        failed = [item["check_id"] for item in checks if not item["passed"]]
        raise AssertionError(f"Q19 validation failed: {failed}")

    def result_block(qa_mode: str) -> dict[str, Any]:
        baseline = summaries[qa_mode][0]
        return {
            "qa_mode": qa_mode,
            "baseline_mean_of_daily_means": baseline["mean_of_daily_means"],
            "windows": summaries[qa_mode],
        }

    analysis_results = {
        "schema_version": "ntl.q19-analysis-results.v1",
        "case_id": CASE_ID,
        "execution": {
            "execution_timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "time_basis": TIME_BASIS,
            "analysis_cutoff_date_utc": ANALYSIS_CUTOFF.isoformat(),
            "source_daily_table_max_date_utc": source_max.isoformat(),
            "source_rows_after_cutoff_excluded": len(later_rows),
        },
        "method": {
            "qualified_rule": "Include only rows with qualified == true; retain gaps; no interpolation or imputation.",
            "daily_statistic": "mean field from the supplied daily table.",
            "window_aggregation": "Arithmetic mean of qualified daily means within each inclusive UTC window.",
            "relative_change_formula": "(window mean - complete baseline mean) / complete baseline mean * 100.",
            "windows_inclusive_utc": [
                {
                    "window_id": window_id,
                    "start_date_utc": start.isoformat(),
                    "end_date_utc": end.isoformat(),
                }
                for window_id, start, end in WINDOWS
            ],
        },
        "strict_primary": result_block("strict"),
        "permissive_sensitivity": result_block("permissive"),
        "interpretation_limits": [
            "Descriptive statistics only; no causal attribution, conflict-effect, outage, damage, or recovery conclusion is made.",
            "The extended-monitoring window is not interpreted as a homogeneous ceasefire, recovery, or peace phase.",
            "The Event Tracker overall-ranking verdict is indeterminate; no complete-census highest-rank claim is adopted.",
            "Any ranking support remains limited to the qualified exact-coordinate subset documented by the Event Tracker input.",
        ],
        "source_artifacts": {
            "daily_csv": project_relative(SOURCE_CSV),
            "data_searcher_audit": project_relative(DATA_SEARCHER_AUDIT),
            "event_tracker_selection": project_relative(EVENT_SELECTION),
        },
    }
    results_path = OUTPUT_DIR / "q19-analysis-results.json"
    results_path.write_text(
        json.dumps(analysis_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report_path = OUTPUT_DIR / "q19-analysis-report.md"
    report_path.write_text(
        build_report(summaries, rows, source_max, event_verdict), encoding="utf-8"
    )

    manifest = {
        "schema_version": "ntl.q19-analysis-artifact-manifest.v1",
        "case_id": CASE_ID,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "output_directory": project_relative(OUTPUT_DIR),
        "artifacts": [
            artifact_record(SCRIPT_PATH),
            artifact_record(window_csv),
            artifact_record(results_path),
            artifact_record(validation_path),
            artifact_record(report_path),
        ],
        "input_artifacts": [
            input_record(SOURCE_CSV),
            input_record(DATA_SEARCHER_AUDIT),
            input_record(EVENT_SELECTION),
        ],
        "validation": {
            "validation_artifact": output_relative(validation_path),
            "overall_pass": validation["overall_pass"],
        },
        "prohibited_external_actions": ["network access", "GEE access", "figure generation"],
    }
    manifest_path = OUTPUT_DIR / "artifact-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Keep the final assertion explicit so a successful exit implies all gates passed.
    if validation["overall_pass"] is not True:
        raise AssertionError("Validation overall_pass must be true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
