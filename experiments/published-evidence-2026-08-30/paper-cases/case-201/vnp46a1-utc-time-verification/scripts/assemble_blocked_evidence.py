"""Write honest no-HDF5 result records without inventing UTC_Time statistics."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
Q18 = ROOT.parent / "paper-case-multiagent-2026-08-13" / "Q18-myanmar-earthquake" / "formal-25km-50km-20260817"
EVENT_UTC = datetime(2025, 3, 28, 6, 20, 52, tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    source = json.loads((ROOT / "source" / "source-manifest.json").read_text(encoding="utf-8"))
    probe = json.loads((ROOT / "source" / "access-probe.json").read_text(encoding="utf-8"))
    formal_validation = json.loads((Q18 / "formal-q18-validation.json").read_text(encoding="utf-8"))
    local = EVENT_UTC.astimezone(ZoneInfo("Asia/Yangon"))
    output = {
        "schema_version": "ntl.q18.vnp46a1-utc-time-analysis.v1",
        "status": "blocked_official_hdf5_not_available",
        "target_granule_id": source["target_granule_id"],
        "utc_product_date": source["utc_product_date"],
        "event": {
            "event_time_utc": EVENT_UTC.isoformat().replace("+00:00", "Z"),
            "event_time_local": local.isoformat(),
            "timezone": "Asia/Yangon",
        },
        "source_access": {
            "cmr_selected": source.get("cmr", {}).get("selected"),
            "download_manifest_status": source["status"],
            "http_download_probe": probe.get("official_hdf5_download_probe"),
            "opendap_metadata_probe": probe.get("opendap_metadata_probe"),
        },
        "utc_time_metadata": {
            "field_read_from_hdf5": False,
            "official_definition_verified_from_source_hdf5": False,
            "reason": "The selected official HDF5 could not be materialized; no HDF5 attribute, fill value, scale, or observation time is inferred from CMR or system timestamps.",
        },
        "event_pixel": {
            "utc_time_decimal_hour": None,
            "observation_time_utc": None,
            "observation_time_local": None,
            "reason": "not computed without the official HDF5 UTC_Time field",
        },
        "buffer_summaries": [
            {"radius_km": 25, "n": 0, "min_utc_hour": None, "median_utc_hour": None, "mean_utc_hour": None, "max_utc_hour": None, "status": "not_computed_source_unavailable"},
            {"radius_km": 50, "n": 0, "min_utc_hour": None, "median_utc_hour": None, "mean_utc_hour": None, "max_utc_hour": None, "status": "not_computed_source_unavailable"},
        ],
        "formal_vnp46a2_immutability": {
            "formal-q18-analysis-ready.csv": sha256(Q18 / "formal-q18-analysis-ready.csv"),
            "formal-observation-package.json": sha256(Q18 / "formal-observation-package.json"),
            "matches_formal_validation": {
                "analysis_csv": sha256(Q18 / "formal-q18-analysis-ready.csv") == formal_validation["artifact_hashes"]["formal-q18-analysis-ready.csv"],
                "observation_package": sha256(Q18 / "formal-observation-package.json") == formal_validation["artifact_hashes"]["formal-observation-package.json"],
            },
        },
        "conclusion": "The event converts to 12:50:52 on 28 March 2025 in Asia/Yangon, but the exact VNP46A1 UTC_Time evidence is unavailable. Do not revise Q18/Section 5.2 to claim pixel-level confirmation of the first post-event local night.",
    }
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    (results / "utc-time-analysis.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (results / "utc-time-summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["radius_km", "n", "min_utc_hour", "median_utc_hour", "mean_utc_hour", "max_utc_hour", "status"])
        writer.writeheader()
        for row in output["buffer_summaries"]:
            writer.writerow(row)


if __name__ == "__main__":
    main()
