"""Extract city TNTL from the annual NPP-VIIRS-like/LongNTL GEE asset.

This is the primary *new retraining* input requested for annual DEI labels.  It
is not interchangeable with the Chen et al. paper-formula input: the LongNTL
asset is an already processed annual, cross-sensor-consistent product on a
500 m grid, whereas the paper built a 15 arc-second annual image from Version 1
monthly ``vcm`` composites.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import ee


DATASET_ID = "projects/sat-io/open-datasets/npp-viirs-ntl"
BAND = "b1"
BOUNDARY_ASSET = "projects/empyrean-caster-430308-m2/assets/city"
BOUNDARY_NAME_FIELD = "name"
BOUNDARY_CODE_FIELD = "gb"
YEARS = tuple(range(2017, 2025))
EXPECTED_BOUNDARY_ROWS = 375
PREPROCESSING_ID = "longntl_annual_native500m_positive_pixel_sum_v1"


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": (
        "Extract 2017-2024 city TNTL from the annual NPP-VIIRS-like LongNTL "
        "asset using Earth Engine server-side reduceRegions."
    ),
    "input_manifest": [
        {"kind": "gee_image_collection", "path": DATASET_ID, "required": True},
        {"kind": "gee_feature_collection", "path": BOUNDARY_ASSET, "required": True},
    ],
    "method_steps": [
        "validate exactly one LongNTL image and band b1 per requested year",
        "preserve each annual image native projection and 500 m grid",
        "mask non-positive background pixels",
        "sum positive pixel values inside all cloud-hosted city boundaries",
        "write compact deterministic CSV and provenance manifest outputs",
    ],
    "parameters": {
        "years": list(YEARS),
        "dataset_id": DATASET_ID,
        "band": BAND,
        "reducer": "sum",
        "preprocessing_id": PREPROCESSING_ID,
        "positive_pixel_mask": "b1 > 0",
    },
    "output_manifest": [
        {
            "kind": "city_year_tntl_csv",
            "path": "data/city_tntl_longntl_2017_2024.csv",
            "required": True,
        },
        {
            "kind": "gee_extraction_manifest_json",
            "path": "data/city_tntl_longntl_2017_2024_manifest.json",
            "required": True,
        },
    ],
    "validation_checks": [
        "Earth Engine initializes without interactive authentication",
        "each year resolves to exactly one LongNTL image with band b1",
        "boundary names and codes are complete and unique",
        "native nominal scale is 500 m for every year",
        "each year returns 375 finite non-negative TNTL rows",
        "final CSV contains 3000 unique year-boundary rows",
    ],
    "failure_gates": [
        "USER_PROJECT_DENIED or Earth Engine API/IAM failure",
        "missing project id or cached credentials",
        "missing or duplicate annual image",
        "missing band, boundary identity, or reducer output",
        "duplicate year-boundary key",
        "negative or non-finite TNTL",
    ],
    "execution": {
        "mode": "execute",
        "timeout_seconds": 1800,
        "overwrite_policy": "explicit --output and --manifest paths",
        "network_scope": ["earth_engine"],
        "test_strategy": (
            "compile/contract checks, live metadata and three-city smoke test, "
            "then full server-side extraction"
        ),
    },
}


class ExtractionError(RuntimeError):
    """Raised when an extraction or integrity gate fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def initialize_ee(project_id: str) -> None:
    if not project_id.strip():
        raise ExtractionError(
            "Earth Engine project id is required via --gee-project or "
            "GEE_DEFAULT_PROJECT_ID."
        )
    try:
        ee.Initialize(project=project_id.strip())
    except Exception as exc:
        raise ExtractionError(
            "Earth Engine initialization failed. Fix credentials/IAM/API state "
            f"without changing the data source: {exc}"
        ) from exc


def validate_boundaries() -> tuple[ee.FeatureCollection, dict[str, Any]]:
    zones = ee.FeatureCollection(BOUNDARY_ASSET)
    count = int(zones.size().getInfo())
    if count != EXPECTED_BOUNDARY_ROWS:
        raise ExtractionError(
            f"boundary row count changed: expected {EXPECTED_BOUNDARY_ROWS}, got {count}"
        )
    names = [str(value) for value in zones.aggregate_array(BOUNDARY_NAME_FIELD).getInfo()]
    codes = [str(value) for value in zones.aggregate_array(BOUNDARY_CODE_FIELD).getInfo()]
    if any(not value.strip() for value in names + codes):
        raise ExtractionError("boundary collection contains a missing name or code")
    if len(set(names)) != count or len(set(codes)) != count:
        raise ExtractionError("boundary name/code identities must be unique")
    asset = ee.data.getAsset(BOUNDARY_ASSET) or {}
    return zones, {
        "asset": BOUNDARY_ASSET,
        "feature_count": count,
        "name_field": BOUNDARY_NAME_FIELD,
        "code_field": BOUNDARY_CODE_FIELD,
        "update_time": asset.get("updateTime"),
        "create_time": asset.get("createTime"),
        "size_bytes": asset.get("sizeBytes"),
        "source_provenance_status": "unresolved_private_asset",
    }


