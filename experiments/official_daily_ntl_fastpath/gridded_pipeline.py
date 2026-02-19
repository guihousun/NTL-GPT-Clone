from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import from_bounds

from .cmr_client import GranuleRecord, download_file_with_curl, extract_download_link


def list_hdf5_dataset_paths(h5_path: Path) -> list[str]:
    paths: list[str] = []
    with h5py.File(h5_path, "r") as handle:
        def visitor(name: str, obj: Any) -> None:
            if isinstance(obj, h5py.Dataset):
                paths.append(name)

        handle.visititems(visitor)
    return paths


def select_variable_path(dataset_paths: list[str], variable_candidates: tuple[str, ...]) -> str | None:
    if not dataset_paths:
        return None
    dataset_set = set(dataset_paths)

    for candidate in variable_candidates:
        if candidate in dataset_set:
            return candidate

    lowered = {path.lower(): path for path in dataset_paths}
    basename_map = {Path(path).name.lower(): path for path in dataset_paths}

    for candidate in variable_candidates:
        key = candidate.lower()
        if key in lowered:
            return lowered[key]
        base_key = Path(candidate).name.lower()
        if base_key in basename_map:
            return basename_map[base_key]

    def score(path: str) -> int:
        tokens = set(_tokenize(Path(path).name))
        best = 0
        for candidate in variable_candidates:
            ct = set(_tokenize(Path(candidate).name))
            if not ct:
                continue
            overlap = len(tokens & ct)
            best = max(best, overlap)
        return best

    ranked = sorted(dataset_paths, key=lambda p: (score(p), p), reverse=True)
    return ranked[0] if score(ranked[0]) > 0 else None


def _tokenize(text: str) -> list[str]:
    normalized = []
    token = []
    for ch in text:
        if ch.isalnum():
            token.append(ch.lower())
        else:
            if token:
                normalized.append("".join(token))
                token = []
    if token:
        normalized.append("".join(token))
    return normalized


def _read_dataset_attrs(ds: h5py.Dataset) -> tuple[float | None, float | None, float | None]:
    fill_value = None
    scale_factor = None
    add_offset = None
    for key in ("_FillValue", "fill_value", "FillValue"):
        if key in ds.attrs:
            fill_value = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    for key in ("scale_factor", "Scale"):
        if key in ds.attrs:
            scale_factor = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    for key in ("add_offset", "Offset"):
        if key in ds.attrs:
            add_offset = float(np.array(ds.attrs[key]).reshape(-1)[0])
            break
    return fill_value, scale_factor, add_offset


def _read_hdf_variable(h5_path: Path, variable_path: str) -> tuple[np.ndarray, float | None]:
    with h5py.File(h5_path, "r") as handle:
        ds = handle[variable_path]
        data = np.array(ds, dtype=np.float32)
        fill_value, scale_factor, add_offset = _read_dataset_attrs(ds)
    if fill_value is not None:
        data = np.where(data == fill_value, np.nan, data)
    if scale_factor is not None:
        data = data * scale_factor
    if add_offset is not None:
        data = data + add_offset
    data = np.where(np.isfinite(data), data, np.nan)
    nodata = -9999.0
    data = np.where(np.isnan(data), nodata, data).astype(np.float32)
    return data, nodata


def _parse_polygon_to_bbox(polygons: list[str], fallback: tuple[float, float, float, float] | None = None) -> tuple[float, float, float, float]:
    values: list[float] = []
    for poly in polygons:
        try:
            values.extend(float(x) for x in str(poly).split())
        except ValueError:
            continue
    if len(values) < 4:
        if fallback is None:
            raise ValueError("No valid polygon coordinates for granule bbox inference.")
        return fallback

    even = values[0::2]
    odd = values[1::2]

    # CMR polygon is typically "lat lon lat lon ...", but keep a fallback for "lon lat".
    latlon_valid = all(-90 <= x <= 90 for x in even) and all(-180 <= y <= 180 for y in odd)
    lonlat_valid = all(-180 <= x <= 180 for x in even) and all(-90 <= y <= 90 for y in odd)

    if latlon_valid and not lonlat_valid:
        lats, lons = even, odd
    elif lonlat_valid and not latlon_valid:
        lons, lats = even, odd
    else:
        # ambiguous -> default to known CMR style lat/lon
        lats, lons = even, odd

    minx, maxx = min(lons), max(lons)
    miny, maxy = min(lats), max(lats)
    if not (math.isfinite(minx) and math.isfinite(miny) and math.isfinite(maxx) and math.isfinite(maxy)):
        if fallback is None:
            raise ValueError("Invalid bbox values inferred from polygon.")
        return fallback
    return float(minx), float(miny), float(maxx), float(maxy)


