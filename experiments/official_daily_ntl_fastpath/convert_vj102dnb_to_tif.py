from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import from_bounds


WGS84_EPSG = "EPSG:4326"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert VJ102DNB NetCDF granules (*.nc) to GeoTIFF tiles with optional date filter and bbox clip."
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing VJ102DNB *.nc files.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--date", default="", help="Optional exact date filter: YYYY-MM-DD")
    parser.add_argument("--start-date", default="", help="Optional start date: YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="Optional end date: YYYY-MM-DD")
    parser.add_argument(
        "--bbox",
        default="",
        help="Optional clip bbox in lon/lat: minx,miny,maxx,maxy",
    )
    parser.add_argument("--nodata", type=float, default=-9999.0, help="Output NoData value. Default -9999")
    parser.add_argument(
        "--apply-qf-mask",
        action="store_true",
        default=True,
        help="Mask pixels where DNB_quality_flags != 0 (default enabled).",
    )
    parser.add_argument(
        "--disable-qf-mask",
        action="store_true",
        help="Disable DNB_quality_flags mask.",
    )
    parser.add_argument(
        "--mosaic-name",
        default="vj102dnb_mosaic_4326.tif",
        help="Filename for mosaic output.",
    )
    parser.add_argument(
        "--clip-name",
        default="vj102dnb_clip_4326.tif",
        help="Filename for clipped output when --bbox is set.",
    )
    return parser.parse_args()


def _parse_iso_date(raw: str, name: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD, got: {raw}") from exc


def _doy_to_date_str(year: int, doy: int) -> str:
    dt = datetime(year, 1, 1) + timedelta(days=doy - 1)
    return dt.strftime("%Y-%m-%d")


def _extract_date_from_filename(path: Path) -> str | None:
    m = re.search(r"\.A(\d{4})(\d{3})\.", path.name, flags=re.IGNORECASE)
    if not m:
        return None
    year = int(m.group(1))
    doy = int(m.group(2))
    if doy < 1 or doy > 366:
        return None
    return _doy_to_date_str(year, doy)


def _collect_dates(files: list[Path]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for f in files:
        ds = _extract_date_from_filename(f)
        if ds and ds not in seen:
            seen.add(ds)
            out.append(ds)
    return sorted(out)


def _date_filter_predicate(
    date_exact: str,
    start_date: str,
    end_date: str,
) -> tuple[callable[[Path], bool], dict[str, Any]]:
    d_exact = _parse_iso_date(date_exact, "--date")
    d_start = _parse_iso_date(start_date, "--start-date")
    d_end = _parse_iso_date(end_date, "--end-date")

    if d_exact and (d_start or d_end):
        raise ValueError("Use either --date OR (--start-date/--end-date), not both.")
    if (d_start and not d_end) or (d_end and not d_start):
        raise ValueError("--start-date and --end-date must be provided together.")
    if d_start and d_end and d_end < d_start:
        raise ValueError("--end-date must be >= --start-date.")

    if d_exact:
        target = d_exact.strftime("%Y-%m-%d")

        def pred(p: Path) -> bool:
            return _extract_date_from_filename(p) == target

        return pred, {"mode": "date", "date": target}

    if d_start and d_end:
        left = d_start.strftime("%Y-%m-%d")
        right = d_end.strftime("%Y-%m-%d")

        def pred(p: Path) -> bool:
            ds = _extract_date_from_filename(p)
            return (ds is not None) and (left <= ds <= right)

        return pred, {"mode": "range", "start_date": left, "end_date": right}

    def pred(_: Path) -> bool:
        return True

    return pred, {"mode": "all"}


def _parse_bbox(raw: str) -> tuple[float, float, float, float] | None:
    text = (raw or "").strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be 'minx,miny,maxx,maxy'")
    minx, miny, maxx, maxy = (float(x) for x in parts)
    if maxx <= minx or maxy <= miny:
        raise ValueError("Invalid bbox: require maxx>minx and maxy>miny")
    return minx, miny, maxx, maxy


def _attr_scalar(h: h5py.File, key: str) -> float:
    v = h.attrs[key]
    arr = np.array(v).reshape(-1)
    return float(arr[0])


def _decode_attr(h: h5py.File, key: str) -> str:
    v = h.attrs.get(key)
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="ignore")
    arr = np.array(v).reshape(-1)
    if arr.size == 0:
        return ""
    x = arr[0]
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="ignore")
    return str(x)


def _read_dnb_from_nc(nc_path: Path, nodata: float, apply_qf_mask: bool) -> tuple[np.ndarray, tuple[float, float, float, float], dict[str, Any]]:
    with h5py.File(nc_path, "r") as h:
        obs = h["observation_data/DNB_observations"]
        qf = h["observation_data/DNB_quality_flags"]

        data = np.array(obs, dtype=np.float32)
        qf_arr = np.array(qf)

        fill = None
        if "_FillValue" in obs.attrs:
            fill = float(np.array(obs.attrs["_FillValue"]).reshape(-1)[0])
        valid_min = None
        valid_max = None
        if "valid_min" in obs.attrs:
            valid_min = float(np.array(obs.attrs["valid_min"]).reshape(-1)[0])
        if "valid_max" in obs.attrs:
            valid_max = float(np.array(obs.attrs["valid_max"]).reshape(-1)[0])

        mask_invalid = ~np.isfinite(data)
        if fill is not None:
            mask_invalid |= np.isclose(data.astype(np.float64), fill, equal_nan=False)
        if valid_min is not None:
            mask_invalid |= data < valid_min
        if valid_max is not None:
            mask_invalid |= data > valid_max
        if apply_qf_mask:
            mask_invalid |= qf_arr != 0

        data = np.where(mask_invalid, nodata, data).astype(np.float32)

        west = _attr_scalar(h, "WestBoundingCoordinate")
        east = _attr_scalar(h, "EastBoundingCoordinate")
        south = _attr_scalar(h, "SouthBoundingCoordinate")
        north = _attr_scalar(h, "NorthBoundingCoordinate")
        bounds = (west, south, east, north)

        meta = {
            "time_coverage_start": _decode_attr(h, "time_coverage_start"),
            "time_coverage_end": _decode_attr(h, "time_coverage_end"),
            "day_night_flag": _decode_attr(h, "DayNightFlag"),
            "valid_min": valid_min,
            "valid_max": valid_max,
            "fill_value": fill,
            "qf_nonzero_ratio": float(np.mean(qf_arr != 0)),
        }
    return data, bounds, meta


def _write_tile_tif(data: np.ndarray, bounds: tuple[float, float, float, float], out_path: Path, nodata: float) -> None:
    west, south, east, north = bounds
    height, width = data.shape[-2], data.shape[-1]
    transform = from_bounds(west, south, east, north, width=width, height=height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=WGS84_EPSG,
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)


def _mosaic_tiles(tile_paths: list[Path], mosaic_path: Path, nodata: float) -> None:
    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, transform = merge(srcs, nodata=nodata)
        meta = srcs[0].meta.copy()
        meta.update(
            {
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": transform,
                "nodata": nodata,
                "compress": "deflate",
            }
        )
    finally:
        for s in srcs:
            s.close()
    mosaic_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(mosaic_path, "w", **meta) as dst:
        dst.write(mosaic)


def _clip_bbox(src_path: Path, dst_path: Path, bbox: tuple[float, float, float, float], nodata: float) -> None:
    minx, miny, maxx, maxy = bbox
    geom = {
        "type": "Polygon",
        "coordinates": [[
            [minx, miny],
            [maxx, miny],
            [maxx, maxy],
            [minx, maxy],
            [minx, miny],
        ]],
    }
    with rasterio.open(src_path) as src:
        clipped, transform = mask(src, [geom], crop=True, nodata=nodata)
        meta = src.meta.copy()
        meta.update(
            {
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": transform,
                "nodata": nodata,
                "compress": "deflate",
            }
        )
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **meta) as dst:
            dst.write(clipped)


