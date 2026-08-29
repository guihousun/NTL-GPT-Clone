"""Minimal read-only input audit for the Q19 Codex-subagent evidence rerun.

This script does not generate an analysis result.  It records the identity and
calendar/QA coverage of an existing daily table so the Engineer can decide
whether it is acceptable as an Analyst input.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINE_START = "2026-01-01"
BASELINE_END = "2026-02-27"


def sha256_and_bytes(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def read_daily_table(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "date_utc",
        "qa_mode",
        "image_available",
        "qualified",
        "mean",
        "valid_count",
        "total_count",
        "valid_fraction",
        "units",
        "scale_m",
        "source_image_id",
    }
    missing = sorted(required.difference(rows[0] if rows else {}))
    by_mode = {}
    for mode in sorted({row.get("qa_mode", "") for row in rows}):
        mode_rows = [row for row in rows if row.get("qa_mode") == mode]
        baseline_rows = [
            row
            for row in mode_rows
            if BASELINE_START <= row.get("date_utc", "") <= BASELINE_END
        ]
        by_mode[mode] = {
            "rows": len(mode_rows),
            "date_min": min((row.get("date_utc", "") for row in mode_rows), default=None),
            "date_max": max((row.get("date_utc", "") for row in mode_rows), default=None),
            "unique_dates": len({row.get("date_utc", "") for row in mode_rows}),
            "image_available_rows": sum(row.get("image_available") == "true" for row in mode_rows),
            "qualified_rows": sum(row.get("qualified") == "true" for row in mode_rows),
            "baseline_calendar_rows": len(baseline_rows),
            "baseline_image_available_rows": sum(row.get("image_available") == "true" for row in baseline_rows),
            "baseline_qualified_rows": sum(row.get("qualified") == "true" for row in baseline_rows),
            "units": sorted({row.get("units", "") for row in mode_rows}),
            "scale_m": sorted({row.get("scale_m", "") for row in mode_rows}),
        }
    date_counts = Counter(row.get("date_utc", "") for row in rows)
    return {
        "row_count": len(rows),
        "columns_missing_from_contract": missing,
        "rows_per_date_distribution": dict(sorted(Counter(date_counts.values()).items())),
        "qa_modes": by_mode,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_files = [
        "daily-vnp46a2.csv",
        "daily-vnp46a2-raw.jsonl",
        "observation-package.json",
        "tehran-boundary.geojson",
        "tehran-boundary-metadata.json",
        "gee-checkpoint.json",
    ]
    sources = {}
    for name in source_files:
        path = args.case_dir / name
        sources[name] = sha256_and_bytes(path) if path.is_file() else {"path": str(path), "missing": True}

    daily_path = args.case_dir / "daily-vnp46a2.csv"
    payload = {
        "schema_version": "codex-subagent-q19-input-audit.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "simulation_scope": "Codex-subagent case-evidence simulation; not deployed NTL-GPT runtime or benchmark evidence.",
        "case_directory": str(args.case_dir),
        "baseline_contract": {
            "time_basis": "UTC",
            "start_date_inclusive": BASELINE_START,
            "end_date_inclusive": BASELINE_END,
        },
        "source_files": sources,
        "daily_table": read_daily_table(daily_path) if daily_path.is_file() else {"missing": True},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
