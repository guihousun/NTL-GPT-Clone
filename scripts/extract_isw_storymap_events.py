"""Extract ISW StoryMap event points from public ArcGIS FeatureServer layers.

Input StoryMap:
https://storymaps.arcgis.com/stories/089bc1a2fe684405a67d67f13bd31324

The StoryMap currently references two event point layers that are directly
useful for ConflictNTL:
- Combined Force / U.S.-Israeli strikes in Iran
- Iran and Axis retaliatory strikes

Outputs are normalized CSV and GeoJSON files under docs/.
"""

from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RAW_DIR = DOCS / "isw_storymap_raw"
START_DATE = datetime(2026, 2, 27, tzinfo=timezone.utc)
END_DATE = datetime(2026, 4, 15, 23, 59, 59, tzinfo=timezone.utc)

STORYMAP_ID = "089bc1a2fe684405a67d67f13bd31324"
STORYMAP_URL = f"https://storymaps.arcgis.com/stories/{STORYMAP_ID}"
STORYMAP_COVERAGE_LABEL = "February 28 - April 14, 2026, at 2:00 PM ET"
STORYMAP_COVERAGE_END_ET = "2026-04-14T14:00:00-04:00"
STORYMAP_COVERAGE_END_UTC = "2026-04-14T18:00:00Z"
STORYMAP_COVERAGE_END_BEIJING = "2026-04-15T02:00:00+08:00"

LAYERS = [
    {
        "name": "combined_force_strikes_on_iran_2026",
        "label": "View Combined Force Strikes on Iran 2026",
        "event_family": "us_israel_combined_force_strike",
        "url": "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services/MDS_CF_Strikes_on_Iran_2026_view/FeatureServer/0",
    },
    {
        "name": "iran_axis_retaliatory_strikes_2026",
        "label": "View Iran Axis Retaliatory Strikes 2026",
        "event_family": "iran_axis_retaliatory_strike",
        "url": "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services/View_Iran_Axis_Retaliatory_Strikes_2026/FeatureServer/0",
    },
]

OUTPUT_CSV = DOCS / "ISW_storymap_events_2026-02-27_2026-04-15.csv"
OUTPUT_GEOJSON = DOCS / "ISW_storymap_events_2026-02-27_2026-04-15.geojson"
OUTPUT_METADATA = DOCS / "ISW_storymap_events_2026-02-27_2026-04-15_metadata.json"

CSV_FIELDS = [
    "source_storymap_url",
    "source_layer",
    "source_layer_url",
    "event_family",
    "objectid",
    "event_id",
    "event_date_utc",
    "post_date_utc",
    "publication_date_utc",
    "time_utc",
    "time_raw",
    "event_type",
    "confirmed",
    "struck",
    "actor",
    "side",
    "subject",
    "site_type",
    "site_subtype",
    "city",
    "province",
    "country",
    "latitude",
    "longitude",
    "coord_type",
    "source_1",
    "source_2",
    "sources",
]


def request_json(url: str, params: dict[str, Any] | None = None, *, retries: int = 6) -> dict[str, Any]:
    params = params or {}
    for attempt in range(retries):
        response = requests.get(url, params=params, timeout=90)
        data = response.json()
        if "error" not in data:
            return data
        error = data["error"]
        if error.get("code") == 429 and attempt < retries - 1:
            detail = " ".join(error.get("details") or [])
            match = re.search(r"Retry after\s+(\d+)", detail, re.I)
            wait_seconds = int(match.group(1)) + 5 if match else 65
            print(f"rate_limited wait_seconds={wait_seconds} url={url}")
            time.sleep(wait_seconds)
            continue
        raise RuntimeError(f"ArcGIS request failed: {url} {error}")
    raise RuntimeError(f"ArcGIS request exhausted retries: {url}")


def arcgis_date_to_iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric) > 10_000_000_000:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return str(value)


def iso_to_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_attr(attrs: dict[str, Any], *names: str) -> Any:
    lower = {key.lower(): key for key in attrs}
    for name in names:
        key = lower.get(name.lower())
        if key is not None:
            return attrs.get(key)
    return ""


def first_date(attrs: dict[str, Any], *names: str) -> str:
    for name in names:
        value = get_attr(attrs, name)
        iso = arcgis_date_to_iso(value)
        if iso:
            return iso
    return ""


