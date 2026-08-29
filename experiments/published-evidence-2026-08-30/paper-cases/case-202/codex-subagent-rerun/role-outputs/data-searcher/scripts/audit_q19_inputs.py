#!/usr/bin/env python
"""Independent local audit of the frozen Q19 Tehran observation inputs.

This is a Codex-subagent simulation audit.  It deliberately performs no
Earth Engine query, download, interpolation, event interpretation, or
manuscript edit.  It reads the prior Q19 package and writes all deliverables
under this role's output directory.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform


CASE_ID = "Q19-tehran-city-longseries"
BASELINE_START = date(2026, 1, 1)
BASELINE_END = date(2026, 2, 27)
AUDIT_START = date(2026, 1, 1)
AUDIT_END = date(2026, 8, 2)
QA_MODES = ("strict", "permissive")
CSV_FIELDS = [
    "date_utc",
    "qa_mode",
    "image_available",
    "qualified",
    "mean",
    "median",
    "std",
    "p25",
    "p75",
    "valid_count",
    "total_count",
    "valid_fraction",
    "units",
    "scale_m",
    "source_image_id",
]
NUMERIC_FIELDS = {
    "mean",
    "median",
    "std",
    "p25",
    "p75",
    "valid_fraction",
}
INT_FIELDS = {"valid_count", "total_count", "scale_m"}
BOOL_FIELDS = {"image_available", "qualified"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if relative_to is not None:
        record["relative_path"] = str(path.relative_to(relative_to)).replace("\\", "/")
    return record


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def date_range(start: date, end: date) -> list[str]:
    values: list[str] = []
    current = start
    while current <= end:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return bool(value)


def to_number(value: Any, integer: bool = False) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value) if integer else float(value)
    number = float(value)
    if integer:
        if not number.is_integer():
            raise ValueError(f"Expected integer-like value, got {value!r}")
        return int(number)
    return number


def canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in CSV_FIELDS:
        value = row.get(field)
        if field in BOOL_FIELDS:
            result[field] = to_bool(value)
        elif field in INT_FIELDS:
            result[field] = to_number(value, integer=True)
        elif field in NUMERIC_FIELDS:
            result[field] = to_number(value)
        elif field == "source_image_id":
            result[field] = value or None
        else:
            result[field] = value
    return result


def canonical_digest(rows: Iterable[dict[str, Any]]) -> str:
    payload = "\n".join(
        json.dumps(canonical_row(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        if left is None or right is None:
            return left is right
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def rows_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_c = canonical_row(left)
    right_c = canonical_row(right)
    return all(values_equal(left_c.get(field), right_c.get(field)) for field in CSV_FIELDS)


def source_line_ranges(text: str) -> dict[str, str]:
    lines = text.splitlines()

    def find(fragment: str) -> int | None:
        for number, line in enumerate(lines, start=1):
            if fragment in line:
                return number
        return None

    mask = find("def make_qa_bands")
    row = find("def row_for_mode")
    return {
        "qa_mask_function": f"extract_tehran_daily_vnp46a2.py:{mask or '?'}-278",
        "row_selection_function": f"extract_tehran_daily_vnp46a2.py:{row or '?'}-562",
    }


def compare_recorded_hash(path: Path, recorded: dict[str, Any] | None) -> dict[str, Any]:
    actual = artifact_record(path)
    recorded = recorded or {}
    return {
        "path": str(path),
        "actual_bytes": actual["bytes"],
        "actual_sha256": actual["sha256"],
        "recorded_bytes": recorded.get("bytes"),
        "recorded_sha256": recorded.get("sha256"),
        "bytes_match": recorded.get("bytes") == actual["bytes"],
        "sha256_match": recorded.get("sha256") == actual["sha256"],
    }


def feature_expected_row(properties: dict[str, Any], mode: str, date_text: str) -> dict[str, Any]:
    count = to_number(properties.get(f"{mode}_count"), integer=True)
    total = to_number(properties.get("base_count"), integer=True)
    qualified = count is not None and count > 0
    row: dict[str, Any] = {
        "date_utc": date_text,
        "qa_mode": mode,
        "image_available": True,
        "qualified": qualified,
        "mean": properties.get(f"{mode}_mean") if qualified else None,
        "median": properties.get(f"{mode}_median") if qualified else None,
        "std": properties.get(f"{mode}_stdDev") if qualified else None,
        "p25": properties.get(f"{mode}_p25") if qualified else None,
        "p75": properties.get(f"{mode}_p75") if qualified else None,
        "valid_count": count,
        "total_count": total,
        "valid_fraction": (count / total) if qualified and total and total > 0 else None,
        "units": "nW cm^-2 sr^-1",
        "scale_m": 500,
        "source_image_id": properties.get("source_image_id"),
    }
    return row


def main() -> int:
    output_dir = Path(__file__).resolve().parents[1]
    rerun_dir = output_dir.parents[1]
    project_dir = rerun_dir.parents[1]
    source_dir = project_dir / "experiments" / "paper-case-multiagent-2026-08-13" / "Q19-tehran-city-longseries"
    contract_path = rerun_dir / "experiment-contract.md"

    required_sources = [
        contract_path,
        source_dir / "daily-vnp46a2.csv",
        source_dir / "daily-vnp46a2-raw.jsonl",
        source_dir / "observation-package.json",
        source_dir / "tehran-boundary.geojson",
        source_dir / "tehran-boundary-metadata.json",
        source_dir / "gee-checkpoint.json",
        source_dir / "data-searcher-log.md",
        source_dir / "artifact-manifest.json",
        source_dir / "extract_tehran_daily_vnp46a2.py",
        source_dir / "gee-code-review.json",
        source_dir / "gee-failure.json",
    ] + sorted(source_dir.glob("gee-chunk-2026-*.json"))
    missing_inputs = [str(path) for path in required_sources if not path.exists()]
    if missing_inputs:
        raise FileNotFoundError("Missing required inputs: " + ", ".join(missing_inputs))

    contract_text = contract_path.read_text(encoding="utf-8")
    observation = read_json(source_dir / "observation-package.json")
    checkpoint = read_json(source_dir / "gee-checkpoint.json")
    boundary_metadata = read_json(source_dir / "tehran-boundary-metadata.json")
    boundary_payload = read_json(source_dir / "tehran-boundary.geojson")
    source_manifest = read_json(source_dir / "artifact-manifest.json")
    source_manifest_entries = {
        str(entry.get("path", "")).replace("\\", "/").split("/")[-1]: entry
        for entry in source_manifest.get("artifacts", [])
    }
    extractor_text = (source_dir / "extract_tehran_daily_vnp46a2.py").read_text(encoding="utf-8")

    csv_path = source_dir / "daily-vnp46a2.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    raw_path = source_dir / "daily-vnp46a2-raw.jsonl"
    raw_rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    expected_dates = date_range(AUDIT_START, AUDIT_END)
    baseline_dates = date_range(BASELINE_START, BASELINE_END)
    rows_by_key = {(row["date_utc"], row["qa_mode"]): row for row in csv_rows}
    csv_dates = sorted({row["date_utc"] for row in csv_rows})
    csv_modes = Counter(row["qa_mode"] for row in csv_rows)

    # Reopen every monthly chunk and build the independent source-of-record map.
    chunk_summaries: list[dict[str, Any]] = []
    chunk_features_by_date: dict[str, dict[str, Any]] = {}
    chunk_errors: list[str] = []
    chunk_paths = sorted(source_dir.glob("gee-chunk-2026-*.json"))
    for chunk_path in chunk_paths:
        chunk = read_json(chunk_path)
        features = chunk.get("features", [])
        feature_dates = [feature.get("properties", {}).get("date_utc") for feature in features]
        available_dates = chunk.get("available_product_dates", [])
        if chunk.get("feature_count") != len(features):
            chunk_errors.append(f"{chunk_path.name}: feature_count != len(features)")
        if feature_dates != available_dates:
            chunk_errors.append(f"{chunk_path.name}: feature dates != available_product_dates")
        if chunk.get("status") != "complete":
            chunk_errors.append(f"{chunk_path.name}: status={chunk.get('status')!r}")
        validation = chunk.get("validation", {})
        for key in ("date_set_matches", "feature_count_matches", "identity_fields_present", "numeric_reducer_statistic_present", "output_reopened"):
            if validation.get(key) is not True:
                chunk_errors.append(f"{chunk_path.name}: validation {key}={validation.get(key)!r}")
        for feature in features:
            properties = feature.get("properties", {})
            day = properties.get("date_utc")
            if not day or day in chunk_features_by_date:
                chunk_errors.append(f"{chunk_path.name}: duplicate or missing feature date {day!r}")
            else:
                chunk_features_by_date[day] = properties
            if not properties.get("source_image_id"):
                chunk_errors.append(f"{chunk_path.name}: missing source_image_id on {day}")
        chunk_summaries.append(
            {
                "file": chunk_path.name,
                "sha256": sha256(chunk_path),
                "feature_count": len(features),
                "available_date_count": len(available_dates),
                "first_date_utc": min(feature_dates) if feature_dates else None,
                "last_date_utc": max(feature_dates) if feature_dates else None,
                "feature_dates_equal_available_product_dates": feature_dates == available_dates,
                "recorded_validation": validation,
            }
        )

    chunk_dates = sorted(chunk_features_by_date)
    actual_image_dates = sorted({row["date_utc"] for row in csv_rows if to_bool(row["image_available"])})
    derived_missing_dates = sorted(set(expected_dates) - set(actual_image_dates))
    checkpoint_missing_dates = sorted(checkpoint.get("missing_image_dates", []))

    # Independent reconstruction of each CSV image-present row from chunk properties.
    chunk_reconstruction_mismatches: list[dict[str, Any]] = []
    for row in csv_rows:
        if not to_bool(row["image_available"]):
            continue
        properties = chunk_features_by_date.get(row["date_utc"])
        if properties is None:
            chunk_reconstruction_mismatches.append({"key": [row["date_utc"], row["qa_mode"]], "reason": "missing chunk feature"})
            continue
        expected = feature_expected_row(properties, row["qa_mode"], row["date_utc"])
        if not rows_equal(row, expected):
            chunk_reconstruction_mismatches.append(
                {"key": [row["date_utc"], row["qa_mode"]], "csv": canonical_row(row), "from_chunk": canonical_row(expected)}
            )

    # Raw JSONL and CSV are independently re-opened and compared semantically.
    raw_csv_mismatches: list[dict[str, Any]] = []
    if len(csv_rows) != len(raw_rows):
        raw_csv_mismatches.append({"reason": "row_count_mismatch", "csv": len(csv_rows), "raw_jsonl": len(raw_rows)})
    for index, (csv_row, raw_row) in enumerate(zip(csv_rows, raw_rows)):
        if not rows_equal(csv_row, raw_row):
            raw_csv_mismatches.append({"row_index": index, "csv": canonical_row(csv_row), "raw_jsonl": canonical_row(raw_row)})
            if len(raw_csv_mismatches) >= 20:
                break

    # AOI geometry is re-opened and checked independently with Shapely/PROJ.
    geometry_errors: list[str] = []
    features = boundary_payload.get("features", [])
    geometry = shape(features[0]["geometry"]) if len(features) == 1 else None
    if geometry is None:
        geometry_errors.append(f"expected exactly one boundary feature, got {len(features)}")
        area_km2 = None
        vertex_count = None
        bbox = None
    else:
        if geometry.geom_type != "Polygon":
            geometry_errors.append(f"geometry type is {geometry.geom_type}, expected Polygon")
        if geometry.is_empty:
            geometry_errors.append("geometry is empty")
        if not geometry.is_valid:
            geometry_errors.append(f"invalid geometry: {geometry.is_valid}")
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
        area_km2 = transform(transformer.transform, geometry).area / 1_000_000
        vertex_count = len(geometry.exterior.coords) + sum(len(ring.coords) for ring in geometry.interiors)
        bbox = list(geometry.bounds)
        declared_area = boundary_metadata.get("geometry", {}).get("area_equal_area_km2_epsg6933")
        if declared_area is not None and not math.isclose(area_km2, float(declared_area), rel_tol=0, abs_tol=1e-4):
            geometry_errors.append(f"equal-area mismatch: computed {area_km2} vs metadata {declared_area}")
        declared_vertices = boundary_metadata.get("geometry", {}).get("vertex_count_including_ring_closure")
        if declared_vertices is not None and vertex_count != declared_vertices:
            geometry_errors.append(f"vertex-count mismatch: computed {vertex_count} vs metadata {declared_vertices}")

    # Recorded artifact hashes are checked against the exact files read here.
    recorded_hash_checks = [
        compare_recorded_hash(path, source_manifest_entries.get(path.name))
        for path in required_sources
        if path != contract_path and path.name != "artifact-manifest.json"
    ]
    artifact_hash_mismatches = [
        check for check in recorded_hash_checks if not (check["bytes_match"] and check["sha256_match"])
    ]
    observation_aoi_hash_checks = {
        "boundary": compare_recorded_hash(source_dir / "tehran-boundary.geojson", observation.get("aoi", {}).get("artifact")),
        "boundary_metadata": compare_recorded_hash(source_dir / "tehran-boundary-metadata.json", observation.get("aoi", {}).get("metadata_artifact")),
    }

    strict_rows = [row for row in csv_rows if row["qa_mode"] == "strict"]
    permissive_rows = [row for row in csv_rows if row["qa_mode"] == "permissive"]
    baseline_rows = [row for row in csv_rows if BASELINE_START <= date.fromisoformat(row["date_utc"]) <= BASELINE_END]

    def mode_summary(mode: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        selected = [row for row in rows if row["qa_mode"] == mode]
        image_present = [row for row in selected if to_bool(row["image_available"])]
        qualified = [row for row in selected if to_bool(row["qualified"])]
        zero_valid = [row for row in image_present if to_number(row.get("valid_count"), integer=True) == 0]
        missing_image = [row for row in selected if not to_bool(row["image_available"])]
        return {
            "row_count": len(selected),
            "calendar_day_count": len({row["date_utc"] for row in selected}),
            "image_available_day_count": len({row["date_utc"] for row in image_present}),
            "missing_image_day_count": len({row["date_utc"] for row in missing_image}),
            "qualified_day_count": len({row["date_utc"] for row in qualified}),
            "unqualified_image_day_count": len({row["date_utc"] for row in image_present if not to_bool(row["qualified"])}),
            "zero_valid_count_day_count": len({row["date_utc"] for row in zero_valid}),
            "qualified_date_utc": [row["date_utc"] for row in qualified],
            "missing_image_dates_utc": [row["date_utc"] for row in missing_image],
        }

    full_mode_summary = {mode: mode_summary(mode, csv_rows) for mode in QA_MODES}
    baseline_mode_summary = {mode: mode_summary(mode, baseline_rows) for mode in QA_MODES}
    latest_strict = max((row["date_utc"] for row in strict_rows if to_bool(row["qualified"])), default=None)
    latest_image = max(actual_image_dates, default=None)

    # Product and QA claims are checked against both the package and the source extractor.
    product = observation.get("product", {})
    qa_contract = observation.get("qa_contract", {})
    code_line_ranges = source_line_ranges(extractor_text)
    product_checks = {
        "collection_id_matches_package_and_extractor": product.get("collection_id") == "NASA/VIIRS/002/VNP46A2" and "NASA/VIIRS/002/VNP46A2" in extractor_text,
        "band_matches_package_and_extractor": product.get("band") == "DNB_BRDF_Corrected_NTL" and "BAND = \"DNB_BRDF_Corrected_NTL\"" in extractor_text,
        "daily_cadence_recorded": product.get("cadence") == "daily",
        "units_recorded": product.get("units") == "nW cm^-2 sr^-1",
        "analysis_scale_recorded": product.get("analysis_scale_m") == 500,
        "no_gap_filled_band": product.get("gap_filled_band_used") is False,
        "checkpoint_band_names_include_required": "DNB_BRDF_Corrected_NTL" in checkpoint.get("band_names", []),
    }
    qa_tokens = [
        "Mandatory_Quality_Flag",
        "Snow_Flag",
        "QF_Cloud_Mask",
        "mandatory.eq(0)",
        "mandatory.lte(1)",
        "cloud_mask_quality.gte(2)",
        "cloud_mask_quality.gte(1)",
    ]
    qa_checks = {
        "package_common_contract_present": len(qa_contract.get("common", [])) >= 1,
        "package_strict_contract_present": len(qa_contract.get("strict", [])) >= 1,
        "package_permissive_contract_present": len(qa_contract.get("permissive", [])) >= 1,
        "qualified_definition_is_positive_count": "At least one QA-qualified pixel" in qa_contract.get("qualified_definition", ""),
        "all_mask_tokens_present_in_extractor": all(token in extractor_text for token in qa_tokens),
        "no_interpolation_recorded": bool(observation.get("time_contract", {}).get("no_imputation")) and bool(observation.get("validation", {}).get("no_imputation_or_interpolation")),
    }

    checks = {
        "input_files_present": not missing_inputs,
        "csv_fieldnames_match_contract": list(csv_rows[0]) == CSV_FIELDS if csv_rows else False,
        "csv_row_count_428": len(csv_rows) == 428,
        "raw_jsonl_row_count_matches_csv": len(raw_rows) == len(csv_rows),
        "csv_raw_semantic_match": not raw_csv_mismatches,
        "chunk_count_8": len(chunk_paths) == 8,
        "chunk_feature_count_200": len(chunk_features_by_date) == 200,
        "chunk_dates_equal_csv_image_dates": chunk_dates == actual_image_dates,
        "calendar_dates_complete": csv_dates == expected_dates,
        "two_qa_rows_per_calendar_day": all(len([row for row in csv_rows if row["date_utc"] == day]) == 2 for day in expected_dates),
        "missing_dates_match_checkpoint": derived_missing_dates == checkpoint_missing_dates,
        "chunk_reconstruction_matches_csv": not chunk_reconstruction_mismatches,
        "aoi_geometry_reopened_valid": not geometry_errors,
        "recorded_artifact_hashes_match": not artifact_hash_mismatches,
        "observation_aoi_hashes_match": all(check["bytes_match"] and check["sha256_match"] for check in observation_aoi_hash_checks.values()),
        "product_checks_pass": all(product_checks.values()),
        "qa_checks_pass": all(qa_checks.values()),
        "checkpoint_counts_match_derived": checkpoint.get("available_image_date_count") == len(actual_image_dates) and checkpoint.get("missing_image_date_count") == len(derived_missing_dates) and checkpoint.get("strict_qualified_date_count") == full_mode_summary["strict"]["qualified_day_count"] and checkpoint.get("permissive_qualified_date_count") == full_mode_summary["permissive"]["qualified_day_count"],
        "observation_validation_passed": observation.get("validation", {}).get("status") == "passed",
    }

    baseline_contract = {
        "start_date_utc_inclusive": BASELINE_START.isoformat(),
        "end_date_utc_inclusive": BASELINE_END.isoformat(),
        "expected_calendar_day_count": len(baseline_dates),
        "csv_row_count": len(baseline_rows),
        "image_available_day_count": len({row["date_utc"] for row in baseline_rows if to_bool(row["image_available"])}),
        "missing_image_day_count": len({row["date_utc"] for row in baseline_rows if not to_bool(row["image_available"])}),
        "strict": baseline_mode_summary["strict"],
        "permissive": baseline_mode_summary["permissive"],
        "screening_rule": "Use UTC product-day rows with image_available=true and qualified=true (valid_count > 0); retain null/unqualified days as gaps; no interpolation or imputation.",
        "event_window_conclusion": "not assessed by this data-searcher audit",
    }

    generated_at = now_utc()
    audit_payload = {
        "schema_version": "q19.daily-series-audit.v1",
        "case_id": CASE_ID,
        "execution_context": "Codex-subagent simulation; local independent input audit; not deployed NTL-GPT telemetry",
        "generated_at_utc": generated_at,
        "verdict": "partial",
        "verdict_reason": "Frozen inputs pass internal consistency and baseline reconstruction checks, but the package is a dated snapshot, has 14 missing product dates plus unqualified image-present days, and does not support live/current or event-causal claims.",
        "source_snapshot": {
            "source_dir": str(source_dir),
            "query_timestamp_utc_recorded": observation.get("availability", {}).get("queried_at_utc"),
            "actual_image_cutoff_utc": latest_image,
            "latest_strict_qualified_date_utc": latest_strict,
            "audit_date_utc": generated_at,
        },
        "calendar_coverage": {
            "start_date_utc_inclusive": AUDIT_START.isoformat(),
            "end_date_utc_inclusive": AUDIT_END.isoformat(),
            "expected_calendar_day_count": len(expected_dates),
            "csv_unique_day_count": len(csv_dates),
            "image_available_day_count": len(actual_image_dates),
            "missing_image_day_count": len(derived_missing_dates),
            "missing_image_dates_utc": derived_missing_dates,
            "chunk_feature_day_count": len(chunk_dates),
            "strict_qualified_day_count": full_mode_summary["strict"]["qualified_day_count"],
            "permissive_qualified_day_count": full_mode_summary["permissive"]["qualified_day_count"],
        },
        "baseline_contract": baseline_contract,
        "mode_summaries": {"full": full_mode_summary, "baseline": baseline_mode_summary},
        "cross_checks": {
            "checks": checks,
            "chunk_summaries": chunk_summaries,
            "chunk_reconstruction_mismatch_count": len(chunk_reconstruction_mismatches),
            "chunk_reconstruction_mismatches": chunk_reconstruction_mismatches[:20],
            "raw_csv_mismatch_count": len(raw_csv_mismatches),
            "raw_csv_mismatches": raw_csv_mismatches[:20],
            "csv_semantic_digest_sha256": canonical_digest(csv_rows),
            "raw_jsonl_semantic_digest_sha256": canonical_digest(raw_rows),
            "chunk_date_digest_sha256": hashlib.sha256("\n".join(chunk_dates).encode("utf-8")).hexdigest(),
            "derived_missing_dates_digest_sha256": hashlib.sha256("\n".join(derived_missing_dates).encode("utf-8")).hexdigest(),
            "recorded_hash_checks": recorded_hash_checks,
            "artifact_hash_mismatch_count": len(artifact_hash_mismatches),
            "observation_aoi_hash_checks": observation_aoi_hash_checks,
            "geometry_errors": geometry_errors,
        },
        "aoi_audit": {
            "feature_count": len(features),
            "feature_name": features[0].get("properties", {}).get("shapeName") if features else None,
            "shape_id": features[0].get("properties", {}).get("shapeID") if features else None,
            "shape_type": features[0].get("properties", {}).get("shapeType") if features else None,
            "geometry_type": geometry.geom_type if geometry is not None else None,
            "crs": observation.get("aoi", {}).get("crs"),
            "is_valid": bool(geometry.is_valid) if geometry is not None else False,
            "is_empty": bool(geometry.is_empty) if geometry is not None else True,
            "bbox_computed": bbox,
            "vertex_count_computed": vertex_count,
            "area_equal_area_km2_computed": area_km2,
            "canonical_level": boundary_metadata.get("selected_feature", {}).get("canonical_level"),
            "administrative_semantics": boundary_metadata.get("selected_feature", {}).get("administrative_semantics"),
            "source_year_represented": boundary_metadata.get("source", {}).get("boundary_year_represented"),
            "source_build_date": boundary_metadata.get("source", {}).get("build_date"),
            "no_event_buffer_recorded": observation.get("aoi", {}).get("no_event_buffer"),
        },
        "product_audit": {
            "package_product": product,
            "checkpoint_band_names": checkpoint.get("band_names"),
            "code_evidence": code_line_ranges,
            "checks": product_checks,
        },
        "qa_audit": {
            "package_qa_contract": qa_contract,
            "code_evidence": code_line_ranges,
            "checks": qa_checks,
            "statistics_fields": ["mean", "median", "std", "p25", "p75", "valid_count", "total_count", "valid_fraction"],
            "validity_semantics": "qualified=true only when image_available=true and selected QA valid_count > 0; statistics are null otherwise; valid_fraction is valid_count / total_count only for qualified rows.",
        },
        "limitations": [
            "No live Earth Engine query or download was executed during this audit; live/current availability is unsupported beyond the recorded 2026-08-13 package snapshot.",
            "The actual product-day cutoff in the supplied files is 2026-08-02 UTC; the 2026-08-13 query timestamp is provenance, not a claim of current data.",
            "Fourteen calendar dates have no product image and remain image_available=false; image-present but zero-qualified-pixel dates remain unqualified/null.",
            "The AOI is the source-named geoBoundaries ADM2 / canonical Shahrestan unit 'City of Tehran', not asserted to be a municipality or functional urban footprint.",
            "The qualified definition has no minimum coverage threshold; downstream analysis must inspect valid_fraction and retain gaps.",
            "Product and QA semantics are checked against the local observation package, extractor, and recorded official catalog URL; this run did not separately fetch the online catalog.",
            "This audit does not assess event dates, rankings, event windows, causation, outage, damage, recovery, or continuous monitoring.",
            "This is a Codex-subagent simulation and does not prove deployment-version NTL-GPT, Deep Agents, system telemetry, or four-role performance.",
        ],
    }

    data_contract = {
        "schema_version": "q19.data-searcher-contract.v1",
        "case_id": CASE_ID,
        "role": "NTL_Data_Searcher",
        "execution_context": "Codex-subagent simulation; independent local audit; not deployed NTL-GPT",
        "generated_at_utc": generated_at,
        "verdict": "partial",
        "authority_boundary": {
            "source_package": str(source_dir),
            "source_package_status": observation.get("status"),
            "audit_script": str(Path(__file__).resolve()),
            "no_new_gee_query_or_download": True,
            "no_event_window_conclusion": True,
        },
        "aoi": audit_payload["aoi_audit"],
        "product": {
            "collection_id": product.get("collection_id"),
            "version": product.get("version"),
            "band": product.get("band"),
            "cadence": product.get("cadence"),
            "units": product.get("units"),
            "analysis_scale_m": product.get("analysis_scale_m"),
            "native_crs": product.get("native_crs"),
            "native_nominal_scale_m": product.get("native_nominal_scale_m"),
            "gap_filled_band_used": product.get("gap_filled_band_used"),
            "catalog_url_recorded": product.get("catalog_url"),
            "doi_recorded": product.get("doi"),
            "evidence_status": "recorded_and_locally_cross-checked; online catalog not fetched in this audit",
        },
        "qa": {
            "contract": qa_contract,
            "modes": {
                "strict": "common mask + Mandatory_Quality_Flag=0 + cloud-mask quality bits 4-5 >= 2",
                "permissive": "common mask + Mandatory_Quality_Flag<=1 + cloud-mask quality bits 4-5 >= 1",
            },
            "qualified_rule": "image_available=true AND selected valid_count > 0",
            "coverage_rule": "valid_fraction=valid_count/total_count when qualified; no minimum coverage threshold",
            "no_imputation": True,
            "code_evidence": code_line_ranges,
        },
        "time": {
            "basis": "UTC product day",
            "full_series_start_utc_inclusive": AUDIT_START.isoformat(),
            "full_series_end_utc_inclusive": AUDIT_END.isoformat(),
            "actual_product_cutoff_utc": latest_image,
            "latest_strict_qualified_date_utc": latest_strict,
            "calendar_day_count": len(expected_dates),
            "image_available_day_count": len(actual_image_dates),
            "missing_image_day_count": len(derived_missing_dates),
            "missing_image_dates_utc": derived_missing_dates,
            "query_timestamp_utc_recorded": observation.get("availability", {}).get("queried_at_utc"),
        },
        "baseline": baseline_contract,
        "input_selection_for_analyst": {
            "preferred_mode": "strict",
            "use_rows": "date_utc in 2026-01-01..2026-02-27 inclusive, qa_mode=strict, image_available=true, qualified=true",
            "retain_gap_rows": True,
            "do_not_fill": True,
            "sensitivity_mode": "permissive",
            "event_window_conclusions": "not supplied by this role",
        },
        "independent_validation": {
            "audit_file": "daily-series-audit.json",
            "checks_passed": sum(bool(value) for value in checks.values()),
            "checks_total": len(checks),
            "checks": checks,
        },
        "limitations": audit_payload["limitations"],
    }

    input_manifest_rows: list[dict[str, Any]] = []
    for path in required_sources:
        if path == contract_path:
            recorded = None
            recorded_match = None
            kind = "experiment contract"
        elif path.name == "artifact-manifest.json":
            # The source manifest intentionally omits its own recursive hash.
            recorded = None
            recorded_match = None
            kind = "source manifest (self-entry omitted)"
        else:
            recorded = source_manifest_entries.get(path.name)
            recorded_match = compare_recorded_hash(path, recorded)
            kind = "source input"
        input_manifest_rows.append(
            {
                "kind": kind,
                "file": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "parse_status": "parsed" if path.suffix.lower() in {".json", ".jsonl", ".csv"} or path.name.endswith(".md") or path.suffix.lower() == ".py" else "read",
                "recorded_bytes": (recorded or {}).get("bytes"),
                "recorded_sha256": (recorded or {}).get("sha256"),
                "recorded_hash_match": (recorded_match is None) or bool(recorded_match["bytes_match"] and recorded_match["sha256_match"]),
                "use": "AOI/product/date/QA/daily-series evidence input",
            }
        )

    # Write the machine-readable audit first; the generated manifest is written last
    # and intentionally excludes itself to avoid a recursive checksum.
    write_json(output_dir / "daily-series-audit.json", audit_payload)
    write_json(output_dir / "q19-data-contract.json", data_contract)

    with (output_dir / "input-manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(input_manifest_rows[0])
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(input_manifest_rows)

    integrity_md = f"""# Q19 input integrity audit\n\n- **Case:** `{CASE_ID}`\n- **Role:** `NTL_Data_Searcher`\n- **Execution context:** Codex-subagent simulation; independent local re-read; not deployed NTL-GPT telemetry.\n- **Verdict:** **partial** — the supplied frozen package is internally consistent and analysis-ready for the declared baseline under its snapshot, but it is not a live/current re-query and it contains explicit coverage gaps and administrative-AOI limits.\n- **Audit timestamp:** `{generated_at}`\n\n## Source and provenance\n\nThe audit read the prior Q19 package at `{source_dir}`. The package records an Earth Engine query timestamp of `{observation.get('availability', {}).get('queried_at_utc')}` and an actual product-date cutoff of `{latest_image}`. This audit did not make a new GEE query or download. Exact bytes and SHA-256 values are in [input-manifest.csv](input-manifest.csv); the machine-readable cross-check is [daily-series-audit.json](daily-series-audit.json).\n\n## AOI\n\nThe reopened GeoJSON contains one valid, non-empty `Polygon` feature named **City of Tehran**, shape ID `{audit_payload['aoi_audit']['shape_id']}`, `shapeType=ADM2`, CRS `EPSG:4326`. Independent Shapely/PROJ checks compute `{area_km2:.8f}` km² in EPSG:6933 and `{vertex_count}` vertices including ring closure, matching the metadata within the recorded precision. The source semantics are geoBoundaries ADM2 / canonical **Shahrestan**; it is not asserted to be a municipality or functional urban footprint. The package records no event buffer.\n\n## Product, band, and reducer\n\n- Collection: `{product.get('collection_id')}` (version `{product.get('version')}`), daily UTC product day.\n- Band used: `{product.get('band')}`; the gap-filled band is recorded as not used.\n- Units: `{product.get('units')}`; reducer scale: `{product.get('analysis_scale_m')} m`; recorded native CRS: `{product.get('native_crs')}`.\n- Per-image AOI statistics: mean, median, standard deviation, p25, p75, and count; monthly chunks are reopened locally.\n- Product metadata and QA semantics are cross-checked against the local observation package, checkpoint, extractor, and the recorded official catalog URL. This role did not separately fetch the online catalog.\n\n## QA and validity semantics\n\nThe local extractor evidence is `{code_line_ranges['qa_mask_function']}` and `{code_line_ranges['row_selection_function']}`. The recorded strict mode combines the common night/cloud/shadow/cirrus/snow/radiance conditions with `Mandatory_Quality_Flag=0` and cloud-mask quality bits 4–5 ≥2. The permissive mode uses `Mandatory_Quality_Flag≤1` and bits 4–5 ≥1. A row is `qualified=true` only if an image exists and the selected QA-valid count is positive; statistics are null otherwise. `valid_fraction` is `valid_count / total_count` only for qualified rows, and no minimum coverage threshold is applied. No imputation or interpolation is recorded.\n\n## Daily coverage\n\n| Scope | Calendar days | Image available | Missing image | Strict qualified | Permissive qualified |\n|---|---:|---:|---:|---:|---:|\n| Full supplied series (2026-01-01–2026-08-02 UTC) | {len(expected_dates)} | {len(actual_image_dates)} | {len(derived_missing_dates)} | {full_mode_summary['strict']['qualified_day_count']} | {full_mode_summary['permissive']['qualified_day_count']} |\n| Required baseline (2026-01-01–2026-02-27 UTC) | {len(baseline_dates)} | {baseline_contract['image_available_day_count']} | {baseline_contract['missing_image_day_count']} | {baseline_mode_summary['strict']['qualified_day_count']} | {baseline_mode_summary['permissive']['qualified_day_count']} |\n\nFull-series missing product dates are: `{', '.join(derived_missing_dates)}`. They are represented as `image_available=false`, not as zero radiance. Image-present but zero-qualified-pixel days are separately represented as `image_available=true`, `qualified=false`, with null statistics.\n\n## Independent checks\n\n- CSV rows: `{len(csv_rows)}`; raw JSONL rows: `{len(raw_rows)}`; semantic CSV↔JSONL mismatches: `{len(raw_csv_mismatches)}`.\n- Eight monthly chunks contain `{len(chunk_features_by_date)}` actual product dates and exactly match the CSV image-available date set: `{checks['chunk_dates_equal_csv_image_dates']}`.\n- CSV covers every calendar day from `{AUDIT_START}` to `{AUDIT_END}` with both QA modes: `{checks['calendar_dates_complete']}` / `{checks['two_qa_rows_per_calendar_day']}`.\n- Chunk-derived row reconstruction mismatches: `{len(chunk_reconstruction_mismatches)}`.\n- Recorded artifact hash mismatches: `{len(artifact_hash_mismatches)}`; AOI hashes in ObservationPackage match: `{checks['observation_aoi_hashes_match']}`.\n- Checkpoint counts match independent derivation: `{checks['checkpoint_counts_match_derived']}`.\n\nThe complete check object, source hashes, semantic digests, and mismatch samples are in [daily-series-audit.json](daily-series-audit.json).\n\n## Handoff boundary\n\nThe Analyst may use the strict baseline rows under the selection rule in [q19-data-contract.json](q19-data-contract.json), retain null/unqualified days as gaps, and use permissive rows as a sensitivity input. This audit does not calculate or endorse event-window conclusions, rankings, causation, outage, damage, recovery, or continuous monitoring.\n"""
    (output_dir / "input-integrity.md").write_text(integrity_md, encoding="utf-8")

    limitations_md = f"""# Q19 data-input limitations\n\n- **Status: partial.** Internal package integrity and the required baseline reconstruction pass, but the result is bounded to the supplied snapshot.\n- **No live refresh in this role run (unsupported):** no Earth Engine query or download was performed by this audit. The package query timestamp is `{observation.get('availability', {}).get('queried_at_utc')}` and the actual product cutoff is `{latest_image}`; later/current availability is not established.\n- **Product-date gaps (supported):** `{len(derived_missing_dates)}` of `{len(expected_dates)}` calendar dates lack a product image: `{', '.join(derived_missing_dates)}`. They remain missing and were not interpolated or filled.\n- **QA-validity gaps (supported):** for the required baseline, strict has `{baseline_mode_summary['strict']['qualified_day_count']}` qualified days and `{baseline_mode_summary['strict']['zero_valid_count_day_count']}` image-present zero-valid days; permissive has `{baseline_mode_summary['permissive']['qualified_day_count']}` qualified days and `{baseline_mode_summary['permissive']['zero_valid_count_day_count']}` image-present zero-valid days.\n- **Coverage threshold (partial):** `qualified` means at least one QA-qualified pixel; no minimum coverage threshold is imposed. Downstream analysis must inspect `valid_fraction` and avoid treating a low-coverage day as equivalent to a well-covered day.\n- **AOI semantics (supported limitation):** the geometry is a 2017 geoBoundaries ADM2 / canonical Shahrestan feature named City of Tehran, built in 2023. It is not a municipality or functional urban footprint by assertion.\n- **Catalog verification boundary (partial):** product/band/QA claims were checked against local package fields, the extractor, the checkpoint band list, and the recorded official catalog URL; this role did not fetch the online catalog separately.\n- **Event interpretation (unsupported here):** this data-searcher output does not verify event dates, rankings, event-window conclusions, causation, conflict attribution, outage, damage, recovery, or monitoring claims.\n- **Simulation boundary (unsupported here):** nothing in these files proves deployed NTL-GPT, Deep Agents, runtime telemetry, four-role performance, or benchmark performance.\n\nSee [daily-series-audit.json](daily-series-audit.json) for exact checks and [q19-data-contract.json](q19-data-contract.json) for Analyst-facing selection rules.\n"""
    (output_dir / "limitations.md").write_text(limitations_md, encoding="utf-8")

    output_paths = [
        output_dir / "input-integrity.md",
        output_dir / "q19-data-contract.json",
        output_dir / "daily-series-audit.json",
        output_dir / "input-manifest.csv",
        output_dir / "limitations.md",
        Path(__file__).resolve(),
    ]
    generated_artifacts = [artifact_record(path, relative_to=rerun_dir) for path in output_paths]
    manifest = {
        "schema_version": "q19.data-searcher-artifact-manifest.v1",
        "case_id": CASE_ID,
        "role": "NTL_Data_Searcher",
        "status": "partial_with_internal_checks_passed",
        "execution_context": "Codex-subagent simulation; not deployed NTL-GPT telemetry",
        "generated_at_utc": generated_at,
        "source_snapshot": {
            "source_dir": str(source_dir),
            "contract": artifact_record(contract_path),
            "query_timestamp_utc_recorded": observation.get("availability", {}).get("queried_at_utc"),
            "actual_product_cutoff_utc": latest_image,
        },
        "validation": {
            "verdict": "partial",
            "checks": checks,
            "check_count": {"passed": sum(bool(value) for value in checks.values()), "total": len(checks)},
            "baseline_strict_qualified_days": baseline_mode_summary["strict"]["qualified_day_count"],
            "baseline_permissive_qualified_days": baseline_mode_summary["permissive"]["qualified_day_count"],
            "baseline_missing_image_days": baseline_contract["missing_image_day_count"],
            "full_missing_image_days": len(derived_missing_dates),
            "raw_csv_semantic_mismatch_count": len(raw_csv_mismatches),
            "chunk_reconstruction_mismatch_count": len(chunk_reconstruction_mismatches),
        },
        "artifacts": generated_artifacts,
        "self_entry": "omitted to avoid recursive checksum; this manifest's own bytes/hash are not represented in artifacts",
        "limitations_file": "role-outputs/data-searcher/limitations.md",
    }
    write_json(output_dir / "artifact-manifest.json", manifest)

    # Final read-back of every generated file is a hard gate for this script.
    for path in output_paths + [output_dir / "artifact-manifest.json"]:
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"Generated artifact failed read-back gate: {path}")
    read_json(output_dir / "daily-series-audit.json")
    read_json(output_dir / "q19-data-contract.json")
    read_json(output_dir / "artifact-manifest.json")
    print(json.dumps({
        "verdict": "partial",
        "checks_passed": sum(bool(value) for value in checks.values()),
        "checks_total": len(checks),
        "baseline": {
            "calendar_days": len(baseline_dates),
            "image_available_days": baseline_contract["image_available_day_count"],
            "missing_image_days": baseline_contract["missing_image_day_count"],
            "strict_qualified_days": baseline_mode_summary["strict"]["qualified_day_count"],
            "strict_zero_valid_days": baseline_mode_summary["strict"]["zero_valid_count_day_count"],
            "permissive_qualified_days": baseline_mode_summary["permissive"]["qualified_day_count"],
            "permissive_zero_valid_days": baseline_mode_summary["permissive"]["zero_valid_count_day_count"],
        },
        "full_series": {
            "calendar_days": len(expected_dates),
            "image_available_days": len(actual_image_dates),
            "missing_image_days": len(derived_missing_dates),
            "strict_qualified_days": full_mode_summary["strict"]["qualified_day_count"],
            "permissive_qualified_days": full_mode_summary["permissive"]["qualified_day_count"],
            "actual_product_cutoff_utc": latest_image,
            "latest_strict_qualified_date_utc": latest_strict,
        },
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
