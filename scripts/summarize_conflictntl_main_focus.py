"""Summarize main-focus and spillover ConflictNTL samples."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CANDIDATE_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
UNITS_CSV = DOCS / "ConflictNTL_analysis_units_2026-02-27_2026-04-07/ConflictNTL_analysis_units_summary.csv"
OUT_CSV = DOCS / "ConflictNTL_main_focus_summary_2026-02-27_2026-04-07.csv"
OUT_JSON = DOCS / "ConflictNTL_main_focus_summary_2026-02-27_2026-04-07.json"

MAIN_COUNTRIES = {"Iran", "Israel"}


def count_units(units: pd.DataFrame, country: str) -> int:
    return int(units["countries"].fillna("").str.contains(country, regex=False).sum())


def main() -> None:
    candidates = pd.read_csv(CANDIDATE_CSV, dtype=str).fillna("")
    units = pd.read_csv(UNITS_CSV, dtype=str).fillna("")

    candidate_total = len(candidates)
    unit_total = len(units)
    rows = []
    for country in sorted(candidates["country"].replace("", "Unknown").unique()):
        n = int((candidates["country"].replace("", "Unknown") == country).sum())
        rows.append(
            {
                "country": country,
                "analysis_role": "main_focus" if country in MAIN_COUNTRIES else "spillover_context",
                "candidate_events": n,
                "candidate_share_pct": round(n / candidate_total * 100, 3) if candidate_total else 0.0,
                "analysis_units_containing_country": count_units(units, country) if country != "Unknown" else 0,
            }
        )
    out = pd.DataFrame(rows).sort_values(["analysis_role", "candidate_events"], ascending=[True, False])
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")

    main_count = int(candidates["country"].isin(MAIN_COUNTRIES).sum())
    summary = {
        "candidate_total": candidate_total,
        "analysis_unit_total": unit_total,
        "main_focus_countries": sorted(MAIN_COUNTRIES),
        "main_focus_candidate_events": main_count,
        "main_focus_candidate_share_pct": round(main_count / candidate_total * 100, 3) if candidate_total else 0.0,
        "iran_analysis_units": count_units(units, "Iran"),
        "israel_analysis_units": count_units(units, "Israel"),
        "spillover_candidate_events": candidate_total - main_count,
        "output_csv": str(OUT_CSV),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