def _write_tile_tif(data: np.ndarray, bbox: tuple[float, float, float, float], out_path: Path, nodata: float) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = data.shape[-2], data.shape[-1]
    transform = from_bounds(*bbox, width=width, height=height)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)


def _mosaic_and_clip(tile_paths: list[Path], roi_gdf, output_path: Path, nodata: float) -> None:
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
        for src in srcs:
            src.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(".mosaic_tmp.tif")
    with rasterio.open(temp_path, "w", **meta) as dst:
        dst.write(mosaic)

    with rasterio.open(temp_path) as src:
        shapes = [geom for geom in roi_gdf.geometry if geom is not None]
        clipped, out_transform = mask(src, shapes=shapes, crop=True, nodata=nodata)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "height": clipped.shape[1],
                "width": clipped.shape[2],
                "transform": out_transform,
                "nodata": nodata,
                "compress": "deflate",
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **out_meta) as dst:
        dst.write(clipped)
    temp_path.unlink(missing_ok=True)


def process_gridded_day(
    source: str,
    day: str,
    entries: list[GranuleRecord],
    variable_candidates: tuple[str, ...],
    roi_gdf,
    workspace: Path,
    earthdata_token: str | None,
) -> dict[str, Any]:
    raw_dir = workspace / "raw" / source / day
    tile_dir = workspace / "tmp_tiles" / source / day
    output_dir = workspace / "outputs" / source / day
    output_path = output_dir / f"{source}_{day}_clipped.tif"

    if not earthdata_token:
        return {
            "status": "auth_missing",
            "output_path": None,
            "notes": "EARTHDATA token missing; skipped file download and clipping.",
        }

    tile_paths: list[Path] = []
    variable_used: str | None = None
    notes: list[str] = []
    failure_status: str | None = None
    roi_bbox = tuple(float(v) for v in roi_gdf.total_bounds)
    for idx, entry in enumerate(entries, start=1):
        link = extract_download_link(entry.links)
        if not link:
            notes.append(f"[{idx}] missing_download_link")
            failure_status = failure_status or "download_link_missing"
            continue
        filename = Path(link.split("?")[0]).name or f"{source}_{day}_{idx}.h5"
        granule_path = raw_dir / filename
        ok, err = download_file_with_curl(link, granule_path, earthdata_token=earthdata_token)
        if not ok:
            notes.append(f"[{idx}] download_failed: {err}")
            failure_status = failure_status or "download_failed"
            continue
        try:
            dataset_paths = list_hdf5_dataset_paths(granule_path)
        except OSError as exc:
            notes.append(f"[{idx}] invalid_granule_format: {exc}")
            failure_status = failure_status or "invalid_granule_format"
            continue
        variable_path = select_variable_path(dataset_paths, variable_candidates)
        if not variable_path:
            notes.append(f"[{idx}] variable_not_found: {granule_path.name}")
            failure_status = failure_status or "variable_not_found"
            continue
        variable_used = variable_used or variable_path
        try:
            data, nodata = _read_hdf_variable(granule_path, variable_path)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"[{idx}] variable_read_failed: {exc}")
            failure_status = failure_status or "variable_read_failed"
            continue
        try:
            bbox = _parse_polygon_to_bbox(entry.polygons, fallback=roi_bbox)
        except ValueError as exc:
            notes.append(f"[{idx}] bbox_inference_failed: {exc}")
            failure_status = failure_status or "bbox_inference_failed"
            continue
        tile_path = tile_dir / f"{granule_path.stem}.tif"
        try:
            _write_tile_tif(data, bbox=bbox, out_path=tile_path, nodata=nodata)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"[{idx}] tile_write_failed: {exc}")
            failure_status = failure_status or "tile_write_failed"
            continue
        tile_paths.append(tile_path)

    if not tile_paths:
        return {
            "status": failure_status or "no_tiles",
            "output_path": None,
            "notes": " | ".join(notes) if notes else "No tile available for mosaicking.",
        }

    try:
        _mosaic_and_clip(tile_paths=tile_paths, roi_gdf=roi_gdf, output_path=output_path, nodata=-9999.0)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"mosaic_or_clip_failed: {exc}")
        return {
            "status": "mosaic_or_clip_failed",
            "output_path": None,
            "notes": " | ".join(notes),
        }
    return {
        "status": "ok",
        "output_path": str(output_path),
        "notes": " | ".join(notes),
        "variable_used": variable_used,
    }
