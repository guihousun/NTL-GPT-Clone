"""ConflictNTL VNP46A1 statistics via NASA LAADS/CMR.

Default workflow:
1) read ConflictNTL analysis-unit GeoJSON;
2) query VNP46A1 granules from CMR for the full AOI/date window;
3) optionally download missing HDF5 files;
4) compute AOI daily statistics and pre/event/recovery metrics from local HDF5.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.official_daily_ntl_fastpath.cmr_client import (  # noqa: E402
    download_file_with_curl,
    extract_download_link,
    resolve_token,
    search_granules,
)


DEFAULT_UNITS = ROOT / "docs/ConflictNTL_analysis_units_2026-02-27_2026-04-07/ConflictNTL_analysis_units_all.geojson"
DEFAULT_OUT = ROOT / "docs/ConflictNTL_vnp46a1_stats_2026-02-27_2026-04-07"
GRID = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
GRANULE_FIELDS = [
    "date",
    "query_dates",
    "query_record_count",
    "producer_granule_id",
    "time_start",
    "updated",
    "day_night_flag",
    "tile_id",
    "download_url",
    "local_path",
    "granule_size_mb",
    "status",
    "error_message",
]
DAILY_FIELDS = [
    "analysis_date",
    "analysis_unit_id",
    "analysis_unit_type",
    "aoi_type",
    "countries",
    "days_from_event",
    "max_ntl",
    "mean_ntl",
    "median_ntl",
    "member_event_count",
    "observation_date",
    "radius_m",
    "site_subtypes",
    "site_types",
    "status",
    "std_ntl",
    "tile_ids",
    "utc_time_max",
    "utc_time_mean",
    "utc_time_min",
    "valid_pixel_count",
]
PATHS = {
    "radiance": [f"{GRID}/DNB_At_Sensor_Radiance", "DNB_At_Sensor_Radiance"],
    "utc": [f"{GRID}/UTC_Time", "UTC_Time"],
    "lat": [f"{GRID}/lat", "lat"],
    "lon": [f"{GRID}/lon", "lon"],
    "cloud": [f"{GRID}/QF_Cloud_Mask", "QF_Cloud_Mask"],
    "dnb_qf": [f"{GRID}/QF_DNB", "QF_DNB"],
}


def dparse(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def drange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def dec(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.size:
        return dec(value.ravel()[0])
    return str(value)


def num(value: Any) -> float | None:
    try:
        if isinstance(value, np.ndarray):
            value = value.ravel()[0]
        return float(value)
    except Exception:
        m = re.search(r"-?\d+(?:\.\d+)?", dec(value))
        return float(m.group(0)) if m else None


def ds(h5: h5py.File, candidates: list[str]):
    for p in candidates:
        if p in h5:
            return h5[p]
    found = {}
    h5.visititems(lambda name, obj: found.setdefault(Path(name).name.lower(), name) if isinstance(obj, h5py.Dataset) else None)
    for p in candidates:
        hit = found.get(Path(p).name.lower())
        if hit:
            return h5[hit]
    return None


def fill(dataset) -> float | None:
    return num(dataset.attrs.get("_FillValue")) if dataset is not None else None


def scaled(dataset, arr):
    out = arr.astype("float64", copy=False)
    scale = num(dataset.attrs.get("scale_factor"))
    offset = num(dataset.attrs.get("add_offset"))
    if scale not in (None, 1.0):
        out = out * scale
    if offset not in (None, 0.0):
        out = out + offset
    return out


def tile_id(name: str) -> str:
    m = re.search(r"\.h(\d{2})v(\d{2})\.", name)
    return f"h{m.group(1)}v{m.group(2)}" if m else ""


def file_day(name: str) -> str:
    m = re.search(r"\.A(\d{4})(\d{3})\.", name)
    if not m:
        return ""
    return (date(int(m.group(1)), 1, 1) + timedelta(days=int(m.group(2)) - 1)).isoformat()


def h5_day(h5: h5py.File, path: Path) -> str:
    raw = dec(h5.attrs.get("RangeBeginningDate", "")).strip("b'\"")
    return raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", raw) else file_day(path.name)


def h5_bounds(h5: h5py.File):
    vals = [num(h5.attrs.get(k)) for k in ["WestBoundingCoord", "SouthBoundingCoord", "EastBoundingCoord", "NorthBoundingCoord"]]
    if all(v is not None for v in vals):
        return tuple(float(v) for v in vals)
    lat, lon = ds(h5, PATHS["lat"]), ds(h5, PATHS["lon"])
    if lat is None or lon is None:
        return None
    la, lo = lat[:], lon[:]
    return float(np.nanmin(lo)), float(np.nanmin(la)), float(np.nanmax(lo)), float(np.nanmax(la))


def read_units(path: Path, max_units: int = 0, bbox_filter=None):
    payload = json.loads(path.read_text(encoding="utf-8"))
    gate = box(*bbox_filter) if bbox_filter else None
    out = []
    for feature in payload.get("features", []):
        props = dict(feature.get("properties") or {})
        geom = shape(feature.get("geometry"))
        if geom.is_empty or (gate is not None and not geom.intersects(gate)):
            continue
        raw_date = props.get("analysis_date") or props.get("event_date") or props.get("event_date_utc")
        if not raw_date:
            continue
        out.append(
            {
                "id": str(props.get("analysis_unit_id") or f"unit_{len(out) + 1}"),
                "date": dparse(str(raw_date)),
                "geom": geom,
                "props": props,
            }
        )
        if max_units and len(out) >= max_units:
            break
    return out


def units_bbox(units):
    arr = np.array([u["geom"].bounds for u in units], dtype="float64")
    return float(arr[:, 0].min()), float(arr[:, 1].min()), float(arr[:, 2].max()), float(arr[:, 3].max())


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({k for r in rows for k in r})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def query_manifest(product: str, start: date, end: date, bbox_value, output_dir: Path, page_size: int):
    records: dict[str, dict[str, Any]] = {}
    failures = []
    for day in drange(start, end):
        day_s = day.isoformat()
        try:
            granules = search_granules(product, day_s, day_s, bbox_value, page_size=page_size)
        except Exception as exc:
            failures.append({"date": day_s, "status": "query_failed", "error_message": str(exc)})
            continue
        for g in granules:
            link = extract_download_link(g.links) or ""
            filename = Path(link.split("?")[0]).name if link else f"{g.producer_granule_id}.h5"
            key = g.producer_granule_id or link or filename
            acquisition_day = file_day(filename) or file_day(g.producer_granule_id) or day_s
            if acquisition_day:
                try:
                    if not (start <= dparse(acquisition_day) <= end):
                        continue
                except Exception:
                    pass
            row = records.setdefault(
                key,
                {
                    "date": acquisition_day,
                    "query_dates": set(),
                    "query_record_count": 0,
                    "producer_granule_id": g.producer_granule_id,
                    "time_start": g.time_start,
                    "updated": g.updated or "",
                    "day_night_flag": g.day_night_flag or "",
                    "tile_id": tile_id(g.producer_granule_id),
                    "download_url": link,
                    "local_path": str(output_dir / "downloads/raw" / product / acquisition_day / filename),
                    "granule_size_mb": (g.raw or {}).get("granule_size", ""),
                    "status": "queried",
                    "error_message": "",
                },
            )
            row["query_dates"].add(day_s)
            row["query_record_count"] += 1
    rows = failures + sorted(records.values(), key=lambda r: (r.get("date", ""), r.get("tile_id", ""), r.get("producer_granule_id", "")))
    for row in rows:
        if isinstance(row.get("query_dates"), set):
            row["query_dates"] = ";".join(sorted(row["query_dates"]))
    return rows


def local_h5_index(dirs: list[Path]):
    idx = {}
    for root in dirs:
        if root.exists():
            for p in root.rglob("*.h5"):
                idx[p.name] = p
    return idx


def materialize(rows, dirs, token_env: str, download_missing: bool):
    token = resolve_token(token_env)
    idx = local_h5_index(dirs)
    counts = {"existing": 0, "downloaded": 0, "failed": 0, "token_present": bool(token), "download_missing": download_missing}
    for r in rows:
        if r.get("status") != "queried" or not r.get("download_url"):
            continue
        expected = Path(r["local_path"])
        found = expected if expected.exists() else idx.get(expected.name)
        if found and found.exists():
            r["local_path"] = str(found)
            r["status"] = "existing"
            counts["existing"] += 1
            continue
        if not download_missing:
            r["status"] = "not_downloaded"
            continue
        ok, err = download_file_with_curl(r["download_url"], expected, token, timeout=900)
        r["status"] = "downloaded" if ok else "download_failed"
        r["error_message"] = "" if ok else err
        counts["downloaded" if ok else "failed"] += 1
    return counts


def contains_xy(geom, xs, ys):
    try:
        from shapely import contains_xy as cxy

        return cxy(geom, xs, ys)
    except Exception:
        from shapely import vectorized

        return vectorized.contains(geom, xs, ys)


def qmask(cloud, dnb_qf, mode: str):
    if mode == "none":
        return None
    mask = None
    if cloud is not None:
        qf = cloud.astype("uint16", copy=False)
        not_fill = qf != np.uint16(65535)
        night = (qf & 1) == 0
        cloud_conf = (qf >> 6) & 3
        no_shadow = ((qf >> 8) & 1) == 0
        no_snow = ((qf >> 10) & 1) == 0
        if mode == "basic":
            mask = not_fill & night
        elif mode == "clear_only":
            mask = not_fill & night & (cloud_conf == 0) & no_shadow & no_snow
        else:
            mask = not_fill & night & (cloud_conf <= 1) & no_shadow & no_snow
    if dnb_qf is not None:
        dnb_ok = dnb_qf != np.uint16(65535)
        mask = dnb_ok if mask is None else mask & dnb_ok
    return mask


def crop_idx(values, lo, hi):
    a, b = min(lo, hi), max(lo, hi)
    return np.where((values >= a) & (values <= b))[0]


def extract_values(h5_path: Path, unit, qa_mode: str):
    with h5py.File(h5_path, "r") as h5:
        rad, lat, lon = ds(h5, PATHS["radiance"]), ds(h5, PATHS["lat"]), ds(h5, PATHS["lon"])
        utc, cloud, dnb = ds(h5, PATHS["utc"]), ds(h5, PATHS["cloud"]), ds(h5, PATHS["dnb_qf"])
        if rad is None or lat is None or lon is None:
            return np.array([]), np.array([])
        minx, miny, maxx, maxy = unit["geom"].bounds
        lats, lons = lat[:], lon[:]
        rows, cols = crop_idx(lats, miny, maxy), crop_idx(lons, minx, maxx)
        if rows.size == 0 or cols.size == 0:
            return np.array([]), np.array([])
        r0, r1, c0, c1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1
        arr = scaled(rad, rad[r0:r1, c0:c1])
        valid = np.isfinite(arr) & (arr >= 0)
        fv = fill(rad)
        if fv is not None:
            valid &= arr != fv
        qa = qmask(
            cloud[r0:r1, c0:c1] if cloud is not None else None,
            dnb[r0:r1, c0:c1] if dnb is not None else None,
            qa_mode,
        )
        if qa is not None:
            valid &= qa
        xs, ys = np.meshgrid(lons[c0:c1], lats[r0:r1])
        valid &= contains_xy(unit["geom"], xs, ys)
        vals = arr[valid].astype("float64", copy=False)
        if utc is None:
            return vals, np.array([])
        utc_arr = utc[r0:r1, c0:c1].astype("float64", copy=False)
        utc_valid = valid & np.isfinite(utc_arr) & (utc_arr >= 0) & (utc_arr <= 24)
        ufv = fill(utc)
        if ufv is not None:
            utc_valid &= utc_arr != ufv
        return vals, utc_arr[utc_valid].astype("float64", copy=False)


def summarize(vals, utc):
    if vals.size == 0:
        return {"status": "no_valid_pixels", "valid_pixel_count": 0}
    out = {
        "status": "ok",
        "mean_ntl": float(np.nanmean(vals)),
        "median_ntl": float(np.nanmedian(vals)),
        "max_ntl": float(np.nanmax(vals)),
        "std_ntl": float(np.nanstd(vals)),
        "valid_pixel_count": int(vals.size),
    }
    if utc.size:
        out.update({"utc_time_min": float(np.nanmin(utc)), "utc_time_mean": float(np.nanmean(utc)), "utc_time_max": float(np.nanmax(utc))})
    return out


def process_stats(units, h5_paths, qa_mode: str):
    buckets, utc_buckets, tiles = defaultdict(list), defaultdict(list), defaultdict(set)
    meta = []
    for p in h5_paths:
        try:
            with h5py.File(p, "r") as h5:
                b = h5_bounds(h5)
                day = h5_day(h5, p)
            if b and day:
                meta.append((p, day, box(*b)))
        except Exception:
            continue
    for p, day, tile_geom in meta:
        for unit in units:
            if not unit["geom"].intersects(tile_geom):
                continue
            vals, utc = extract_values(p, unit, qa_mode)
            if vals.size:
                key = (unit["id"], day)
                buckets[key].append(vals)
                if utc.size:
                    utc_buckets[key].append(utc)
                tiles[key].add(tile_id(p.name))
    by_id = {u["id"]: u for u in units}
    rows = []
    for (uid, obs), arrays in sorted(buckets.items(), key=lambda x: (x[0][1], x[0][0])):
        unit = by_id[uid]
        vals = np.concatenate(arrays)
        utc = np.concatenate(utc_buckets[(uid, obs)]) if utc_buckets.get((uid, obs)) else np.array([])
        props = unit["props"]
        row = {
            "analysis_unit_id": uid,
            "analysis_date": unit["date"].isoformat(),
            "observation_date": obs,
            "days_from_event": (dparse(obs) - unit["date"]).days,
            "analysis_unit_type": props.get("analysis_unit_type", ""),
            "aoi_type": props.get("aoi_type", ""),
            "radius_m": props.get("radius_m", ""),
            "countries": props.get("countries", ""),
            "site_types": props.get("site_types", ""),
            "site_subtypes": props.get("site_subtypes", ""),
            "member_event_count": props.get("member_event_count", ""),
            "tile_ids": ";".join(sorted(tiles[(uid, obs)])),
            **summarize(vals, utc),
        }
        rows.append(row)
    return rows


def period_mean(df):
    df = df.dropna(subset=["mean_ntl"])
    df = df[df["valid_pixel_count"] > 0]
    return float(np.average(df["mean_ntl"], weights=df["valid_pixel_count"])) if not df.empty else math.nan


def impact_metrics(units, daily_rows, threshold: float):
    daily = pd.DataFrame(daily_rows)
    if daily.empty:
        daily = pd.DataFrame(columns=["analysis_unit_id", "days_from_event", "mean_ntl", "valid_pixel_count", "observation_date"])
    out = []
    for unit in units:
        g = daily[daily["analysis_unit_id"] == unit["id"]]
        base = period_mean(g[(g["days_from_event"] >= -7) & (g["days_from_event"] <= -1)])
        event = period_mean(g[(g["days_from_event"] >= 0) & (g["days_from_event"] <= 1)])
        rec = period_mean(g[(g["days_from_event"] >= 2) & (g["days_from_event"] <= 7)])
        delta = event - base if np.isfinite(event) and np.isfinite(base) else math.nan
        pct = delta / base * 100 if np.isfinite(delta) and np.isfinite(base) and abs(base) > 1e-9 else math.nan
        direction = "invalid" if not np.isfinite(pct) else ("decrease" if pct <= -abs(threshold) else ("increase" if pct >= abs(threshold) else "stable"))
        props = unit["props"]
        out.append(
            {
                "analysis_unit_id": unit["id"],
                "analysis_date": unit["date"].isoformat(),
                "analysis_unit_type": props.get("analysis_unit_type", ""),
                "aoi_type": props.get("aoi_type", ""),
                "radius_m": props.get("radius_m", ""),
                "countries": props.get("countries", ""),
                "site_types": props.get("site_types", ""),
                "site_subtypes": props.get("site_subtypes", ""),
                "member_event_count": props.get("member_event_count", ""),
                "baseline_mean": base,
                "event_window_mean": event,
                "recovery_mean": rec,
                "delta_abs": delta,
                "delta_pct": pct,
                "direction": direction,
                "status": "ok" if direction != "invalid" else "insufficient_observations",
            }
        )
    return out


def write_notes(path: Path, args, units, bbox_value):
    path.write_text(
        f"""# ConflictNTL VNP46A1 Method Notes

