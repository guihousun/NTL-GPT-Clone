from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject


SINUSOIDAL_CRS = CRS.from_proj4("+proj=sinu +R=6371007.181 +units=m +no_defs")
WGS84_CRS = CRS.from_epsg(4326)
SIN_TILE_SIZE_M = 1111950.5196666667
SIN_X_MIN = -20015109.354
SIN_Y_MAX = 10007554.677


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert local VNP46A1 HDF5 files to GeoTIFF tiles, then optional mosaic/reproject/clip."
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing VNP46A1 *.h5 files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for tiles and mosaic products.")
    parser.add_argument("--date", default="", help="Optional exact date filter: YYYY-MM-DD")
    parser.add_argument("--start-date", default="", help="Optional start date: YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="Optional end date: YYYY-MM-DD")
    parser.add_argument(
        "--variable",
        default="DNB_At_Sensor_Radiance",
        help="Variable basename to extract from HDF5. Default: DNB_At_Sensor_Radiance",
    )
    parser.add_argument(
        "--bbox",
        default="",
        help="Optional clip bbox in lon/lat: minx,miny,maxx,maxy",
    )
    parser.add_argument(
        "--nodata",
        type=float,
        default=-9999.0,
        help="NoData value for outputs. Default: -9999",
    )
    parser.add_argument(
        "--mosaic-name",
        default="vnp46a1_mosaic_4326.tif",
        help="Filename for reprojected mosaic in EPSG:4326.",
    )
    parser.add_argument(
        "--clip-name",
        default="vnp46a1_clip_4326.tif",
        help="Filename for bbox-clipped output (if --bbox provided).",
    )
    return parser.parse_args()


def _collect_dataset_paths(h5_path: Path) -> list[str]:
    paths: list[str] = []
    with h5py.File(h5_path, "r") as h:
        def visit(name: str, obj: Any) -> None:
            if isinstance(obj, h5py.Dataset):
                paths.append(name)

        h.visititems(visit)
    return paths


def _select_variable_path(dataset_paths: list[str], variable_name: str) -> str:
    normalized = (variable_name or "").strip()
    if not normalized:
        normalized = "DNB_At_Sensor_Radiance"

    candidates = [
        f"HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/{normalized}",
        f"HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/{normalized}",
        normalized,
    ]
    # Backward-compatible aliases across VNP46A1 variants.
    if normalized.lower() == "dnb_at_sensor_radiance":
        candidates.extend(
            [
                "HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields/DNB_At_Sensor_Radiance_500m",
                "DNB_At_Sensor_Radiance_500m",
            ]
        )

    dataset_set = set(dataset_paths)
    for c in candidates:
        if c in dataset_set:
            return c
    by_base = {Path(p).name.lower(): p for p in dataset_paths}
    key = variable_name.lower()
    if key in by_base:
        return by_base[key]
    raise ValueError(f"Variable '{variable_name}' not found in HDF5 datasets.")


def _array_to_text(raw: Any) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        return raw
    arr = np.array(raw)
    if arr.dtype.kind in {"S", "a"}:
        return b"".join(arr.reshape(-1).tolist()).decode("utf-8", errors="ignore")
    if arr.dtype.kind == "U":
        return "".join(arr.reshape(-1).tolist())
    return str(raw)


def _extract_points_from_struct_metadata(text: str) -> tuple[float, float, float, float] | None:
    ul_match = re.search(
        r"UpperLeftPointMtrs\s*=\s*\(\s*([\-+0-9.eE]+)\s*,\s*([\-+0-9.eE]+)\s*\)",
        text,
    )
    lr_match = re.search(
        r"LowerRightMtrs\s*=\s*\(\s*([\-+0-9.eE]+)\s*,\s*([\-+0-9.eE]+)\s*\)",
        text,
    )
    if not ul_match or not lr_match:
        return None
    ulx = float(ul_match.group(1))
    uly = float(ul_match.group(2))
    lrx = float(lr_match.group(1))
    lry = float(lr_match.group(2))
    return ulx, uly, lrx, lry


def _extract_projection_from_struct_metadata(text: str) -> str:
    m = re.search(r"Projection\s*=\s*([A-Za-z0-9_]+)", text)
    if not m:
        return ""
    return m.group(1).strip()


def _extract_tile_hv_from_filename(path: Path) -> tuple[int, int] | None:
    m = re.search(r"\.h(\d{2})v(\d{2})\.", path.name, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _bounds_from_hv(path: Path) -> tuple[float, float, float, float]:
    hv = _extract_tile_hv_from_filename(path)
    if hv is None:
        raise ValueError(f"Cannot infer tile h/v from filename: {path.name}")
    h, v = hv
    minx = SIN_X_MIN + h * SIN_TILE_SIZE_M
    maxx = minx + SIN_TILE_SIZE_M
    maxy = SIN_Y_MAX - v * SIN_TILE_SIZE_M
    miny = maxy - SIN_TILE_SIZE_M
    return minx, maxy, maxx, miny


def _read_fill_scale_offset(ds: h5py.Dataset) -> tuple[float | None, float | None, float | None]:
    fill = None
    scale = None
    offset = None
    for key in ("_FillValue", "fill_value", "FillValue"):
        if key in ds.attrs:
            fill = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    for key in ("scale_factor", "Scale"):
        if key in ds.attrs:
            scale = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    for key in ("add_offset", "Offset"):
        if key in ds.attrs:
            offset = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    return fill, scale, offset


def _read_h5_variable(
    h5_path: Path, variable_path: str, nodata: float
) -> tuple[np.ndarray, tuple[float, float, float, float], CRS]:
    with h5py.File(h5_path, "r") as h:
        ds = h[variable_path]
        data = np.array(ds)
        fill, scale, offset = _read_fill_scale_offset(ds)

        if fill is not None:
            if np.issubdtype(data.dtype, np.floating):
                invalid = np.isclose(data.astype(np.float64), fill, equal_nan=False)
            else:
                invalid = data == fill
            data = np.where(invalid, np.nan, data)

        data = data.astype(np.float32)
        if scale is not None:
            data = data * scale
        if offset is not None:
            data = data + offset
        data = np.where(np.isfinite(data), data, np.nan)
        data = np.where(np.isnan(data), nodata, data).astype(np.float32)

        bounds = None
        tile_crs = SINUSOIDAL_CRS
        if "HDFEOS INFORMATION/StructMetadata.0" in h:
            text = _array_to_text(h["HDFEOS INFORMATION/StructMetadata.0"][()])
            parsed = _extract_points_from_struct_metadata(text)
            if parsed is not None:
                ulx, uly, lrx, lry = parsed
                projection = _extract_projection_from_struct_metadata(text).upper()
                # Some VIIRS VNP46A1 granules use geographic grids but store
                # "PointMtrs" with 1e6 scaled lon/lat.
                if projection == "HE5_GCTP_GEO" and max(abs(ulx), abs(uly), abs(lrx), abs(lry)) > 1000:
                    ulx, uly, lrx, lry = ulx / 1_000_000.0, uly / 1_000_000.0, lrx / 1_000_000.0, lry / 1_000_000.0
                    tile_crs = WGS84_CRS
                bounds = (ulx, uly, lrx, lry)
        if bounds is None:
            bounds = _bounds_from_hv(h5_path)
            tile_crs = SINUSOIDAL_CRS
    return data, bounds, tile_crs


def _write_tile_tif(
    data: np.ndarray,
    bounds: tuple[float, float, float, float],
    tile_crs: CRS,
    out_path: Path,
    nodata: float,
) -> None:
    ulx, uly, lrx, lry = bounds
    height, width = data.shape[-2], data.shape[-1]
    transform = from_bounds(ulx, lry, lrx, uly, width=width, height=height)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=tile_crs,
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)


def _mosaic_tiles(tile_paths: list[Path], mosaic_sinu_path: Path, nodata: float) -> None:
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

    mosaic_sinu_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(mosaic_sinu_path, "w", **meta) as dst:
        dst.write(mosaic)


def _reproject_to_4326(src_path: Path, dst_path: Path, nodata: float) -> None:
    with rasterio.open(src_path) as src:
        if src.crs == WGS84_CRS:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_path, dst_path)
            return
        transform, width, height = calculate_default_transform(
            src.crs, WGS84_CRS, src.width, src.height, *src.bounds
        )
        meta = src.meta.copy()
        meta.update(
            {
                "crs": WGS84_CRS,
                "transform": transform,
                "width": width,
                "height": height,
                "nodata": nodata,
                "compress": "deflate",
            }
        )
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **meta) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=nodata,
                dst_transform=transform,
                dst_crs=WGS84_CRS,
                dst_nodata=nodata,
                resampling=Resampling.bilinear,
            )


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