def annual_image(year: int) -> tuple[ee.Image, ee.Projection, dict[str, Any]]:
    collection = (
        ee.ImageCollection(DATASET_ID)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    )
    count = int(collection.size().getInfo())
    if count != 1:
        raise ExtractionError(f"{year}: expected one annual image, got {count}")
    indexes = [str(value) for value in collection.aggregate_array("system:index").getInfo()]
    image = ee.Image(collection.first())
    bands = list(image.bandNames().getInfo())
    if BAND not in bands:
        raise ExtractionError(f"{year}: required band {BAND!r} is absent")
    selected = image.select(BAND)
    projection = selected.projection()
    projection_info = projection.getInfo()
    scale = float(projection.nominalScale().getInfo())
    if projection_info.get("crs") != "EPSG:4326":
        raise ExtractionError(f"{year}: unexpected native CRS {projection_info.get('crs')}")
    if not math.isclose(scale, 500.0, rel_tol=0, abs_tol=0.01):
        raise ExtractionError(f"{year}: expected nominal 500 m scale, got {scale}")
    metadata = {
        "year": year,
        "image_count": count,
        "system_indexes": indexes,
        "projection": projection_info,
        "nominal_scale_m": scale,
    }
    return selected.updateMask(selected.gt(0)), projection, metadata


