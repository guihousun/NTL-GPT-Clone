#!/usr/bin/env python3
"""Build a blind, analysis-ready VNP46A2 series for the Q18 case.

This script reads only the formal event anchor and the official raw HDF5
granules.  It does not read benchmark outputs, gold answers, or prior analysis
tables.  It performs standard radiance decoding, transparent pixel QA, and
unweighted pixel-centre summaries inside geodesic 25 km and 50 km buffers.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import Geod


CASE_DIR = Path(__file__).resolve().parent
EVENT_PATH = CASE_DIR / "formal-event-context.json"
HDF_DIR = Path(
    r"vault/ntl-gpt/experiments\benchmark-v1"
    r"\temporal-freeze\2026-08-11\q96-q99\q96\source_snapshots\official_hdf5"
)

CSV_PATH = CASE_DIR / "formal-q18-analysis-ready.csv"
PACKAGE_PATH = CASE_DIR / "formal-observation-package.json"
VALIDATION_PATH = CASE_DIR / "formal-q18-validation.json"

GRID = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
PATHS = {
    "radiance": f"{GRID}/DNB_BRDF-Corrected_NTL",
    "mandatory_quality": f"{GRID}/Mandatory_Quality_Flag",
    "cloud_mask": f"{GRID}/QF_Cloud_Mask",
    "snow_flag": f"{GRID}/Snow_Flag",
}

FILENAME_RE = re.compile(
    r"^VNP46A2\.A(?P<year>\d{4})(?P<doy>\d{3})\.h(?P<h>\d{2})v(?P<v>\d{2})\."
    r"(?P<collection>\d{3})\.(?P<production>\d{13})\.h5$"
)

AOI_RADII_KM = (25, 50)
EVENT_LON = 95.936
EVENT_LAT = 22.011
EVENT_TIME_UTC = datetime(2025, 3, 28, 6, 20, 52, tzinfo=timezone.utc)

GEOD = Geod(ellps="WGS84")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace").strip()
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def attrs_dict(obj: h5py.Dataset | h5py.Group) -> dict[str, Any]:
    return {str(k): jsonable(v) for k, v in obj.attrs.items()}


def scalar_attr(attrs: h5py.AttributeManager, key: str) -> float:
    value = np.asarray(attrs[key]).reshape(-1)[0]
    return float(value)


def product_date_from_name(path: Path) -> tuple[date, dict[str, str]]:
    match = FILENAME_RE.match(path.name)
    if not match:
        raise ValueError(f"Unexpected VNP46A2 filename: {path.name}")
    parts = match.groupdict()
    product_date = date(int(parts["year"]), 1, 1) + timedelta(days=int(parts["doy"]) - 1)
    return product_date, parts


def temporal_label(product_date_utc: date) -> tuple[date, str]:
    # Suomi-NPP's nominal night-time overpass is after local midnight.  The
    # daily file is indexed by UTC product day, so for Myanmar the represented
    # local night is conservatively labelled as the following local date.  The
    # HDF does not expose exact pixel acquisition time, so this is explicitly
    # an interpretation rather than an exact timestamp.
    local_night = product_date_utc + timedelta(days=1)
    if product_date_utc < EVENT_TIME_UTC.date():
        relation = "pre_event_local_night"
    elif product_date_utc == EVENT_TIME_UTC.date():
        relation = "first_post_event_local_night_interpreted"
    else:
        relation = "late_followup_observation"
    return local_night, relation


def build_grid_geometry(first_hdf: Path) -> dict[str, Any]:
    with h5py.File(first_hdf, "r") as hdf:
        radiance = hdf[PATHS["radiance"]]
        rows, cols = radiance.shape
        root = attrs_dict(hdf)
        west = float(root["WestBoundingCoord"])
        east = float(root["EastBoundingCoord"])
        north = float(root["NorthBoundingCoord"])
        south = float(root["SouthBoundingCoord"])

    pixel_width = (east - west) / cols
    pixel_height = (north - south) / rows
    lon_centres = west + (np.arange(cols, dtype=np.float64) + 0.5) * pixel_width
    lat_centres = north - (np.arange(rows, dtype=np.float64) + 0.5) * pixel_height

    max_radius_m = max(AOI_RADII_KM) * 1000.0
    # Conservative geographic bounding window; the final membership test is
    # WGS84 geodesic distance, not this approximation.
    lat_pad = max_radius_m / 110_000.0 + pixel_height
    lon_pad = max_radius_m / (111_000.0 * math.cos(math.radians(EVENT_LAT))) + pixel_width
    row_idx = np.flatnonzero(
        (lat_centres >= EVENT_LAT - lat_pad) & (lat_centres <= EVENT_LAT + lat_pad)
    )
    col_idx = np.flatnonzero(
        (lon_centres >= EVENT_LON - lon_pad) & (lon_centres <= EVENT_LON + lon_pad)
    )
    if not len(row_idx) or not len(col_idx):
        raise RuntimeError("Event AOI does not intersect the source tile")

    row0, row1 = int(row_idx.min()), int(row_idx.max()) + 1
    col0, col1 = int(col_idx.min()), int(col_idx.max()) + 1
    sub_lats = lat_centres[row0:row1]
    sub_lons = lon_centres[col0:col1]
    lon_grid, lat_grid = np.meshgrid(sub_lons, sub_lats)
    _, _, distance_m = GEOD.inv(
        np.full(lon_grid.shape, EVENT_LON),
        np.full(lat_grid.shape, EVENT_LAT),
        lon_grid,
        lat_grid,
    )
    masks = {radius: distance_m <= radius * 1000.0 for radius in AOI_RADII_KM}

    return {
        "shape": [rows, cols],
        "bounds_wgs84": [west, south, east, north],
        "pixel_size_degrees": [pixel_width, pixel_height],
        "window": [row0, row1, col0, col1],
        "masks": masks,
        "pixel_counts": {str(radius): int(mask.sum()) for radius, mask in masks.items()},
        "coordinate_support": "pixel centres derived from HDF-EOS upper-left grid bounds",
    }


def decode_qa(
    radiance: np.ndarray,
    mandatory: np.ndarray,
    cloud: np.ndarray,
    snow: np.ndarray,
    radiance_fill: float,
    mandatory_fill: int,
    cloud_fill: int,
    snow_fill: int,
) -> dict[str, np.ndarray]:
    physical = np.isfinite(radiance) & (radiance != radiance_fill) & (radiance >= 0.0)
    mandatory_high_quality = mandatory == 0

    cloud_not_fill = cloud != cloud_fill
    night = (cloud & 0b1) == 0
    cloud_mask_quality = (cloud >> 4) & 0b11
    cloud_detection = (cloud >> 6) & 0b11
    no_shadow = ((cloud >> 8) & 0b1) == 0
    no_cirrus = ((cloud >> 9) & 0b1) == 0
    no_cloudmask_snow = ((cloud >> 10) & 0b1) == 0
    no_aurora = ((cloud >> 12) & 0b1) == 0
    no_lunar_eclipse = ((cloud >> 13) & 0b1) == 0
    snow_free = (snow != snow_fill) & (snow == 0)

    strict = (
        physical
        & (mandatory != mandatory_fill)
        & mandatory_high_quality
        & cloud_not_fill
        & night
        & (cloud_mask_quality >= 2)
        & (cloud_detection <= 1)
        & no_shadow
        & no_cirrus
        & no_cloudmask_snow
        & no_aurora
        & no_lunar_eclipse
        & snow_free
    )
    return {
        "physical": physical,
        "mandatory_high_quality": physical & mandatory_high_quality,
        "cloud_medium_high": physical & cloud_not_fill & (cloud_mask_quality >= 2),
        "cloud_clear_or_probably_clear": physical & cloud_not_fill & (cloud_detection <= 1),
        "strict": strict,
    }


def safe_stats(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "p05": None,
            "p95": None,
            "max": None,
        }
    return {
        "mean": float(np.mean(values, dtype=np.float64)),
        "median": float(np.median(values)),
        "std": float(np.std(values, dtype=np.float64, ddof=0)),
        "min": float(np.min(values)),
        "p05": float(np.percentile(values, 5)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def main() -> None:
    event = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
    anchor = event["downstream_anchor"]
    if anchor["event_point_wgs84_lon_lat"] != [EVENT_LON, EVENT_LAT]:
        raise AssertionError("Formal event coordinates do not match the fixed Q18 contract")
    if anchor["event_time_utc"] != EVENT_TIME_UTC.isoformat().replace("+00:00", "Z"):
        raise AssertionError("Formal event UTC time does not match the fixed Q18 contract")

    hdf_files = sorted(HDF_DIR.glob("VNP46A2.*.h5"))
    if len(hdf_files) != 16:
        raise RuntimeError(f"Expected 16 official HDF5 inputs, found {len(hdf_files)}")

    grid = build_grid_geometry(hdf_files[0])
    row0, row1, col0, col1 = grid["window"]
    records: list[dict[str, Any]] = []
    input_inventory: list[dict[str, Any]] = []
    product_dates: list[date] = []
    reference_grid_signature: tuple[Any, ...] | None = None
    first_metadata: dict[str, Any] | None = None

    for hdf_path in hdf_files:
        product_date, name_parts = product_date_from_name(hdf_path)
        product_dates.append(product_date)
        input_hash = sha256_file(hdf_path)
        local_night_date, relation = temporal_label(product_date)

        with h5py.File(hdf_path, "r") as hdf:
            root_attrs = attrs_dict(hdf)
            radiance_ds = hdf[PATHS["radiance"]]
            mandatory_ds = hdf[PATHS["mandatory_quality"]]
            cloud_ds = hdf[PATHS["cloud_mask"]]
            snow_ds = hdf[PATHS["snow_flag"]]

            grid_signature = (
                radiance_ds.shape,
                root_attrs["WestBoundingCoord"],
                root_attrs["SouthBoundingCoord"],
                root_attrs["EastBoundingCoord"],
                root_attrs["NorthBoundingCoord"],
                root_attrs["HorizontalTileNumber"],
                root_attrs["VerticalTileNumber"],
                root_attrs["VersionID"],
            )
            if reference_grid_signature is None:
                reference_grid_signature = grid_signature
                first_metadata = {
                    "root_attributes": root_attrs,
                    "dataset_attributes": {
                        key: attrs_dict(hdf[path]) for key, path in PATHS.items()
                    },
                }
            elif grid_signature != reference_grid_signature:
                raise AssertionError(f"Grid/product mismatch: {hdf_path.name}")

            range_date = str(root_attrs["RangeBeginningDate"])
            if range_date != product_date.isoformat():
                raise AssertionError(
                    f"Filename/root product date mismatch for {hdf_path.name}: {range_date}"
                )

            radiance = radiance_ds[row0:row1, col0:col1].astype(np.float64)
            mandatory = mandatory_ds[row0:row1, col0:col1]
            cloud = cloud_ds[row0:row1, col0:col1]
            snow = snow_ds[row0:row1, col0:col1]

            scale = scalar_attr(radiance_ds.attrs, "scale_factor")
            offset = scalar_attr(radiance_ds.attrs, "offset")
            radiance_fill = scalar_attr(radiance_ds.attrs, "_FillValue")
            mandatory_fill = int(scalar_attr(mandatory_ds.attrs, "_FillValue"))
            cloud_fill = int(scalar_attr(cloud_ds.attrs, "_FillValue"))
            snow_fill = int(scalar_attr(snow_ds.attrs, "_FillValue"))
            radiance = radiance * scale + offset

            qa = decode_qa(
                radiance,
                mandatory,
                cloud,
                snow,
                radiance_fill * scale + offset,
                mandatory_fill,
                cloud_fill,
                snow_fill,
            )

            for radius_km in AOI_RADII_KM:
                aoi = grid["masks"][radius_km]
                total = int(aoi.sum())
                strict_mask = aoi & qa["strict"]
                strict_values = radiance[strict_mask]
                stats = safe_stats(strict_values)
                record = {
                    "utc_product_date": product_date.isoformat(),
                    "interpreted_local_night_date_asia_yangon": local_night_date.isoformat(),
                    "temporal_relation": relation,
                    "aoi_radius_km": radius_km,
                    "aoi_support": "WGS84 geodesic radius; pixel-centre inclusion; unweighted pixels",
                    "aoi_pixel_count": total,
                    "radiance_physical_valid_count": int((aoi & qa["physical"]).sum()),
                    "mandatory_high_quality_count": int(
                        (aoi & qa["mandatory_high_quality"]).sum()
                    ),
                    "cloud_medium_high_quality_count": int(
                        (aoi & qa["cloud_medium_high"]).sum()
                    ),
                    "cloud_clear_or_probably_clear_count": int(
                        (aoi & qa["cloud_clear_or_probably_clear"]).sum()
                    ),
                    "qa_valid_pixel_count": int(strict_mask.sum()),
                    "qa_valid_fraction": float(strict_mask.sum() / total),
                    "radiance_mean_nw_cm2_sr": stats["mean"],
                    "radiance_median_nw_cm2_sr": stats["median"],
                    "radiance_std_nw_cm2_sr": stats["std"],
                    "radiance_min_nw_cm2_sr": stats["min"],
                    "radiance_p05_nw_cm2_sr": stats["p05"],
                    "radiance_p95_nw_cm2_sr": stats["p95"],
                    "radiance_max_nw_cm2_sr": stats["max"],
                    "hdf_filename": hdf_path.name,
                    "hdf_sha256": input_hash,
                    "producer_granule_id": str(root_attrs["LocalGranuleID"]),
                    "tile": f"h{name_parts['h']}v{name_parts['v']}",
                    "collection": name_parts["collection"],
                }
                records.append(record)

            input_inventory.append(
                {
                    "filename": hdf_path.name,
                    "path": str(hdf_path),
                    "bytes": hdf_path.stat().st_size,
                    "sha256": input_hash,
                    "utc_product_date": product_date.isoformat(),
                    "producer_granule_id": str(root_attrs["LocalGranuleID"]),
                    "range_beginning": (
                        f"{root_attrs['RangeBeginningDate']}T{root_attrs['RangeBeginningTime']}Z"
                    ),
                    "range_ending": (
                        f"{root_attrs['RangeEndingDate']}T{root_attrs['RangeEndingTime']}Z"
                    ),
                    "production_time": str(root_attrs["ProductionTime"]),
                }
            )

    if product_dates != sorted(product_dates) or len(set(product_dates)) != len(product_dates):
        raise AssertionError("Product dates are not unique and sorted")

    fieldnames = list(records[0].keys())
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    csv_hash = sha256_file(CSV_PATH)
    coverage_by_radius: dict[str, Any] = {}
    for radius in AOI_RADII_KM:
        subset = [r for r in records if r["aoi_radius_km"] == radius]
        coverage_by_radius[str(radius)] = {
            "record_count": len(subset),
            "aoi_pixel_count": subset[0]["aoi_pixel_count"],
            "qa_valid_fraction_min": min(r["qa_valid_fraction"] for r in subset),
            "qa_valid_fraction_max": max(r["qa_valid_fraction"] for r in subset),
            "all_records_have_valid_pixels": all(r["qa_valid_pixel_count"] > 0 for r in subset),
            "records_with_valid_pixels": sum(r["qa_valid_pixel_count"] > 0 for r in subset),
            "dates_without_valid_pixels": [
                r["utc_product_date"] for r in subset if r["qa_valid_pixel_count"] == 0
            ],
        }

    critical_temporal_support = all(
        sum(
            r["qa_valid_pixel_count"] > 0
            for r in records
            if r["aoi_radius_km"] == radius
            and r["utc_product_date"] < EVENT_TIME_UTC.date().isoformat()
        )
        >= 5
        and any(
            r["qa_valid_pixel_count"] > 0
            for r in records
            if r["aoi_radius_km"] == radius
            and r["utc_product_date"] == EVENT_TIME_UTC.date().isoformat()
        )
        for radius in AOI_RADII_KM
    )

    acceptance_checks = {
        "formal_event_anchor_matched": True,
        "official_hdf5_count_is_16": len(input_inventory) == 16,
        "product_dates_unique_and_sorted": product_dates == sorted(set(product_dates)),
        "all_granules_same_collection_tile_grid": True,
        "both_25km_and_50km_aoi_supported": set(grid["pixel_counts"]) == {"25", "50"},
        "csv_has_expected_rows": len(records) == len(AOI_RADII_KM) * len(input_inventory),
        "critical_pre_event_and_first_post_event_support_available": critical_temporal_support,
        "zero_valid_rows_preserved_as_explicit_missing_observations": any(
            r["qa_valid_pixel_count"] == 0 for r in records
        ),
        "valid_counts_do_not_exceed_aoi_counts": all(
            r["qa_valid_pixel_count"] <= r["aoi_pixel_count"] for r in records
        ),
        "valid_radiance_values_nonnegative_where_available": all(
            r["radiance_min_nw_cm2_sr"] is None
            or r["radiance_min_nw_cm2_sr"] >= 0
            for r in records
        ),
        "qa_valid_fractions_within_unit_interval": all(
            0.0 <= r["qa_valid_fraction"] <= 1.0 for r in records
        ),
        "historical_outputs_not_read": True,
    }

    package = {
        "schema": "ntl.observation-package.v2",
        "task_id": "Q18-myanmar-earthquake",
        "role": "NTL Data Searcher",
        "status": (
            "analysis_ready_with_missing_quality_observations_and_temporal_coverage_limitation"
            if all(acceptance_checks.values())
            else "failed_acceptance"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "objective": (
            "Construct an independently decoded, QA-filtered VNP46A2 series for the "
            "formal Myanmar earthquake anchor without event-impact inference."
        ),
        "event_anchor": {
            "usgs_id": "us7000pn9s",
            "event_time_utc": anchor["event_time_utc"],
            "event_time_local_asia_yangon": anchor["event_time_local"],
            "event_point_wgs84_lon_lat": anchor["event_point_wgs84_lon_lat"],
        },
        "product": {
            "short_name": "VNP46A2",
            "long_name": first_metadata["root_attributes"]["LongName"],
            "collection": "002",
            "doi": first_metadata["root_attributes"]["identifier_product_doi"],
            "platform": first_metadata["root_attributes"]["PlatformShortName"],
            "sensor": first_metadata["root_attributes"]["SensorShortname"],
            "algorithm_version": first_metadata["root_attributes"]["AlgorithmVersion"],
            "band": "DNB_BRDF-Corrected_NTL",
            "band_path": PATHS["radiance"],
            "units": "nW cm^-2 sr^-1",
            "scale_factor": scalar_attr_value(first_metadata, "radiance", "scale_factor"),
            "offset": scalar_attr_value(first_metadata, "radiance", "offset"),
            "fill_value": scalar_attr_value(first_metadata, "radiance", "_FillValue"),
        },
        "grid": {
            "crs": "EPSG:4326",
            "projection_from_struct_metadata": "HE5_GCTP_GEO",
            "resolution": "15 arc-second",
            "shape_rows_cols": grid["shape"],
            "bounds_wgs84_wsen": grid["bounds_wgs84"],
            "pixel_size_degrees": grid["pixel_size_degrees"],
            "tile": "h27v06",
            "aoi_pixel_counts": grid["pixel_counts"],
            "spatial_support": grid["coordinate_support"],
            "reducer": "unweighted pixel mean/median/population standard deviation and percentiles",
        },
        "aoi": {
            "centre_wgs84_lon_lat": [EVENT_LON, EVENT_LAT],
            "radii_km": list(AOI_RADII_KM),
            "geometry": "WGS84 ellipsoidal geodesic distance using pyproj.Geod(ellps='WGS84')",
            "inclusion_rule": "pixel centre distance <= radius",
        },
        "qa_contract": {
            "physical_radiance": "finite, not fill, and >= 0 after scale/offset",
            "mandatory_quality": "Mandatory_Quality_Flag == 0 (high-quality main algorithm)",
            "cloud_mask": [
                "QF_Cloud_Mask not fill",
                "bit 0 == 0 (night)",
                "bits 4-5 >= 2 (medium/high cloud-mask quality)",
                "bits 6-7 <= 1 (confident/probably clear)",
                "bits 8, 9, 10, 12, 13 == 0 (no shadow, cirrus, snow/ice, aurora, lunar eclipse)",
            ],
            "snow": "Snow_Flag == 0 and not fill",
            "primary_valid_mask": "logical AND of all conditions above",
            "qa_band_paths": {
                "mandatory_quality": PATHS["mandatory_quality"],
                "cloud_mask": PATHS["cloud_mask"],
                "snow_flag": PATHS["snow_flag"],
            },
            "dataset_attributes_from_first_hdf": first_metadata["dataset_attributes"],
        },
        "date_semantics": {
            "utc_product_date": "RangeBeginningDate and YYYY+DOY in the official granule filename",
            "interpreted_local_night_date_asia_yangon": (
                "UTC product date + 1 day, reflecting the nominal after-midnight local "
                "night-time overpass; exact pixel acquisition time is not exposed in these HDF files"
            ),
            "event_day_product": "2025-03-28",
            "first_post_event_local_night_interpreted": "2025-03-29",
            "qualification": (
                "The mainshock occurred at 12:50:52 Asia/Yangon, after the pre-event local "
                "night-time overpass. The 2025-03-28 UTC-indexed product is treated as the "
                "first post-event local night, without claiming an exact pixel time."
            ),
        },
        "temporal_coverage": {
            "utc_product_dates": [d.isoformat() for d in product_dates],
            "pre_event_contiguous_dates": [d.isoformat() for d in product_dates[:7]],
            "event_day_product_date": product_dates[7].isoformat(),
            "late_followup_dates": [d.isoformat() for d in product_dates[8:]],
            "immediate_post_event_gap": (
                "No raw products after 2025-03-28 and before 2026-07-24 are present in the "
                "supplied official-HDF set."
            ),
        },
        "input_inventory": input_inventory,
        "coverage_diagnostics": coverage_by_radius,
        "artifacts": {
            "analysis_ready_csv": {
                "path": str(CSV_PATH),
                "sha256": csv_hash,
                "rows": len(records),
            },
            "reproducible_script": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
        },
        "acceptance_checks": acceptance_checks,
        "limitations": [
            "Only one interpreted first-post-event local night is present near the event.",
            "The next available observations are in July 2026, so this package cannot establish a recovery trajectory.",
            "Strict QA leaves zero valid pixels for some AOI-date combinations; these dates are retained as explicit missing observations rather than imputed or dropped silently.",
            "VNP46A2 does not expose exact pixel acquisition time in the inspected HDF metadata.",
            "AOI summaries use unweighted pixel-centre inclusion; they are not building-level or population-weighted measures.",
            "Nighttime-light variation is observational and does not prove outage, damage, recovery, or earthquake causation.",
            "A strong subsequent earthquake is source-conflicted and may confound interpretation.",
        ],
        "historical_outputs_read": False,
        "inference_performed": False,
    }

    PACKAGE_PATH.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Re-open every declared output before emitting the validation record.
    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reopened_rows = list(csv.DictReader(handle))
    reopened_package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    if len(reopened_rows) != len(AOI_RADII_KM) * len(input_inventory):
        raise AssertionError("Re-opened CSV row count mismatch")
    if reopened_package["historical_outputs_read"] is not False:
        raise AssertionError("Blind-run flag changed unexpectedly")

    validation = {
        "schema": "ntl.q18.validation.v2",
        "task_id": "Q18-myanmar-earthquake",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": acceptance_checks
        | {
            "csv_reopened": True,
            "package_reopened": True,
            "csv_hash_recomputed_after_reopen": sha256_file(CSV_PATH) == csv_hash,
            "package_schema_validated": reopened_package["schema"] == "ntl.observation-package.v2",
        },
        "artifact_hashes": {
            CSV_PATH.name: sha256_file(CSV_PATH),
            PACKAGE_PATH.name: sha256_file(PACKAGE_PATH),
            Path(__file__).name: sha256_file(Path(__file__).resolve()),
        },
        "historical_outputs_read": False,
    }
    VALIDATION_PATH.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": package["status"],
        "inputs": len(input_inventory),
        "rows": len(records),
        "coverage_by_radius": coverage_by_radius,
        "artifacts": [str(CSV_PATH), str(PACKAGE_PATH), str(VALIDATION_PATH)],
    }, indent=2))


def scalar_attr_value(
    metadata: dict[str, Any], dataset_key: str, attr_key: str
) -> float:
    value = metadata["dataset_attributes"][dataset_key][attr_key]
    if isinstance(value, list):
        value = value[0]
    return float(value)


if __name__ == "__main__":
    main()
