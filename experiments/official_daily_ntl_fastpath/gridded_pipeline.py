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

from .cmr_client import GranuleRecord, download_file_with_curl, extract_download_link, validate_download_payload


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


def _read_hdf_raw_dataset(h5_path: Path, variable_path: str) -> np.ndarray:
    with h5py.File(h5_path, "r") as handle:
        return np.array(handle[variable_path])


def _valid_data_mask(data: np.ndarray, nodata: float) -> np.ndarray:
    valid = np.isfinite(data)
    if np.isfinite(nodata):
        valid &= data != nodata
    return valid


def _coerce_qa_array(
    qa_layers: dict[str, np.ndarray],
    key: str,
    shape: tuple[int, ...],
) -> np.ndarray | None:
    arr = qa_layers.get(key)
    if arr is None:
        return None
    if arr.shape != shape:
        return None
    return arr


def _apply_vj146a1_balanced_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)

    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        is_night = ((cloud >> 0) & 0b1) == 0
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        no_shadow = ((cloud >> 8) & 0b1) == 0
        no_cirrus = ((cloud >> 9) & 0b1) == 0
        no_snow = ((cloud >> 10) & 0b1) == 0
        mask &= is_night
        mask &= cloud_mask_quality >= 1
        mask &= cloud_confidence <= 1
        mask &= no_shadow
        mask &= no_cirrus
        mask &= no_snow

    qf_dnb = _coerce_qa_array(qa_layers, "QF_DNB", shape)
    if qf_dnb is not None:
        dnb = qf_dnb.astype(np.uint16, copy=False)
        severe_flags = 2 | 4 | 16 | 256 | 512 | 1024 | 2048
        mask &= (dnb & severe_flags) == 0

    return mask


def _apply_vj146a1_strict_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)

    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        is_night = ((cloud >> 0) & 0b1) == 0
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        no_shadow = ((cloud >> 8) & 0b1) == 0
        no_cirrus = ((cloud >> 9) & 0b1) == 0
        no_snow = ((cloud >> 10) & 0b1) == 0
        mask &= is_night
        mask &= cloud_mask_quality >= 2
        mask &= cloud_confidence == 0
        mask &= no_shadow
        mask &= no_cirrus
        mask &= no_snow

    qf_dnb = _coerce_qa_array(qa_layers, "QF_DNB", shape)
    if qf_dnb is not None:
        dnb = qf_dnb.astype(np.uint16, copy=False)
        mask &= dnb == 0

    return mask


def _apply_vj146a2_balanced_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)

    mandatory_quality_flag = _coerce_qa_array(qa_layers, "Mandatory_Quality_Flag", shape)
    if mandatory_quality_flag is not None:
        mqf = mandatory_quality_flag.astype(np.uint16, copy=False)
        mask &= mqf == 0

    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        is_night = ((cloud >> 0) & 0b1) == 0
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        no_shadow = ((cloud >> 8) & 0b1) == 0
        no_cirrus = ((cloud >> 9) & 0b1) == 0
        no_snow = ((cloud >> 10) & 0b1) == 0
        mask &= is_night
        mask &= cloud_mask_quality >= 1
        mask &= cloud_confidence <= 1
        mask &= no_shadow
        mask &= no_cirrus
        mask &= no_snow

    snow_flag = _coerce_qa_array(qa_layers, "Snow_Flag", shape)
    if snow_flag is not None:
        mask &= snow_flag.astype(np.uint16, copy=False) == 0

    return mask


def _apply_vj146a2_strict_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = _apply_vj146a2_balanced_mask(qa_layers, shape)
    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        mask &= cloud_mask_quality >= 2
        mask &= cloud_confidence == 0
    return mask


