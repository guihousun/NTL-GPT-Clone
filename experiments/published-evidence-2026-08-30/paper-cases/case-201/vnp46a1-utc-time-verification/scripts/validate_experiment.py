"""Validate the source-backed UTC_Time evidence package and immutability boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

import h5py


ROOT = Path(__file__).resolve().parents[1]
Q18 = ROOT.parent / "paper-case-multiagent-2026-08-13" / "Q18-myanmar-earthquake" / "formal-25km-50km-20260817"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    source = json.loads((ROOT / "source" / "source-manifest.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "results" / "utc-time-analysis.json").read_text(encoding="utf-8"))
    formal = json.loads((Q18 / "formal-q18-validation.json").read_text(encoding="utf-8"))
    h5_path = ROOT / "source" / source["download"]["path"]
    event = datetime(2025, 3, 28, 6, 20, 52, tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Yangon")).isoformat()
    with h5py.File(h5_path, "r") as handle:
        dataset = handle["HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/UTC_Time"]
        field_metadata = {
            "long_name": dataset.attrs["long_name"].decode("utf-8"),
            "units": dataset.attrs["units"].decode("utf-8"),
            "valid_min": int(dataset.attrs["valid_min"][0]),
            "valid_max": int(dataset.attrs["valid_max"][0]),
        }
    event_pixel = result.get("event_pixel", {})
    buffer_summaries = result.get("buffer_summaries", [])
    checks = {
        "cmr_target_identity": source.get("target_granule_id") == "VNP46A1.A2025087.h27v06.002.2025088113623.h5",
        "cmr_selected_target": source.get("cmr", {}).get("selected", {}).get("producer_granule_id") == "VNP46A1.A2025087.h27v06.002.2025088113623.h5",
        "official_hdf5_identity": source.get("status") == "official_hdf5_ready" and h5_path.is_file() and sha256(h5_path) == source.get("download", {}).get("sha256"),
        "hdf5_signature_valid": source.get("download", {}).get("hdf5_signature_valid") is True,
        "event_timezone_conversion": result.get("event", {}).get("event_time_local") == event,
        "official_utc_time_metadata": field_metadata == {"long_name": "View Time (UTC)", "units": "decimal hours", "valid_min": 0, "valid_max": 24},
        "event_pixel_post_event_local_night": event_pixel.get("valid") is True and event_pixel.get("observation_time_local", "").startswith("2025-03-29T") and result.get("interpretation", {}).get("event_pixel_is_post_event") is True,
        "buffer_supports_local_2025_03_29": len(buffer_summaries) == 2 and all(row.get("n", 0) > 0 and row.get("local_date_counts") == {"2025-03-29": row.get("n")} for row in buffer_summaries),
        "vnp46a2_csv_unchanged": sha256(Q18 / "formal-q18-analysis-ready.csv") == formal["artifact_hashes"]["formal-q18-analysis-ready.csv"],
        "vnp46a2_package_unchanged": sha256(Q18 / "formal-observation-package.json") == formal["artifact_hashes"]["formal-observation-package.json"],
        "no_system_time_inference": "system:time_start" not in (ROOT / "results" / "utc-time-analysis.json").read_text(encoding="utf-8").lower(),
    }
    payload = {"schema_version": "ntl.q18.vnp46a1-utc-time-validation.v1", "checks": checks, "passed": all(checks.values())}
    destination = ROOT / "validation" / "engineer-validation.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