def _doy_to_date_str(year: int, doy: int) -> str:
    dt = datetime(year, 1, 1) + timedelta(days=doy - 1)
    return dt.strftime("%Y-%m-%d")


def _extract_date_from_filename(path: Path) -> str | None:
    # Example: VNP46A1.A2026059.h23v06.002....
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


def _parse_iso_date(raw: str, name: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD, got: {raw}") from exc


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
            ds = _extract_date_from_filename(p)
            return ds == target

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


def _clip_bbox(src_4326_path: Path, dst_clip_path: Path, bbox: tuple[float, float, float, float], nodata: float) -> None:
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
    with rasterio.open(src_4326_path) as src:
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
        dst_clip_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_clip_path, "w", **meta) as dst:
            dst.write(clipped)


def main() -> None:
    args = _parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    tiles_dir = output_dir / "tiles_sinu"
    mosaic_dir = output_dir / "mosaic"

    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    all_h5_files = sorted(input_dir.glob("*.h5"))
    if not all_h5_files:
        raise FileNotFoundError(f"No *.h5 found in: {input_dir}")
    date_pred, date_filter_info = _date_filter_predicate(args.date, args.start_date, args.end_date)
    h5_files = [p for p in all_h5_files if date_pred(p)]
    if not h5_files:
        all_dates = _collect_dates(all_h5_files)
        raise RuntimeError(
            f"No HDF5 matched date filter {date_filter_info}. "
            f"Available dates in folder: {all_dates}"
        )

    created_tiles: list[Path] = []
    variable_used = None
    errors: list[str] = []
    for h5_file in h5_files:
        try:
            dataset_paths = _collect_dataset_paths(h5_file)
            variable_path = _select_variable_path(dataset_paths, args.variable)
            variable_used = variable_used or variable_path
            data, bounds, tile_crs = _read_h5_variable(h5_file, variable_path, nodata=float(args.nodata))
            out_tile = tiles_dir / f"{h5_file.stem}.tif"
            _write_tile_tif(data, bounds, tile_crs, out_tile, nodata=float(args.nodata))
            created_tiles.append(out_tile)
            print(f"[tile] {h5_file.name} -> {out_tile.name}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{h5_file.name}: {exc}")
            print(f"[skip] {h5_file.name}: {exc}")

    if not created_tiles:
        raise RuntimeError("No tiles created.")

    mosaic_sinu = mosaic_dir / "vnp46a1_mosaic_sinu.tif"
    _mosaic_tiles(created_tiles, mosaic_sinu, nodata=float(args.nodata))
    print(f"[mosaic] sinusoidal: {mosaic_sinu}")

    mosaic_4326 = mosaic_dir / args.mosaic_name
    _reproject_to_4326(mosaic_sinu, mosaic_4326, nodata=float(args.nodata))
    print(f"[mosaic] epsg:4326: {mosaic_4326}")

    clip_path = None
    bbox = _parse_bbox(args.bbox)
    if bbox is not None:
        clip_path = mosaic_dir / args.clip_name
        _clip_bbox(mosaic_4326, clip_path, bbox=bbox, nodata=float(args.nodata))
        print(f"[clip] bbox: {clip_path}")

    summary = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "h5_count_selected": len(h5_files),
        "h5_count_total": len(all_h5_files),
        "selected_dates": _collect_dates(h5_files),
        "date_filter": date_filter_info,
        "tile_count": len(created_tiles),
        "variable_used": variable_used,
        "mosaic_sinu": str(mosaic_sinu),
        "mosaic_4326": str(mosaic_4326),
        "clip_4326": str(clip_path) if clip_path else None,
        "errors": errors,
    }
    summary_path = mosaic_dir / "convert_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[summary] {summary_path}")


if __name__ == "__main__":
    main()
