"""Create daily count tables for ConflictNTL candidate events and analysis units."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TOP_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
BUFFER_GEOJSON = (
    DOCS
    / "ISW_candidate_aois_2026-02-27_2026-04-07"
    / "ISW_candidate_point_buffers_2km.geojson"
)
ADMIN_GEOJSON = (
    DOCS
    / "ISW_candidate_admin_aois_2026-02-27_2026-04-07"
    / "ISW_candidate_admin_boundaries.geojson"
)
UNRESOLVED_ADMIN_CSV = (
    DOCS
    / "ISW_candidate_admin_aois_2026-02-27_2026-04-07"
    / "unresolved_admin_boundaries.csv"
)
UNITS_CSV = (
    DOCS
    / "ConflictNTL_analysis_units_2026-02-27_2026-04-07"
    / "ConflictNTL_analysis_units_summary.csv"
)
OUTPUT_CSV = DOCS / "ConflictNTL_daily_counts_2026-02-27_2026-04-07.csv"
OUTPUT_XLSX = DOCS / "ConflictNTL_daily_counts_2026-02-27_2026-04-07.xlsx"
OUTPUT_JSON = DOCS / "ConflictNTL_daily_counts_2026-02-27_2026-04-07.json"

START = date(2026, 2, 27)
END = date(2026, 4, 7)


def norm(value: object) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def event_date_from_row(row: dict[str, str]) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc", "event_date"):
        value = norm(row.get(field))
        if value:
            return value[:10]
    return ""


def date_range() -> list[str]:
    days: list[str] = []
    current = START
    while current <= END:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_geojson_features(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [feature.get("properties", {}) for feature in data.get("features", [])]


def split_member_count(value: object) -> int:
    try:
        return int(float(norm(value)))
    except Exception:
        return 0


def main() -> None:
    top_rows = read_csv_rows(TOP_CSV)
    buffer_features = load_geojson_features(BUFFER_GEOJSON)
    admin_features = load_geojson_features(ADMIN_GEOJSON)
    unresolved_rows = read_csv_rows(UNRESOLVED_ADMIN_CSV)
    unit_rows = read_csv_rows(UNITS_CSV)

    candidate_by_day = Counter(event_date_from_row(row) for row in top_rows)
    candidate_exact_neighborhood_by_day = Counter(
        event_date_from_row(row)
        for row in top_rows
        if norm(row.get("coord_quality")).lower() in {"exact", "general neighborhood"}
    )
    candidate_admin_pending_by_day = Counter(
        event_date_from_row(row)
        for row in top_rows
        if norm(row.get("coord_quality")).lower()
        in {"pov", "general_town", "coordinate_precision_unknown"}
    )

    buffer_features_by_day = Counter(norm(row.get("event_date"))[:10] for row in buffer_features)
    buffer_features_2km_by_day = Counter(
        norm(row.get("event_date"))[:10] for row in buffer_features if str(row.get("radius_m")) == "2000"
    )
    buffer_features_5km_by_day = Counter(
        norm(row.get("event_date"))[:10] for row in buffer_features if str(row.get("radius_m")) == "5000"
    )
    admin_features_by_day = Counter(norm(row.get("event_date"))[:10] for row in admin_features)
    unresolved_admin_by_day = Counter(event_date_from_row(row) for row in unresolved_rows)

    unit_count_by_day = Counter(row["analysis_date"] for row in unit_rows)
    buffer_units_by_day = Counter(
        row["analysis_date"] for row in unit_rows if row.get("analysis_unit_type") == "buffer_overlap_day"
    )
    admin_units_by_day = Counter(
        row["analysis_date"] for row in unit_rows if row.get("analysis_unit_type") == "admin_day"
    )
    aggregated_units_by_day = Counter(
        row["analysis_date"] for row in unit_rows if row.get("is_aggregated") == "true"
    )
    represented_events_by_day: dict[str, int] = defaultdict(int)
    for row in unit_rows:
        represented_events_by_day[row["analysis_date"]] += split_member_count(row.get("member_event_count"))

    rows: list[dict[str, object]] = []
    for day in date_range():
        input_features = buffer_features_by_day[day] + admin_features_by_day[day]
        analysis_units = unit_count_by_day[day]
        rows.append(
            {
                "date_utc": day,
                "candidate_events": candidate_by_day[day],
                "candidate_buffer_points": candidate_exact_neighborhood_by_day[day],
                "candidate_admin_pending_points": candidate_admin_pending_by_day[day],
                "buffer_aoi_features_total": buffer_features_by_day[day],
                "buffer_aoi_features_2km": buffer_features_2km_by_day[day],
                "buffer_aoi_features_5km": buffer_features_5km_by_day[day],
                "admin_aoi_features_matched": admin_features_by_day[day],
                "admin_aoi_unresolved": unresolved_admin_by_day[day],
                "input_aoi_features_for_aggregation": input_features,
                "analysis_units_total": analysis_units,
                "buffer_overlap_units": buffer_units_by_day[day],
                "admin_day_units": admin_units_by_day[day],
                "aggregated_units_member_count_gt1": aggregated_units_by_day[day],
                "aggregation_reduction": input_features - analysis_units,
                "represented_member_events_in_units": represented_events_by_day[day],
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="daily_counts", index=False)
    OUTPUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "output_csv": str(OUTPUT_CSV),
        "output_xlsx": str(OUTPUT_XLSX),
        "output_json": str(OUTPUT_JSON),
        "days": len(rows),
        "candidate_events": int(df["candidate_events"].sum()),
        "input_aoi_features_for_aggregation": int(df["input_aoi_features_for_aggregation"].sum()),
        "analysis_units_total": int(df["analysis_units_total"].sum()),
        "aggregation_reduction": int(df["aggregation_reduction"].sum()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