Primary backend: NASA LAADS / Earthdata official `VNP46A1`.

- Analysis units: `{args.analysis_units}`
- Unit count loaded: `{len(units)}`
- Query bbox: `{bbox_value[0]:.6f},{bbox_value[1]:.6f},{bbox_value[2]:.6f},{bbox_value[3]:.6f}`
- Date range: `{args.start_date}` to `{args.end_date}`
- Windows: baseline_pre = D-7..D-1; event_window = D..D+1; recovery_early = D+2..D+7
- Granule downloads are deduplicated by `producer_granule_id` / LAADS URL. The same
  official HDF5 granule can serve multiple analysis units and can also appear in
  more than one daily CMR query response.

Interpretation: report outputs as source-aligned NTL change signals or candidate
conflict-associated NTL anomalies. Do not state confirmed damage caused by conflict
without independent verification.
""",
        encoding="utf-8",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--analysis-units", default=str(DEFAULT_UNITS))
    p.add_argument("--output-dir", default=str(DEFAULT_OUT))
    p.add_argument("--start-date", default="2026-02-20")
    p.add_argument("--end-date", default="2026-04-14")
    p.add_argument("--product", default="VNP46A1")
    p.add_argument("--token-env", default="EARTHDATA_TOKEN")
    p.add_argument("--page-size", type=int, default=200)
    p.add_argument("--download-missing", action="store_true")
    p.add_argument("--skip-query", action="store_true")
    p.add_argument("--query-only", action="store_true")
    p.add_argument("--local-h5-dir", action="append", default=[])
    p.add_argument("--max-units", type=int, default=0)
    p.add_argument("--bbox-filter", default="")
    p.add_argument("--qa-mode", choices=["none", "basic", "balanced", "clear_only"], default="balanced")
    p.add_argument("--stable-threshold-pct", type=float, default=10.0)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bbox_filter = tuple(float(x) for x in args.bbox_filter.split(",")) if args.bbox_filter else None
    units = read_units(Path(args.analysis_units), args.max_units, bbox_filter)
    if not units:
        raise RuntimeError("No analysis units loaded.")
    bbox_value = units_bbox(units)
    start, end = dparse(args.start_date), dparse(args.end_date)
    write_notes(out_dir / "method_notes.md", args, units, bbox_value)

    local_dirs = [Path(x) for x in args.local_h5_dir] + [out_dir / "downloads/raw" / args.product]
    manifest = []
    materialized = {"existing": 0, "downloaded": 0, "failed": 0, "token_present": bool(resolve_token(args.token_env))}
    if not args.skip_query:
        manifest = query_manifest(args.product, start, end, bbox_value, out_dir, args.page_size)
        materialized = materialize(manifest, local_dirs, args.token_env, args.download_missing)
        write_csv(out_dir / "granule_query_manifest.csv", manifest, GRANULE_FIELDS)

    h5_paths = sorted(set(local_h5_index(local_dirs).values()))
    h5_paths = [x for x in h5_paths if file_day(x.name) and start <= dparse(file_day(x.name)) <= end]
    granule_rows = [r for r in manifest if r.get("producer_granule_id") and r.get("download_url")]
    download_manifest = {
        "product": args.product,
        "backend": "nasa_laads",
        "analysis_units": str(Path(args.analysis_units)),
        "date_range": {"start": args.start_date, "end": args.end_date},
        "bbox": bbox_value,
        "query_count": len(granule_rows),
        "manifest_row_count": len(manifest),
        "raw_query_record_count": sum(int(r.get("query_record_count") or 0) for r in granule_rows),
        "unique_granule_count": len(granule_rows),
        "local_h5_count": len(h5_paths),
        "materialize": materialized,
    }
    (out_dir / "download_manifest.json").write_text(json.dumps(download_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.query_only:
        (out_dir / "run_summary.json").write_text(json.dumps({"status": "query_only", **download_manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "query_only",
                    "query_count": len(manifest),
                    "raw_query_record_count": download_manifest["raw_query_record_count"],
                    "unique_granule_count": download_manifest["unique_granule_count"],
                    "output_dir": str(out_dir),
                },
                ensure_ascii=False,
            )
        )
        return

    daily = process_stats(units, h5_paths, args.qa_mode)
    write_csv(out_dir / "unit_daily_stats.csv", daily, DAILY_FIELDS)
    metrics = impact_metrics(units, daily, args.stable_threshold_pct)
    write_csv(out_dir / "unit_impact_metrics.csv", metrics)
    mdf = pd.DataFrame(metrics)
    if not mdf.empty:
        mdf.groupby("analysis_date", dropna=False).agg(
            unit_count=("analysis_unit_id", "count"),
            valid_unit_count=("status", lambda s: int((s == "ok").sum())),
            mean_delta_pct=("delta_pct", "mean"),
            median_delta_pct=("delta_pct", "median"),
            decrease_count=("direction", lambda s: int((s == "decrease").sum())),
            increase_count=("direction", lambda s: int((s == "increase").sum())),
            invalid_count=("direction", lambda s: int((s == "invalid").sum())),
        ).reset_index().to_csv(out_dir / "daily_summary.csv", index=False, encoding="utf-8")
        mdf.groupby(["countries", "site_types", "aoi_type"], dropna=False).agg(
            unit_count=("analysis_unit_id", "count"),
            mean_delta_pct=("delta_pct", "mean"),
            median_delta_pct=("delta_pct", "median"),
            decrease_count=("direction", lambda s: int((s == "decrease").sum())),
            increase_count=("direction", lambda s: int((s == "increase").sum())),
            invalid_count=("direction", lambda s: int((s == "invalid").sum())),
        ).reset_index().to_csv(out_dir / "group_summary_by_country_site_type.csv", index=False, encoding="utf-8")
        ok = mdf[mdf["status"] == "ok"]
        ok.sort_values("delta_pct").head(50).to_csv(out_dir / "top_decrease_units.csv", index=False, encoding="utf-8")
        ok.sort_values("delta_pct", ascending=False).head(50).to_csv(out_dir / "top_increase_units.csv", index=False, encoding="utf-8")
    summary = {"status": "success", **download_manifest, "unit_count": len(units), "unit_daily_stats_rows": len(daily), "unit_impact_metrics_rows": len(metrics)}
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "success", "daily_rows": len(daily), "output_dir": str(out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