def reduce_year(
    year: int, zones: ee.FeatureCollection
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    image, projection, metadata = annual_image(year)
    reducer = (
        ee.Reducer.sum()
        .combine(ee.Reducer.count(), sharedInputs=True)
        .combine(ee.Reducer.mean(), sharedInputs=True)
        .combine(ee.Reducer.minMax(), sharedInputs=True)
    )
    raw = image.reduceRegions(
        collection=zones,
        reducer=reducer,
        crs=projection,
        scale=projection.nominalScale(),
        tileScale=8,
    )

    def normalize(feature: ee.Feature) -> ee.Feature:
        return ee.Feature(
            None,
            {
                "boundary_name": feature.get(BOUNDARY_NAME_FIELD),
                "boundary_gb": feature.get(BOUNDARY_CODE_FIELD),
                "tntl": feature.get("sum"),
                "valid_pixel_count": feature.get("count"),
                "annual_mean": feature.get("mean"),
                "annual_min": feature.get("min"),
                "annual_max": feature.get("max"),
            },
        )

    features = raw.map(normalize).getInfo().get("features", [])
    if len(features) != EXPECTED_BOUNDARY_ROWS:
        raise ExtractionError(
            f"{year}: expected {EXPECTED_BOUNDARY_ROWS} reduced rows, got {len(features)}"
        )
    rows: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties", {}) or {}
        identity = (props.get("boundary_name"), props.get("boundary_gb"))
        raw_values = (
            props.get("tntl"),
            props.get("valid_pixel_count"),
            props.get("annual_mean"),
            props.get("annual_min"),
            props.get("annual_max"),
        )
        if any(value is None for value in identity):
            raise ExtractionError(f"{year}: null boundary identity")
        # A masked reduction is null when a boundary has no positive pixels.
        # Preserve the boundary row and encode that physically meaningful empty
        # case as zeros; downstream log-model training still rejects TNTL <= 0.
        has_positive_pixels = (
            raw_values[1] is not None and float(raw_values[1]) > 0
        )
        values = tuple(0 if value is None else value for value in raw_values)
        numeric = [float(value) for value in values]
        if any(not math.isfinite(value) or value < 0 for value in numeric):
            raise ExtractionError(f"{year} {identity[0]}: invalid output {numeric}")
        rows.append(
            {
                "Year": year,
                "BoundaryName": str(identity[0]),
                "BoundaryGB": str(identity[1]),
                "TNTL": format(float(values[0]), ".15g"),
                "ValidPixelCount": int(values[1]),
                "AnnualMean": format(float(values[2]), ".15g"),
                "AnnualMin": format(float(values[3]), ".15g"),
                "AnnualMax": format(float(values[4]), ".15g"),
                "HasPositivePixels": str(has_positive_pixels).lower(),
                "DatasetID": DATASET_ID,
                "Band": BAND,
                "PreprocessingID": PREPROCESSING_ID,
            }
        )
    rows.sort(key=lambda row: str(row["BoundaryGB"]))
    metadata["rows"] = len(rows)
    return rows, metadata


CSV_FIELDS = [
    "Year",
    "BoundaryName",
    "BoundaryGB",
    "TNTL",
    "ValidPixelCount",
    "AnnualMean",
    "AnnualMin",
    "AnnualMax",
    "HasPositivePixels",
    "DatasetID",
    "Band",
    "PreprocessingID",
]


def parse_years(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values or any(year not in YEARS for year in values):
        raise argparse.ArgumentTypeError(
            f"years must be a comma-separated subset of {YEARS[0]}-{YEARS[-1]}"
        )
    return values


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gee-project",
        default=os.getenv("GEE_DEFAULT_PROJECT_ID", ""),
        help="Authorized quota project; the script never starts interactive OAuth.",
    )
    parser.add_argument("--years", type=parse_years, default=YEARS)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data" / "city_tntl_longntl_2017_2024.csv",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=root / "data" / "city_tntl_longntl_2017_2024_manifest.json",
    )
    args = parser.parse_args()

    initialize_ee(args.gee_project)
    zones, boundary_metadata = validate_boundaries()
    rows: list[dict[str, Any]] = []
    yearly_metadata: list[dict[str, Any]] = []
    for year in args.years:
        year_rows, metadata = reduce_year(year, zones)
        rows.extend(year_rows)
        yearly_metadata.append(metadata)
        print(f"year={year} status=success rows={len(year_rows)}", flush=True)

    expected = len(args.years) * EXPECTED_BOUNDARY_ROWS
    if len(rows) != expected:
        raise ExtractionError(f"expected {expected} total rows, got {len(rows)}")
    keys = {(int(row["Year"]), str(row["BoundaryGB"])) for row in rows}
    if len(keys) != len(rows):
        raise ExtractionError("duplicate year-boundary key in final table")
    rows.sort(key=lambda row: (int(row["Year"]), str(row["BoundaryGB"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "schema_version": "ntl-gpt.dei.city-tntl-longntl-extraction.v1",
        "status": "complete",
        "classification": "retrained-input-candidate-not-paper-reproduction",
        "gee_project": args.gee_project,
        "dataset": {
            "id": DATASET_ID,
            "band": BAND,
            "product_name": "annual NPP-VIIRS-like / LongNTL",
            "edition": "Version 1",
            "source_paper_doi": "10.5194/essd-13-889-2021",
            "asset_hosting": "community-hosted Earth Engine asset",
            "upstream": {
                "repository": "Harvard Dataverse",
                "doi": "10.7910/DVN/YGIVCD",
                "dataverse_version": "6.0",
                "release_date": "2025-06-04",
                "coverage": "2000-2024",
                "scientific_creators": "Zuoqi Chen et al.",
                "gee_curator": "Samapriya Roy",
            },
            "raster_semantics": {
                "dtype": "float32",
                "crs": "EPSG:4326",
                "nominal_resolution_degrees": 0.00449157642,
                "nominal_resolution": "15 arcsec / approximately 500 m",
                "unit": "nW cm-2 sr-1",
                "unit_source": "ESSD paper; not embedded in GEE band metadata",
                "nodata": "Earth Engine mask",
                "numeric_nodata": None,
                "zero_is_valid_background": True,
                "native_grid_varies_by_year": True,
            },
            "processing_provenance": {
                "branch": "post-2013 VIIRS-composite branch",
                "autoencoder_applied": False,
                "verified_lineage": (
                    "corrected yearly VIIRS median multiplied by a fixed 2013 mask"
                ),
                "exact_monthly_input_inventory_verified": False,
                "full_update_code_public": False,
                "correction_stage_3_parameters_verified": False,
            },
            "license": {
                "data": "CC0-1.0",
                "article": "CC-BY-4.0",
            },
            "upstream_zip_md5": {
                "2019": "402144c288c3a9663df6908590bdc34c",
                "2020": "5f9b7db5520830edf7d99707691ec31d",
                "2021": "030975fe0633c6b49239b90d43fc7b16",
                "2022": "217e2b18c4e5a95e210ccb4b11938cef",
                "2023": "2265b45991c6a1e25feec3d38c15f99b",
                "2024": "8f3b22d43d373ef5b93c0474e8db26e5",
            },
            "provenance_status": "partially-reproducible",
        },
        "boundary": boundary_metadata,
        "preprocessing": {
            "id": PREPROCESSING_ID,
            "steps": [
                "select the single annual b1 image for the requested year",
                "mask b1 <= 0 background pixels",
                "preserve the native EPSG:4326 nominal 500 m grid",
                "sum positive native-grid pixel values inside each boundary",
            ],
        },
        "year_semantics": (
            "LongNTL calendar year is paired to the same user-confirmed H3C IndexYear; "
            "this is a user-defined model-year mapping, not an independently verified natural-observation year"
        ),
        "years": yearly_metadata,
        "output": {
            "path": str(args.output.resolve()),
            "row_count": len(rows),
            "sha256": sha256_file(args.output),
            "encoding": "UTF-8-SIG",
        },
        "limitations": [
            "The annual LongNTL grid and preprocessing are not numerically interchangeable with the Chen paper TNTL input.",
            "Author sidecars establish the high-level 2019-2024 lineage, but the exact monthly input inventory, correction-stage implementation, and update scripts are not public.",
            "The GEE mirror has no content checksum proving byte identity with the Harvard Dataverse Version 6.0 files.",
            "The b1 unit is sourced from the ESSD paper and is not embedded in the GEE band metadata.",
            "The private boundary asset has no source, licence, or reference-year metadata.",
            "One static boundary layer is used for every year, so historical administrative changes are not represented.",
            "H3C IndexYear and natural observation year conflict in official materials; same-key pairing follows the user's explicit instruction.",
        ],
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"status=success rows={len(rows)} output={args.output}", flush=True)
    print(f"manifest={args.manifest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
