"""Export ConflictNTL two-round screening rules as CSV and XLSX."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screening_rulebook"
OUT_XLSX = OUT_DIR / "ConflictNTL_two_round_screening_rulebook.xlsx"


SHEETS: dict[str, list[dict[str, object]]] = {
    "overview": [
        {
            "step": "Round 1",
            "name": "event candidate screening",
            "purpose": "Decide whether an ISW event point is traceable enough to enter the event-candidate pool.",
            "uses_fields": "event_date_utc; post_date_utc; publication_date_utc; latitude; longitude; coord_type; source_1; source_2; sources",
            "does_not_use": "site_type; site_subtype; nightlight relevance; remote-sensing results",
            "pass_rule": "time_score >= 10 AND coord_score >= 8 AND source_score >= 3 AND round1_score >= 25",
            "output_status": "event_candidate; needs_geocoding; needs_source_hardening; archive_only",
        },
        {
            "step": "Round 2",
            "name": "NTL relevance screening",
            "purpose": "Decide whether a traceable event has a plausible nighttime-light/thermal/industrial-light impact pathway.",
            "uses_fields": "event_type; site_type; site_subtype; subject; city; country",
            "does_not_use": "source quality as event confirmation; remote-sensing results",
            "pass_rule": "round1_event_candidate_status == event_candidate AND ntl_relevance_level == ntl_applicable",
            "output_status": "promoted_to_ntl_queue; not_promoted",
        },
    ],
    "round1_time": [
        {"condition": "event_date_utc available", "time_quality": "event_date_available", "score": 20, "meaning": "Event date is available and used as primary date."},
        {"condition": "event_date_utc missing but post_date_utc or publication_date_utc available", "time_quality": "fallback_date_available", "score": 10, "meaning": "Only fallback date is available; usable but weaker."},
        {"condition": "no parseable date", "time_quality": "missing_date", "score": 0, "meaning": "Cannot align event with imagery date."},
    ],
    "round1_coordinate": [
        {"condition": "lat/lon present and coord_type == exact", "coord_quality": "exact", "score": 25, "aoi_policy": "2 km point buffer", "meaning": "Coordinate is treated as a target/facility point and is usable for point-buffer AOI."},
        {"condition": "lat/lon present and coord_type == general neighborhood", "coord_quality": "general neighborhood", "score": 15, "aoi_policy": "2 km point buffer", "meaning": "Neighborhood-level point is accepted for the current first-pass buffer rule, but with lower spatial confidence than exact coordinates."},
        {"condition": "lat/lon present and coord_type == pov", "coord_quality": "pov", "score": 15, "aoi_policy": "smallest town/municipality/district boundary", "meaning": "Viewpoint/source perspective coordinates are not treated as target points."},
        {"condition": "lat/lon present and coord_type == general town", "coord_quality": "general_town", "score": 10, "aoi_policy": "smallest town/municipality/district boundary", "meaning": "Town-level coordinate is too coarse for point buffer."},
        {"condition": "lat/lon present but precision unknown", "coord_quality": "coordinate_precision_unknown", "score": 8, "aoi_policy": "smallest town/municipality/district boundary", "meaning": "Coordinate exists but precision is not reliable enough for automatic point buffer."},
        {"condition": "missing lat/lon", "coord_quality": "missing_coordinates", "score": 0, "aoi_policy": "geocode first; then smallest town/municipality/district if only place name is available", "meaning": "Cannot run spatial analysis until a place or coordinate is resolved."},
    ],
    "round1_source": [
        {"condition": "at least one strong source domain", "source_quality": "strong", "score": 15, "meaning": "Traceable candidate source present.", "examples": "Reuters; AP; BBC; CENTCOM; White House; IAEA; Bloomberg; NYTimes; WSJ; CNN; Bellingcat; GeoConfirmed"},
        {"condition": "reference/map source plus at least one other source", "source_quality": "reference_plus_leads", "score": 8, "meaning": "Good for geocoding/facility identity; event semantics may still need confirmation.", "examples": "Wikimapia/OpenStreetMap/Google Maps plus other source links"},
        {"condition": "three or more sources and at least two social/messaging sources", "source_quality": "social_multi_lead", "score": 5, "meaning": "Multiple leads, but not enough for conservative main sample.", "examples": "multiple X/Twitter and Telegram links"},
        {"condition": "at least one weak source link", "source_quality": "weak_lead", "score": 3, "meaning": "Minimum traceable lead. It can pass Round 1 under the current fast experiment rule, but should be hardened before paper-level case writing.", "examples": "single X/Twitter; Telegram; YouTube; local uncorroborated source"},
        {"condition": "no usable source URL", "source_quality": "missing_sources", "score": 0, "meaning": "Cannot support event traceability.", "examples": "empty or unparseable source fields"},
    ],
    "round1_status": [
        {"status": "event_candidate", "rule": "time_score >= 10 AND coord_score >= 8 AND source_score >= 3 AND round1_score >= 25", "next_step": "Run Round 2 NTL relevance screening."},
        {"status": "needs_geocoding", "rule": "time_score >= 10 AND coord_score < 8", "next_step": "Improve coordinates or use admin boundary before NTL."},
        {"status": "needs_source_hardening", "rule": "time_score >= 10 AND coord_score >= 8 AND source_score < 3", "next_step": "Find at least one usable source link or source trace."},
        {"status": "archive_only", "rule": "time_score == 0 OR round1_score too low", "next_step": "Keep record but do not run NTL."},
    ],
    "round2_ntl_parameters": [
        {"parameter": "direct_light_dependency", "question": "Does the target normally emit stable nighttime light?", "positive_examples": "refinery; LNG plant; port; airport; industrial zone", "effect": "Supports ntl_applicable."},
        {"parameter": "power_or_grid_pathway", "question": "Could the event affect electricity supply or urban lighting?", "positive_examples": "power plant; substation; grid node", "effect": "Supports ntl_applicable."},
        {"parameter": "thermal_or_fire_pathway", "question": "Could the event create fire, flaring, explosion heat or thermal anomaly?", "positive_examples": "fuel depot; refinery fire; fuel tank explosion", "effect": "Supports ntl_applicable and FIRMS cross-check."},
        {"parameter": "transport_logistics_pathway", "question": "Could the event affect illuminated logistics/transport activity?", "positive_examples": "port; airport; runway; railway terminal", "effect": "Supports ntl_applicable."},
        {"parameter": "facility_scale", "question": "Is the target large enough relative to VIIRS pixel size?", "positive_examples": "large facility or complex", "effect": "Improves expected observability but is not used as a separate label."},
        {"parameter": "urban_background_complexity", "question": "Is the target in a bright city background?", "positive_examples": "dense Tehran urban target", "effect": "May require tighter AOI/control design."},
        {"parameter": "impact_duration", "question": "Would the effect persist until VIIRS overpass?", "positive_examples": "persistent outage/fire/shutdown", "effect": "Improves expected observability."},
        {"parameter": "location_precision", "question": "Is location precise enough to build a small AOI?", "positive_examples": "exact facility point", "effect": "Determines whether point buffers or admin AOI should be used."},
    ],
    "round2_ntl_levels": [
        {"ntl_relevance_level": "ntl_applicable", "score_range": "30", "definition": "Event has a fixed or interpretable target and is not explicitly an unknown/no-ground-impact case. It can enter the first-pass NTL workflow after Round 1.", "examples": "energy/oil/gas/refinery; power/substation; port/airport/airbase; industrial/nuclear; military/government/civilian/internal-security facility; fixed bridge/road/building target"},
        {"ntl_relevance_level": "ntl_uncertain", "score_range": "5", "definition": "Unknown target, no fixed target, interception/air-defense activity without ground impact, or engagement/explosion report without identifiable target.", "examples": "unknown target; unlocated explosion; air-defense/interception without ground damage; direct engagement without fixed target"},
    ],
    "final_status": [
        {"final_ntl_candidate_status": "promoted_to_ntl_queue", "rule": "round1_event_candidate_status == event_candidate AND ntl_relevance_level == ntl_applicable", "meaning": "Generate AOI and VIIRS overpass check."},
        {"final_ntl_candidate_status": "not_promoted", "rule": "round1 failed OR ntl_relevance_level == ntl_uncertain", "meaning": "Do not run first-pass NTL; keep as archive or review item."},
    ],
    "weak_source_definition": [
        {"weak_source_type": "single X/Twitter post", "why_weak": "May be unverified, duplicated, deleted, misdated or mislocated.", "use": "Minimum Round 1 lead only; harden before paper-level case writing."},
        {"weak_source_type": "Telegram post", "why_weak": "Often fast but anonymous/partisan/hard to archive.", "use": "Cross-check with media/official/ISW."},
        {"weak_source_type": "YouTube/social video", "why_weak": "Visual evidence but timing/location may be uncertain.", "use": "Use if geolocated and archived; otherwise lead only."},
        {"weak_source_type": "Wikipedia timeline", "why_weak": "Editable secondary chronology.", "use": "Scaffold only."},
        {"weak_source_type": "GDELT hit", "why_weak": "Search/index result, not event confirmation.", "use": "Use to find article URLs."},
        {"weak_source_type": "map-only source", "why_weak": "Confirms facility location but not event occurrence.", "use": "AOI/geocoding only."},
        {"weak_source_type": "single local outlet without corroboration", "why_weak": "May be correct but fragile for international paper claims.", "use": "Minimum Round 1 lead only; harden before paper-level case writing."},
    ],
}


def write_csvs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sheet_name, rows in SHEETS.items():
        path = OUT_DIR / f"{sheet_name}.csv"
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def write_xlsx() -> None:
    target = OUT_XLSX
    try:
        handle = target.open("ab")
        handle.close()
    except PermissionError:
        target = OUT_DIR / "ConflictNTL_two_round_screening_rulebook_v2.xlsx"

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, rows in SHEETS.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name[:31], index=False)
    print(f"xlsx={target}")


def main() -> None:
    write_csvs()
    write_xlsx()
    print(f"output_dir={OUT_DIR}")
    print(f"sheets={len(SHEETS)}")


if __name__ == "__main__":
    main()
