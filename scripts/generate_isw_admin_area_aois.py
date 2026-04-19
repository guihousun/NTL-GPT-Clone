"""Generate administrative-boundary AOIs for ISW candidates pending admin matching.

Input:
    docs/ISW_candidate_aois_2026-02-27_2026-04-07/ISW_candidate_admin_area_pending.csv

Outputs:
    docs/ISW_candidate_admin_aois_2026-02-27_2026-04-07/
      ISW_candidate_admin_boundaries.geojson
      ISW_candidate_admin_boundaries.shp
      unresolved_admin_boundaries.csv
      admin_boundary_match_summary.json

Matching strategy:
    Use each event coordinate as a lookup point against geoBoundaries ADM4, then
    ADM3, then ADM2. This avoids fragile name matching for translated or
    inconsistently spelled city names.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.global_admin_boundary_fetch import fetch_geoboundaries_boundary

DOCS = ROOT / "docs"
INPUT_CSV = (
    DOCS
    / "ISW_candidate_aois_2026-02-27_2026-04-07"
    / "ISW_candidate_admin_area_pending.csv"
)
OUTPUT_DIR = DOCS / "ISW_candidate_admin_aois_2026-02-27_2026-04-07"
CACHE_DIR = OUTPUT_DIR / "boundary_cache"
ADMIN_GEOJSON = OUTPUT_DIR / "ISW_candidate_admin_boundaries.geojson"
ADMIN_SHP = OUTPUT_DIR / "ISW_candidate_admin_boundaries.shp"
UNRESOLVED_CSV = OUTPUT_DIR / "unresolved_admin_boundaries.csv"
SUMMARY_JSON = OUTPUT_DIR / "admin_boundary_match_summary.json"

ADM_LEVELS = (4, 3, 2)

COUNTRY_ISO3 = {
    "azerbaijan": "AZE",
    "bahrain": "BHR",
    "iran": "IRN",
    "iraq": "IRQ",
    "israel": "ISR",
    "kuwait": "KWT",
    "lebanon": "LBN",
    "oman": "OMN",
    "qatar": "QAT",
    "saudi arabia": "SAU",
    "uae": "ARE",
    "united arab emirates": "ARE",
    "west bank": "PSE",
    "palestine": "PSE",
}

ADMIN_NAME_COLUMNS = ("shapeName", "shapeISO", "shapeID")


def norm(value: str | None) -> str:
    return (value or "").replace("\xa0", " ").strip()


def event_date(row: dict[str, str]) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc", "event_date"):
        value = norm(row.get(field))
        if value:
            return value[:10]
    return ""


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", norm(value)).strip("_") or "unknown"


def candidate_id(row: dict[str, str]) -> str:
    objectid = norm(row.get("objectid")) or "no_objectid"
    event_id = norm(row.get("event_id")) or "no_eventid"
    date = (event_date(row) or "unknown_date").replace("-", "")
    return f"ISW_{date}_{objectid}_{event_id}"


def country_to_iso3(country: str) -> str:
    key = norm(country).casefold()
    if re.fullmatch(r"[A-Za-z]{3}", norm(country)):
        upper = norm(country).upper()
        if upper == "UAE":
            return "ARE"
        return upper
    return COUNTRY_ISO3.get(key, "")


def load_rows() -> list[dict[str, str]]:
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def boundary_cache_path(iso3: str, adm_level: int) -> Path:
    return CACHE_DIR / f"{iso3.lower()}_geoboundaries_adm{adm_level}.geojson"


def load_boundary_layer(iso3: str, adm_level: int) -> tuple[gpd.GeoDataFrame | None, str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = boundary_cache_path(iso3, adm_level)
    if not path.exists():
        try:
            fetch_geoboundaries_boundary(
                country=iso3,
                adm_level=adm_level,
                output_name=path.stem,
                output_dir=str(path.parent),
                output_format="geojson",
                convert_geojson_to_shp=False,
            )
        except Exception as exc:
            return None, str(exc)

    try:
        layer = gpd.read_file(path).to_crs("EPSG:4326")
        layer = layer[~layer.geometry.is_empty & layer.geometry.notna()].copy()
        if layer.empty:
            return None, f"empty layer: {path}"
        return layer, ""
    except Exception as exc:
        return None, str(exc)


def first_containing_feature(layer: gpd.GeoDataFrame, point: Point) -> Any | None:
    candidates = layer.iloc[list(layer.sindex.intersection(point.bounds))]
    if candidates.empty:
        return None
    mask = candidates.geometry.contains(point) | candidates.geometry.touches(point)
    hits = candidates[mask]
    if hits.empty:
        return None
    return hits.iloc[0]


def admin_value(feature: Any, columns: tuple[str, ...]) -> str:
    for column in columns:
        if column in feature and norm(str(feature[column])):
            return norm(str(feature[column]))
    return ""


def build_matched_feature(row: dict[str, str], feature: Any, iso3: str, adm_level: int) -> dict[str, object]:
    return {
        "candidate_id": candidate_id(row),
        "objectid": norm(row.get("objectid")),
        "event_id": norm(row.get("event_id")),
        "event_date": event_date(row),
        "event_type": norm(row.get("event_type")),
        "site_type": norm(row.get("site_type")),
        "site_sub": norm(row.get("site_subtype")),
        "city": norm(row.get("city")),
        "province": norm(row.get("province")),
        "country": norm(row.get("country")),
        "latitude": norm(row.get("latitude")),
        "longitude": norm(row.get("longitude")),
        "coord_type": norm(row.get("coord_type")),
        "coord_qual": norm(row.get("coord_quality")),
        "round1_scr": norm(row.get("round1_score")),
        "ntl_level": norm(row.get("ntl_relevance_level")),
        "src_quality": norm(row.get("source_quality")),
        "aoi_method": "geoboundaries_admin_containing_point",
        "aoi_status": "matched",
        "admin_src": "geoBoundaries",
        "admin_iso3": iso3,
        "admin_level": f"ADM{adm_level}",
        "admin_name": admin_value(feature, ("shapeName", "shapeName_1", "NAME_4", "NAME_3", "NAME_2")),
        "admin_id": admin_value(feature, ("shapeID", "shapeISO", "GID_4", "GID_3", "GID_2")),
        "match_reason": f"point_within_geoboundaries_adm{adm_level}",
        "geometry": feature.geometry,
    }


def unresolved_row(row: dict[str, str], reason: str, iso3: str = "") -> dict[str, str]:
    out = dict(row)
    out["admin_iso3"] = iso3
    out["admin_match_status"] = "unresolved"
    out["admin_match_reason"] = reason
    return out


def write_unresolved(rows: list[dict[str, str]]) -> None:
    if not rows:
        UNRESOLVED_CSV.write_text("admin_match_status\n", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with UNRESOLVED_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def match_admin_aois(rows: list[dict[str, str]]) -> tuple[gpd.GeoDataFrame, list[dict[str, str]], dict[str, object]]:
    matched_features: list[dict[str, object]] = []
    unresolved: list[dict[str, str]] = []
    layer_errors: dict[str, list[str]] = defaultdict(list)

    by_country: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_country[norm(row.get("country"))].append(row)

    for country, country_rows in sorted(by_country.items()):
        iso3 = country_to_iso3(country)
        if not iso3:
            unresolved.extend(unresolved_row(row, f"unsupported_or_blank_country:{country}") for row in country_rows)
            continue

        remaining = list(country_rows)
        for adm_level in ADM_LEVELS:
            if not remaining:
                break
            layer, error = load_boundary_layer(iso3, adm_level)
            if layer is None:
                layer_errors[iso3].append(f"ADM{adm_level}:{error}")
                continue

            next_remaining: list[dict[str, str]] = []
            for row in remaining:
                try:
                    point = Point(float(row["longitude"]), float(row["latitude"]))
                except Exception:
                    next_remaining.append(row)
                    continue

                feature = first_containing_feature(layer, point)
                if feature is None:
                    next_remaining.append(row)
                    continue
                matched_features.append(build_matched_feature(row, feature, iso3, adm_level))
            remaining = next_remaining

        for row in remaining:
            reason = "no_containing_geoBoundaries_ADM4_ADM3_ADM2"
            if layer_errors.get(iso3):
                reason += "; layer_errors=" + " | ".join(layer_errors[iso3])
            unresolved.append(unresolved_row(row, reason, iso3=iso3))

    gdf = gpd.GeoDataFrame(matched_features, geometry="geometry", crs="EPSG:4326")
    summary = {
        "input": str(INPUT_CSV),
        "output_dir": str(OUTPUT_DIR),
        "input_pending_records": len(rows),
        "matched_records": len(gdf),
        "unresolved_records": len(unresolved),
        "adm_levels_tried": [f"ADM{level}" for level in ADM_LEVELS],
        "matched_by_admin_level": dict(Counter(gdf["admin_level"]) if not gdf.empty else {}),
        "matched_by_country": dict(Counter(gdf["country"]) if not gdf.empty else {}),
        "unresolved_by_country": dict(Counter(row.get("country", "") for row in unresolved)),
        "layer_errors": dict(layer_errors),
        "geojson": str(ADMIN_GEOJSON),
        "shapefile": str(ADMIN_SHP),
        "unresolved_csv": str(UNRESOLVED_CSV),
        "cache_dir": str(CACHE_DIR),
    }
    return gdf, unresolved, summary


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    gdf, unresolved, summary = match_admin_aois(rows)

    if not gdf.empty:
        gdf.to_file(ADMIN_GEOJSON, driver="GeoJSON")
        gdf.to_file(ADMIN_SHP, driver="ESRI Shapefile", encoding="UTF-8")
    else:
        ADMIN_GEOJSON.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")

    write_unresolved(unresolved)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
