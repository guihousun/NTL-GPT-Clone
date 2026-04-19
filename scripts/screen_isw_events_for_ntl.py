"""Screen ISW event points for ConflictNTL nighttime-light relevance.

Input:
    docs/ISW_storymap_events_2026-02-27_2026-04-15.csv

Outputs:
    docs/ISW_screened_events_2026-02-27_2026-04-07.csv
    docs/ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv
    docs/ISW_screened_events_2026-02-27_2026-04-07_summary.json

The scoring rules mirror docs/ConflictNTL_event_screening_criteria.md.
They are intentionally conservative: the script ranks NTL candidates; it does
not confirm conflict facts.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INPUT_CSV = DOCS / "ISW_storymap_events_2026-02-27_2026-04-15.csv"
OUTPUT_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07.csv"
TOP_CSV = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv"
SUMMARY_JSON = DOCS / "ISW_screened_events_2026-02-27_2026-04-07_summary.json"
START_DATE = datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2026, 4, 7, 23, 59, 59, tzinfo=timezone.utc)
CEASEFIRE_EFFECTIVE_UTC = "2026-04-08T00:00:00Z"

DERIVED_FIELDS = [
    "time_quality",
    "time_score",
    "coord_quality",
    "coord_score",
    "source_count",
    "strong_source_count",
    "source_quality",
    "source_score",
    "round1_score",
    "round1_event_candidate_status",
    "round1_reason",
    "target_class",
    "ntl_relevance_level",
    "ntl_relevance_score",
    "ntl_relevance_reason",
    "final_ntl_candidate_status",
    "drop_reason",
    "needs_geocoding",
    "needs_source_hardening",
    "needs_precise_overpass_check",
    "default_viirs_transition_local",
    "recommended_next_step",
    "reason_codes",
]

APPLICABLE_NTL_KEYWORDS = {
    "energy",
    "oil",
    "gas",
    "lng",
    "refinery",
    "terminal",
    "fuel",
    "depot",
    "petrochemical",
    "power",
    "substation",
    "electric",
    "grid",
    "port",
    "airport",
    "airbase",
    "runway",
    "industrial",
    "nuclear",
    "desalination",
    "water",
    "railway",
    "transit",
    "military",
    "base",
    "naval base",
    "missile base",
    "hq",
    "radar",
    "command",
    "government",
    "political",
    "building",
    "bridge",
    "road",
    "civilian",
    "internal security",
}

UNCERTAIN_EVENT_KEYWORDS = {
    "air defense activity",
    "intercept",
    "direct engagement",
    "mortar",
    "unknown",
    "report of explosion",
}

STRONG_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "centcom.mil",
    "whitehouse.gov",
    "iaea.org",
    "bloomberg.com",
    "nytimes.com",
    "wsj.com",
    "cnn.com",
    "washingtonpost.com",
    "timesofisrael.com",
    "bellingcat.com",
    "geoconfirmed.org",
    "home.treasury.gov",
    "iranintl.com",
    "aljazeera.com",
}

REFERENCE_DOMAINS = {
    "wikimapia.org",
    "openstreetmap.org",
    "google.com",
    "maps.app.goo.gl",
    "browser.dataspace.copernicus.eu",
}

SOCIAL_DOMAINS = {
    "x.com",
    "twitter.com",
    "t.me",
    "youtube.com",
    "facebook.com",
    "instagram.com",
}


def norm(value: str | None) -> str:
    return (value or "").replace("\xa0", " ").strip()


def lower_blob(row: dict[str, str]) -> str:
    fields = [
        "event_type",
        "site_type",
        "site_subtype",
        "subject",
        "city",
        "province",
        "country",
    ]
    return " ".join(norm(row.get(field)).lower() for field in fields)


def split_sources(row: dict[str, str]) -> list[str]:
    sources: list[str] = []
    for field in ("source_1", "source_2", "sources"):
        raw = norm(row.get(field))
        if not raw:
            continue
        parts = re.split(r"\s*;\s*|\s*\|\s*", raw)
        for item in parts:
            item = item.strip()
            if item:
                sources.append(item)
    return sources


def domain_of(url: str) -> str:
    if not url.startswith("http"):
        return ""
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def score_time(row: dict[str, str]) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    if norm(row.get("event_date_utc")):
        return "event_date_available", 20, reasons
    if norm(row.get("post_date_utc")) or norm(row.get("publication_date_utc")):
        reasons.append("fallback_date_only")
        return "fallback_date_available", 10, reasons
    reasons.append("missing_date")
    return "missing_date", 0, reasons


def score_coord(row: dict[str, str]) -> tuple[str, int, list[str]]:
    reasons: list[str] = []
    coord_type = norm(row.get("coord_type")).lower()
    lat = norm(row.get("latitude"))
    lon = norm(row.get("longitude"))
    has_xy = bool(lat and lon)
    if coord_type == "exact" and has_xy:
        return "exact", 25, reasons
    if coord_type in {"general neighborhood", "pov"} and has_xy:
        reasons.append("non_exact_coordinate")
        return coord_type, 15, reasons
    if coord_type == "general town" and has_xy:
        reasons.append("town_level_coordinate")
        return "general_town", 10, reasons
    if has_xy:
        reasons.append("coordinate_precision_unknown")
        return "coordinate_precision_unknown", 8, reasons
    reasons.append("missing_coordinates")
    return "missing_coordinates", 0, reasons


def classify_target(row: dict[str, str]) -> tuple[str, str, int, list[str]]:
    blob = lower_blob(row)
    reasons: list[str] = []
    event_type = norm(row.get("event_type")).lower()
    site_type = norm(row.get("site_type")).lower()
    site_subtype = norm(row.get("site_subtype")).lower()
    subject = norm(row.get("subject")).lower()
    unknown_site = site_type in {"", "unknown", "na"} and site_subtype in {"", "unknown", "na"}
    no_fixed_target = unknown_site and not subject

    if unknown_site:
        reasons.append("ntl_uncertain_unknown_target")
        return "unknown_or_no_fixed_target", "ntl_uncertain", 5, reasons

    if any(keyword in event_type for keyword in {"air defense activity", "direct engagement", "mortar"}) and no_fixed_target:
        reasons.append("ntl_uncertain_no_fixed_ground_target")
        return "no_fixed_ground_target", "ntl_uncertain", 5, reasons

    if "report of explosion" in event_type and no_fixed_target:
        reasons.append("ntl_uncertain_explosion_without_target")
        return "explosion_without_target", "ntl_uncertain", 5, reasons

    if any(keyword in blob for keyword in APPLICABLE_NTL_KEYWORDS):
        matched = sorted(keyword for keyword in APPLICABLE_NTL_KEYWORDS if keyword in blob)
        reasons.append("ntl_applicable_fixed_or_interpretable_target:" + "|".join(matched[:5]))
        return "fixed_or_interpretable_target", "ntl_applicable", 30, reasons

    reasons.append("ntl_applicable_by_default_non_unknown_target")
    return "fixed_or_interpretable_target", "ntl_applicable", 30, reasons


def score_sources(row: dict[str, str]) -> tuple[int, int, str, int, list[str]]:
    sources = split_sources(row)
    domains = [domain_of(source) for source in sources]
    strong = sum(1 for domain in domains if domain in STRONG_DOMAINS or any(domain.endswith("." + d) for d in STRONG_DOMAINS))
    reference = sum(1 for domain in domains if domain in REFERENCE_DOMAINS)
    social = sum(1 for domain in domains if domain in SOCIAL_DOMAINS)
    reasons: list[str] = []

    if strong >= 1:
        reasons.append("strong_source_present")
        return len(sources), strong, "strong", 15, reasons
    if reference >= 1 and len(sources) >= 2:
        reasons.append("reference_plus_other_sources")
        return len(sources), strong, "reference_plus_leads", 8, reasons
    if len(sources) >= 3 and social >= 2:
        reasons.append("multiple_social_leads")
        return len(sources), strong, "social_multi_lead", 5, reasons
    if len(sources) >= 1:
        reasons.append("weak_source_lead")
        return len(sources), strong, "weak_lead", 3, reasons
    reasons.append("no_source_url")
    return 0, 0, "missing_sources", 0, reasons


def round1_status_from_scores(
    time_score: int,
    coord_score: int,
    source_score: int,
) -> tuple[int, str, dict[str, bool], str]:
    round1_score = time_score + coord_score + source_score
    needs_geocoding = coord_score < 8
    needs_source = source_score < 3

    if time_score < 10:
        status = "archive_only"
        reason = "missing_or_invalid_event_date"
    elif needs_geocoding:
        status = "needs_geocoding"
        reason = "coordinate_precision_or_coordinates_not_sufficient"
    elif needs_source:
        status = "needs_source_hardening"
        reason = "source_traceability_not_sufficient"
    elif round1_score >= 25:
        status = "event_candidate"
        reason = "time_coordinate_source_pass"
    else:
        status = "archive_only"
        reason = "round1_score_too_low"

    flags = {
        "needs_geocoding": needs_geocoding,
        "needs_source_hardening": needs_source,
    }
    return round1_score, status, flags, reason


def final_status_from_rounds(round1_status: str, ntl_level: str) -> tuple[str, str, str]:
    if round1_status != "event_candidate":
        if round1_status == "needs_geocoding":
            return "not_promoted", "round1_needs_geocoding", "improve_coordinates_before_ntl"
        if round1_status == "needs_source_hardening":
            return "not_promoted", "round1_needs_source_hardening", "find_official_or_major_media_confirmation"
        return "not_promoted", "round1_archive_only", "keep_event_record_no_ntl_task"

    if ntl_level == "ntl_applicable":
        return "promoted_to_ntl_queue", "", "generate_aoi_and_viirs_overpass_check"
    return "not_promoted", "ntl_uncertain_no_fixed_or_ground_target", "archive_or_manual_review_if_sample_needed"


def row_datetime(row: dict[str, str]) -> datetime | None:
    for field in ("event_date_utc", "post_date_utc", "publication_date_utc"):
        value = norm(row.get(field))
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def in_experiment_window(row: dict[str, str]) -> bool:
    dt_value = row_datetime(row)
    return dt_value is not None and START_DATE <= dt_value <= END_DATE


def screen_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    screened: list[dict[str, str]] = []

    for row in rows:
        reasons: list[str] = []
        time_quality, time_score, time_reasons = score_time(row)
        coord_quality, coord_score, coord_reasons = score_coord(row)
        target_class, ntl_level, ntl_score, ntl_reasons = classify_target(row)
        source_count, strong_source_count, source_quality, source_score, source_reasons = score_sources(row)

        reasons.extend(time_reasons)
        reasons.extend(coord_reasons)
        reasons.extend(source_reasons)

        round1_score, round1_status, flags, round1_reason = round1_status_from_scores(
            time_score, coord_score, source_score
        )
        final_status, drop_reason, next_step = final_status_from_rounds(round1_status, ntl_level)

        # ISW layers usually provide event dates, not precise event occurrence
        # timestamps. VIIRS image matching therefore needs per-AOI UTC_Time.
        needs_overpass_check = True
        if norm(row.get("time_raw")) and norm(row.get("time_raw")) not in {"0", "na", "NA"}:
            reasons.append("time_raw_not_used_for_event_occurrence")

        out = dict(row)
        out.update(
            {
                "time_quality": time_quality,
                "time_score": str(time_score),
                "coord_quality": coord_quality,
                "coord_score": str(coord_score),
                "target_class": target_class,
                "source_count": str(source_count),
                "strong_source_count": str(strong_source_count),
                "source_quality": source_quality,
                "source_score": str(source_score),
                "round1_score": str(round1_score),
                "round1_event_candidate_status": round1_status,
                "round1_reason": "; ".join(reasons + [round1_reason]),
                "target_class": target_class,
                "ntl_relevance_level": ntl_level,
                "ntl_relevance_score": str(ntl_score),
                "ntl_relevance_reason": "; ".join(ntl_reasons),
                "final_ntl_candidate_status": final_status,
                "drop_reason": drop_reason,
                "needs_geocoding": str(flags["needs_geocoding"]).lower(),
                "needs_source_hardening": str(flags["needs_source_hardening"]).lower(),
                "needs_precise_overpass_check": str(needs_overpass_check).lower(),
                "default_viirs_transition_local": "00:30-02:30",
                "recommended_next_step": next_step,
                "reason_codes": "; ".join(reasons),
            }
        )
        screened.append(out)

    screened.sort(
        key=lambda row: (
            0 if row["final_ntl_candidate_status"] == "promoted_to_ntl_queue" else 1,
            -int(row["round1_score"]),
            -int(row["ntl_relevance_score"]),
            row.get("event_date_utc", ""),
            row.get("country", ""),
            row.get("city", ""),
        )
    )
    return screened


def write_csv(path: Path, rows: list[dict[str, str]], base_fields: list[str]) -> None:
    fields = list(base_fields)
    for field in DERIVED_FIELDS:
        if field not in fields:
            fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    by_round1 = Counter(row["round1_event_candidate_status"] for row in rows)
    by_final = Counter(row["final_ntl_candidate_status"] for row in rows)
    round1_candidates = [
        row for row in rows if row["round1_event_candidate_status"] == "event_candidate"
    ]
    by_round2_after_round1 = Counter(row["ntl_relevance_level"] for row in round1_candidates)
    by_ntl_all_records = Counter(row["ntl_relevance_level"] for row in rows)
    by_country = Counter(row.get("country", "") for row in rows)
    top = rows[:25]
    return {
        "input": str(INPUT_CSV),
        "output": str(OUTPUT_CSV),
        "top_candidates": str(TOP_CSV),
        "date_window_utc": {
            "start": START_DATE.isoformat().replace("+00:00", "Z"),
            "end": END_DATE.isoformat().replace("+00:00", "Z"),
        },
        "ceasefire_effective_utc": CEASEFIRE_EFFECTIVE_UTC,
        "ceasefire_note": "Pakistan confirmed the ceasefire took effect at 2026-04-08 03:30 IRST, which equals 2026-04-08 00:00 UTC; therefore 2026-04-08 UTC events are excluded.",
        "aggregation_policy": "no clustering; point-level screening only",
        "total_records": len(rows),
        "round1_status_counts": dict(by_round1),
        "round2_input_records": len(round1_candidates),
        "round2_ntl_relevance_counts_after_round1": dict(by_round2_after_round1),
        "final_status_counts": dict(by_final),
        "diagnostic_ntl_relevance_counts_all_records": dict(by_ntl_all_records),
        "top_countries": by_country.most_common(20),
        "top_25": [
            {
                "round1_score": row["round1_score"],
                "round1_event_candidate_status": row["round1_event_candidate_status"],
                "ntl_relevance_level": row["ntl_relevance_level"],
                "final_ntl_candidate_status": row["final_ntl_candidate_status"],
                "event_date_utc": row.get("event_date_utc", ""),
                "country": row.get("country", ""),
                "city": row.get("city", ""),
                "event_type": row.get("event_type", ""),
                "site_type": row.get("site_type", ""),
                "site_subtype": row.get("site_subtype", ""),
                "coord_quality": row["coord_quality"],
                "source_quality": row["source_quality"],
            }
            for row in top
        ],
    }


def main() -> None:
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])

    rows = [row for row in rows if in_experiment_window(row)]
    screened = screen_rows(rows)
    top = [row for row in screened if row["final_ntl_candidate_status"] == "promoted_to_ntl_queue"]

    write_csv(OUTPUT_CSV, screened, base_fields)
    write_csv(TOP_CSV, top, base_fields)
    summary = summarize(screened)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"screened_records={len(screened)}")
    print(f"top_candidates={len(top)}")
    print(f"round1_status_counts={summary['round1_status_counts']}")
    print(f"round2_input_records={summary['round2_input_records']}")
    print(
        "round2_ntl_relevance_counts_after_round1="
        f"{summary['round2_ntl_relevance_counts_after_round1']}"
    )
    print(f"final_status_counts={summary['final_status_counts']}")
    print(
        "diagnostic_ntl_relevance_counts_all_records="
        f"{summary['diagnostic_ntl_relevance_counts_all_records']}"
    )
    print(f"output={OUTPUT_CSV}")
    print(f"top={TOP_CSV}")
    print(f"summary={SUMMARY_JSON}")


if __name__ == "__main__":
    main()
