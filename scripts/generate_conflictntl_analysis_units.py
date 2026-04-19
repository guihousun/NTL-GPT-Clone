"""Aggregate ConflictNTL AOIs into same-day analysis units.

This script intentionally uses only two conservative aggregation rules:

1. Buffer AOIs: same event date + same radius + any positive spatial overlap.
2. Admin AOIs: same event date + same geoBoundaries administrative unit.

It does not infer shared facilities, targets, compounds, or source semantics.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
OUTPUT_DIR = DOCS / "ConflictNTL_analysis_units_2026-02-27_2026-04-07"
BUFFER_UNITS_GEOJSON = OUTPUT_DIR / "ConflictNTL_buffer_overlap_units.geojson"
ADMIN_UNITS_GEOJSON = OUTPUT_DIR / "ConflictNTL_admin_day_units.geojson"
ALL_UNITS_GEOJSON = OUTPUT_DIR / "ConflictNTL_analysis_units_all.geojson"
SUMMARY_CSV = OUTPUT_DIR / "ConflictNTL_analysis_units_summary.csv"
SUMMARY_JSON = OUTPUT_DIR / "ConflictNTL_analysis_units_summary.json"

OVERLAP_THRESHOLD = 0.0
AREA_CRS = "EPSG:6933"

SOURCE_QUALITY_RANK = {
    "missing_sources": 0,
    "weak_lead": 1,
    "social_multi_lead": 2,
    "reference_plus_leads": 3,
    "strong": 4,
}


def norm(value: object) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def candidate_id_from_row(row: dict[str, str]) -> str:
    objectid = norm(row.get("objectid")) or "no_objectid"
    event_id = norm(row.get("event_id")) or "no_eventid"
    date = (event_date_from_row(row) or "unknown_date").replace("-", "")
    return f"ISW_{date}_{objectid}_{event_id}"


def event_date_from_row(row: dict[str, str]) -> str:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc", "event_date"):
        value = norm(row.get(field))
        if value:
            return value[:10]
    return ""


def unique_join(values: Iterable[object], sep: str = ";") -> str:
    seen: list[str] = []
    for value in values:
        item = norm(value)
        if item and item not in seen:
            seen.append(item)
    return sep.join(seen)


def max_int(values: Iterable[object]) -> int:
    nums: list[int] = []
    for value in values:
        try:
            nums.append(int(float(norm(value))))
        except Exception:
            pass
    return max(nums) if nums else 0


def best_source_quality(values: Iterable[object]) -> str:
    best = ""
    best_rank = -1
    for value in values:
        item = norm(value)
        rank = SOURCE_QUALITY_RANK.get(item, -1)
        if rank > best_rank:
            best = item
            best_rank = rank
    return best


def load_candidate_metadata() -> dict[str, dict[str, str]]:
    with TOP_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {candidate_id_from_row(row): row for row in rows}


def add_candidate_metadata(gdf: gpd.GeoDataFrame, metadata: dict[str, dict[str, str]]) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    for field in ("source_layer", "event_family", "source_layer_url"):
        if field not in gdf.columns:
            gdf[field] = gdf["candidate_id"].map(lambda cid: metadata.get(norm(cid), {}).get(field, ""))
    return gdf


def normalize_event_date_column(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    raw = gdf["event_date"].map(norm).str[:10]
    parsed = pd.to_datetime(raw, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    gdf["event_date"] = parsed

    missing = gdf["event_date"].eq("")
    if missing.any() and "candidate_id" in gdf.columns:
        from_id = gdf.loc[missing, "candidate_id"].map(date_from_candidate_id)
        gdf.loc[missing, "event_date"] = from_id
    return gdf


def date_from_candidate_id(candidate_id: object) -> str:
    match = re.search(r"ISW_(\d{8})_", norm(candidate_id))
    if not match:
        return ""
    value = match.group(1)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


class UnionFind:
    def __init__(self, items: list[int]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: int) -> int:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, a: int, b: int) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a

    def components(self) -> list[list[int]]:
        groups: dict[int, list[int]] = defaultdict(list)
        for item in self.parent:
            groups[self.find(item)].append(item)
        return list(groups.values())


def overlap_components(group: gpd.GeoDataFrame, threshold: float) -> list[list[int]]:
    indexes = list(group.index)
    uf = UnionFind(indexes)
    projected = group.to_crs(AREA_CRS)
    areas = projected.geometry.area.to_dict()
    sindex = projected.sindex

    for idx in indexes:
        geom = projected.at[idx, "geometry"]
        if geom is None or geom.is_empty:
            continue
        for other_idx in sindex.intersection(geom.bounds):
            other_idx = int(other_idx)
            other = projected.index[other_idx]
            if other <= idx:
                continue
            other_geom = projected.at[other, "geometry"]
            if other_geom is None or other_geom.is_empty:
                continue
            inter_area = geom.intersection(other_geom).area
            if inter_area <= 0:
                continue
            denom = min(areas.get(idx, 0), areas.get(other, 0))
            if denom > 0 and inter_area / denom >= threshold:
                uf.union(idx, other)
    return uf.components()


def summarize_members(members: gpd.GeoDataFrame, geometry, unit_id: str, unit_type: str, method: str) -> dict[str, object]:
    projected_area = gpd.GeoSeries([geometry], crs=members.crs).to_crs(AREA_CRS).area.iloc[0] / 1_000_000
    return {
        "analysis_unit_id": unit_id,
        "analysis_unit_type": unit_type,
        "analysis_date": unique_join(members["event_date"]),
        "aggregation_method": method,
        "member_event_count": int(len(members)),
        "member_candidate_ids": unique_join(members["candidate_id"]),
        "member_event_ids": unique_join(members.get("event_id", [])),
        "member_objectids": unique_join(members.get("objectid", [])),
        "countries": unique_join(members.get("country", [])),
        "cities": unique_join(members.get("city", [])),
        "site_types": unique_join(members.get("site_type", [])),
        "site_subtypes": unique_join(members.get("site_sub", [])),
        "coord_qualities": unique_join(members.get("coord_qual", members.get("coord_type", []))),
        "source_layers": unique_join(members.get("source_layer", [])),
        "source_quality_max": best_source_quality(members.get("src_quality", [])),
        "round1_score_max": max_int(members.get("round1_scr", [])),
        "ntl_relevance_levels": unique_join(members.get("ntl_level", [])),
        "aoi_area_km2": round(float(projected_area), 6),
        "is_aggregated": str(len(members) > 1).lower(),
        "geometry": geometry,
    }


def aggregate_buffers(buffer_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    output_rows: list[dict[str, object]] = []
    seq = 1

    for (event_date, radius_m), group in buffer_gdf.groupby(["event_date", "radius_m"], dropna=False):
        components = overlap_components(group, OVERLAP_THRESHOLD)
        for component in components:
            members = group.loc[component]
            geometry = members.geometry.union_all()
            unit_id = f"BUF_{str(event_date).replace('-', '')}_R{int(radius_m)}_{seq:05d}"
            row = summarize_members(
                members=members,
                geometry=geometry,
                unit_id=unit_id,
                unit_type="buffer_overlap_day",
                method="same_day_same_radius_any_positive_overlap",
            )
            row.update(
                {
                    "aoi_type": "buffer",
                    "radius_m": int(radius_m),
                    "admin_iso3": "",
                    "admin_level": "",
                    "admin_id": "",
                    "admin_name": "",
                }
            )
            output_rows.append(row)
            seq += 1

    return gpd.GeoDataFrame(output_rows, geometry="geometry", crs=buffer_gdf.crs)


def aggregate_admin(admin_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    output_rows: list[dict[str, object]] = []
    seq = 1
    keys = ["event_date", "admin_iso3", "admin_level", "admin_id"]

    for key_values, group in admin_gdf.groupby(keys, dropna=False):
        event_date, admin_iso3, admin_level, admin_id = key_values
        geometry = group.geometry.union_all()
        unit_id = f"ADM_{str(event_date).replace('-', '')}_{norm(admin_iso3)}_{norm(admin_level)}_{seq:05d}"
        row = summarize_members(
            members=group,
            geometry=geometry,
            unit_id=unit_id,
            unit_type="admin_day",
            method="same_day_same_admin_boundary",
        )
        row.update(
            {
                "aoi_type": "admin",
                "radius_m": "",
                "admin_iso3": norm(admin_iso3),
                "admin_level": norm(admin_level),
                "admin_id": norm(admin_id),
                "admin_name": unique_join(group.get("admin_name", [])),
            }
        )
        output_rows.append(row)
        seq += 1

    return gpd.GeoDataFrame(output_rows, geometry="geometry", crs=admin_gdf.crs)


def write_summary_csv(all_units: gpd.GeoDataFrame) -> None:
    rows = all_units.drop(columns="geometry").to_dict("records")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    buffer_gdf: gpd.GeoDataFrame,
    buffer_units: gpd.GeoDataFrame,
    admin_gdf: gpd.GeoDataFrame,
    admin_units: gpd.GeoDataFrame,
    all_units: gpd.GeoDataFrame,
) -> dict[str, object]:
    return {
        "inputs": {
            "buffer_geojson": str(BUFFER_GEOJSON),
            "admin_geojson": str(ADMIN_GEOJSON),
        },
        "outputs": {
            "buffer_units_geojson": str(BUFFER_UNITS_GEOJSON),
            "admin_units_geojson": str(ADMIN_UNITS_GEOJSON),
            "all_units_geojson": str(ALL_UNITS_GEOJSON),
            "summary_csv": str(SUMMARY_CSV),
        },
        "rules": {
            "buffer_overlap_threshold": OVERLAP_THRESHOLD,
            "buffer_overlap_rule": "intersection_area > 0",
            "buffer_overlap_ratio": "intersection_area / min(area_a, area_b), retained for diagnostics",
            "buffer_grouping": "same event_date and same radius_m",
            "admin_grouping": "same event_date, admin_iso3, admin_level, admin_id",
            "area_crs": AREA_CRS,
        },
        "buffer_input_features": int(len(buffer_gdf)),
        "buffer_analysis_units": int(len(buffer_units)),
        "buffer_merged_feature_reduction": int(len(buffer_gdf) - len(buffer_units)),
        "buffer_units_by_radius": {
            str(k): int(v) for k, v in Counter(buffer_units["radius_m"]).items()
        },
        "buffer_aggregated_units": int((buffer_units["member_event_count"] > 1).sum()),
        "buffer_singleton_units": int((buffer_units["member_event_count"] == 1).sum()),
        "admin_input_features": int(len(admin_gdf)),
        "admin_analysis_units": int(len(admin_units)),
        "admin_merged_feature_reduction": int(len(admin_gdf) - len(admin_units)),
        "admin_aggregated_units": int((admin_units["member_event_count"] > 1).sum()),
        "admin_singleton_units": int((admin_units["member_event_count"] == 1).sum()),
        "total_analysis_units": int(len(all_units)),
        "total_input_aoi_features": int(len(buffer_gdf) + len(admin_gdf)),
        "total_feature_reduction": int((len(buffer_gdf) + len(admin_gdf)) - len(all_units)),
        "analysis_units_by_type": {
            str(k): int(v) for k, v in Counter(all_units["analysis_unit_type"]).items()
        },
        "top_aggregated_units": all_units.sort_values(
            ["member_event_count", "analysis_date"], ascending=[False, True]
        )
        .head(25)
        .drop(columns="geometry")
        .to_dict("records"),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = load_candidate_metadata()

    buffer_gdf = gpd.read_file(BUFFER_GEOJSON).to_crs("EPSG:4326")
    admin_gdf = gpd.read_file(ADMIN_GEOJSON).to_crs("EPSG:4326")
    buffer_gdf = normalize_event_date_column(buffer_gdf)
    admin_gdf = normalize_event_date_column(admin_gdf)
    buffer_gdf = add_candidate_metadata(buffer_gdf, metadata)
    admin_gdf = add_candidate_metadata(admin_gdf, metadata)

    buffer_units = aggregate_buffers(buffer_gdf)
    admin_units = aggregate_admin(admin_gdf)
    all_units = gpd.GeoDataFrame(
        pd.concat([buffer_units, admin_units], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )

    buffer_units.to_file(BUFFER_UNITS_GEOJSON, driver="GeoJSON")
    admin_units.to_file(ADMIN_UNITS_GEOJSON, driver="GeoJSON")
    all_units.to_file(ALL_UNITS_GEOJSON, driver="GeoJSON")
    write_summary_csv(all_units)

    summary = build_summary(buffer_gdf, buffer_units, admin_gdf, admin_units, all_units)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