def fetch_layer(layer: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_path = RAW_DIR / f"{layer['name']}.json"
    metadata = request_json(layer["url"], {"f": "json"})
    if raw_path.exists():
        features = json.loads(raw_path.read_text(encoding="utf-8"))
        print(f"using_cache layer={layer['name']} count={len(features)}")
        return metadata, features

    count_payload = request_json(
        f"{layer['url']}/query",
        {"f": "json", "where": "1=1", "returnCountOnly": "true"},
    )
    total = int(count_payload.get("count", 0))
    page_size = min(int(metadata.get("maxRecordCount") or 2000), 2000)
    features: list[dict[str, Any]] = []
    offset = 0
    while offset < total:
        payload = request_json(
            f"{layer['url']}/query",
            {
                "f": "json",
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            },
        )
        batch = payload.get("features", [])
        if not batch:
            break
        features.extend(batch)
        offset += len(batch)
        print(f"fetched layer={layer['name']} offset={offset}/{total}")
        time.sleep(1)
    return metadata, features


def normalize_feature(layer: dict[str, str], feature: dict[str, Any]) -> dict[str, Any]:
    attrs = feature.get("attributes") or {}
    geom = feature.get("geometry") or {}
    event_date = first_date(attrs, "strikedate", "AssessedDayofStrike", "assesseddayofstrike")
    post_date = first_date(attrs, "post_date", "Post_Date")
    pub_date = first_date(attrs, "pub_date", "Publication_Date")
    time_date = first_date(attrs, "time")

    longitude = get_attr(attrs, "longitude", "Longitude") or geom.get("x") or ""
    latitude = get_attr(attrs, "latitude", "Latitude") or geom.get("y") or ""

    return {
        "source_storymap_url": STORYMAP_URL,
        "source_layer": layer["label"],
        "source_layer_url": layer["url"],
        "event_family": layer["event_family"],
        "objectid": get_attr(attrs, "OBJECTID"),
        "event_id": get_attr(attrs, "event_id"),
        "event_date_utc": event_date,
        "post_date_utc": post_date,
        "publication_date_utc": pub_date,
        "time_utc": time_date,
        "time_raw": get_attr(attrs, "Time", "time"),
        "event_type": get_attr(attrs, "event_type", "Event_Type__Confirmed_Airstrike__Reported_Airstrike__Report_of_E"),
        "confirmed": get_attr(attrs, "confirmed", "confirmed_"),
        "struck": get_attr(attrs, "struck", "struck_"),
        "actor": get_attr(attrs, "actor", "Actor"),
        "side": get_attr(attrs, "side"),
        "subject": get_attr(attrs, "subject", "SIGACT"),
        "site_type": get_attr(attrs, "site_type", "Site_Type__Nuclear__Military__Energy__etc__"),
        "site_subtype": get_attr(attrs, "siteStype", "SiteSubtype"),
        "city": get_attr(attrs, "city", "City"),
        "province": get_attr(attrs, "province", "Province", "District"),
        "country": get_attr(attrs, "country", "Country"),
        "latitude": latitude,
        "longitude": longitude,
        "coord_type": get_attr(attrs, "coord_type", "Coord_Type", "Geolocated_"),
        "source_1": get_attr(attrs, "source_1", "Source_1"),
        "source_2": get_attr(attrs, "source_2", "Source_2"),
        "sources": get_attr(attrs, "sources", "sources_combined"),
        "_raw_attributes": attrs,
        "_geometry": geom,
    }


def include_record(row: dict[str, Any]) -> bool:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        dt_value = iso_to_dt(str(row.get(field) or ""))
        if dt_value is not None:
            return START_DATE <= dt_value <= END_DATE
    return True


def to_geojson_feature(row: dict[str, Any]) -> dict[str, Any]:
    properties = {key: value for key, value in row.items() if not key.startswith("_")}
    try:
        lon = float(row["longitude"])
        lat = float(row["latitude"])
        geometry = {"type": "Point", "coordinates": [lon, lat]}
    except (TypeError, ValueError):
        geometry = None
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    metadata_out: dict[str, Any] = {
        "storymap_id": STORYMAP_ID,
        "storymap_url": STORYMAP_URL,
        "storymap_coverage_label": STORYMAP_COVERAGE_LABEL,
        "storymap_coverage_time_note": "ISW public coverage label uses U.S. Eastern Time. April is EDT / UTC-4, so Beijing time is 12 hours ahead.",
        "storymap_coverage_end_et": STORYMAP_COVERAGE_END_ET,
        "storymap_coverage_end_utc": STORYMAP_COVERAGE_END_UTC,
        "storymap_coverage_end_beijing": STORYMAP_COVERAGE_END_BEIJING,
        "date_grouping_note": "Rows are filtered and daily shapefiles are grouped by normalized UTC date fields unless a separate ET/BJT grouping is requested.",
        "date_window_utc": {
            "start": START_DATE.isoformat().replace("+00:00", "Z"),
            "end": END_DATE.isoformat().replace("+00:00", "Z"),
        },
        "layers": [],
    }

    for layer in LAYERS:
        metadata, features = fetch_layer(layer)
        raw_path = RAW_DIR / f"{layer['name']}.json"
        if not raw_path.exists():
            raw_path.write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
        rows = [normalize_feature(layer, feature) for feature in features]
        rows = [row for row in rows if include_record(row)]
        all_rows.extend(rows)
        metadata_out["layers"].append(
            {
                "name": layer["name"],
                "label": layer["label"],
                "url": layer["url"],
                "feature_count_raw": len(features),
                "feature_count_in_window": len(rows),
                "raw_export": str(raw_path),
                "fields": [field.get("name") for field in metadata.get("fields", [])],
            }
        )

    all_rows.sort(key=lambda row: (row.get("event_date_utc") or row.get("post_date_utc") or "", row["source_layer"], str(row["objectid"])))

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})

    geojson = {
        "type": "FeatureCollection",
        "name": OUTPUT_GEOJSON.stem,
        "source": STORYMAP_URL,
        "features": [to_geojson_feature(row) for row in all_rows],
    }
    OUTPUT_GEOJSON.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata_out["total_records"] = len(all_rows)
    OUTPUT_METADATA.write_text(json.dumps(metadata_out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"records={len(all_rows)}")
    print(f"csv={OUTPUT_CSV}")
    print(f"geojson={OUTPUT_GEOJSON}")
    print(f"metadata={OUTPUT_METADATA}")


if __name__ == "__main__":
    main()
