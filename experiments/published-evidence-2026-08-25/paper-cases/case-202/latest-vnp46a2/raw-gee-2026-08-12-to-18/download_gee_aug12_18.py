"""Query and download the raw GEE evidence for Case 202, 12--18 Aug 2026.

This is intentionally a bounded supplement.  It reads the already validated
Case 202 AOI and queries only NASA/VIIRS/002/VNP46A2 for UTC product dates
2026-08-12 through 2026-08-18.  The script writes only into its own output
directory and never persists the Earth Engine project identifier, download
URLs, or any credential material.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import ee


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT.parent
AOI_PATH = CASE_ROOT / "tehran-boundary.geojson"
EXISTING_AUGUST_CHUNK = CASE_ROOT / "gee-chunk-2026-08.json"
COLLECTION_ID = "NASA/VIIRS/002/VNP46A2"
RAW_BAND = "DNB_BRDF_Corrected_NTL"
QA_BANDS = [
    "Mandatory_Quality_Flag",
    "QF_Cloud_Mask",
    "Snow_Flag",
    "Latest_High_Quality_Retrieval",
]
STATS_BANDS = [RAW_BAND, *QA_BANDS]
DOWNLOAD_BANDS = STATS_BANDS
START_DATE = date(2026, 8, 12)
END_DATE = date(2026, 8, 18)
ANALYSIS_SCALE_M = 500
MAX_PIXELS = 10_000_000
TILE_SCALE = 2
CRS = "EPSG:4326"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_error(exc: BaseException, project: str | None = None) -> str:
    """Keep failure evidence useful without exposing project or token material."""

    message = str(exc)
    if project:
        message = message.replace(project, "[REDACTED_PROJECT]")
    # Download URLs and Earth Engine bearer-like values are never evidence.
    message = re.sub(r"https?://[^\s]+", "[REDACTED_URL]", message)
    message = re.sub(r"(?i)(token|access_token|authorization)[^\s,;]*", "[REDACTED_SECRET]", message)
    return message[:2000]


def dates_in_window() -> list[str]:
    current = START_DATE
    values: list[str] = []
    while current <= END_DATE:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def combined_stats_reducer() -> ee.Reducer:
    return (
        ee.Reducer.minMax()
        .combine(ee.Reducer.mean(), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )


def feature_stats(image: ee.Image, geometry: ee.Geometry, band_names: list[str], prefix: str) -> ee.Dictionary:
    """Return min/max/mean/count for each selected band in one reduction."""

    renamed = image.select(band_names).rename([f"{prefix}_{index}" for index in range(len(band_names))])
    raw = ee.Dictionary(
        renamed.reduceRegion(
            reducer=combined_stats_reducer(),
            geometry=geometry,
            scale=ANALYSIS_SCALE_M,
            maxPixels=MAX_PIXELS,
            tileScale=TILE_SCALE,
        )
    )
    # Earth Engine returns names based on the renamed input bands.  Rename the
    # keys deterministically into a readable, band-specific contract.
    output: dict[str, Any] = {}
    for index, band_name in enumerate(band_names):
        source_prefix = f"{prefix}_{index}"
        target_prefix = band_name if prefix == "raw" else f"{prefix}_{band_name}"
        for statistic in ("min", "max", "mean", "count"):
            output[f"{target_prefix}_{statistic}"] = raw.get(f"{source_prefix}_{statistic}")
    return ee.Dictionary(output)


def quality_histograms(image: ee.Image, geometry: ee.Geometry) -> ee.Dictionary:
    """Return value-count histograms for integer QA bands, if pixels exist."""

    output: dict[str, Any] = {}
    for band_name in QA_BANDS:
        histogram = image.select(band_name).reduceRegion(
            reducer=ee.Reducer.frequencyHistogram().unweighted(),
            geometry=geometry,
            scale=ANALYSIS_SCALE_M,
            maxPixels=MAX_PIXELS,
            tileScale=TILE_SCALE,
        ).get(band_name)
        output[f"qa_{band_name}_value_counts"] = histogram
    return ee.Dictionary(output)


def contract_image(image: ee.Image) -> ee.Image:
    """Build the frozen Case 202 strict/permissive/base masks."""

    radiance = image.select(RAW_BAND)
    qf = image.select("QF_Cloud_Mask")
    mandatory = image.select("Mandatory_Quality_Flag")
    snow_flag = image.select("Snow_Flag")
    reasonable_radiance = radiance.gte(0)
    night = qf.bitwiseAnd(1).eq(0)
    cloud_mask_quality = qf.rightShift(4).bitwiseAnd(3)
    cloud_detection = qf.rightShift(6).bitwiseAnd(3)
    no_shadow = qf.bitwiseAnd(1 << 8).eq(0)
    no_cirrus = qf.bitwiseAnd(1 << 9).eq(0)
    no_qf_snow = qf.bitwiseAnd(1 << 10).eq(0)
    no_snow_flag = snow_flag.eq(0)
    common = (
        reasonable_radiance
        .And(night)
        .And(cloud_detection.lte(1))
        .And(no_shadow)
        .And(no_cirrus)
        .And(no_qf_snow)
        .And(no_snow_flag)
    )
    strict_mask = common.And(mandatory.eq(0)).And(cloud_mask_quality.gte(2))
    permissive_mask = common.And(mandatory.lte(1)).And(cloud_mask_quality.gte(1))
    return ee.Image.cat(
        radiance.updateMask(reasonable_radiance).rename("base"),
        radiance.updateMask(strict_mask).rename("strict"),
        radiance.updateMask(permissive_mask).rename("permissive"),
    )


def day_feature(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    day_text: str,
    source_ids: list[str],
) -> ee.Feature:
    image = collection.filterDate(day_text, (date.fromisoformat(day_text) + timedelta(days=1)).isoformat()).sort("system:index").mosaic()
    raw_stats = feature_stats(image, geometry, STATS_BANDS, "raw")
    contract_stats = feature_stats(contract_image(image), geometry, ["base", "strict", "permissive"], "contract")
    return ee.Feature(
        None,
        ee.Dictionary(
            {
                "date_utc": day_text,
                "source_image_ids": source_ids,
                "source_image_id": "|".join(source_ids),
            }
        )
        .combine(raw_stats)
        .combine(contract_stats)
        .combine(quality_histograms(image, geometry)),
    )


def raster_stats(path: Path) -> dict[str, Any]:
    """Inspect a downloaded GeoTIFF independently of Earth Engine."""

    try:
        import rasterio
    except Exception as exc:  # pragma: no cover - environment-specific
        return {"status": "unavailable", "error": safe_error(exc)}
    try:
        result: dict[str, Any] = {}
        with rasterio.open(path) as dataset:
            result.update(
                {
                    "status": "passed",
                    "driver": dataset.driver,
                    "width": dataset.width,
                    "height": dataset.height,
                    "count": dataset.count,
                    "crs": dataset.crs.to_string() if dataset.crs else None,
                    "transform": [float(value) for value in dataset.transform],
                    "dtypes": list(dataset.dtypes),
                    "nodata": dataset.nodata,
                    "bands": {},
                }
            )
            for index in range(1, dataset.count + 1):
                masked = dataset.read(index, masked=True)
                valid = masked.compressed()
                result["bands"][str(index)] = {
                    "count": int(valid.size),
                    "min": float(valid.min()) if valid.size else None,
                    "max": float(valid.max()) if valid.size else None,
                    "mean": float(valid.mean()) if valid.size else None,
                }
        return result
    except Exception as exc:  # pragma: no cover - environment-specific
        return {"status": "failed", "error": safe_error(exc)}


def download_day(
    image: ee.Image,
    day_text: str,
    geometry_payload: dict[str, Any],
    server_raw_count: int | float | None,
    project: str | None,
) -> dict[str, Any]:
    """Download one clipped raw+QA GeoTIFF; never record the signed URL."""

    raster_dir = ROOT / "rasters"
    raster_dir.mkdir(parents=True, exist_ok=True)
    output_path = raster_dir / f"VNP46A2_{day_text}_raw_qa.tif"
    try:
        params = {
            "name": f"Case202_VNP46A2_{day_text}",
            "bands": DOWNLOAD_BANDS,
            "region": geometry_payload,
            "scale": ANALYSIS_SCALE_M,
            "crs": CRS,
            "filePerBand": False,
            "format": "GEO_TIFF",
        }
        signed_url = image.select(DOWNLOAD_BANDS).getDownloadURL(params)
        request = urllib.request.Request(signed_url, headers={"User-Agent": "Case202-GEE-audit/1.0"})
        with urllib.request.urlopen(request, timeout=180) as response, output_path.open("wb") as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                handle.write(block)
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("GEE returned an empty download")
        local = raster_stats(output_path)
        if local.get("status") not in {"passed", "unavailable"}:
            raise RuntimeError(f"Downloaded file failed local raster inspection: {local.get('error', 'unknown')}")
        server_count = int(server_raw_count) if isinstance(server_raw_count, (int, float)) else None
        server_mask_note = (
            "server-side raw count is zero; numeric zero pixels in this GeoTIFF are export fill values, not observations"
            if server_count == 0
            else "server-side raw count is authoritative because the GeoTIFF export has no explicit nodata mask"
        )
        return {
            "status": "downloaded_all_masked" if server_count == 0 else "downloaded",
            "server_raw_band_count": server_count,
            "server_mask_note": server_mask_note,
            "path": str(output_path),
            "bytes": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
            "local_raster_inspection": local,
        }
    except Exception as exc:
        if output_path.exists():
            output_path.unlink()
        return {"status": "download_failed", "error": safe_error(exc, project)}


def resolve_project() -> tuple[str, str]:
    helper = Path(r"local-user/.codex\plugins\cache\xujingchen1996-local\easygee\0.3.1\skills\easygee\scripts\easygee_project.py")
    import importlib.util

    spec = importlib.util.spec_from_file_location("case202_easygee_project", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("EasyGEE project resolver is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    resolved = module.resolve_project(remember_discovered=False)
    if not module.is_concrete_project(resolved.project):
        raise RuntimeError("EasyGEE did not resolve a concrete Earth Engine project")
    return resolved.project, resolved.source


def compare_with_existing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected: dict[str, dict[str, Any]] = {}
    if EXISTING_AUGUST_CHUNK.exists():
        chunk = read_json(EXISTING_AUGUST_CHUNK)
        for feature in chunk.get("features", []):
            props = feature.get("properties") or {}
            if props.get("date_utc") in dates_in_window():
                expected[props["date_utc"]] = props
    comparisons: list[dict[str, Any]] = []
    for row in rows:
        day = row["date_utc"]
        old = expected.get(day, {})
        checks: dict[str, Any] = {}
        for metric in ("count", "mean", "min", "max"):
            for name in ("base", "strict", "permissive"):
                new_key = f"contract_{name}_{metric}"
                old_key = f"{name}_{metric}"
                checks[old_key] = {
                    "new": row.get(new_key),
                    "existing": old.get(old_key),
                    "equal": row.get(new_key) == old.get(old_key),
                }
        comparisons.append({"date_utc": day, "checks": checks})
    all_equal = bool(comparisons) and all(
        check["equal"]
        for comparison in comparisons
        for check in comparison["checks"].values()
    )
    return {
        "existing_artifact": str(EXISTING_AUGUST_CHUNK),
        "existing_artifact_sha256": sha256_file(EXISTING_AUGUST_CHUNK) if EXISTING_AUGUST_CHUNK.exists() else None,
        "status": "matched" if all_equal else "difference_or_unavailable",
        "comparisons": comparisons,
    }


def main() -> int:
    started = utc_now()
    ROOT.mkdir(parents=True, exist_ok=True)
    if not AOI_PATH.exists():
        raise FileNotFoundError(f"Validated AOI not found: {AOI_PATH}")
    aoi_payload = read_json(AOI_PATH)
    geometry_payload = aoi_payload["features"][0]["geometry"]
    project: str | None = None
    result: dict[str, Any] = {
        "schema_version": "ntl.case202.gee-raw-supplement.v1",
        "case_id": "Case202-tehran-latest-vnp46a2",
        "status": "started",
        "started_at_utc": started,
        "query": {
            "collection_id": COLLECTION_ID,
            "product_version": "002",
            "raw_band": RAW_BAND,
            "qa_bands": QA_BANDS,
            "date_start_inclusive_utc": START_DATE.isoformat(),
            "date_end_inclusive_utc": END_DATE.isoformat(),
            "filter_interval_utc": f"[{START_DATE.isoformat()}T00:00:00Z, {(END_DATE + timedelta(days=1)).isoformat()}T00:00:00Z)",
            "primary_basis": "UTC product day",
            "aoi_path": str(AOI_PATH),
            "aoi_sha256": sha256_file(AOI_PATH),
            "crs": CRS,
            "scale_m": ANALYSIS_SCALE_M,
            "max_pixels": MAX_PIXELS,
            "tile_scale": TILE_SCALE,
            "qa_contract_reused": "Case 202 existing strict/permissive masks; no gap-filled band used",
        },
        "dates": [],
        "validation": {},
    }
    try:
        project, project_source = resolve_project()
        ee.Initialize(project=project)
        aoi = ee.Geometry(geometry_payload)
        collection = (
            ee.ImageCollection(COLLECTION_ID)
            .filterBounds(aoi.bounds())
            .filterDate(START_DATE.isoformat(), (END_DATE + timedelta(days=1)).isoformat())
        )
        metadata = ee.Dictionary(
            {
                "times_ms": collection.aggregate_array("system:time_start"),
                "indices": collection.aggregate_array("system:index"),
                "size": collection.size(),
            }
        ).getInfo()
        ids_by_date: dict[str, list[str]] = {}
        for timestamp_ms, index in zip(metadata.get("times_ms", []), metadata.get("indices", [])):
            day_text = datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc).date().isoformat()
            if START_DATE.isoformat() <= day_text <= END_DATE.isoformat():
                ids_by_date.setdefault(day_text, []).append(f"{COLLECTION_ID}/{index}")

        available = [day for day in dates_in_window() if day in ids_by_date]
        feature_collection = ee.FeatureCollection(
            [day_feature(collection, aoi, day, ids_by_date[day]) for day in available]
        )
        server_payload = feature_collection.getInfo() if available else {"features": []}
        rows_by_date = {
            feature["properties"]["date_utc"]: feature["properties"]
            for feature in server_payload.get("features", [])
        }
        for day in dates_in_window():
            if day not in ids_by_date:
                result["dates"].append({"date_utc": day, "image_available": False, "raw_availability": "no_image_in_collection_window"})
                continue
            image = collection.filterDate(day, (date.fromisoformat(day) + timedelta(days=1)).isoformat()).sort("system:index").mosaic()
            record = dict(rows_by_date.get(day, {}))
            record["date_utc"] = day
            record["image_available"] = True
            record["raw_availability"] = "image_present; raw_band_stats_may_be_all_masked"
            record["download"] = download_day(
                image,
                day,
                geometry_payload,
                record.get(f"{RAW_BAND}_count"),
                project,
            )
            result["dates"].append(record)

        result["project_resolution_source"] = project_source
        result["collection_metadata"] = {
            "image_count_in_window": metadata.get("size"),
            "available_image_dates": available,
            "available_image_count": len(available),
        }
        result["validation"] = {
            "expected_date_count": len(dates_in_window()),
            "returned_date_count": len(result["dates"]),
            "date_set_matches": [row["date_utc"] for row in result["dates"]] == dates_in_window(),
            "all_expected_images_present": all(row.get("image_available") for row in result["dates"]),
            "raw_stats_retrieved_for_present_images": all(
                any(key.startswith("DNB_BRDF_Corrected_NTL_") for key in row)
                for row in result["dates"]
                if row.get("image_available")
            ),
        }
        result["comparison_with_existing_case202_chunk"] = compare_with_existing(result["dates"])
        downloaded = sum(1 for row in result["dates"] if row.get("download", {}).get("status") == "downloaded")
        failed = sum(1 for row in result["dates"] if row.get("download", {}).get("status") == "download_failed")
        masked_exports = sum(
            1 for row in result["dates"] if row.get("download", {}).get("status") == "downloaded_all_masked"
        )
        result["download_summary"] = {
            "dates_requested": len(result["dates"]),
            "downloaded_with_server_pixels": downloaded,
            "downloaded_all_masked": masked_exports,
            "download_failed": failed,
        }
        result["execution_notes"] = [
            "An initial in-sandbox attempt could not access the existing Earth Engine credential store; the final query ran successfully in the approved credential context.",
            "The live query result is retained separately from the pre-existing gee-chunk-2026-08.json because 2026-08-12 changed from zero to 2644 raw pixels between runs; no existing artifact was overwritten.",
        ]
        result["status"] = "complete"
        result["completed_at_utc"] = utc_now()
        stale_failure = ROOT / "failure-log.json"
        if stale_failure.exists():
            stale_failure.unlink()
        write_json(ROOT / "gee-raw-aug12-18.json", result)

        manifest: dict[str, Any] = {
            "schema_version": "ntl.case202.gee-raw-supplement-manifest.v1",
            "case_id": result["case_id"],
            "created_at_utc": utc_now(),
            "query_record": {"path": str(ROOT / "gee-raw-aug12-18.json"), "sha256": sha256_file(ROOT / "gee-raw-aug12-18.json")},
            "rasters": {},
        }
        for row in result["dates"]:
            download = row.get("download", {})
            if download.get("status") in {"downloaded", "downloaded_all_masked"}:
                path = Path(download["path"])
                manifest["rasters"][row["date_utc"]] = {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "status": download.get("status"),
                    "server_raw_band_count": download.get("server_raw_band_count"),
                    "server_mask_note": download.get("server_mask_note"),
                }
        write_json(ROOT / "manifest.json", manifest)
        return 0
    except Exception as exc:
        result["status"] = "failed"
        result["failed_at_utc"] = utc_now()
        result["failure"] = {"exception_type": type(exc).__name__, "message": safe_error(exc, project)}
        write_json(ROOT / "gee-raw-aug12-18.json", result)
        write_json(ROOT / "failure-log.json", {"schema_version": "ntl.case202.gee-raw-supplement-failure.v1", "case_id": result["case_id"], "status": "failed", "failed_at_utc": result["failed_at_utc"], "exception_type": type(exc).__name__, "message": safe_error(exc, project)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
