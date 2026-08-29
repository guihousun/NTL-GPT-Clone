#!/usr/bin/env python3
"""Independent Case-201 cross-check for the formal Q18 25/50 km table.

Only Python's standard library is used.  The input is the current formal Q18
25 km / 50 km ``formal-q18-analysis-ready.csv``; no runtime, benchmark, raw
pixel, or previously computed result is consulted.
"""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = Path(__file__).resolve().parent
INPUT_PATH = (
    ROOT
    / "experiments"
    / "paper-case-multiagent-2026-08-13"
    / "Q18-myanmar-earthquake"
    / "formal-25km-50km-20260817"
    / "formal-q18-analysis-ready.csv"
)
INPUT_RELPATH = INPUT_PATH.relative_to(ROOT).as_posix()

BASELINE_START = "2025-03-21"
BASELINE_END = "2025-03-27"
EXACT_DATE = "2025-03-28"
EXPECTED_LOCAL_NIGHT = "2025-03-29"
SUPPORTS = (25, 50)
PERCENT_TOLERANCE = Decimal("0.01")
TEN_PLACES = Decimal("0.0000000001")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decimal_or_none(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def decimal_required(value: str | None, field: str) -> Decimal:
    parsed = decimal_or_none(value)
    if parsed is None:
        raise ValueError(f"Missing required numeric field {field!r}")
    return parsed


def int_required(value: str | None, field: str) -> int:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"Missing required integer field {field!r}")
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {field!r}: {value!r}") from exc


