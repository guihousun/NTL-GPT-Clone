"""Summarize ConflictNTL candidate-event counts by country and date."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
OUT_TOTAL_CSV = DOCS / "ConflictNTL_country_candidate_totals_2026-02-27_2026-04-07.csv"
OUT_DAILY_CSV = DOCS / "ConflictNTL_country_daily_candidate_counts_2026-02-27_2026-04-07.csv"
OUT_XLSX = DOCS / "ConflictNTL_country_candidate_counts_2026-02-27_2026-04-07.xlsx"
OUT_JSON = DOCS / "ConflictNTL_country_candidate_counts_2026-02-27_2026-04-07.json"


def norm_text(value: object) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    return "" if text.lower() == "nan" else text


def first_date(row: pd.Series) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        value = norm_text(row.get(field))
        if value:
            return value[:10]
    return ""


def main() -> None:
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    df["event_date"] = df.apply(first_date, axis=1)
    df["country_clean"] = df["country"].map(norm_text).replace("", "Unknown")

    total = (
        df.groupby("country_clean", dropna=False)
        .size()
        .reset_index(name="candidate_events")
        .rename(columns={"country_clean": "country"})
        .sort_values(["candidate_events", "country"], ascending=[False, True])
    )
    total["share_pct"] = (total["candidate_events"] / len(df) * 100).round(3)

    daily = (
        df.groupby(["event_date", "country_clean"], dropna=False)
        .size()
        .reset_index(name="candidate_events")
        .rename(columns={"country_clean": "country"})
        .sort_values(["event_date", "country"])
    )

    pivot = (
        daily.pivot(index="event_date", columns="country", values="candidate_events")
        .fillna(0)
        .astype(int)
        .reset_index()
    )

    total.to_csv(OUT_TOTAL_CSV, index=False, encoding="utf-8")
    daily.to_csv(OUT_DAILY_CSV, index=False, encoding="utf-8")
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        total.to_excel(writer, sheet_name="country_totals", index=False)
        daily.to_excel(writer, sheet_name="country_daily_long", index=False)
        pivot.to_excel(writer, sheet_name="country_daily_pivot", index=False)

    summary = {
        "input_csv": str(INPUT_CSV),
        "country_totals_csv": str(OUT_TOTAL_CSV),
        "country_daily_csv": str(OUT_DAILY_CSV),
        "xlsx": str(OUT_XLSX),
        "candidate_events": int(len(df)),
        "country_count": int(total["country"].nunique()),
        "date_count": int(daily["event_date"].nunique()),
        "top_countries": total.head(20).to_dict("records"),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
