"""Summarize official VNP46A1 UTC_Time for the Q18 event point and buffers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import h5py
import numpy as np
from pyproj import Geod


EVENT_LON = 95.936
EVENT_LAT = 22.011
EVENT_UTC = datetime(2025, 3, 28, 6, 20, 52, tzinfo=timezone.utc)
UTC_PRODUCT_DAY = datetime(2025, 3, 28, tzinfo=timezone.utc)
LOCAL_ZONE = ZoneInfo("Asia/Yangon")
RADII_KM = (25, 50)


def scalar(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return scalar(value.reshape(-1)[0])
        return value.tolist()
    if isinstance(value, np.generic):
        return scalar(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_dataset(handle: h5py.File, suffix: str) -> tuple[str, h5py.Dataset]:
    matches: list[str] = []

    def visitor(name: str, value: Any) -> None:
        if isinstance(value, h5py.Dataset) and name.replace("-", "_").endswith(suffix):
            matches.append(name)

    handle.visititems(visitor)
    if not matches:
        raise KeyError(f"missing {suffix}")
    return matches[0], handle[matches[0]]


def decoded_values(dataset: h5py.Dataset, raw: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    attrs = {key: scalar(value) for key, value in dataset.attrs.items()}
    fill = attrs.get("_FillValue", attrs.get("FillValue"))
    scale = float(attrs.get("scale_factor", attrs.get("ScaleFactor", 1.0)))
    offset = float(attrs.get("add_offset", attrs.get("Offset", 0.0)))
    values = raw.astype("float64") * scale + offset
    valid = np.isfinite(values)
    if fill is not None:
        valid &= raw != fill
    raw_range = attrs.get("valid_range")
    if isinstance(raw_range, list) and len(raw_range) >= 2:
        valid &= raw >= raw_range[0]
        valid &= raw <= raw_range[1]
    raw_min = attrs.get("valid_min")
    raw_max = attrs.get("valid_max")
    if raw_min is not None:
        valid &= raw >= raw_min
    if raw_max is not None:
        valid &= raw <= raw_max
    valid &= values >= 0.0
    valid &= values <= 24.0
    return values, valid, attrs


def buffer_bounds(west: float, east: float, south: float, north: float, height: int, width: int, radius_km: float) -> tuple[int, int, int, int]:
    # A conservative geographic prefilter; exact membership is calculated geodesically.
    lat_margin = radius_km / 110.0 + 0.03
    lon_margin = radius_km / (110.0 * max(np.cos(np.deg2rad(EVENT_LAT)), 0.1)) + 0.03
    xres = (east - west) / width
    yres = (north - south) / height
    col0 = max(0, int(np.floor((EVENT_LON - lon_margin - west) / xres)))
    col1 = min(width, int(np.ceil((EVENT_LON + lon_margin - west) / xres)))
    row0 = max(0, int(np.floor((north - (EVENT_LAT + lat_margin)) / yres)))
    row1 = min(height, int(np.ceil((north - (EVENT_LAT - lat_margin)) / yres)))
    return row0, row1, col0, col1


def local_timestamp(decimal_hour: float) -> datetime:
    return (UTC_PRODUCT_DAY + timedelta(hours=float(decimal_hour))).astimezone(LOCAL_ZONE)


def json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()

    h5_path = args.h5.resolve(strict=True)
    results_dir = args.results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    with h5py.File(h5_path, "r") as handle:
        dataset_path, dataset = find_dataset(handle, "UTC_Time")
        raw = dataset[()]
        height, width = raw.shape[-2:]
        root_attrs = {key: scalar(value) for key, value in handle.attrs.items()}
        west = float(root_attrs["WestBoundingCoord"])
        east = float(root_attrs["EastBoundingCoord"])
        north = float(root_attrs["NorthBoundingCoord"])
        south = float(root_attrs["SouthBoundingCoord"])
        values, valid, attrs = decoded_values(dataset, raw)

    xres = (east - west) / width
    yres = (north - south) / height
    event_col = int(np.floor((EVENT_LON - west) / xres))
    event_row = int(np.floor((north - EVENT_LAT) / yres))
    if not (0 <= event_row < height and 0 <= event_col < width):
        raise ValueError("event point is outside the VNP46A1 tile bounds")
    center_lon = west + (event_col + 0.5) * xres
    center_lat = north - (event_row + 0.5) * yres
    event_valid = bool(valid[event_row, event_col])
    event_value = float(values[event_row, event_col]) if event_valid else None
    event_local = local_timestamp(event_value).isoformat() if event_value is not None else None

    geod = Geod(ellps="WGS84")
    summary_rows: list[dict[str, Any]] = []
    for radius in RADII_KM:
        row0, row1, col0, col1 = buffer_bounds(west, east, south, north, height, width, radius)
        yy = north - (np.arange(row0, row1) + 0.5) * yres
        xx = west + (np.arange(col0, col1) + 0.5) * xres
        lon_grid, lat_grid = np.meshgrid(xx, yy)
        _, _, distance_m = geod.inv(
            np.full(lon_grid.shape, EVENT_LON),
            np.full(lat_grid.shape, EVENT_LAT),
            lon_grid,
            lat_grid,
        )
        inside = distance_m <= radius * 1000.0
        subset_values = values[row0:row1, col0:col1]
        subset_valid = valid[row0:row1, col0:col1] & inside
        chosen = subset_values[subset_valid]
        if chosen.size == 0:
            stats = {"n": 0, "min_utc_hour": None, "median_utc_hour": None, "mean_utc_hour": None, "max_utc_hour": None, "local_date_counts": {}}
        else:
            local_dates = [local_timestamp(value).date().isoformat() for value in chosen]
            counts: dict[str, int] = {}
            for day in local_dates:
                counts[day] = counts.get(day, 0) + 1
            stats = {
                "n": int(chosen.size),
                "min_utc_hour": float(np.min(chosen)),
                "median_utc_hour": float(np.median(chosen)),
                "mean_utc_hour": float(np.mean(chosen)),
                "max_utc_hour": float(np.max(chosen)),
                "local_date_counts": counts,
                "min_local_time": local_timestamp(float(np.min(chosen))).isoformat(),
                "median_local_time": local_timestamp(float(np.median(chosen))).isoformat(),
                "mean_local_time": local_timestamp(float(np.mean(chosen))).isoformat(),
                "max_local_time": local_timestamp(float(np.max(chosen))).isoformat(),
            }
        summary_rows.append({"support": f"{radius} km", "radius_km": radius, **stats})

    event_observation_utc = (
        (UTC_PRODUCT_DAY + timedelta(hours=event_value)).isoformat().replace("+00:00", "Z")
        if event_value is not None
        else None
    )
    post_event = bool(event_value is not None and UTC_PRODUCT_DAY + timedelta(hours=event_value) > EVENT_UTC)
    local_next_day = bool(event_local and datetime.fromisoformat(event_local).date().isoformat() == "2025-03-29")
    result = {
        "schema_version": "ntl.q18.vnp46a1-utc-time-analysis.v1",
        "source": {"filename": h5_path.name, "sha256": sha256(h5_path), "bytes": h5_path.stat().st_size},
        "product": {"short_name": "VNP46A1", "collection": "002", "utc_product_date": "2025-03-28", "tile": "h27v06"},
        "event": {
            "lon": EVENT_LON,
            "lat": EVENT_LAT,
            "event_time_utc": EVENT_UTC.isoformat().replace("+00:00", "Z"),
            "event_time_local": EVENT_UTC.astimezone(LOCAL_ZONE).isoformat(),
            "timezone": "Asia/Yangon",
        },
        "utc_time_metadata": {
            "dataset_path": dataset_path,
            "dataset_shape": [int(height), int(width)],
            "dataset_attributes": attrs,
            "tile_bounds_wgs84": {"west": west, "south": south, "east": east, "north": north},
            "decode_rule": "raw * scale_factor + add_offset; invalid fill, declared valid-range failures, non-finite values, and decoded values outside [0,24] are excluded without imputation.",
        },
        "event_pixel": {
            "row": event_row,
            "column": event_col,
            "pixel_center_wgs84": {"lon": center_lon, "lat": center_lat},
            "valid": event_valid,
            "utc_time_decimal_hour": event_value,
            "observation_time_utc": event_observation_utc,
            "observation_time_local": event_local,
        },
        "buffer_summaries": summary_rows,
        "interpretation": {
            "event_pixel_is_post_event": post_event,
            "event_pixel_local_date_is_2025_03_29": local_next_day,
            "conclusion": (
                "The UTC_Time at the containing event pixel falls after the mainshock and maps to 29 March 2025 in Asia/Yangon; therefore the A2025087 UTC-indexed product supports interpretation as the first post-event local night."
                if post_event and local_next_day
                else "The containing event pixel does not provide a valid post-event 29 March local-time observation; do not label this UTC product date as the first post-event local night."
            ),
            "limits": [
                "UTC_Time is a per-pixel view-time field; a tile product date is not mechanically converted to a local calendar day.",
                "This timing-only VNP46A1 check does not replace the VNP46A2 radiance product or make causal, damage, outage, or recovery claims.",
            ],
        },
    }
    json_write(results_dir / "utc-time-analysis.json", result)
    with (results_dir / "utc-time-summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "support", "radius_km", "n", "min_utc_hour", "median_utc_hour", "mean_utc_hour", "max_utc_hour", "min_local_time", "median_local_time", "mean_local_time", "max_local_time", "local_date_counts"
        ])
        writer.writeheader()
        for row in summary_rows:
            output = dict(row)
            output["local_date_counts"] = json.dumps(output.pop("local_date_counts"), sort_keys=True)
            writer.writerow(output)


if __name__ == "__main__":
    main()