def _apply_vj146a1_clear_only_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)

    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        is_night = ((cloud >> 0) & 0b1) == 0
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        no_shadow = ((cloud >> 8) & 0b1) == 0
        no_cirrus = ((cloud >> 9) & 0b1) == 0
        no_snow = ((cloud >> 10) & 0b1) == 0
        mask &= is_night
        mask &= cloud_mask_quality == 3
        mask &= cloud_confidence == 0
        mask &= no_shadow
        mask &= no_cirrus
        mask &= no_snow

    qf_dnb = _coerce_qa_array(qa_layers, "QF_DNB", shape)
    if qf_dnb is not None:
        dnb = qf_dnb.astype(np.uint16, copy=False)
        mask &= dnb == 0

    return mask


def _apply_vj146a2_clear_only_mask(qa_layers: dict[str, np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
    mask = np.ones(shape, dtype=bool)

    mandatory_quality_flag = _coerce_qa_array(qa_layers, "Mandatory_Quality_Flag", shape)
    if mandatory_quality_flag is not None:
        mqf = mandatory_quality_flag.astype(np.uint16, copy=False)
        mask &= mqf == 0

    qf_cloud_mask = _coerce_qa_array(qa_layers, "QF_Cloud_Mask", shape)
    if qf_cloud_mask is not None:
        cloud = qf_cloud_mask.astype(np.uint16, copy=False)
        is_night = ((cloud >> 0) & 0b1) == 0
        cloud_mask_quality = (cloud >> 4) & 0b11
        cloud_confidence = (cloud >> 6) & 0b11
        no_shadow = ((cloud >> 8) & 0b1) == 0
        no_cirrus = ((cloud >> 9) & 0b1) == 0
        no_snow = ((cloud >> 10) & 0b1) == 0
        mask &= is_night
        mask &= cloud_mask_quality == 3
        mask &= cloud_confidence == 0
        mask &= no_shadow
        mask &= no_cirrus
        mask &= no_snow

    snow_flag = _coerce_qa_array(qa_layers, "Snow_Flag", shape)
    if snow_flag is not None:
        mask &= snow_flag.astype(np.uint16, copy=False) == 0

    return mask


def apply_quality_mask(
    *,
    source: str,
    data: np.ndarray,
    nodata: float,
    qa_mode: str,
    qa_layers: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    qa_mode_normalized = (qa_mode or "balanced").strip().lower()
    if qa_mode_normalized not in {"balanced", "strict", "clear_only", "none"}:
        raise ValueError(f"Unsupported qa_mode: {qa_mode}")

    source_key = (source or "").strip().upper()
    base_valid_mask = _valid_data_mask(data, nodata)

    if qa_mode_normalized == "none":
        masked = np.where(base_valid_mask, data, nodata).astype(np.float32, copy=False)
        summary = {
            "source": source_key,
            "qa_mode": qa_mode_normalized,
            "valid_pixel_count": int(base_valid_mask.sum()),
            "masked_pixel_count": int(base_valid_mask.size - base_valid_mask.sum()),
            "valid_ratio": float(base_valid_mask.mean()) if base_valid_mask.size else 0.0,
            "applied_qa_layers": [],
        }
        return masked, base_valid_mask, summary

    if source_key == "VJ146A1":
        if qa_mode_normalized == "balanced":
            qa_mask = _apply_vj146a1_balanced_mask(qa_layers, data.shape)
        elif qa_mode_normalized == "strict":
            qa_mask = _apply_vj146a1_strict_mask(qa_layers, data.shape)
        else:
            qa_mask = _apply_vj146a1_clear_only_mask(qa_layers, data.shape)
    elif source_key == "VJ146A2":
        if qa_mode_normalized == "balanced":
            qa_mask = _apply_vj146a2_balanced_mask(qa_layers, data.shape)
        elif qa_mode_normalized == "strict":
            qa_mask = _apply_vj146a2_strict_mask(qa_layers, data.shape)
        else:
            qa_mask = _apply_vj146a2_clear_only_mask(qa_layers, data.shape)
    else:
        qa_mask = np.ones(data.shape, dtype=bool)

    valid_mask = base_valid_mask & qa_mask
    masked = np.where(valid_mask, data, nodata).astype(np.float32, copy=False)
    applied_qa_layers = sorted([key for key, arr in qa_layers.items() if arr is not None and arr.shape == data.shape])
    summary = {
        "source": source_key,
        "qa_mode": qa_mode_normalized,
        "valid_pixel_count": int(valid_mask.sum()),
        "masked_pixel_count": int(valid_mask.size - valid_mask.sum()),
        "valid_ratio": float(valid_mask.mean()) if valid_mask.size else 0.0,
        "applied_qa_layers": applied_qa_layers,
    }
    return masked, valid_mask, summary


def _read_qa_layers(
    h5_path: Path,
    dataset_paths: list[str],
    qa_variable_candidates: dict[str, tuple[str, ...]] | None,
) -> tuple[dict[str, np.ndarray], list[str]]:
    if not qa_variable_candidates:
        return {}, []

    out: dict[str, np.ndarray] = {}
    missing: list[str] = []
    for qa_key, candidates in qa_variable_candidates.items():
        variable_path = select_variable_path(dataset_paths, candidates)
        if not variable_path:
            missing.append(qa_key)
            continue
        try:
            out[qa_key] = _read_hdf_raw_dataset(h5_path, variable_path)
        except Exception:  # noqa: BLE001
            missing.append(qa_key)
    return out, missing


def ensure_required_qa_layers_present(
    *,
    source: str,
    qa_mode: str,
    qa_layers: dict[str, np.ndarray],
    qa_variable_candidates: dict[str, tuple[str, ...]] | None,
) -> None:
    qa_mode_normalized = (qa_mode or "balanced").strip().lower()
    if qa_mode_normalized == "none":
        return
    if not qa_variable_candidates:
        raise ValueError(f"{source} qa_mode={qa_mode_normalized} requires QA layers but none are configured")

    missing = sorted([key for key in qa_variable_candidates if key not in qa_layers])
    if missing:
        raise ValueError(
            f"{source} qa_mode={qa_mode_normalized} missing required QA layers: {', '.join(missing)}"
        )


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
    qa_variable_candidates: dict[str, tuple[str, ...]] | None,
    roi_gdf,
    workspace: Path,
    earthdata_token: str | None,
    qa_mode: str = "balanced",
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
    qa_summaries: list[dict[str, Any]] = []
    roi_bbox = tuple(float(v) for v in roi_gdf.total_bounds)
    for idx, entry in enumerate(entries, start=1):
        link = extract_download_link(entry.links)
        if not link:
            notes.append(f"[{idx}] missing_download_link")
            failure_status = failure_status or "download_link_missing"
            continue
        filename = Path(link.split("?")[0]).name or f"{source}_{day}_{idx}.h5"
        granule_path = raw_dir / filename
        if granule_path.exists():
            ok, err = validate_download_payload(granule_path)
            if not ok:
                granule_path.unlink(missing_ok=True)
        else:
            ok, err = False, "missing_local_granule"
        if not ok:
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
        qa_layers, missing_qa_layers = _read_qa_layers(
            granule_path,
            dataset_paths=dataset_paths,
            qa_variable_candidates=qa_variable_candidates,
        )
        try:
            ensure_required_qa_layers_present(
                source=source,
                qa_mode=qa_mode,
                qa_layers=qa_layers,
                qa_variable_candidates=qa_variable_candidates,
            )
        except ValueError as exc:
            notes.append(f"[{idx}] qa_required_missing: {exc}")
            failure_status = failure_status or "qa_required_missing"
            continue
        data, _valid_mask, qa_summary = apply_quality_mask(
            source=source,
            data=data,
            nodata=float(nodata),
            qa_mode=qa_mode,
            qa_layers=qa_layers,
        )
        if missing_qa_layers:
            qa_summary["missing_qa_layers"] = missing_qa_layers
            notes.append(f"[{idx}] qa_missing:{','.join(missing_qa_layers)}")
        qa_summaries.append(qa_summary)
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
        "qa_mode": qa_mode,
        "qa_summaries": qa_summaries,
    }
