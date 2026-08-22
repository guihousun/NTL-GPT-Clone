"""Normalize the supplied H3C city DEI workbook into deterministic CSV assets.

The source workbook is read directly from OOXML members with the Python
standard library and is never modified.  Column headings are interpreted as
the actual DEI years 2017--2024; no temporal shifting or imputation is applied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": (
        "Read the supplied H3C DEI workbook without mutation and emit "
        "validated long-form 2017-2024 city-year labels and a city inventory."
    ),
    "input_manifest": [
        {
            "kind": "xlsx_label_workbook",
            "path": "D:/NTL-GPT-main/base_data/dei_2017-2023.xlsx",
            "required": True,
            "sha256": "6C7ABE1A06917FBF9BEEE26C7462ED00557EA038A5374DFC0EDA9BEB240AB753",
        }
    ],
    "method_steps": [
        "verify the immutable source workbook SHA-256",
        "read the first worksheet directly from OOXML ZIP members",
        "treat column headings 2017-2024 as the actual DEI years without shifting",
        "skip exact repeated table-header rows embedded in the worksheet",
        "strip workbook rank prefixes and conservatively normalize Unicode city names",
        "reject empty, duplicate, non-finite, or out-of-range city-year labels",
        "write deterministic UTF-8-SIG long-form labels and city inventory CSV files",
    ],
    "parameters": {
        "years": [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
        "year_semantics": "actual DEI year from workbook header; no shift",
        "expected_row_count": 1474,
        "expected_year_counts": {
            "2017": 40,
            "2018": 100,
            "2019": 113,
            "2020": 220,
            "2021": 242,
            "2022": 242,
            "2023": 257,
            "2024": 260,
        },
        "city_normalization": (
            "Unicode NFKC, trim outer whitespace, remove leading numeric rank "
            "prefix, remove remaining Unicode whitespace, and casefold"
        ),
    },
    "output_manifest": [
        {
            "kind": "long_form_dei_labels_csv",
            "path": "data/dei_labels_2017_2024.csv",
            "required": True,
            "encoding": "UTF-8-SIG",
        },
        {
            "kind": "city_inventory_csv",
            "path": "data/dei_city_inventory.csv",
            "required": True,
            "encoding": "UTF-8-SIG",
        },
    ],
    "validation_checks": [
        "source workbook checksum and year headers",
        "exact total and per-year row counts",
        "non-empty conservative normalized city name",
        "unique (Year, CityNormalized) keys",
        "finite DEI in the inclusive range 0-100",
        "inventory observation counts reconcile with the long-form labels",
    ],
    "failure_gates": [
        "workbook checksum mismatch",
        "unreadable or structurally unexpected OOXML",
        "unpaired city or DEI worksheet cell",
        "unexpected year header or sample count",
        "empty or colliding normalized city name",
        "non-numeric, non-finite, or out-of-range DEI",
    ],
    "execution": {
        "mode": "local",
        "timeout_seconds": 120,
        "overwrite_policy": "replace deterministic derived CSV outputs only",
        "network_scope": [],
        "test_strategy": (
            "unit tests plus actual-workbook integration checks for counts, keys, "
            "ranges, determinism, and observed Jiangsu coverage"
        ),
    },
}


ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = ROOT.parents[1] / "base_data" / "dei_2017-2023.xlsx"
DEFAULT_LABELS = ROOT / "data" / "dei_labels_2017_2024.csv"
DEFAULT_INVENTORY = ROOT / "data" / "dei_city_inventory.csv"
EXPECTED_SHA256 = "6C7ABE1A06917FBF9BEEE26C7462ED00557EA038A5374DFC0EDA9BEB240AB753"
EXPECTED_YEAR_COUNTS = {
    2017: 40,
    2018: 100,
    2019: 113,
    2020: 220,
    2021: 242,
    2022: 242,
    2023: 257,
    2024: 260,
}
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


class LabelIntegrityError(ValueError):
    """Raised when the source workbook cannot produce trustworthy labels."""


@dataclass(frozen=True)
class LabelRecord:
    year: int
    city: str
    city_normalized: str
    dei: Decimal


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
        raise LabelIntegrityError("workbook contains no worksheets")
    relationship_id = sheet.attrib.get(f"{REL_NS}id")
    relationships = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    for relationship in relationships.findall(f"{PACKAGE_REL_NS}Relationship"):
        if relationship.attrib.get("Id") != relationship_id:
            continue
        target = relationship.attrib["Target"].replace("\\", "/")
        if target.startswith("/"):
            return target.lstrip("/")
        if target.startswith("xl/"):
            return target
        return "xl/" + target.lstrip("./")
    raise LabelIntegrityError("first worksheet relationship is missing")


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


def _read_cells(path: Path) -> dict[tuple[int, str], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            shared = _shared_strings(archive)
            sheet = ElementTree.fromstring(
                archive.read(_first_sheet_path(archive))
            )
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise LabelIntegrityError(f"unreadable OOXML workbook: {exc}") from exc

    cells: dict[tuple[int, str], str] = {}
    for cell in sheet.iter(f"{XML_NS}c"):
        reference = cell.attrib.get("r", "")
        matched = re.fullmatch(r"([A-Z]+)([0-9]+)", reference)
        if matched is None:
            continue
        value = _cell_text(cell, shared)
        if value is not None:
            cells[(int(matched.group(2)), matched.group(1))] = value
    return cells


def clean_city_name(raw_city: str) -> str:
    """Remove workbook rank metadata while preserving the source place name."""

    value = unicodedata.normalize("NFKC", str(raw_city)).strip()
    value = re.sub(r"^\d+\s*", "", value)
    value = "".join(value.split())
    return value


def normalize_city_name(city: str) -> str:
    """Return a conservative, deterministic matching key for a city name."""

    return clean_city_name(city).casefold()


def _parse_dei(raw_value: str, *, year: int, row: int) -> Decimal:
    try:
        value = Decimal(str(raw_value).strip())
    except InvalidOperation as exc:
        raise LabelIntegrityError(
            f"{year} row {row}: DEI is not numeric: {raw_value!r}"
        ) from exc
    if not value.is_finite():
        raise LabelIntegrityError(f"{year} row {row}: DEI must be finite")
    if not Decimal("0") <= value <= Decimal("100"):
        raise LabelIntegrityError(
            f"{year} row {row}: DEI {value} is outside 0-100"
        )
    return value


def read_labels(path: Path, *, expected_sha256: str = EXPECTED_SHA256) -> list[LabelRecord]:
    actual_hash = sha256_file(path)
    if expected_sha256 and actual_hash != expected_sha256.upper():
        raise LabelIntegrityError(
            "workbook SHA-256 mismatch: "
            f"expected {expected_sha256.upper()}, found {actual_hash}"
        )

    cells = _read_cells(path)
    maximum_row = max((row for row, _ in cells), default=0)
    records: list[LabelRecord] = []
    seen: dict[tuple[int, str], int] = {}

    for year, (city_column, score_column) in sorted(COLUMN_PAIRS.items()):
        city_header = unicodedata.normalize("NFKC", cells.get((1, city_column), "")).strip()
        year_header = unicodedata.normalize("NFKC", cells.get((1, score_column), "")).strip()
        if city_header not in {"城市", "City"} or year_header != str(year):
            raise LabelIntegrityError(
                f"unexpected headers for {year}: {city_header!r}, {year_header!r}"
            )

        for row in range(2, maximum_row + 1):
            raw_city = cells.get((row, city_column))
            raw_score = cells.get((row, score_column))
            if raw_city is None and raw_score is None:
                continue
            if raw_city is None or raw_score is None:
                raise LabelIntegrityError(
                    f"{year} row {row}: city and DEI cells must be paired"
                )
            city_cell = unicodedata.normalize("NFKC", raw_city).strip()
            score_cell = unicodedata.normalize("NFKC", raw_score).strip()
            if city_cell in {"城市", "City"}:
                if score_cell in {"总分", "DEI", str(year)}:
                    continue
                raise LabelIntegrityError(
                    f"{year} row {row}: malformed repeated header: "
                    f"{city_cell!r}, {score_cell!r}"
                )

            city = clean_city_name(raw_city)
            normalized = normalize_city_name(city)
            if not city or not normalized:
                raise LabelIntegrityError(f"{year} row {row}: city is empty after normalization")
            key = (year, normalized)
            if key in seen:
                raise LabelIntegrityError(
                    f"{year} row {row}: duplicate normalized city {normalized!r}; "
                    f"first seen at row {seen[key]}"
                )
            seen[key] = row
            records.append(
                LabelRecord(
                    year=year,
                    city=city,
                    city_normalized=normalized,
                    dei=_parse_dei(raw_score, year=year, row=row),
                )
            )

    records.sort(key=lambda item: (item.year, item.city_normalized, item.city))
    validate_labels(records)
    return records


def validate_labels(records: list[LabelRecord]) -> None:
    counts = {year: 0 for year in EXPECTED_YEAR_COUNTS}
    seen: set[tuple[int, str]] = set()
    for record in records:
        if record.year not in counts:
            raise LabelIntegrityError(f"unexpected year: {record.year}")
        if not record.city or not record.city_normalized:
            raise LabelIntegrityError("empty city name in normalized records")
        key = (record.year, record.city_normalized)
        if key in seen:
            raise LabelIntegrityError(f"duplicate normalized city-year key: {key}")
        seen.add(key)
        if not record.dei.is_finite() or not Decimal("0") <= record.dei <= Decimal("100"):
            raise LabelIntegrityError(f"invalid DEI for {key}: {record.dei}")
        counts[record.year] += 1
    if counts != EXPECTED_YEAR_COUNTS:
        raise LabelIntegrityError(
            f"unexpected year counts: expected {EXPECTED_YEAR_COUNTS}, found {counts}"
        )
    if len(records) != sum(EXPECTED_YEAR_COUNTS.values()):
        raise LabelIntegrityError(
            f"unexpected total row count: {len(records)}"
        )


def _decimal_text(value: Decimal) -> str:
    if value == value.to_integral():
        return format(value.quantize(Decimal("1")), "f")
    return format(value.normalize(), "f")


def _write_labels(path: Path, records: list[LabelRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Year", "City", "CityNormalized", "DEI"],
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "Year": record.year,
                    "City": record.city,
                    "CityNormalized": record.city_normalized,
                    "DEI": _decimal_text(record.dei),
                }
            )


def _inventory_rows(records: list[LabelRecord]) -> list[dict[str, str | int]]:
    by_name: dict[str, list[LabelRecord]] = {}
    for record in records:
        by_name.setdefault(record.city_normalized, []).append(record)
    all_years = sorted(EXPECTED_YEAR_COUNTS)
    rows: list[dict[str, str | int]] = []
    for normalized, observations in sorted(by_name.items()):
        variants = sorted({item.city for item in observations})
        years = sorted({item.year for item in observations})
        missing = [year for year in all_years if year not in years]
        rows.append(
            {
                "CityNormalized": normalized,
                "City": variants[0],
                "SourceNameVariants": "|".join(variants),
                "YearsObserved": "|".join(map(str, years)),
                "MissingYears": "|".join(map(str, missing)),
                "FirstYear": years[0],
                "LastYear": years[-1],
                "ObservationCount": len(observations),
            }
        )
    if sum(int(row["ObservationCount"]) for row in rows) != len(records):
        raise LabelIntegrityError("city inventory does not reconcile with label rows")
    return rows


def _write_inventory(path: Path, records: list[LabelRecord]) -> None:
    rows = _inventory_rows(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "CityNormalized",
        "City",
        "SourceNameVariants",
        "YearsObserved",
        "MissingYears",
        "FirstYear",
        "LastYear",
        "ObservationCount",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(
    workbook: Path,
    labels_output: Path,
    inventory_output: Path,
    *,
    expected_sha256: str = EXPECTED_SHA256,
) -> dict[str, object]:
    records = read_labels(workbook, expected_sha256=expected_sha256)
    _write_labels(labels_output, records)
    _write_inventory(inventory_output, records)
    year_counts = {
        str(year): sum(record.year == year for record in records)
        for year in sorted(EXPECTED_YEAR_COUNTS)
    }
    return {
        "status": "passed",
        "year_semantics": "actual DEI year from workbook header; no shift",
        "source": str(workbook.resolve()),
        "source_sha256": sha256_file(workbook),
        "row_count": len(records),
        "year_counts": year_counts,
        "unique_city_count": len({record.city_normalized for record in records}),
        "labels_output": str(labels_output.resolve()),
        "labels_sha256": sha256_file(labels_output),
        "inventory_output": str(inventory_output.resolve()),
        "inventory_sha256": sha256_file(inventory_output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--labels-output", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--inventory-output", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    args = parser.parse_args()
    try:
        result = prepare(
            args.workbook,
            args.labels_output,
            args.inventory_output,
            expected_sha256=args.expected_sha256,
        )
    except (OSError, LabelIntegrityError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
