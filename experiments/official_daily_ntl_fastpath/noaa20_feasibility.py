from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cmr_client import GranuleRecord, extract_download_link, search_granules, select_latest_day_entries


def _filter_night(granules: list[GranuleRecord]) -> list[GranuleRecord]:
    out: list[GranuleRecord] = []
    for granule in granules:
        if str(granule.day_night_flag or "").upper() == "NIGHT":
            out.append(granule)
    return out


def evaluate_noaa20_feasibility(
    short_name: str,
    bbox: tuple[float, float, float, float],
    start_date: str,
    end_date: str,
    workspace: Path,
    token_present: bool,
    night_only: bool = True,
) -> dict[str, Any]:
    granules = search_granules(
        short_name=short_name,
        start_date=start_date,
        end_date=end_date,
        bbox=bbox,
        page_size=200,
    )
    effective = _filter_night(granules) if night_only else granules
    latest_day, latest_entries = select_latest_day_entries(effective, night_only=night_only)

    sample_link = None
    if latest_entries:
        sample_link = extract_download_link(latest_entries[0].links)

    if short_name.startswith("VJ102DNB"):
        compatibility = {
            "existing_tool": "Noaa20_VIIRS_Preprocess",
            "directly_compatible": False,
            "reason": (
                "Current preprocess tool expects VIIRS DNB SDR-like HDF5 structure, "
                "while VJ102DNB from CMR is L1B netCDF swath product and needs adapter logic."
            ),
        }
    else:
        compatibility = {
            "existing_tool": None,
            "directly_compatible": None,
            "reason": "Feasibility-only source in this round; metadata chain verified, clipping adapter pending.",
        }

    payload = {
        "source": short_name,
        "status": "ok" if latest_day else "no_granules",
        "latest_available_date": latest_day,
        "latest_night_date": latest_day,
        "night_granule_count": len(effective),
        "token_present": bool(token_present),
        "sample_download_link": sample_link,
        "compatibility": compatibility,
    }

    out_dir = workspace / "outputs" / short_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "feasibility.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["feasibility_path"] = str(out_path)
    return payload