def q10(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(TEN_PLACES, rounding=ROUND_HALF_UP)


def text10(value: Decimal | None) -> str:
    rounded = q10(value)
    return "" if rounded is None else format(rounded, ".10f")


def json_number(value: Decimal | None) -> float | None:
    rounded = q10(value)
    return None if rounded is None else float(rounded)


def read_rows() -> tuple[list[dict[str, str]], str]:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(INPUT_PATH)
    with INPUT_PATH.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header")
        rows = list(reader)
    if len(rows) != 32:
        raise ValueError(f"Expected 32 Q18 rows, found {len(rows)}")
    required = {
        "utc_product_date",
        "interpreted_local_night_date_asia_yangon",
        "temporal_relation",
        "aoi_radius_km",
        "aoi_pixel_count",
        "qa_valid_pixel_count",
        "qa_valid_fraction",
        "radiance_mean_nw_cm2_sr",
    }
    missing = required.difference(reader.fieldnames)
    if missing:
        raise ValueError(f"Input CSV is missing fields: {sorted(missing)}")
    return rows, sha256(INPUT_PATH)


def row_radius(row: dict[str, str]) -> int:
    radius = int_required(row.get("aoi_radius_km"), "aoi_radius_km")
    if radius not in SUPPORTS:
        raise ValueError(f"Unexpected support radius: {radius}")
    return radius


def row_is_qualified(row: dict[str, str]) -> bool:
    """Strict-QA qualification represented by the supplied formal CSV.

    The formal table preserves unavailable days as blank radiance means and
    zero strict-QA valid pixels.  A daily mean is qualified only when both the
    mean is present and at least one strict-QA pixel remains.
    """

    qa_count = int_required(row.get("qa_valid_pixel_count"), "qa_valid_pixel_count")
    aoi_count = int_required(row.get("aoi_pixel_count"), "aoi_pixel_count")
    if qa_count < 0 or qa_count > aoi_count:
        raise ValueError(f"Invalid QA count for {row.get('utc_product_date')}")
    fraction = decimal_required(row.get("qa_valid_fraction"), "qa_valid_fraction")
    if fraction < 0 or fraction > 1:
        raise ValueError(f"Invalid QA fraction for {row.get('utc_product_date')}")
    mean = decimal_or_none(row.get("radiance_mean_nw_cm2_sr"))
    if mean is not None and mean < 0:
        raise ValueError(f"Negative radiance mean for {row.get('utc_product_date')}")
    return qa_count > 0 and mean is not None


def observation_record(row: dict[str, str], qualified: bool) -> dict[str, object]:
    mean = decimal_or_none(row.get("radiance_mean_nw_cm2_sr"))
    return {
        "utc_product_date": row["utc_product_date"],
        "interpreted_local_night_date_asia_yangon": row[
            "interpreted_local_night_date_asia_yangon"
        ],
        "qa_valid_pixel_count": int_required(
            row.get("qa_valid_pixel_count"), "qa_valid_pixel_count"
        ),
        "aoi_pixel_count": int_required(row.get("aoi_pixel_count"), "aoi_pixel_count"),
        "qa_valid_fraction": json_number(
            decimal_required(row.get("qa_valid_fraction"), "qa_valid_fraction")
        ),
        "radiance_mean_nw_cm2_sr": json_number(mean),
        "qualified": qualified,
    }


def summarize_support(rows: list[dict[str, str]], radius: int) -> dict[str, object]:
    support_rows = [row for row in rows if row_radius(row) == radius]
    if len(support_rows) != 16:
        raise ValueError(f"Expected 16 rows for {radius} km, found {len(support_rows)}")

    baseline_rows = [
        row
        for row in support_rows
        if BASELINE_START <= row["utc_product_date"] <= BASELINE_END
    ]
    if len(baseline_rows) != 7:
        raise ValueError(
            f"Expected 7 baseline rows for {radius} km, found {len(baseline_rows)}"
        )
    baseline_rows.sort(key=lambda row: row["utc_product_date"])
    if len({row["utc_product_date"] for row in baseline_rows}) != 7:
        raise ValueError(f"Duplicate baseline dates for {radius} km")
    for row in baseline_rows:
        if row.get("temporal_relation") != "pre_event_local_night":
            raise ValueError(f"Unexpected baseline relation for {radius} km: {row}")

    qualified_baseline = [
        row for row in baseline_rows if row_is_qualified(row)
    ]
    baseline_values = [
        decimal_required(row.get("radiance_mean_nw_cm2_sr"), "radiance_mean_nw_cm2_sr")
        for row in qualified_baseline
    ]
    if not baseline_values:
        raise ValueError(f"No qualified baseline values for {radius} km")
    baseline_mean = sum(baseline_values, Decimal("0")) / Decimal(len(baseline_values))

    exact_rows = [row for row in support_rows if row["utc_product_date"] == EXACT_DATE]
    if len(exact_rows) > 1:
        raise ValueError(f"Duplicate exact-date rows for {radius} km")
    exact_row = exact_rows[0] if exact_rows else None
    exact_qualified = exact_row is not None and row_is_qualified(exact_row)
    exact_mean = (
        decimal_required(exact_row.get("radiance_mean_nw_cm2_sr"), "radiance_mean_nw_cm2_sr")
        if exact_qualified and exact_row is not None
        else None
    )
    exact_local_night = (
        exact_row.get("interpreted_local_night_date_asia_yangon") if exact_row else None
    )
    if exact_row is not None and exact_local_night != EXPECTED_LOCAL_NIGHT:
        raise ValueError(
            f"Exact {EXACT_DATE} local-night label for {radius} km is {exact_local_night!r}, "
            f"expected {EXPECTED_LOCAL_NIGHT!r}"
        )
    percent_change = (
        Decimal("100") * (exact_mean - baseline_mean) / baseline_mean
        if exact_qualified and exact_mean is not None
        else None
    )
    expected = Decimal("-29.61") if radius == 25 else Decimal("4.92")
    matches = (
        abs(percent_change - expected) <= PERCENT_TOLERANCE
        if percent_change is not None
        else False
    )

    return {
        "support_km": radius,
        "baseline": {
            "utc_product_window": [BASELINE_START, BASELINE_END],
            "daily_rows_in_window": len(baseline_rows),
            "qualified_daily_mean_n": len(qualified_baseline),
            "excluded_unqualified_daily_n": len(baseline_rows) - len(qualified_baseline),
            "mean_of_qualified_daily_means_nw_cm2_sr": json_number(baseline_mean),
            "daily_observations": [
                observation_record(row, row in qualified_baseline)
                for row in baseline_rows
            ],
        },
        "exact_first_night": {
            "utc_product_date": EXACT_DATE,
            "interpreted_local_night_date_asia_yangon": exact_local_night,
            "eligible": exact_qualified,
            "observation": observation_record(exact_row, exact_qualified)
            if exact_row is not None
            else None,
            "no_later_product_date_fallback": True,
            "fallback_rule": (
                "If the exact UTC 2025-03-28 row is not qualified, report "
                "no_eligible_first_night_observation; do not substitute UTC 2025-03-29."
            ),
        },
        "comparison": {
            "baseline_mean_nw_cm2_sr": json_number(baseline_mean),
            "exact_first_night_mean_nw_cm2_sr": json_number(exact_mean),
            "absolute_difference_nw_cm2_sr": json_number(
                exact_mean - baseline_mean if exact_mean is not None else None
            ),
            "percent_change_vs_baseline": json_number(percent_change),
            "expected_percent_change": float(expected),
            "tolerance_percentage_points": float(PERCENT_TOLERANCE),
            "target_match_within_tolerance": matches,
        },
    }


CSV_FIELDS = [
    "support_km",
    "record_type",
    "baseline_window_utc",
    "utc_product_date",
    "interpreted_local_night_date_asia_yangon",
    "daily_rows_in_window",
    "qualified_daily_mean_n",
    "mean_nw_cm2_sr",
    "baseline_mean_nw_cm2_sr",
    "percent_change_vs_baseline",
    "expected_percent_change",
    "target_match_within_0p01_percentage_points",
    "exact_date_eligible",
    "no_later_product_date_fallback",
    "note",
]


def csv_rows(summary: dict[str, object]) -> list[dict[str, object]]:
    radius = int(summary["support_km"])
    baseline = summary["baseline"]
    exact = summary["exact_first_night"]
    comparison = summary["comparison"]
    baseline_mean = Decimal(str(comparison["baseline_mean_nw_cm2_sr"]))
    exact_mean = comparison["exact_first_night_mean_nw_cm2_sr"]
    exact_mean_decimal = Decimal(str(exact_mean)) if exact_mean is not None else None
    pct = comparison["percent_change_vs_baseline"]
    pct_decimal = Decimal(str(pct)) if pct is not None else None
    expected = Decimal(str(comparison["expected_percent_change"]))
    match = comparison["target_match_within_tolerance"]
    exact_eligible = exact["eligible"]
    exact_row = exact["observation"]
    exact_date = exact_row["utc_product_date"] if exact_row else ""
    exact_local = (
        exact_row["interpreted_local_night_date_asia_yangon"] if exact_row else ""
    )
    window = f"{BASELINE_START}..{BASELINE_END}"
    return [
        {
            "support_km": radius,
            "record_type": "qualified_baseline_daily_mean",
            "baseline_window_utc": window,
            "utc_product_date": window,
            "interpreted_local_night_date_asia_yangon": "2025-03-22..2025-03-28",
            "daily_rows_in_window": baseline["daily_rows_in_window"],
            "qualified_daily_mean_n": baseline["qualified_daily_mean_n"],
            "mean_nw_cm2_sr": text10(baseline_mean),
            "baseline_mean_nw_cm2_sr": text10(baseline_mean),
            "percent_change_vs_baseline": "",
            "expected_percent_change": "",
            "target_match_within_0p01_percentage_points": "",
            "exact_date_eligible": str(exact_eligible).lower(),
            "no_later_product_date_fallback": "true",
            "note": (
                "Blank strict-QA daily means excluded from the baseline; never treated as zero."
            ),
        },
        {
            "support_km": radius,
            "record_type": "exact_first_night_mean_and_change",
            "baseline_window_utc": window,
            "utc_product_date": exact_date,
            "interpreted_local_night_date_asia_yangon": exact_local,
            "daily_rows_in_window": 1,
            "qualified_daily_mean_n": 1 if exact_eligible else 0,
            "mean_nw_cm2_sr": text10(exact_mean_decimal),
            "baseline_mean_nw_cm2_sr": text10(baseline_mean),
            "percent_change_vs_baseline": text10(pct_decimal),
            "expected_percent_change": text10(expected),
            "target_match_within_0p01_percentage_points": str(match).lower(),
            "exact_date_eligible": str(exact_eligible).lower(),
            "no_later_product_date_fallback": "true",
            "note": (
                "Exact UTC 2025-03-28 is the only first-night product date; if unqualified, "
                "report unavailable and do not use UTC 2025-03-29."
            ),
        },
    ]


def write_outputs(rows: list[dict[str, object]], summaries: dict[int, dict[str, object]], input_hash: str) -> None:
    csv_path = OUTPUT_DIR / "crosscheck.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    payload = {
        "schema": "case-201.analyst-crosscheck.v1",
        "case_id": "CASE-201",
        "role": "NTL Analyst independent crosscheck",
        "input": {
            "relative_path": INPUT_RELPATH,
            "sha256": input_hash,
            "reader": "Python standard-library csv.DictReader",
            "row_count": 32,
        },
        "contract": {
            "baseline_utc_window": [BASELINE_START, BASELINE_END],
            "exact_first_night_utc_product_date": EXACT_DATE,
            "exact_first_night_interpreted_local_date": EXPECTED_LOCAL_NIGHT,
            "qualified_daily_mean_rule": (
                "Use the formal CSV's strict-QA daily mean only when the radiance mean "
                "is present and qa_valid_pixel_count > 0; exclude blank/zero-valid rows."
            ),
            "percent_change_formula": "100 * (exact_first_night_mean - baseline_mean) / baseline_mean",
            "fallback_rule": (
                "If exact UTC 2025-03-28 is not qualified, report "
                "no_eligible_first_night_observation; do not substitute UTC 2025-03-29."
            ),
        },
        "supports": {str(radius): summaries[radius] for radius in SUPPORTS},
        "decision": {
            "exact_2025_03_28_eligible_for_25km": summaries[25]["exact_first_night"]["eligible"],
            "exact_2025_03_28_eligible_for_50km": summaries[50]["exact_first_night"]["eligible"],
            "target_25km_percent_change": summaries[25]["comparison"]["target_match_within_tolerance"],
            "target_50km_percent_change": summaries[50]["comparison"]["target_match_within_tolerance"],
            "runtime_or_benchmark_claim": False,
        },
    }
    with (OUTPUT_DIR / "crosscheck.json").open("w", encoding="utf-8", newline="") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> None:
    rows, input_hash = read_rows()
    summaries = {radius: summarize_support(rows, radius) for radius in SUPPORTS}
    output_rows = [
        item
        for radius in SUPPORTS
        for item in csv_rows(summaries[radius])
    ]
    if len(output_rows) != 4:
        raise AssertionError(f"Expected four crosscheck rows, found {len(output_rows)}")
    write_outputs(output_rows, summaries, input_hash)


if __name__ == "__main__":
    main()
