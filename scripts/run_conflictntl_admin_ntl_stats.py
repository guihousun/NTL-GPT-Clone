"""Admin-level ConflictNTL VNP46A1 statistics for Iran/Israel.

This script intentionally skips 2 km buffers. It counts all promoted
candidate strike points by administrative boundary, selects the top attacked
ADM1 and ADM2 units, and computes daily VNP46A1 statistics directly from
local HDF5 files with AOI-day quality filtering.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, shape


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


GRID = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
PATHS = {
    "radiance": [f"{GRID}/DNB_At_Sensor_Radiance", "DNB_At_Sensor_Radiance"],
    "utc": [f"{GRID}/UTC_Time", "UTC_Time"],
    "lat": [f"{GRID}/lat", "lat"],
    "lon": [f"{GRID}/lon", "lon"],
    "cloud": [f"{GRID}/QF_Cloud_Mask", "QF_Cloud_Mask"],
    "dnb_qf": [f"{GRID}/QF_DNB", "QF_DNB"],
}
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def dparse(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def drange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


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
    found: dict[str, str] = {}
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


def file_day(name: str) -> str:
    m = re.search(r"\.A(\d{4})(\d{3})\.", name)
    if not m:
        return ""
    return (date(int(m.group(1)), 1, 1) + timedelta(days=int(m.group(2)) - 1)).isoformat()


def tile_id(name: str) -> str:
    m = re.search(r"\.h(\d{2})v(\d{2})\.", name)
    return f"h{m.group(1)}v{m.group(2)}" if m else ""


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


def read_events(path: Path):
    rows = list(csv.DictReader(path.open("r", newline="", encoding="utf-8-sig")))
    out = []
    for row in rows:
        if row.get("country") not in {"Iran", "Israel"}:
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
        row["_point"] = Point(lon, lat)
        out.append(row)
    return out


def read_boundaries(boundary_dir: Path, level: str):
    files = {
        "ADM1": [
            boundary_dir / "irn_geoboundaries_adm1.geojson",
            boundary_dir / "isr_geoboundaries_adm1.geojson",
        ],
        "ADM2": [
            boundary_dir / "irn_geoboundaries_adm2.geojson",
            boundary_dir / "isr_geoboundaries_adm2.geojson",
        ],
    }[level]
    records = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            geom = shape(feature.get("geometry"))
            country = {"IRN": "Iran", "ISR": "Israel"}.get(str(props.get("shapeGroup") or ""), props.get("shapeGroup") or "")
            records.append(
                {
                    "admin_id": str(props.get("shapeID") or props.get("shapeISO") or props.get("shapeName")),
                    "admin_name": str(props.get("shapeName") or ""),
                    "admin_iso": str(props.get("shapeISO") or ""),
                    "country": country,
                    "admin_level": level,
                    "geom": geom,
                }
            )
    return records


def assign_events(events, admins):
    counts: Counter[str] = Counter()
    unmatched = []
    by_id = {a["admin_id"]: a for a in admins}
    for event in events:
        pt = event["_point"]
        hit = None
        for admin in admins:
            if admin["country"] != event.get("country"):
                continue
            if admin["geom"].contains(pt) or admin["geom"].touches(pt):
                hit = admin
                break
        if hit is None:
            unmatched.append(event)
            continue
        counts[hit["admin_id"]] += 1
    rows = []
    for admin_id, count in counts.most_common():
        admin = by_id[admin_id]
        rows.append(
            {
                "admin_id": admin_id,
                "admin_name": admin["admin_name"],
                "admin_iso": admin["admin_iso"],
                "admin_level": admin["admin_level"],
                "country": admin["country"],
                "candidate_event_count": count,
            }
        )
    return rows, unmatched


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({k for r in rows for k in r})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def valid_h5_paths(root: Path, start: date, end: date):
    paths = []
    for path in root.rglob("*.h5"):
        day = file_day(path.name)
        if not day:
            continue
        d = dparse(day)
        if start <= d <= end:
            try:
                if path.read_bytes()[:8] == HDF5_SIGNATURE:
                    paths.append(path)
            except OSError:
                pass
    return sorted(paths, key=lambda p: (file_day(p.name), tile_id(p.name), p.name))


def h5_meta(paths: list[Path]):
    out = []
    for path in paths:
        try:
            with h5py.File(path, "r") as h5:
                bounds = h5_bounds(h5)
                day = h5_day(h5, path)
            if bounds and day:
                out.append({"path": path, "date": day, "tile_id": tile_id(path.name), "geom": box(*bounds)})
        except Exception:
            continue
    return out


def extract_admin_stats(h5_path: Path, geom, qa_mode: str, valid_threshold: float):
    with h5py.File(h5_path, "r") as h5:
        rad, lat, lon = ds(h5, PATHS["radiance"]), ds(h5, PATHS["lat"]), ds(h5, PATHS["lon"])
        utc, cloud, dnb = ds(h5, PATHS["utc"]), ds(h5, PATHS["cloud"]), ds(h5, PATHS["dnb_qf"])
        if rad is None or lat is None or lon is None:
            return {"quality_status": "missing_required_sds", "total_aoi_pixel_count": 0, "valid_pixel_count": 0}
        minx, miny, maxx, maxy = geom.bounds
        lats, lons = lat[:], lon[:]
        rows, cols = crop_idx(lats, miny, maxy), crop_idx(lons, minx, maxx)
        if rows.size == 0 or cols.size == 0:
            return {"quality_status": "outside_granule", "total_aoi_pixel_count": 0, "valid_pixel_count": 0}
        r0, r1, c0, c1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()) , int(cols.max()) + 1
        xs, ys = np.meshgrid(lons[c0:c1], lats[r0:r1])
        inside = contains_xy(geom, xs, ys)
        total = int(np.count_nonzero(inside))
        if total == 0:
            return {"quality_status": "outside_granule", "total_aoi_pixel_count": 0, "valid_pixel_count": 0}

        arr = scaled(rad, rad[r0:r1, c0:c1])
        valid = inside & np.isfinite(arr) & (arr >= 0)
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
        vals = arr[valid].astype("float64", copy=False)
        valid_count = int(vals.size)
        ratio = valid_count / total if total else math.nan
        status = "ok" if ratio >= valid_threshold and valid_count > 0 else ("no_valid_pixels" if valid_count == 0 else "quality_rejected")
        out = {
            "quality_status": status,
            "total_aoi_pixel_count": total,
            "valid_pixel_count": valid_count,
            "invalid_pixel_count": total - valid_count,
            "valid_pixel_ratio": ratio,
        }
        if valid_count:
            out.update(
                {
                    "mean_ntl": float(np.nanmean(vals)),
                    "median_ntl": float(np.nanmedian(vals)),
                    "max_ntl": float(np.nanmax(vals)),
                    "std_ntl": float(np.nanstd(vals)),
                }
            )
        if utc is not None and valid_count:
            utc_arr = utc[r0:r1, c0:c1].astype("float64", copy=False)
            utc_valid = valid & np.isfinite(utc_arr) & (utc_arr >= 0) & (utc_arr <= 24)
            ufv = fill(utc)
            if ufv is not None:
                utc_valid &= utc_arr != ufv
            utc_vals = utc_arr[utc_valid].astype("float64", copy=False)
            if utc_vals.size:
                out.update(
                    {
                        "utc_time_min": float(np.nanmin(utc_vals)),
                        "utc_time_mean": float(np.nanmean(utc_vals)),
                        "utc_time_max": float(np.nanmax(utc_vals)),
                    }
                )
        return out


def daily_stats(top_units, metas, qa_mode: str, valid_threshold: float):
    rows = []
    for unit in top_units:
        for meta in metas:
            if not unit["geom"].intersects(meta["geom"]):
                continue
            stats = extract_admin_stats(meta["path"], unit["geom"], qa_mode, valid_threshold)
            rows.append(
                {
                    "admin_id": unit["admin_id"],
                    "admin_name": unit["admin_name"],
                    "admin_iso": unit["admin_iso"],
                    "admin_level": unit["admin_level"],
                    "country": unit["country"],
                    "candidate_event_count": unit["candidate_event_count"],
                    "observation_date": meta["date"],
                    "tile_id": meta["tile_id"],
                    "h5_path": str(meta["path"]),
                    **stats,
                }
            )
    return rows


def aggregate_daily(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    ok = df[df["quality_status"] == "ok"].copy()
    grouped = []
    keys = ["admin_id", "admin_name", "admin_iso", "admin_level", "country", "candidate_event_count", "observation_date"]
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
        grouped.append(row)
    return grouped


def impact_summary(daily_rows, baseline_start: date, baseline_end: date, event_start: date, event_end: date):
    df = pd.DataFrame(daily_rows)
    if df.empty:
        return []
    df["observation_date_d"] = pd.to_datetime(df["observation_date"]).dt.date
    out = []
    for (admin_id, admin_name, level, country, event_count), g in df.groupby(
        ["admin_id", "admin_name", "admin_level", "country", "candidate_event_count"], dropna=False
    ):
        b = g[(g["observation_date_d"] >= baseline_start) & (g["observation_date_d"] <= baseline_end)]
        e = g[(g["observation_date_d"] >= event_start) & (g["observation_date_d"] <= event_end)]
        def wmean(x):
            if x.empty:
                return math.nan
            return float(np.average(x["mean_ntl"], weights=x["valid_pixel_count"]))
        base, event = wmean(b), wmean(e)
        delta = event - base if np.isfinite(base) and np.isfinite(event) else math.nan
        pct = delta / base * 100 if np.isfinite(delta) and abs(base) > 1e-9 else math.nan
        out.append(
            {
                "admin_id": admin_id,
                "admin_name": admin_name,
                "admin_level": level,
                "country": country,
                "candidate_event_count": int(event_count),
                "baseline_valid_days": int(b["observation_date"].nunique()),
                "event_period_valid_days": int(e["observation_date"].nunique()),
                "baseline_mean": base,
                "event_period_mean": event,
                "delta_abs": delta,
                "delta_pct": pct,
                "direction_5pct": "invalid" if not np.isfinite(pct) else ("decrease" if pct <= -5 else ("increase" if pct >= 5 else "stable")),
                "direction_10pct": "invalid" if not np.isfinite(pct) else ("decrease" if pct <= -10 else ("increase" if pct >= 10 else "stable")),
            }
        )
    return sorted(out, key=lambda r: (-r["candidate_event_count"], r["country"], r["admin_name"]))


def attach_counts(admins, count_rows, top_n: int):
    by_id = {a["admin_id"]: a for a in admins}
    out = []
    for row in count_rows[:top_n]:
        admin = dict(by_id[row["admin_id"]])
        admin["candidate_event_count"] = int(row["candidate_event_count"])
        out.append(admin)
    return out


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default=str(ROOT / "docs/ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"))
    p.add_argument("--boundary-dir", default=str(ROOT / "docs/geoboundaries_irn_isr_all_levels"))
    p.add_argument("--vnp-dir", default=r"E:\VNP46A1")
    p.add_argument("--output-dir", default=str(ROOT / "docs/ConflictNTL_admin_ntl_stats_iran_israel"))
    p.add_argument("--start-date", default="2026-02-20")
    p.add_argument("--end-date", default="2026-04-07")
    p.add_argument("--baseline-start", default="2026-02-20")
    p.add_argument("--baseline-end", default="2026-02-27")
    p.add_argument("--event-start", default="2026-02-28")
    p.add_argument("--event-end", default="2026-04-07")
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--qa-mode", choices=["none", "basic", "balanced", "clear_only"], default="balanced")
    p.add_argument("--valid-pixel-ratio", type=float, default=0.80)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = dparse(args.start_date), dparse(args.end_date)
    baseline_start, baseline_end = dparse(args.baseline_start), dparse(args.baseline_end)
    event_start, event_end = dparse(args.event_start), dparse(args.event_end)

    events = read_events(Path(args.events))
    paths = valid_h5_paths(Path(args.vnp_dir), start, end)
    metas = h5_meta(paths)
    summary: dict[str, Any] = {
        "candidate_events": len(events),
        "h5_files": len(paths),
        "h5_files_with_meta": len(metas),
        "qa_mode": args.qa_mode,
        "valid_pixel_ratio_threshold": args.valid_pixel_ratio,
    }

    for level in ["ADM1", "ADM2"]:
        admins = read_boundaries(Path(args.boundary_dir), level)
        counts, unmatched = assign_events(events, admins)
        write_csv(out_dir / f"{level.lower()}_attack_counts_iran_israel.csv", counts)
        write_csv(
            out_dir / f"{level.lower()}_unmatched_events.csv",
            [{k: v for k, v in e.items() if k != "_point"} for e in unmatched],
        )
        top_units = attach_counts(admins, counts, args.top_n)
        write_csv(
            out_dir / f"top{args.top_n}_{level.lower()}_units.csv",
            [{k: v for k, v in u.items() if k != "geom"} for u in top_units],
        )
        raw_daily = daily_stats(top_units, metas, args.qa_mode, args.valid_pixel_ratio)
        write_csv(out_dir / f"{level.lower()}_top{args.top_n}_daily_tile_stats.csv", raw_daily)
        daily = aggregate_daily(raw_daily)
        write_csv(out_dir / f"{level.lower()}_top{args.top_n}_daily_ntl.csv", daily)
        impacts = impact_summary(daily, baseline_start, baseline_end, event_start, event_end)
        write_csv(out_dir / f"{level.lower()}_top{args.top_n}_impact_summary.csv", impacts)
        summary[level] = {
            "admin_count": len(admins),
            "matched_admin_count": len(counts),
            "unmatched_events": len(unmatched),
            "top_units": len(top_units),
            "daily_tile_rows": len(raw_daily),
            "daily_rows": len(daily),
            "impact_rows": len(impacts),
        }

    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "success", "output_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
