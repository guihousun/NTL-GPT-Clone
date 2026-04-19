"""Export all promoted ConflictNTL candidate events as point GeoJSON.

This is the non-AOI point layer used before buffer/admin aggregation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
OUTPUT_GEOJSON = DOCS / "ISW_candidate_points_2026-02-27_2026-04-07.geojson"
SUMMARY_JSON = DOCS / "ISW_candidate_points_2026-02-27_2026-04-07_summary.json"


def norm(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def event_date(row: dict[str, str]) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        value = norm(row.get(field))
        if value:
            return value[:10]
    return ""


def candidate_id(row: dict[str, str]) -> str:
    objectid = norm(row.get("objectid")) or "no_objectid"
    event_id = norm(row.get("event_id")) or "no_eventid"
    date = (event_date(row) or "unknown_date").replace("-", "")
    return f"ISW_{date}_{objectid}_{event_id}"


def coerce_float(value: Any) -> float | None:
    try:
        return float(norm(value))
    except Exception:
        return None


def main() -> None:
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    features: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        lon = coerce_float(row.get("longitude"))
        lat = coerce_float(row.get("latitude"))
        if lon is None or lat is None:
            skipped.append(row)
            continue
        props = {k: norm(v) for k, v in row.items()}
        props["candidate_id"] = candidate_id(row)
        props["event_date"] = event_date(row)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "name": "ISW_candidate_points_2026-02-27_2026-04-07",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }
    OUTPUT_GEOJSON.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "input_csv": str(INPUT_CSV),
        "output_geojson": str(OUTPUT_GEOJSON),
        "input_rows": len(rows),
        "output_features": len(features),
        "skipped_missing_coordinates": len(skipped),
        "geometry": "Point EPSG:4326",
        "candidate_id_rule": "ISW_{YYYYMMDD}_{objectid}_{event_id}",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
