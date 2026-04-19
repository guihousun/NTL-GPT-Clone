"""Add source traceability fields to the ConflictNTL candidate event outputs.

This script is intentionally conservative: it separates direct/official or
high-confidence reporting from lead-level search scaffolds such as GDELT and
Wikipedia. The candidate table is for downstream NTL triage, not final fact
assertions.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CSV_PATH = DOCS / "ConflictNTL_candidate_events_2026-02-27_2026-04-14.csv"
JSON_PATH = DOCS / "ConflictNTL_candidate_events_2026-02-27_2026-04-14.json"
MD_PATH = DOCS / "ConflictNTL_event_collection_2026-02-27_2026-04-14.md"

ADDED_FIELDS = [
    "primary_sources",
    "secondary_sources",
    "lead_sources",
    "source_urls",
    "source_risk",
    "verification_notes",
]


def gdelt_doc_url(query: str, start: str, end: str, maxrecords: int = 10) -> str:
    return (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={quote(query)}"
        "&mode=artlist"
        "&format=json"
        f"&maxrecords={maxrecords}"
        f"&startdatetime={start}000000"
        f"&enddatetime={end}235959"
        "&sort=date"
    )


GLOBAL_URLS = {
    "white_house_launch": "https://www.whitehouse.gov/releases/2026/03/peace-through-strength-president-trump-launches-operation-epic-fury-to-crush-iranian-regime-end-nuclear-threat/",
    "white_house_progress": "https://www.whitehouse.gov/articles/2026/03/operation-epic-fury-decisive-american-power-to-crush-irans-terror-regime/",
    "white_house_ceasefire": "https://www.whitehouse.gov/releases/2026/04/peace-through-strength-operation-epic-fury-crushes-iranian-threat-as-ceasefire-takes-hold/",
    "centcom_fact_sheet": "https://www.centcom.mil/Portals/6/Documents/Publications/260401-Fact%20Sheet.pdf?ver=ezk_KiJvld1N84sCwrTJEg%3D%3D",
    "ap_leadup": "https://apnews.com/article/6c602da7d44cb8c34fa1a9f85f352e4a",
    "time_explainer": "https://time.com/7382631/iran-israel-us-war-explainer-trump-middle-east/",
    "le_monde_geolocation": "https://www.lemonde.fr/en/international/video/2026/03/03/how-the-us-israel-strikes-unfolded-across-iran_6751062_4.html",
    "csis_nuclear": "https://www.csis.org/analysis/operation-epic-fury-and-remnants-irans-nuclear-program",
    "ap_natanz": "https://apnews.com/article/e42a12c14ec7d6b3704cbb0ea610404f",
    "gard_shipping": "https://gard.no/en/insights/escalating-israel-iran-conflict-threatens-gulf-shipping/",
    "global_security_day8": "https://www.globalsecurity.org/military/ops/iran-war-20260307.htm",
    "global_security_day20": "https://www.globalsecurity.org/military/ops/iran-war-20260319.htm",
    "soufan_apr6": "https://thesoufancenter.org/intelbrief-2026-april-6/",
    "times_india_flames": "https://timesofindia.indiatimes.com/defence/international/the-middle-east-in-flames-how-operation-epic-fury-ignited-a-regional-conflagration/amp_articleshow/129679266.cms",
    "times_india_desert": "https://timesofindia.indiatimes.com/defence/international/the-desert-is-not-neutral-how-heat-and-sand-change-weapons-in-war/articleshow/130002429.cms",
    "roan_mar19": "https://roancp.com/situation-report-epic-fury-us-iranian-conflict-as-of-march-19-2026/",
    "yahoo_haifa": "https://www.yahoo.com/news/articles/israel-says-haifa-oil-refinery-181201455.html",
    "tribune_haifa": "https://www.tribuneindia.com/news/world/iranian-missile-strikes-haifa-refinery-in-northern-israel-no-casualties-reported/",
    "all_israel_haifa": "https://allisraelnews.com/haifa-oil-refinery-deemed-time-bomb-especially-after-damage-caused-by-iranian-missile-strike",
    "jinsa_pdf": "https://jinsa.org/wp-content/uploads/2026/03/Operations-Epic-Fury-and-Roaring-Lion-03-20-26.pdf",
    "aman_sandesh_pdf": "https://theamansandeshtimes.com/wp-content/uploads/2026/03/02-March-2026-Final.pdf",
    "wiki_timeline": "https://en.wikipedia.org/wiki/Timeline_of_the_2026_Iran_war",
    "wiki_attacks": "https://en.wikipedia.org/wiki/List_of_attacks_during_the_2026_Iran_war",
}


SOURCE_MAP = {
    "CNL-2026-IRN-001": {
        "primary_sources": [
            "White House launch statement",
            "CENTCOM Operation Epic Fury fact sheet",
        ],
        "secondary_sources": [
            "Associated Press strike-order timeline",
            "Le Monde authenticated/geolocated Tehran strike footage",
            "TIME conflict explainer",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["white_house_launch"],
            GLOBAL_URLS["centcom_fact_sheet"],
            GLOBAL_URLS["ap_leadup"],
            GLOBAL_URLS["le_monde_geolocation"],
            GLOBAL_URLS["time_explainer"],
            GLOBAL_URLS["wiki_timeline"],
            gdelt_doc_url('"Operation Epic Fury" Tehran strikes', "20260228", "20260303"),
        ],
        "source_risk": "medium",
        "verification_notes": "Overall operation and Tehran strike window are supported by official and major-media sources; neighborhood-level target coordinates still need source hardening before publication-grade NTL attribution.",
    },
    "CNL-2026-IRN-002": {
        "primary_sources": [
            "CENTCOM Operation Epic Fury fact sheet",
        ],
        "secondary_sources": [
            "AP satellite-imagery report on Natanz",
            "CSIS analysis on Operation Epic Fury and Iran nuclear infrastructure",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia attack list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["centcom_fact_sheet"],
            GLOBAL_URLS["ap_natanz"],
            GLOBAL_URLS["csis_nuclear"],
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Operation Epic Fury" Natanz nuclear facility damage', "20260301", "20260305"),
        ],
        "source_risk": "medium",
        "verification_notes": "Natanz is a strong NTL candidate because facility identity is constrained, but the direct damage extent should be cross-checked against satellite imagery and IAEA-style technical updates before quantitative claims.",
    },
    "CNL-2026-GULF-003": {
        "primary_sources": [
            "CENTCOM Operation Epic Fury fact sheet",
        ],
        "secondary_sources": [
            "Gard maritime-risk briefing",
            "GlobalSecurity day-8 conflict update",
            "White House March 12 operation-status release",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia attack list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["centcom_fact_sheet"],
            GLOBAL_URLS["gard_shipping"],
            GLOBAL_URLS["global_security_day8"],
            GLOBAL_URLS["white_house_progress"],
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Operation Epic Fury" Gulf refinery desalination airport port disruption', "20260307", "20260312"),
        ],
        "source_risk": "high",
        "verification_notes": "This remains a cluster-level retrieval bucket. It should not be treated as one event; split into facility-level AOIs and attach facility-specific sources before NTL analysis.",
    },
    "CNL-2026-UAE-004": {
        "primary_sources": [],
        "secondary_sources": [
            "Times of India regional conflict report",
            "GDELT-indexed open-web leads",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia attack list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["times_india_desert"],
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Ruwais refinery" "Operation Epic Fury" drone strike shutdown', "20260309", "20260311"),
        ],
        "source_risk": "high",
        "verification_notes": "Ruwais is NTL-relevant, but current direct sourcing is weak. Require ADNOC/UAE official statement, Reuters/AP, or high-confidence incident imagery before using as a confirmed event.",
    },
    "CNL-2026-QAT-005": {
        "primary_sources": [],
        "secondary_sources": [
            "GlobalSecurity day-20 conflict update",
            "Roan Capital Partners March 19 situation report",
            "Times of India regional energy-disruption report",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["global_security_day20"],
            GLOBAL_URLS["roan_mar19"],
            GLOBAL_URLS["times_india_flames"],
            GLOBAL_URLS["wiki_timeline"],
            gdelt_doc_url('"South Pars" "Ras Laffan" "Operation Epic Fury"', "20260318", "20260320"),
        ],
        "source_risk": "medium",
        "verification_notes": "South Pars/Ras Laffan is source-rich enough for triage, but Iran-side and Qatar-side AOIs must be separated; use official QatarEnergy/Qatari ministry or Reuters/AP confirmation before damage quantification.",
    },
    "CNL-2026-ISR-006": {
        "primary_sources": [],
        "secondary_sources": [
            "Yahoo/Al Jazeera-Reuters report quoting Israeli Energy Minister",
            "Tribune/ANI report citing CNN and Israeli sources",
            "All Israel News follow-up on Bazan/Haifa refinery impact",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Social-media/video leads only where independently verified",
        ],
        "source_urls": [
            GLOBAL_URLS["yahoo_haifa"],
            GLOBAL_URLS["tribune_haifa"],
            GLOBAL_URLS["all_israel_haifa"],
            gdelt_doc_url('"Haifa oil refinery" Iran missile March 19 2026', "20260319", "20260321"),
        ],
        "source_risk": "medium",
        "verification_notes": "Multiple reports converge on a Haifa refinery impact/disruption, but severity is disputed. NTL analysis should test outage/fire-light signatures without assuming major lasting damage.",
    },
    "CNL-2026-IRN-007": {
        "primary_sources": [],
        "secondary_sources": [],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["wiki_timeline"],
            gdelt_doc_url('"Eastern Tehran" Karaj power outage substation "Operation Epic Fury"', "20260330", "20260401"),
        ],
        "source_risk": "high",
        "verification_notes": "Treat as an outage lead, not a confirmed event. Needs official grid/operator report, credible local reporting, or independent remote-sensing anomaly before promotion.",
    },
    "CNL-2026-IRN-008": {
        "primary_sources": [],
        "secondary_sources": [],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia attack list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Karaj bridge" "Mashhad airport fuel tank" Bahrain fire "Operation Epic Fury"', "20260401", "20260403"),
        ],
        "source_risk": "high",
        "verification_notes": "This is a multi-location lead cluster and should be decomposed. Each sub-claim needs independent source hardening before entering an NTL workflow.",
    },
    "CNL-2026-KWT-009": {
        "primary_sources": [],
        "secondary_sources": [
            "JINSA operations brief",
            "Aman Sandesh Times PDF lead mentioning KIPIC/Mina Al-Ahmadi",
            "Soufan Center April 6 regional energy-infrastructure note",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia attack list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["jinsa_pdf"],
            GLOBAL_URLS["aman_sandesh_pdf"],
            GLOBAL_URLS["soufan_apr6"],
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Mina Al-Ahmadi" Habshan BAPCO Kuwait desalination "Operation Epic Fury"', "20260402", "20260404"),
        ],
        "source_risk": "high",
        "verification_notes": "Facility names are NTL-relevant, but sourcing is not publication-grade. Treat as a prioritized verification bundle, not a confirmed facility-damage record.",
    },
    "CNL-2026-IRN-010": {
        "primary_sources": [],
        "secondary_sources": [
            "GDELT-indexed open-web leads",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline/attack-list scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["wiki_timeline"],
            GLOBAL_URLS["wiki_attacks"],
            gdelt_doc_url('"Mahshahr" "Bandar Imam" Bushehr Kharg Jubail "Operation Epic Fury"', "20260403", "20260405"),
        ],
        "source_risk": "high",
        "verification_notes": "This is a broad energy-chain lead. Do not combine Iranian and Saudi/Iraqi/Gulf targets in one AOI; validate each facility separately.",
    },
    "CNL-2026-IRN-011": {
        "primary_sources": [],
        "secondary_sources": [
            "GDELT-indexed open-web leads",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["wiki_timeline"],
            gdelt_doc_url('"Asaluyeh" Mehrabad "Sharif University" Baharestan "Operation Epic Fury"', "20260405", "20260407"),
        ],
        "source_risk": "high",
        "verification_notes": "Late-war urban/energy cluster remains weakly sourced and geographically heterogeneous. Promote only after target-level confirmation and geocoding.",
    },
    "CNL-2026-MAR-012": {
        "primary_sources": [
            "CENTCOM Operation Epic Fury fact sheet",
            "White House ceasefire/Hormuz statement",
        ],
        "secondary_sources": [
            "Gard maritime-risk briefing",
            "GlobalSecurity conflict updates",
        ],
        "lead_sources": [
            "GDELT DOC reproducible query",
            "Wikipedia timeline scaffold only",
        ],
        "source_urls": [
            GLOBAL_URLS["centcom_fact_sheet"],
            GLOBAL_URLS["white_house_ceasefire"],
            GLOBAL_URLS["gard_shipping"],
            GLOBAL_URLS["global_security_day8"],
            GLOBAL_URLS["wiki_timeline"],
            gdelt_doc_url('"Strait of Hormuz" shipping port fuel logistics "Operation Epic Fury"', "20260311", "20260414"),
        ],
        "source_risk": "medium",
        "verification_notes": "Use this as a monitoring window for port/fuel-logistics anomalies, not as a single strike event. AIS/shipping, port notices, and NTL should be fused before attribution.",
    },
}


def as_csv_value(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def update_csv() -> int:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        base_fields = list(f.seekable() and rows[0].keys() if rows else [])

    if not rows:
        raise RuntimeError(f"No rows found in {CSV_PATH}")

    fieldnames = [field for field in base_fields if field not in ADDED_FIELDS]
    fieldnames.extend(ADDED_FIELDS)

    for row in rows:
        source = SOURCE_MAP.get(row["event_id"])
        if source is None:
            raise KeyError(f"No source mapping for {row['event_id']}")
        for field in ADDED_FIELDS:
            row[field] = as_csv_value(source.get(field))

    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def update_json() -> int:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8-sig"))
    data["schema_version"] = "0.2"
    data["source_note"] = (
        data.get("source_note", "")
        + " Source traceability fields were added in schema 0.2; GDELT and Wikipedia are recorded as lead/scaffold sources unless independently confirmed."
    ).strip()

    records = data.get("records", [])
    for record in records:
        source = SOURCE_MAP.get(record["event_id"])
        if source is None:
            raise KeyError(f"No source mapping for {record['event_id']}")
        for field in ADDED_FIELDS:
            record[field] = source.get(field, [] if field.endswith("sources") or field == "source_urls" else "")

    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(records)


def update_markdown() -> None:
    text = MD_PATH.read_text(encoding="utf-8-sig")
    section = """## Candidate Table Traceability Update