def main() -> None:
    args = _parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    tiles_dir = output_dir / "tiles_4326"
    mosaic_dir = output_dir / "mosaic"
    apply_qf_mask = bool(args.apply_qf_mask) and (not bool(args.disable_qf_mask))

    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    all_nc_files = sorted(input_dir.glob("*.nc"))
    if not all_nc_files:
        raise FileNotFoundError(f"No *.nc found in: {input_dir}")

    date_pred, date_filter_info = _date_filter_predicate(args.date, args.start_date, args.end_date)
    nc_files = [p for p in all_nc_files if date_pred(p)]
    if not nc_files:
        raise RuntimeError(
            f"No NetCDF matched filter {date_filter_info}. "
            f"Available dates in folder: {_collect_dates(all_nc_files)}"
        )

    created_tiles: list[Path] = []
    per_granule: list[dict[str, Any]] = []
    errors: list[str] = []

    for nc_file in nc_files:
        try:
            data, bounds, meta = _read_dnb_from_nc(
                nc_file, nodata=float(args.nodata), apply_qf_mask=apply_qf_mask
            )
            out_tile = tiles_dir / f"{nc_file.stem}.tif"
            _write_tile_tif(data, bounds, out_tile, nodata=float(args.nodata))
            created_tiles.append(out_tile)
            per_granule.append(
                {
                    "file": nc_file.name,
                    "tile": str(out_tile),
                    "bounds": bounds,
                    **meta,
                }
            )
            print(f"[tile] {nc_file.name} -> {out_tile.name}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{nc_file.name}: {exc}")
            print(f"[skip] {nc_file.name}: {exc}")

    if not created_tiles:
        raise RuntimeError("No GeoTIFF tiles were created.")

    mosaic_path = mosaic_dir / args.mosaic_name
    _mosaic_tiles(created_tiles, mosaic_path, nodata=float(args.nodata))
    print(f"[mosaic] {mosaic_path}")

    clip_path = None
    bbox = _parse_bbox(args.bbox)
    if bbox is not None:
        clip_path = mosaic_dir / args.clip_name
        _clip_bbox(mosaic_path, clip_path, bbox=bbox, nodata=float(args.nodata))
        print(f"[clip] {clip_path}")

    summary = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "h5_count_total": len(all_nc_files),
        "h5_count_selected": len(nc_files),
        "selected_dates": _collect_dates(nc_files),
        "date_filter": date_filter_info,
        "tile_count": len(created_tiles),
        "mosaic_4326": str(mosaic_path),
        "clip_4326": str(clip_path) if clip_path else None,
        "nodata": float(args.nodata),
        "apply_qf_mask": apply_qf_mask,
        "geolocation_mode": "approx_granule_bbox_from_global_attrs",
        "notes": [
            "VJ102DNB granules here do not include per-pixel lat/lon.",
            "Georeferencing is approximate using West/East/South/NorthBoundingCoordinate.",
            "For precise geolocation, pair each VJ102DNB with matching VJ103DNB geolocation granule.",
        ],
        "per_granule": per_granule,
        "errors": errors,
    }
    summary_path = mosaic_dir / "convert_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[summary] {summary_path}")


if __name__ == "__main__":
    main()
