"""Refresh the Case 202 August GEE reduction without changing its method.

The existing Case 202 August chunk recorded every 12--18 August collection
image as fully masked.  A later bounded raw-GEE check found that 12 August had
valid ``DNB_BRDF_Corrected_NTL`` pixels under the *same* strict and permissive
quality masks.  This script re-queries that August range through the original
Q19 reducer, replaces its stale cached monthly chunk only after cross-checking
the live result, and asks the original extractor to rebuild the dependent
daily table and observation package.  It never fills dates or switches to the
gap-filled band.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import ee


CASE_ID = "Case202-tehran-latest-vnp46a2"
ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT.parent
SOURCE_EXTRACTOR = (
    EXPERIMENTS / "paper-case-multiagent-2026-08-13" / "Q19-tehran-city-longseries" / "extract_tehran_daily_vnp46a2.py"
)
RAW_SUPPLEMENT = ROOT / "raw-gee-2026-08-12-to-18" / "gee-raw-aug12-18.json"
AUGUST_DATES = [f"2026-08-{day:02d}" for day in range(12, 19)]
BACKUP_DIR = ROOT / "history" / "august-live-refresh-2026-08-21"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def import_extractor() -> Any:
    spec = importlib.util.spec_from_file_location("case202_q19_refresh", SOURCE_EXTRACTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to import the accepted Q19 extractor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.CASE_ID = CASE_ID
    module.START_DATE = date(2026, 1, 1)
    return module


def backup(paths: list[Path]) -> dict[str, str]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        destination = BACKUP_DIR / path.name
        if not destination.exists():
            shutil.copy2(path, destination)
        result[path.name] = sha256(destination)
    return result


def source_ids(collection: ee.ImageCollection) -> dict[str, str]:
    payload = ee.Dictionary(
        {
            "times_ms": collection.aggregate_array("system:time_start"),
            "indices": collection.aggregate_array("system:index"),
        }
    ).getInfo()
    grouped: dict[str, list[str]] = {}
    for timestamp_ms, index in zip(payload.get("times_ms", []), payload.get("indices", [])):
        day = datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc).date().isoformat()
        if day in AUGUST_DATES:
            grouped.setdefault(day, []).append(f"NASA/VIIRS/002/VNP46A2/{index}")
    if sorted(grouped) != AUGUST_DATES:
        raise RuntimeError(f"Live GEE date set does not match expected 12--18 August: {sorted(grouped)}")
    return {day: "|".join(grouped[day]) for day in AUGUST_DATES}


def live_refresh() -> dict[str, Any]:
    if not SOURCE_EXTRACTOR.is_file():
        raise FileNotFoundError("Accepted Q19 extractor is unavailable")
    if not RAW_SUPPLEMENT.is_file():
        raise FileNotFoundError("Bounded raw-GEE supplement is unavailable")

    supplement = read_json(RAW_SUPPLEMENT)
    raw_by_date = {str(row["date_utc"]): row for row in supplement.get("dates", [])}
    observed_raw_count = raw_by_date.get("2026-08-12", {}).get("DNB_BRDF_Corrected_NTL_count")
    if not isinstance(observed_raw_count, (int, float)) or observed_raw_count <= 0:
        raise RuntimeError("Bounded raw-GEE supplement does not establish usable 12 August radiance")

    extractor = import_extractor()
    boundary = read_json(ROOT / "tehran-boundary.geojson")
    project, project_source = extractor.resolve_project()
    ee.Initialize(project=project)
    aoi = ee.Geometry(boundary["features"][0]["geometry"])
    collection = (
        ee.ImageCollection(extractor.COLLECTION_ID)
        .filterBounds(aoi.bounds())
        .filterDate("2026-08-12", "2026-08-19")
    )
    ids = source_ids(collection)
    live_payload = extractor.fetch_server_chunk(collection, aoi, AUGUST_DATES, ids)
    live_properties = extractor.validate_server_chunk(live_payload, AUGUST_DATES)
    august12 = live_properties["2026-08-12"]
    if int(august12.get("base_count", 0)) <= 0 or int(august12.get("strict_count", 0)) <= 0:
        raise RuntimeError("Live original reducer did not retain 12 August under the frozen QA contract")
    if abs(float(august12["base_mean"]) - float(raw_by_date["2026-08-12"]["contract_base_mean"])) > 1e-9:
        raise RuntimeError("Original reducer and bounded raw-GEE supplement disagree for 12 August")

    chunk_path = ROOT / "gee-chunk-2026-08.json"
    existing_chunk = read_json(chunk_path)
    existing_dates = list(existing_chunk.get("available_product_dates", []))
    existing_features = {
        feature.get("properties", {}).get("date_utc"): feature
        for feature in existing_chunk.get("features", [])
        if feature.get("properties", {}).get("date_utc")
    }
    if not all(day in existing_features for day in AUGUST_DATES):
        raise RuntimeError("Existing August cache lacks one or more current live dates")
    live_features = {
        feature.get("properties", {}).get("date_utc"): feature
        for feature in live_payload.get("features", [])
        if feature.get("properties", {}).get("date_utc")
    }
    merged_features = {**existing_features, **live_features}
    merged_payload = {"type": "FeatureCollection", "features": [merged_features[day] for day in existing_dates]}

    affected = [
        chunk_path,
        ROOT / "daily-vnp46a2.csv",
        ROOT / "daily-vnp46a2-raw.jsonl",
        ROOT / "gee-checkpoint.json",
        ROOT / "observation-package.json",
        ROOT / "gee-code-review.json",
    ]
    backup_hashes = backup(affected)
    try:
        refreshed_chunk_path, _ = extractor.write_validated_chunk(ROOT, "2026-08", existing_dates, merged_payload)
        full_run = extractor.run_live(ROOT)
    except Exception:
        for original in affected:
            saved = BACKUP_DIR / original.name
            if saved.is_file():
                shutil.copy2(saved, original)
        raise

    rows = list(csv.DictReader((ROOT / "daily-vnp46a2.csv").open(encoding="utf-8-sig")))
    by_key = {(row["date_utc"], row["qa_mode"]): row for row in rows}
    strict_12 = by_key.get(("2026-08-12", "strict"))
    permissive_12 = by_key.get(("2026-08-12", "permissive"))
    if not strict_12 or not permissive_12 or strict_12["qualified"].lower() != "true" or permissive_12["qualified"].lower() != "true":
        raise RuntimeError("Rebuilt daily table did not retain 12 August in both QA modes")
    if abs(float(strict_12["mean"]) - float(august12["strict_mean"])) > 1e-9:
        raise RuntimeError("Rebuilt strict daily row disagrees with live original reducer")
    later = [
        {"date_utc": day, "strict_qualified": by_key[(day, "strict")]["qualified"], "permissive_qualified": by_key[(day, "permissive")]["qualified"]}
        for day in AUGUST_DATES[1:]
    ]
    if any(row["strict_qualified"].lower() == "true" or row["permissive_qualified"].lower() == "true" for row in later):
        raise RuntimeError("Later August dates unexpectedly changed QA eligibility; manual review required")

    checkpoint = read_json(ROOT / "gee-checkpoint.json")
    result = {
        "schema_version": "ntl.case202.august-live-refresh.v1",
        "case_id": CASE_ID,
        "status": "passed",
        "refreshed_at_utc": utc_now(),
        "source": "Live GEE re-query through the accepted Q19 reducer and the frozen Case 202 QA contract.",
        "project_resolution_source": project_source,
        "date_scope_utc": AUGUST_DATES,
        "backup_hashes": backup_hashes,
        "raw_supplement": {"path": str(RAW_SUPPLEMENT), "sha256": sha256(RAW_SUPPLEMENT)},
        "updated_chunk": {"path": str(refreshed_chunk_path), "sha256": sha256(refreshed_chunk_path)},
        "rebuild": {
            "daily_csv_sha256": sha256(ROOT / "daily-vnp46a2.csv"),
            "daily_raw_jsonl_sha256": sha256(ROOT / "daily-vnp46a2-raw.jsonl"),
            "observation_package_sha256": sha256(ROOT / "observation-package.json"),
            "gee_checkpoint_sha256": sha256(ROOT / "gee-checkpoint.json"),
            "full_run_status": full_run.get("status"),
        },
        "latest_collection_image_date_utc": checkpoint.get("live_latest_image_date_utc"),
        "latest_strict_qualified_date_utc": checkpoint.get("latest_strict_qualified_date_utc"),
        "august_12": {
            "strict_mean": float(strict_12["mean"]),
            "strict_valid_count": int(float(strict_12["valid_count"])),
            "strict_total_count": int(float(strict_12["total_count"])),
            "permissive_mean": float(permissive_12["mean"]),
            "permissive_valid_count": int(float(permissive_12["valid_count"])),
            "permissive_total_count": int(float(permissive_12["total_count"])),
        },
        "august_13_to_18": later,
        "interpretation": "12 August is a newly refreshed valid observation. Products remain present through the current GEE endpoint, but 13--18 August have no retained daily value under the unchanged quality contract and remain explicit gaps; no interpolation or gap-filled band was used.",
    }
    write_json(ROOT / "qa" / "august-live-refresh.json", result)
    return result


def main() -> int:
    result = live_refresh()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