The candidate CSV/JSON now include explicit source-trace fields:
- `primary_sources`: official, operator, or otherwise direct/high-authority sources when available.
- `secondary_sources`: major media, specialist briefings, think-tank notes, or reputable republications used for triangulation.
- `lead_sources`: reproducible search/scaffold sources such as GDELT DOC queries or Wikipedia timelines. These are not treated as confirmation by themselves.
- `source_urls`: URLs used to reproduce the retrieval path, including GDELT DOC API queries where direct reporting is still weak.
- `source_risk`: risk of using the row as a factual event without more verification. `high` means the row should remain a lead or split-cluster until hardened.
- `verification_notes`: event-specific caution for whether the record can feed NTL analysis directly or should first be decomposed/geocoded/source-hardened.

Important interpretation rule: source traceability is not the same as event confirmation. Some rows remain valuable because they are NTL-relevant leads, but weakly sourced rows must not be used as final conflict facts until a stronger source is attached.

"""
    marker = "## Candidate Table Traceability Update\n"
    next_marker = "## Daily Event Collection\n"
    if marker in text:
        start = text.index(marker)
        end = text.index(next_marker, start)
        text = text[:start] + section + text[end:]
    else:
        insert_at = text.index(next_marker)
        text = text[:insert_at] + section + text[insert_at:]
    MD_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    csv_count = update_csv()
    json_count = update_json()
    update_markdown()
    print(f"updated_csv_rows={csv_count}")
    print(f"updated_json_records={json_count}")
    print(f"csv={CSV_PATH}")
    print(f"json={JSON_PATH}")
    print(f"markdown={MD_PATH}")


if __name__ == "__main__":
    main()
