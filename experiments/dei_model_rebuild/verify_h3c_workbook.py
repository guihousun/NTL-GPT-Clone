"""Compare the DEI workbook with the live official H3C JSONP endpoint.

The workbook is read directly from its OOXML ZIP members with the Python
standard library.  It is never modified.  The H3C endpoint is a mutable live
surface, so this script reports current observations and can compare them with
the committed 2026-08-08 verification record; it does not turn the API into a
frozen data archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Read the supplied DEI workbook without mutation and compare every city-score pair with the live official H3C API.",
    "input_manifest": [
        {
            "kind": "xlsx_label_workbook",
            "path": "CLI workbook argument",
            "required": True,
        },
        {
            "kind": "live_official_jsonp_api",
            "path": "https://deindex.h3c.com/API/AllCityOneInfo.ashx",
            "required": True,
        },
    ],
    "method_steps": [
        "verify the workbook SHA-256",
        "read Sheet1 OOXML cells without writing the workbook",
        "normalize repeated headers and leading numeric rank-change prefixes",
        "fetch each 2017-2024 official H3C edition",
        "compare city sets and numeric scores exactly",
    ],
    "parameters": {
        "years": [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
        "expected_workbook_sha256": "6C7ABE1A06917FBF9BEEE26C7462ED00557EA038A5374DFC0EDA9BEB240AB753",
    },
    "output_manifest": [
        {
            "kind": "live_comparison_json",
            "path": "stdout",
            "required": True,
        }
    ],
    "validation_checks": [
        "workbook checksum",
        "duplicate normalized city names",
        "missing and extra cities",
        "numeric score mismatches",
    ],
    "failure_gates": [
        "workbook checksum mismatch",
        "unreadable OOXML",
        "official API request or JSONP parse failure",
        "any city-set or score mismatch when --require-exact is used",
    ],
    "execution": {
        "mode": "local_with_explicit_network_read",
        "timeout_seconds": 120,
        "overwrite_policy": "stdout only; source workbook is read-only",
        "network_scope": [
            {
                "scheme": "https",
                "host": "deindex.h3c.com",
                "path": "/API/AllCityOneInfo.ashx",
                "method": "GET",
            }
        ],
        "test_strategy": "offline OOXML count test plus explicit live endpoint comparison",
    },
}


EXPECTED_SHA256 = "6C7ABE1A06917FBF9BEEE26C7462ED00557EA038A5374DFC0EDA9BEB240AB753"
COLUMN_PAIRS = {
    2024: ("A", "B"),
    2023: ("D", "E"),
    2022: ("F", "G"),
    2021: ("H", "I"),
    2020: ("J", "K"),
    2019: ("L", "M"),
    2018: ("N", "O"),
    2017: ("P", "Q"),
}
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{XML_NS}t"))
        for item in root.findall(f"{XML_NS}si")
    ]


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    sheet = workbook.find(f"{XML_NS}sheets/{XML_NS}sheet")
    if sheet is None:
        raise ValueError("workbook contains no worksheets")
    relationship_id = sheet.attrib.get(f"{REL_NS}id")
    relationships = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    for relationship in relationships.findall(f"{PACKAGE_REL_NS}Relationship"):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].replace("\\", "/")
            if target.startswith("/"):
                return target.lstrip("/")
            if target.startswith("xl/"):
                return target
            return "xl/" + target.lstrip("./")
    raise ValueError("first worksheet relationship is missing")


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{XML_NS}t"))
    value = cell.find(f"{XML_NS}v")
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        return shared[int(value.text)]
    if cell_type == "b":
        return "1" if value.text == "1" else "0"
    return value.text


def read_workbook_pairs(path: Path) -> dict[int, dict[str, float]]:
    """Return normalized city-score pairs per workbook edition year."""

    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet = ElementTree.fromstring(archive.read(_first_sheet_path(archive)))
    cells: dict[tuple[int, str], str] = {}
    for cell in sheet.iter(f"{XML_NS}c"):
        reference = cell.attrib.get("r", "")
        matched = re.fullmatch(r"([A-Z]+)([0-9]+)", reference)
        if not matched:
            continue
        value = _cell_text(cell, shared)
        if value is not None:
            cells[(int(matched.group(2)), matched.group(1))] = value

    maximum_row = max((row for row, _ in cells), default=0)
    results: dict[int, dict[str, float]] = {}
    for year, (city_column, score_column) in COLUMN_PAIRS.items():
        pairs: dict[str, float] = {}
        for row in range(2, maximum_row + 1):
            raw_city = cells.get((row, city_column))
            raw_score = cells.get((row, score_column))
            if raw_city is None or raw_score is None:
                continue
            if raw_city.strip() in {"城市", "City"}:
                continue
            city = re.sub(r"^\d+", "", raw_city.strip())
            if not city:
                continue
            try:
                score = float(raw_score)
            except ValueError:
                continue
            if not score == score or score in (float("inf"), float("-inf")):
                continue
            if city in pairs:
                raise ValueError(f"{year}: duplicate normalized workbook city {city}")
            pairs[city] = score
        results[year] = pairs
    return results


def fetch_official_pairs(year: int, timeout: float) -> tuple[dict[str, float], str]:
    query = urllib.parse.urlencode({"IndexYear": year, "callback": "cb"})
    url = "https://deindex.h3c.com/API/AllCityOneInfo.ashx?" + query
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NTL-GPT-DEI-provenance-audit/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8-sig").strip()
    matched = re.fullmatch(r"cb\((.*)\);?", body, flags=re.DOTALL)
    if not matched:
        raise ValueError(f"{year}: official endpoint did not return expected cb(...) JSONP")
    payload = json.loads(matched.group(1))
    info = payload.get("info")
    if not isinstance(info, list):
        raise ValueError(f"{year}: official payload has no info list")
    pairs: dict[str, float] = {}
    for item in info:
        city = str(item["city"]).strip()
        score = float(item["total"])
        if city in pairs:
            raise ValueError(f"{year}: duplicate official city {city}")
        pairs[city] = score
    return pairs, url


def compare(
    workbook_pairs: dict[int, dict[str, float]], *, timeout: float
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for year in sorted(COLUMN_PAIRS):
        local = workbook_pairs[year]
        official, url = fetch_official_pairs(year, timeout)
        missing = sorted(set(official) - set(local))
        extra = sorted(set(local) - set(official))
        mismatches = [
            {"city": city, "workbook": local[city], "official": official[city]}
            for city in sorted(set(local) & set(official))
            if abs(local[city] - official[city]) > 1e-12
        ]
        results.append(
            {
                "year": year,
                "workbook_count": len(local),
                "official_count": len(official),
                "missing_from_workbook": missing,
                "extra_in_workbook": extra,
                "value_mismatches": mismatches,
                "exact_pair_match": not missing and not extra and not mismatches,
                "source_url": url,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--require-exact", action="store_true")
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()

    actual_hash = sha256_file(args.workbook)
    if actual_hash != args.expected_sha256.upper():
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "workbook SHA-256 mismatch",
                    "expected": args.expected_sha256.upper(),
                    "actual": actual_hash,
                },
                indent=2,
            )
        )
        return 2
    try:
        results = compare(read_workbook_pairs(args.workbook), timeout=args.timeout)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        return 3
    exact = all(result["exact_pair_match"] for result in results)
    print(
        json.dumps(
            {
                "status": "pass" if exact else "mismatch",
                "workbook_sha256": actual_hash,
                "api_is_live_mutable_surface": True,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.require_exact and not exact:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
