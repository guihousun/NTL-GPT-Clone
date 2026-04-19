"""Summarize VNP46A1 per-pixel UTC_Time.

Usage:
    conda run -n NTL-Claw-Stable python scripts/summarize_vnp46a1_utc_time.py <path.h5>

Optional bbox:
    --bbox min_lon,min_lat,max_lon,max_lat
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np


UTC_TIME_PATH = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/UTC_Time"
LAT_PATH = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/lat"
LON_PATH = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/lon"
IRST = timezone(timedelta(hours=3, minutes=30))


def decode_attr(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.shape == ():
        return decode_attr(value.item())
    return str(value)


def decimal_hour_to_datetime(date_str: str, hour: float, tz: timezone = timezone.utc) -> datetime:
    base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    dt_utc = base + timedelta(hours=float(hour))
    return dt_utc.astimezone(tz)


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [float(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be min_lon,min_lat,max_lon,max_lat")
    return parts[0], parts[1], parts[2], parts[3]


def summarize(values: np.ndarray, date_str: str) -> dict[str, object]:
    finite = values[np.isfinite(values) & (values >= 0) & (values <= 24)]
    if finite.size == 0:
        return {"valid_pixels": 0}

    percentiles = np.percentile(finite, [0, 1, 5, 25, 50, 75, 95, 99, 100])
    keys = ["p0_min", "p1", "p5", "p25", "p50_median", "p75", "p95", "p99", "p100_max"]
    out: dict[str, object] = {
        "valid_pixels": int(finite.size),
        "decimal_hours_utc": {key: float(value) for key, value in zip(keys, percentiles)},
        "mean_decimal_hour_utc": float(np.mean(finite)),
    }
    out["utc_datetimes"] = {
        key: decimal_hour_to_datetime(date_str, float(value), timezone.utc).isoformat().replace("+00:00", "Z")
        for key, value in zip(keys, percentiles)
    }
    out["iran_local_datetimes_irst"] = {
        key: decimal_hour_to_datetime(date_str, float(value), IRST).isoformat()
        for key, value in zip(keys, percentiles)
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("h5_path")
    parser.add_argument("--bbox", default=None, help="Optional min_lon,min_lat,max_lon,max_lat")
    args = parser.parse_args()

    path = Path(args.h5_path)
    bbox = parse_bbox(args.bbox)

    with h5py.File(path, "r") as h5:
        date_str = decode_attr(h5.attrs.get("RangeBeginningDate"))
        utc_time = h5[UTC_TIME_PATH][:]
        lat = h5[LAT_PATH][:]
        lon = h5[LON_PATH][:]
        attrs = {key: str(value) for key, value in h5[UTC_TIME_PATH].attrs.items()}

    report: dict[str, object] = {
        "file": str(path),
        "range_beginning_date": date_str,
        "range_beginning_time": "00:00:00",
        "range_ending_time": "23:59:59",
        "utc_time_dataset": UTC_TIME_PATH,
        "utc_time_attrs": attrs,
        "tile_extent": {
            "min_lon": float(np.nanmin(lon)),
            "max_lon": float(np.nanmax(lon)),
            "min_lat": float(np.nanmin(lat)),
            "max_lat": float(np.nanmax(lat)),
        },
        "whole_tile": summarize(utc_time, date_str),
    }

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        lon_mask = (lon >= min_lon) & (lon <= max_lon)
        lat_mask = (lat >= min_lat) & (lat <= max_lat)
        subset = utc_time[np.ix_(lat_mask, lon_mask)]
        report["bbox"] = {
            "input": bbox,
            "row_count": int(np.sum(lat_mask)),
            "col_count": int(np.sum(lon_mask)),
            "summary": summarize(subset, date_str),
        }

    out = path.with_suffix(path.suffix + ".utc_time_summary.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("summary_json:", out)


if __name__ == "__main__":
    main()
