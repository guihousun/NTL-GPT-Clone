"""Package Q19 Analyst outputs as source tables for a future figure renderer.

This does not render or alter a manuscript figure.  It preserves every product
date, leaves unqualified values blank, and annotates a rolling line that uses
only actual strict-QA observations.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DISPLAY_START = date(2026, 1, 1)
DISPLAY_END = date(2026, 7, 31)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def phase_for(day: date) -> str:
    if day <= date(2026, 2, 27):
        return "pre_conflict_baseline"
    if day <= date(2026, 4, 7):
        return "conflict_evaluation"
    if day <= date(2026, 4, 21):
        return "fixed_ceasefire_evaluation"
    return "extended_monitoring"


def optional_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    return float(value) if value not in (None, "") else None


def read_source(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def strict_rolling(values: dict[date, float], target: date) -> tuple[float | None, int]:
    # A centred 14-day temporal footprint, [-6, +7], without interpolation.
    sample = [
        value
        for day, value in values.items()
        if target - timedelta(days=6) <= day <= target + timedelta(days=7)
    ]
    return ((sum(sample) / len(sample)) if len(sample) >= 3 else None, len(sample))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-csv", type=Path, required=True)
    parser.add_argument("--event-selection", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = [
        row
        for row in read_source(args.daily_csv)
        if DISPLAY_START <= parse_date(row["date_utc"]) <= DISPLAY_END
    ]
    strict_values = {
        parse_date(row["date_utc"]): float(row["mean"])
        for row in rows
        if row["qa_mode"] == "strict" and row["qualified"] == "true" and row["mean"]
    }

    daily_output: list[dict[str, Any]] = []
    for row in rows:
        day = parse_date(row["date_utc"])
        rolling, rolling_n = strict_rolling(strict_values, day)
        daily_output.append(
            {
                "date_utc": row["date_utc"],
                "analysis_phase": phase_for(day),
                "qa_mode": row["qa_mode"],
                "image_available": row["image_available"],
                "qualified": row["qualified"],
                "daily_mean_nw_cm2_sr": row["mean"],
                "daily_median_nw_cm2_sr": row["median"],
                "valid_fraction": row["valid_fraction"],
                "source_image_id": row["source_image_id"],
                "strict_centered_14day_mean_nw_cm2_sr": (
                    f"{rolling:.12f}" if row["qa_mode"] == "strict" and rolling is not None else ""
                ),
                "strict_centered_14day_actual_sample_count": (
                    str(rolling_n) if row["qa_mode"] == "strict" else ""
                ),
                "rolling_note": (
                    "centred [-6,+7] calendar-day window; actual qualified strict observations only; no interpolation; requires >=3 samples"
                    if row["qa_mode"] == "strict"
                    else ""
                ),
            }
        )

    selection = json.loads(args.event_selection.read_text(encoding="utf-8"))
    event_rows = [
        {
            "event_date_utc": "2026-04-08",
            "label": "Initial two-week ceasefire announced",
            "precision": "date-only",
            "display_role": "background_marker",
            "note": "Not a precise UTC instant.",
        },
        {
            "event_date_utc": "2026-04-21",
            "label": "Ceasefire extension announced",
            "precision": "date-only",
            "display_role": "formal_marker",
            "note": "2026-04-22 is an institutional reporting date, not a ceasefire-end date.",
        },
        {
            "event_date_utc": "2026-06-17",
            "label": "Islamabad MoU signed",
            "precision": "date-only",
            "display_role": "formal_marker",
            "note": "No precise UTC signing time asserted.",
        },
        {
            "event_date_utc": "2026-07-07",
            "label": "Renewed hostilities (U.S. notice)",
            "precision": "date-only",
            "display_role": "formal_marker",
            "note": "Date marks source-reported notice semantics, not causal attribution.",
        },
    ]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    daily_path = args.out_dir / "q19-figure-input-daily.csv"
    events_path = args.out_dir / "q19-figure-input-events.csv"
    with daily_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(daily_output[0]))
        writer.writeheader()
        writer.writerows(daily_output)
    with events_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(event_rows[0]))
        writer.writeheader()
        writer.writerows(event_rows)

    notes = args.out_dir / "q19-figure-input-notes.md"
    notes.write_text(
        "# Q19 figure-input packaging\n\n"
        "These tables were packaged by the Engineer from the accepted Analyst data contract; they are not a rendered manuscript figure. "
        "The rolling field is a visual aid based only on observed, strict-QA-qualified records and never fills missing observations.\n\n"
        f"- Display interval: {DISPLAY_START.isoformat()} to {DISPLAY_END.isoformat()} UTC.\n"
        f"- Event-selection overall ranking verdict: `{selection['verdict']}`; this table does not claim that City of Tehran is highest-ranked overall.\n"
        "- The 2026-04-22 date is deliberately absent as a vertical event marker because it is not ceasefire-end evidence.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
