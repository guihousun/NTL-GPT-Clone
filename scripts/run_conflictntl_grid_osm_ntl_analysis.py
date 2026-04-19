"""Grid + OSM building exposure analysis for ConflictNTL.

The script builds 5 km x 5 km country-clipped grid cells for Iran and Israel,
aggregates promoted ConflictNTL candidate events into those cells, optionally
adds OSM building exposure, and computes VNP46A1 change classes for high
building-density and high attack-density grids.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, shape


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_conflictntl_admin_ntl_stats import (  # noqa: E402
    dparse,
    extract_admin_stats,
    file_day,
    h5_meta,
    valid_h5_paths,
)


COUNTRIES = {"Iran", "Israel"}
COUNTRY_ISO3 = {"Iran": "IRN", "Israel": "ISR"}
PROJECTED_CRS = "EPSG:6933"
WGS84 = "EPSG:4326"
CHANGE_ORDER = [
    "large_decrease",
    "small_decrease",
    "stable",
    "small_increase",
    "large_increase",
]
CHANGE_CN = {
    "large_decrease": "大幅减小",
    "small_decrease": "小幅减小",
    "stable": "几乎不变",
    "small_increase": "小幅增加",
    "large_increase": "大幅增加",
    "invalid": "无效",
    "insufficient_valid_observations": "有效观测不足",
}
CHANGE_COLORS = {
    "large_decrease": "#b2182b",
    "small_decrease": "#ef8a62",
    "stable": "#f7f7f7",
    "small_increase": "#67a9cf",
    "large_increase": "#2166ac",
}


def read_events(path: Path) -> gpd.GeoDataFrame:
    rows = list(csv.DictReader(path.open("r", newline="", encoding="utf-8-sig")))
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("country") not in COUNTRIES:
            continue
        if row.get("final_ntl_candidate_status") != "promoted_to_ntl_queue":
            continue
        try:
            lat = float(row.get("latitude") or "")
            lon = float(row.get("longitude") or "")
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        day_raw = str(row.get("event_date_utc") or "")[:10]
        try:
            event_date = dparse(day_raw)
        except Exception:
            continue
        row["event_date"] = event_date.isoformat()
        row["geometry"] = Point(lon, lat)
        out.append(row)
    if not out:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=WGS84)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=WGS84)


def read_admin0(boundary_dir: Path) -> gpd.GeoDataFrame:
    paths = [
        boundary_dir / "irn_geoboundaries_adm0.geojson",
        boundary_dir / "isr_geoboundaries_adm0.geojson",
    ]
    records: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            iso3 = str(props.get("shapeGroup") or "")
            country = {v: k for k, v in COUNTRY_ISO3.items()}.get(iso3, iso3)
            records.append(
                {
                    "country": country,
                    "iso3": iso3,
                    "name": str(props.get("shapeName") or country),
                    "geometry": shape(feature.get("geometry")),
                }
            )
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=WGS84)
    return gdf[gdf["country"].isin(COUNTRIES)].copy()


def make_country_grid(admin0: gpd.GeoDataFrame, cell_size_m: float) -> gpd.GeoDataFrame:
    admin_p = admin0.to_crs(PROJECTED_CRS)
    rows: list[dict[str, Any]] = []
    for _, country_row in admin_p.iterrows():
        geom = country_row.geometry
        minx, miny, maxx, maxy = geom.bounds
        x0 = math.floor(minx / cell_size_m) * cell_size_m
        y0 = math.floor(miny / cell_size_m) * cell_size_m
        x_values = np.arange(x0, maxx + cell_size_m, cell_size_m)
        y_values = np.arange(y0, maxy + cell_size_m, cell_size_m)
        seq = 0
        for x in x_values:
            for y in y_values:
                cell = box(float(x), float(y), float(x + cell_size_m), float(y + cell_size_m))
                if not cell.intersects(geom):
                    continue
                clipped = cell.intersection(geom)
                if clipped.is_empty:
                    continue
                seq += 1
                rows.append(
                    {
                        "grid_id": f"{country_row.iso3}_G{seq:06d}",
                        "country": country_row.country,
                        "iso3": country_row.iso3,
                        "grid_area_km2": float(clipped.area / 1_000_000.0),
                        "geometry": clipped,
                    }
                )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=PROJECTED_CRS)


def aggregate_events_to_grid(events: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if events.empty or grid.empty:
        return grid.iloc[0:0].copy()
    events_p = events.to_crs(grid.crs)
    joined = gpd.sjoin(events_p, grid[["grid_id", "country", "geometry"]], how="inner", predicate="within")
    if joined.empty:
        return grid.iloc[0:0].copy()
    rows = []
    for grid_id, group in joined.groupby("grid_id", dropna=False):
        event_dates = sorted(str(v)[:10] for v in group["event_date"].dropna().astype(str))
        source_layers = sorted(set(group.get("source_layer", pd.Series(dtype=str)).dropna().astype(str)))
        site_types = sorted(set(group.get("site_type", pd.Series(dtype=str)).dropna().astype(str)))
        cities = sorted(set(group.get("city", pd.Series(dtype=str)).dropna().astype(str)))
        objectids = sorted(set(group.get("objectid", pd.Series(dtype=str)).dropna().astype(str)))
        rows.append(
            {
                "grid_id": grid_id,
                "event_count": int(len(group)),
                "first_attack_date": event_dates[0] if event_dates else "",
                "last_attack_date": event_dates[-1] if event_dates else "",
                "active_event_days": int(len(set(event_dates))),
                "source_layers": ";".join(source_layers),
                "site_types": ";".join(site_types),
                "cities": ";".join(cities),
                "event_objectids": ";".join(objectids),
            }
        )
    event_df = pd.DataFrame(rows)
    attacked = grid.merge(event_df, on="grid_id", how="inner")
    return gpd.GeoDataFrame(attacked, geometry="geometry", crs=grid.crs)


def expand_paths(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        for part in str(value).split(";"):
            part = part.strip().strip('"')
            if not part:
                continue
            p = Path(part)
            if p.is_dir():
                for suffix in ("*.geojson", "*.gpkg", "*.shp"):
                    paths.extend(sorted(p.rglob(suffix)))
            else:
                paths.append(p)
    return paths


def read_buildings(paths: list[Path], admin0: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if not paths:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=WGS84)
    bbox = tuple(admin0.total_bounds)
    parts = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Building file not found: {path}")
        try:
            gdf = gpd.read_file(path, bbox=bbox)
        except TypeError:
            gdf = gpd.read_file(path)
        if gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(WGS84)
        gdf = gdf[["geometry"]].copy()
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        if not gdf.empty:
            parts.append(gdf.to_crs(WGS84))
    if not parts:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=WGS84)
    return pd.concat(parts, ignore_index=True).pipe(gpd.GeoDataFrame, geometry="geometry", crs=WGS84)


def attach_building_exposure(grids: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = grids.copy()
    out["building_count"] = 0
    out["building_area_km2"] = 0.0
    out["building_density"] = 0.0
    if grids.empty or buildings.empty:
        return out
    buildings_p = buildings.to_crs(grids.crs)
    buildings_p = buildings_p[buildings_p.geometry.notna() & ~buildings_p.geometry.is_empty].copy()
    if buildings_p.empty:
        return out
    buildings_p["building_area_km2_single"] = buildings_p.geometry.area / 1_000_000.0
    buildings_p["geometry"] = buildings_p.geometry.representative_point()
    joined = gpd.sjoin(
        buildings_p[["building_area_km2_single", "geometry"]],
        grids[["grid_id", "geometry"]],
        how="inner",
        predicate="within",
    )
    if joined.empty:
        return out
    exposure = (
        joined.groupby("grid_id", dropna=False)
        .agg(building_count=("building_area_km2_single", "size"), building_area_km2=("building_area_km2_single", "sum"))
        .reset_index()
    )
    out = out.drop(columns=["building_count", "building_area_km2", "building_density"]).merge(exposure, on="grid_id", how="left")
    out["building_count"] = out["building_count"].fillna(0).astype(int)
    out["building_area_km2"] = out["building_area_km2"].fillna(0.0).astype(float)
    out["building_density"] = out["building_area_km2"] / out["grid_area_km2"].replace({0: np.nan})
    out["building_density"] = out["building_density"].fillna(0.0)
    return gpd.GeoDataFrame(out, geometry="geometry", crs=grids.crs)


def select_high_exposure_grids(
    grids: gpd.GeoDataFrame,
    quantile: float,
    fallback_quantile: float,
    min_selected: int,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    eligible = grids[(grids["event_count"] >= 1) & (grids["building_area_km2"] > 0)].copy()
    info: dict[str, Any] = {
        "eligible_attacked_builtup_grids": int(len(eligible)),
        "requested_quantile": quantile,
        "used_quantile": quantile,
    }
    if eligible.empty:
        info.update({"event_count_threshold": None, "building_density_threshold": None, "selected_grids": 0})
        return eligible, info
    q = quantile
    selected = _select_by_quantile(eligible, q)
    if len(selected) < min_selected and fallback_quantile < quantile:
        q = fallback_quantile
        selected = _select_by_quantile(eligible, q)
    bd_thr = float(eligible["building_density"].quantile(q))
    ev_thr = float(eligible["event_count"].quantile(q))
    info.update(
        {
            "used_quantile": q,
            "event_count_threshold": ev_thr,
            "building_density_threshold": bd_thr,
            "selected_grids": int(len(selected)),
        }
    )
    return selected, info


def _select_by_quantile(eligible: gpd.GeoDataFrame, q: float) -> gpd.GeoDataFrame:
    bd_thr = eligible["building_density"].quantile(q)
    ev_thr = eligible["event_count"].quantile(q)
    return eligible[(eligible["building_density"] >= bd_thr) & (eligible["event_count"] >= ev_thr)].copy()


def aggregate_daily_grid_stats(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return []
    ok = df[df["quality_status"] == "ok"].copy()
    rows: list[dict[str, Any]] = []
    keys = [
        "grid_id",
        "country",
        "event_count",
        "first_attack_date",
        "last_attack_date",
        "building_count",
        "building_area_km2",
        "building_density",
        "observation_date",
    ]
    for key, g in ok.groupby(keys, dropna=False):
        weights = g["valid_pixel_count"].astype(float)
        total = int(g["total_aoi_pixel_count"].sum())
        valid = int(g["valid_pixel_count"].sum())
        row = dict(zip(keys, key))
        row.update(
            {
                "tile_count": int(g["tile_id"].nunique()),
                "tile_ids": ";".join(sorted(g["tile_id"].dropna().astype(str).unique())),
                "total_aoi_pixel_count": total,
                "valid_pixel_count": valid,
                "invalid_pixel_count": total - valid,
                "valid_pixel_ratio": valid / total if total else math.nan,
                "mean_ntl": float(np.average(g["mean_ntl"], weights=weights)),
                "median_ntl": float(np.nanmedian(g["median_ntl"])),
                "max_ntl": float(np.nanmax(g["max_ntl"])),
                "std_ntl": float(np.nanmean(g["std_ntl"])),
                "quality_status": "ok",
            }
        )
        for col in ["utc_time_min", "utc_time_mean", "utc_time_max"]:
            if col in g and g[col].notna().any():
                row[col] = float(np.nanmean(g[col]))
        rows.append(row)
    return rows


def compute_grid_daily_stats(
    grids: gpd.GeoDataFrame,
    metas: list[dict[str, Any]],
    qa_mode: str,
    valid_threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows: list[dict[str, Any]] = []
    grids_wgs = grids.to_crs(WGS84)
    for _, unit in grids_wgs.iterrows():
        geom = unit.geometry
        for meta in metas:
            if not geom.intersects(meta["geom"]):
                continue
            stats = extract_admin_stats(meta["path"], geom, qa_mode, valid_threshold)
            raw_rows.append(
                {
                    "grid_id": unit.grid_id,
                    "country": unit.country,
                    "event_count": int(unit.event_count),
                    "first_attack_date": unit.first_attack_date,
                    "last_attack_date": unit.last_attack_date,
                    "building_count": int(unit.building_count),
                    "building_area_km2": float(unit.building_area_km2),
                    "building_density": float(unit.building_density),
                    "observation_date": meta["date"],
                    "tile_id": meta["tile_id"],
                    "h5_path": str(meta["path"]),
                    **stats,
                }
            )
    return raw_rows, aggregate_daily_grid_stats(raw_rows)


def classify_change(delta_pct: float) -> str:
    if not np.isfinite(delta_pct):
        return "invalid"
    if delta_pct <= -10:
        return "large_decrease"
    if delta_pct <= -5:
        return "small_decrease"
    if delta_pct < 5:
        return "stable"
    if delta_pct < 10:
        return "small_increase"
    return "large_increase"


def impact_summary(
    grids: gpd.GeoDataFrame,
    daily_rows: list[dict[str, Any]],
    start: date,
    end: date,
    min_baseline_days: int,
    min_post_days: int,
    min_baseline_ntl: float,
) -> gpd.GeoDataFrame:
    df = pd.DataFrame(daily_rows)
    base_rows = grids.drop(columns="geometry").copy()
    if df.empty:
        base_rows["change_class"] = "insufficient_valid_observations"
        base_rows["change_class_cn"] = CHANGE_CN["insufficient_valid_observations"]
        return grids[["grid_id", "geometry"]].merge(base_rows, on="grid_id")
    df["observation_date_d"] = pd.to_datetime(df["observation_date"]).dt.date
    rows: list[dict[str, Any]] = []
    for _, grid in grids.iterrows():
        g = df[df["grid_id"] == grid.grid_id]
        first_attack = dparse(grid.first_attack_date)
        baseline_end = first_attack - timedelta(days=1)
        baseline = g[(g["observation_date_d"] >= start) & (g["observation_date_d"] <= baseline_end)]
        post = g[(g["observation_date_d"] >= first_attack) & (g["observation_date_d"] <= end)]

        def wmean(part: pd.DataFrame) -> float:
            if part.empty:
                return math.nan
            return float(np.average(part["mean_ntl"], weights=part["valid_pixel_count"]))

        base_mean = wmean(baseline)
        post_mean = wmean(post)
        base_days = int(baseline["observation_date"].nunique()) if not baseline.empty else 0
        post_days = int(post["observation_date"].nunique()) if not post.empty else 0
        if base_days < min_baseline_days or post_days < min_post_days:
            cls = "insufficient_valid_observations"
            delta_abs = math.nan
            delta_pct = math.nan
        elif not np.isfinite(base_mean) or base_mean <= min_baseline_ntl:
            cls = "invalid"
            delta_abs = math.nan
            delta_pct = math.nan
        else:
            delta_abs = post_mean - base_mean
            delta_pct = delta_abs / base_mean * 100
            cls = classify_change(delta_pct)
        rows.append(
            {
                "grid_id": grid.grid_id,
                "country": grid.country,
                "event_count": int(grid.event_count),
                "first_attack_date": grid.first_attack_date,
                "last_attack_date": grid.last_attack_date,
                "active_event_days": int(grid.active_event_days),
                "building_count": int(grid.building_count),
                "building_area_km2": float(grid.building_area_km2),
                "building_density": float(grid.building_density),
                "baseline_mean_ntl": base_mean,
                "post_attack_mean_ntl": post_mean,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "change_class": cls,
                "change_class_cn": CHANGE_CN.get(cls, cls),
                "baseline_valid_days": base_days,
                "post_valid_days": post_days,
            }
        )
    out = pd.DataFrame(rows)
    return grids[["grid_id", "geometry"]].merge(out, on="grid_id", how="right")


def write_csv(path: Path, rows: pd.DataFrame | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_crs(WGS84).to_file(path, driver="GeoJSON")


def plot_change_bar(path: Path, class_counts: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=180)
    labels = [CHANGE_CN[c] for c in CHANGE_ORDER]
    counts = [int(class_counts.set_index("change_class").get("grid_count", pd.Series(dtype=int)).get(c, 0)) for c in CHANGE_ORDER]
    colors = [CHANGE_COLORS[c] for c in CHANGE_ORDER]
    ax.bar(labels, counts, color=colors, edgecolor="#333333", linewidth=0.6)
    ax.set_ylabel("Grid count")
    ax.set_xlabel("NTL change class")
    ax.set_title("High building-density and high attack-density grids")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_change_map(path: Path, admin0: gpd.GeoDataFrame, impact: gpd.GeoDataFrame, events: gpd.GeoDataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 6), dpi=180)
    admin0.to_crs(WGS84).boundary.plot(ax=ax, color="#555555", linewidth=0.8)
    plot_gdf = impact[impact["change_class"].isin(CHANGE_ORDER)].copy()
    if not plot_gdf.empty:
        plot_gdf = plot_gdf.to_crs(WGS84)
        for cls in CHANGE_ORDER:
            part = plot_gdf[plot_gdf["change_class"] == cls]
            if not part.empty:
                part.plot(ax=ax, color=CHANGE_COLORS[cls], edgecolor="#222222", linewidth=0.15, alpha=0.72, label=CHANGE_CN[cls])
    if not events.empty:
        events.to_crs(WGS84).plot(ax=ax, color="#111111", markersize=2, alpha=0.35)
    ax.set_title("Grid-based built-environment NTL change classes")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=7, frameon=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default=str(ROOT / "docs/ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"))
    p.add_argument("--boundary-dir", default=str(ROOT / "docs/geoboundaries_irn_isr_all_levels"))
    p.add_argument("--buildings", nargs="*", default=[], help="OSM building files or directories; supports ';' separated paths.")
    p.add_argument("--vnp-dir", default=r"E:\VNP46A1")
    p.add_argument("--output-dir", default=str(ROOT / "docs/ConflictNTL_grid_osm_ntl_stats_iran_israel"))
    p.add_argument("--start-date", default="2026-02-20")
    p.add_argument("--end-date", default="2026-04-07")
    p.add_argument("--cell-size-m", type=float, default=5000.0)
    p.add_argument("--qa-mode", choices=["none", "basic", "balanced", "clear_only"], default="balanced")
    p.add_argument("--valid-pixel-ratio", type=float, default=0.80)
    p.add_argument("--quantile", type=float, default=0.75)
    p.add_argument("--fallback-quantile", type=float, default=0.67)
    p.add_argument("--min-selected-grids", type=int, default=10)
    p.add_argument("--min-baseline-days", type=int, default=3)
    p.add_argument("--min-post-days", type=int, default=5)
    p.add_argument("--min-baseline-ntl", type=float, default=1e-9)
    p.add_argument("--event-grid-only", action="store_true", help="Stop after writing attacked event grids.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = dparse(args.start_date), dparse(args.end_date)

    events = read_events(Path(args.events))
    admin0 = read_admin0(Path(args.boundary_dir))
    grid = make_country_grid(admin0, args.cell_size_m)
    attacked = aggregate_events_to_grid(events, grid)
    write_geojson(out_dir / "ConflictNTL_5km_grid_attacked.geojson", attacked)
    write_csv(out_dir / "grid_event_counts.csv", attacked.drop(columns="geometry"))

    summary: dict[str, Any] = {
        "status": "partial",
        "events": int(len(events)),
        "country_grid_cells": int(len(grid)),
        "attacked_grid_cells": int(len(attacked)),
        "cell_size_m": args.cell_size_m,
        "qa_mode": args.qa_mode,
        "valid_pixel_ratio_threshold": args.valid_pixel_ratio,
    }

    building_paths = expand_paths(args.buildings)
    summary["building_inputs"] = [str(p) for p in building_paths]
    if args.event_grid_only or not building_paths:
        summary["reason"] = "building_inputs_missing" if not building_paths else "event_grid_only"
        (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))
        return 0

    buildings = read_buildings(building_paths, admin0)
    attacked = attach_building_exposure(attacked, buildings)
    write_geojson(out_dir / "ConflictNTL_5km_grid_attacked_with_buildings.geojson", attacked)
    write_csv(out_dir / "grid_event_building_exposure.csv", attacked.drop(columns="geometry"))
    summary["building_features"] = int(len(buildings))
    summary["attacked_builtup_grid_cells"] = int((attacked["building_area_km2"] > 0).sum())

    selected, selection_info = select_high_exposure_grids(
        attacked,
        quantile=args.quantile,
        fallback_quantile=args.fallback_quantile,
        min_selected=args.min_selected_grids,
    )
    summary["selection"] = selection_info
    write_geojson(out_dir / "ConflictNTL_5km_high_exposure_attacked_grids.geojson", selected)
    write_csv(out_dir / "high_exposure_attacked_grid_inputs.csv", selected.drop(columns="geometry"))

    if selected.empty:
        summary["status"] = "no_selected_grids"
        (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))
        return 0

    h5_paths = valid_h5_paths(Path(args.vnp_dir), start, end)
    metas = h5_meta(h5_paths)
    summary["h5_files"] = int(len(h5_paths))
    summary["h5_files_with_meta"] = int(len(metas))

    raw_daily, daily = compute_grid_daily_stats(selected, metas, args.qa_mode, args.valid_pixel_ratio)
    write_csv(out_dir / "grid_daily_tile_stats.csv", raw_daily)
    write_csv(out_dir / "grid_daily_ntl.csv", daily)

    impact = impact_summary(
        selected,
        daily,
        start=start,
        end=end,
        min_baseline_days=args.min_baseline_days,
        min_post_days=args.min_post_days,
        min_baseline_ntl=args.min_baseline_ntl,
    )
    write_geojson(out_dir / "ConflictNTL_5km_high_exposure_change_classes.geojson", impact)
    write_csv(out_dir / "grid_impact_summary.csv", impact.drop(columns="geometry"))

    valid_impact = impact[impact["change_class"].isin(CHANGE_ORDER)].copy()
    counts = (
        valid_impact.groupby("change_class", dropna=False)
        .size()
        .reindex(CHANGE_ORDER, fill_value=0)
        .rename("grid_count")
        .reset_index()
    )
    total = int(counts["grid_count"].sum())
    counts["change_class_cn"] = counts["change_class"].map(CHANGE_CN)
    counts["percent"] = counts["grid_count"] / total * 100 if total else 0.0
    write_csv(out_dir / "change_class_counts.csv", counts)

    top = valid_impact.copy()
    top["abs_delta_pct"] = top["delta_pct"].abs()
    top = top.sort_values(["abs_delta_pct", "event_count"], ascending=[False, False]).head(30)
    write_csv(
        out_dir / "top_changed_grids.csv",
        top.drop(columns="geometry")[
            [
                "grid_id",
                "country",
                "event_count",
                "building_density",
                "first_attack_date",
                "baseline_mean_ntl",
                "post_attack_mean_ntl",
                "delta_abs",
                "delta_pct",
                "change_class",
                "change_class_cn",
                "baseline_valid_days",
                "post_valid_days",
            ]
        ],
    )

    plot_change_bar(out_dir / "fig_change_class_counts.png", counts)
    plot_change_map(out_dir / "fig_grid_change_class_map.png", admin0, impact, events)

    summary.update(
        {
            "status": "success",
            "selected_grids": int(len(selected)),
            "daily_tile_rows": int(len(raw_daily)),
            "daily_rows": int(len(daily)),
            "impact_rows": int(len(impact)),
            "valid_impact_rows": int(len(valid_impact)),
            "change_class_counts": counts.to_dict(orient="records"),
        }
    )
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
