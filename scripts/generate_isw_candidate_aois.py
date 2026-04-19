"""Generate first-pass AOIs for screened ISW NTL candidates.

Rules requested for the letter experiment:
- exact and general neighborhood points: generate a 2 km buffer.
- pov, general town, and unknown precision coordinates: mark them for smallest
  town/municipality/district AOI handling in a later step.

Run:
    conda run -n NTL-Claw-Stable python scripts/generate_isw_candidate_aois.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import Point, Polygon


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
OUTPUT_DIR = DOCS / "ISW_candidate_aois_2026-02-27_2026-04-07"
AOI_GEOJSON = OUTPUT_DIR / "ISW_candidate_point_buffers_2km.geojson"
AOI_SHP = OUTPUT_DIR / "ISW_candidate_point_buffers_2km.shp"
ADMIN_PENDING_CSV = OUTPUT_DIR / "ISW_candidate_admin_area_pending.csv"
SUMMARY_JSON = OUTPUT_DIR / "ISW_candidate_aoi_summary.json"
BUFFER_RADIUS_M = 2000

GEOD = Geod(ellps="WGS84")


def norm(value: str | None) -> str:
    return (value or "").replace("\xa0", " ").strip()


def event_date(row: dict[str, str]) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        value = norm(row.get(field))
        if value:
            return value[:10]
    return ""


def geodesic_buffer(lon: float, lat: float, radius_m: float, n: int = 96) -> Polygon:
    coords = []
    for azimuth in range(0, 360, max(1, int(360 / n))):
        x, y, _ = GEOD.fwd(lon, lat, azimuth, radius_m)
        coords.append((x, y))
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def candidate_id(row: dict[str, str]) -> str:
    objectid = norm(row.get("objectid")) or "no_objectid"
    event_id = norm(row.get("event_id")) or "no_eventid"
    date = (event_date(row) or "unknown_date").replace("-", "")
    return f"ISW_{date}_{objectid}_{event_id}"


BUFFER_COORD_QUALITIES = {"exact", "general neighborhood"}
BUFFER_COORD_TYPES = {"exact", "general neighborhood"}
ADMIN_COORD_QUALITIES = {"pov", "general_town", "coordinate_precision_unknown"}
ADMIN_COORD_TYPES = {"pov", "general town"}


def aoi_reason(row: dict[str, str], radius_m: int) -> str:
    site_type = norm(row.get("site_type")).lower() or "unknown"
    site_subtype = norm(row.get("site_subtype")).lower() or "unknown"
    coord_type = norm(row.get("coord_type")).lower() or "unknown"
    return (
        f"coord_type={coord_type}; first-pass fixed-target point-buffer AOI; "
        f"radius={radius_m}m; site_type={site_type}; site_subtype={site_subtype}"
    )


def build_aois(rows: list[dict[str, str]]) -> tuple[gpd.GeoDataFrame, list[dict[str, str]]]:
    features: list[dict[str, object]] = []
    pending: list[dict[str, str]] = []

    for row in rows:
        coord_quality = norm(row.get("coord_quality")).lower()
        coord_type = norm(row.get("coord_type")).lower()
        if coord_quality in BUFFER_COORD_QUALITIES or coord_type in BUFFER_COORD_TYPES:
            lon = float(row["longitude"])
            lat = float(row["latitude"])
            features.append(
                {
                    "candidate_id": candidate_id(row),
                    "objectid": norm(row.get("objectid")),
                    "event_id": norm(row.get("event_id")),
                    "event_date": event_date(row),
                    "event_type": norm(row.get("event_type")),
                    "site_type": norm(row.get("site_type")),
                    "site_sub": norm(row.get("site_subtype")),
                    "city": norm(row.get("city")),
                    "country": norm(row.get("country")),
                    "coord_type": coord_type,
                    "aoi_method": "geodesic_point_buffer",
                    "radius_m": BUFFER_RADIUS_M,
                    "aoi_conf": "medium_high" if coord_quality == "exact" else "medium",
                    "manual_ref": "false",
                    "round1_scr": norm(row.get("round1_score")),
                    "ntl_level": norm(row.get("ntl_relevance_level")),
                    "src_quality": norm(row.get("source_quality")),
                    "reason": aoi_reason(row, BUFFER_RADIUS_M),
                    "geometry": geodesic_buffer(lon, lat, BUFFER_RADIUS_M),
                }
            )
        elif coord_type in ADMIN_COORD_TYPES or coord_quality in ADMIN_COORD_QUALITIES:
            pending_row = dict(row)
            pending_row["aoi_method"] = "smallest_town_municipality_district"
            pending_row["aoi_status"] = "pending_admin_boundary_match"
            pending_row["aoi_reason"] = "coord_type is not exact/general neighborhood; use smallest available town/municipality/district boundary"
            pending.append(pending_row)
        else:
            pending_row = dict(row)
            pending_row["aoi_method"] = "none"
            pending_row["aoi_status"] = "missing_or_unsupported_coordinate_quality"
            pending_row["aoi_reason"] = "no exact point and not a supported admin-area coordinate class"
            pending.append(pending_row)

    gdf = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")
    return gdf, pending


def write_pending(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("aoi_status\n", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    gdf, pending = build_aois(rows)
    gdf.to_file(AOI_GEOJSON, driver="GeoJSON")
    gdf.to_file(AOI_SHP, driver="ESRI Shapefile", encoding="UTF-8")
    write_pending(ADMIN_PENDING_CSV, pending)

    summary = {
        "input": str(INPUT_CSV),
        "output_dir": str(OUTPUT_DIR),
        "input_candidate_points": len(rows),
        "buffered_points": int(len(gdf)),
        "buffer_features": len(gdf),
        "buffer_radii_m": [BUFFER_RADIUS_M],
        "admin_area_pending": len(pending),
        "geojson": str(AOI_GEOJSON),
        "shapefile": str(AOI_SHP),
        "admin_pending_csv": str(ADMIN_PENDING_CSV),
        "rules": [
            "exact and general neighborhood points receive one 2 km geodesic buffer",
            "pov, general town, and unknown precision coordinates are deferred to smallest town/municipality/district boundary matching",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
