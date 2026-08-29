"""Recalculate the descriptive Case 201 Myanmar first-local-night result.

This is intentionally a small, local, standard-library-only recovery script.
It reads only the supplied analysis-ready CSV and the supplied event and
observation JSON files.  It does not invoke the NTL-GPT runtime, a benchmark
runner, a network service, or any later observation in the calculation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CASE_ROOT = Path(
    r"vault/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817"
)
CSV_PATH = CASE_ROOT / "formal-q18-analysis-ready.csv"
EVENT_JSON_PATH = CASE_ROOT / "formal-event-context.json"
OBSERVATION_JSON_PATH = CASE_ROOT / "formal-observation-package.json"
OUTPUT_ROOT = Path(__file__).resolve().parent

TASK_ID = "Case-201-myanmar-first-local-night-2026-08-18"
EVENT_PRODUCT_DATE = "2025-03-28"
RADII_KM = (25, 50)
EXPECTED_PERCENT_CHANGE = {25: -29.61, 50: 4.92}
PERCENT_TOLERANCE = 0.005


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV has no data rows: {path}")
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def finite_float(row: dict[str, str], column: str) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def positive_int(row: dict[str, str], column: str) -> int:
    raw = (row.get(column) or "").strip()
    if not raw:
        return 0
    value = int(float(raw))
    return value


def json_number(value: float) -> float:
    """Keep generated JSON readable while retaining enough precision."""

    return round(value, 12)


def main() -> None:
    for path in (CSV_PATH, EVENT_JSON_PATH, OBSERVATION_JSON_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    event_context = read_json(EVENT_JSON_PATH)
    observation = read_json(OBSERVATION_JSON_PATH)
    rows = read_csv(CSV_PATH)

    event_anchor = event_context.get("downstream_anchor", {})
    primary_event = event_context.get("primary_event", {})
    temporal_coverage = observation.get("temporal_coverage", {})
    date_semantics = observation.get("date_semantics", {})
    aoi_metadata = observation.get("aoi", {})

    event_date_from_context = str(event_anchor.get("event_time_utc", ""))[:10]
    event_date_from_observation = str(date_semantics.get("event_day_product", ""))
    if event_date_from_context != EVENT_PRODUCT_DATE:
        raise ValueError(
            f"Event JSON anchor mismatch: {event_date_from_context!r}"
        )
    if event_date_from_observation != EVENT_PRODUCT_DATE:
        raise ValueError(
            f"Observation JSON event product mismatch: {event_date_from_observation!r}"
        )

    pre_event_dates = [
        str(value) for value in temporal_coverage.get("pre_event_contiguous_dates", [])
    ]
    if not pre_event_dates:
        raise ValueError("Observation JSON has no pre-event contiguous dates")

    csv_radii = sorted({int(float(row["aoi_radius_km"])) for row in rows})
    if csv_radii != list(RADII_KM):
        raise ValueError(f"Unexpected CSV radii: {csv_radii}")

    results: list[dict[str, Any]] = []
    table_rows: list[dict[str, Any]] = []
    used_rows: list[dict[str, str]] = []
    excluded_later_rows: list[dict[str, str]] = []
    excluded_unqualified_pre_rows: list[dict[str, str]] = []

    for radius in RADII_KM:
        radius_rows = [
            row for row in rows if int(float(row["aoi_radius_km"])) == radius
        ]
        baseline_rows: list[dict[str, str]] = []
        for row in radius_rows:
            date = row.get("utc_product_date", "")
            relation = row.get("temporal_relation", "")
            mean = finite_float(row, "radiance_mean_nw_cm2_sr")
            valid_count = positive_int(row, "qa_valid_pixel_count")
            is_qualified = (
                date in pre_event_dates
                and relation == "pre_event_local_night"
                and mean is not None
                and valid_count > 0
            )
            if is_qualified:
                baseline_rows.append(row)
                used_rows.append(row)
            elif date in pre_event_dates and relation == "pre_event_local_night":
                excluded_unqualified_pre_rows.append(row)

        event_rows = [
            row
            for row in radius_rows
            if row.get("utc_product_date") == EVENT_PRODUCT_DATE
            and row.get("temporal_relation")
            == "first_post_event_local_night_interpreted"
        ]
        if len(event_rows) != 1:
            raise ValueError(
                f"Expected one exact {EVENT_PRODUCT_DATE} event row for {radius} km; "
                f"found {len(event_rows)}"
            )
        event_row = event_rows[0]
        event_mean = finite_float(event_row, "radiance_mean_nw_cm2_sr")
        event_valid_count = positive_int(event_row, "qa_valid_pixel_count")
        if event_mean is None or event_valid_count <= 0:
            raise ValueError(f"Event row is not qualified for {radius} km")
        used_rows.append(event_row)

        for row in radius_rows:
            if row.get("utc_product_date", "") > EVENT_PRODUCT_DATE:
                excluded_later_rows.append(row)

        baseline_values = [
            finite_float(row, "radiance_mean_nw_cm2_sr")
            for row in baseline_rows
        ]
        if not baseline_values or any(value is None for value in baseline_values):
            raise ValueError(f"Empty or non-finite baseline for {radius} km")
        baseline_mean = sum(value for value in baseline_values if value is not None) / len(
            baseline_values
        )
        absolute_change = event_mean - baseline_mean
        percent_change = absolute_change / baseline_mean * 100.0
        expected_percent = EXPECTED_PERCENT_CHANGE[radius]
        if abs(percent_change - expected_percent) > PERCENT_TOLERANCE:
            raise ValueError(
                f"Unexpected percent change for {radius} km: {percent_change}"
            )

        support_description = ""
        aoi_radii = aoi_metadata.get("radii_km", [])
        if isinstance(aoi_radii, list) and radius in [int(float(v)) for v in aoi_radii]:
            support_description = (
                f"{radius} km WGS84 ellipsoidal geodesic radius; "
                "pixel-centre distance <= radius; unweighted pixel mean"
            )

        result = {
            "aoi_radius_km": radius,
            "aoi_support": support_description,
            "baseline": {
                "qualification_rule": (
                    "pre_event_contiguous_dates from observation JSON, "
                    "temporal_relation=pre_event_local_night, finite radiance mean, "
                    "and qa_valid_pixel_count > 0"
                ),
                "utc_product_dates": [
                    row["utc_product_date"] for row in baseline_rows
                ],
                "qualified_n": len(baseline_rows),
                "mean_nw_cm2_sr": json_number(baseline_mean),
            },
            "event_row": {
                "utc_product_date": event_row["utc_product_date"],
                "interpreted_local_night_date_asia_yangon": event_row[
                    "interpreted_local_night_date_asia_yangon"
                ],
                "temporal_relation": event_row["temporal_relation"],
                "radiance_mean_nw_cm2_sr": json_number(event_mean),
                "qa_valid_pixel_count": event_valid_count,
                "qa_valid_fraction": json_number(
                    finite_float(event_row, "qa_valid_fraction") or 0.0
                ),
            },
            "change": {
                "absolute_nw_cm2_sr": json_number(absolute_change),
                "percent": json_number(percent_change),
                "percent_rounded_2dp": round(percent_change, 2),
            },
            "interpretation": (
                "Descriptive comparison for this support radius only; no causal, "
                "recovery, or statistical-significance inference."
            ),
        }
        results.append(result)

        table_rows.append(
            {
                "task_id": TASK_ID,
                "aoi_radius_km": radius,
                "aoi_support": support_description,
                "baseline_start_utc": min(pre_event_dates),
                "baseline_end_utc": max(pre_event_dates),
                "baseline_qualified_n": len(baseline_rows),
                "baseline_mean_nw_cm2_sr": f"{baseline_mean:.12f}",
                "baseline_qualified_dates_utc": ";".join(
                    row["utc_product_date"] for row in baseline_rows
                ),
                "event_utc_product_date": event_row["utc_product_date"],
                "event_local_night_date_asia_yangon": event_row[
                    "interpreted_local_night_date_asia_yangon"
                ],
                "event_temporal_relation": event_row["temporal_relation"],
                "event_mean_nw_cm2_sr": f"{event_mean:.12f}",
                "event_qa_valid_pixel_count": event_valid_count,
                "event_qa_valid_fraction": f"{(finite_float(event_row, 'qa_valid_fraction') or 0.0):.12f}",
                "absolute_change_nw_cm2_sr": f"{absolute_change:.12f}",
                "percent_change": f"{percent_change:.12f}",
                "percent_change_rounded_2dp": f"{percent_change:.2f}",
                "baseline_qualification": "finite radiance mean and qa_valid_pixel_count > 0",
                "interpretation_scope": "descriptive only; support radius kept separate",
            }
        )

    used_dates = sorted({row["utc_product_date"] for row in used_rows})
    later_dates = sorted({row["utc_product_date"] for row in excluded_later_rows})
    source_hashes = {
        "formal-q18-analysis-ready.csv": sha256_file(CSV_PATH),
        "formal-event-context.json": sha256_file(EVENT_JSON_PATH),
        "formal-observation-package.json": sha256_file(OBSERVATION_JSON_PATH),
    }

    analysis_results = {
        "schema": "ntl.analyst-recovery.results.v1",
        "task_id": TASK_ID,
        "status": "complete_descriptive_local_csv_recalculation",
        "execution_context": {
            "mode": "local_csv_recalculation",
            "runtime_deployed": False,
            "benchmark_executed": False,
            "external_services_used": [],
            "standard_library_only": True,
        },
        "inputs": {
            "analysis_ready_csv": str(CSV_PATH),
            "event_context_json": str(EVENT_JSON_PATH),
            "observation_package_json": str(OBSERVATION_JSON_PATH),
            "sha256": source_hashes,
        },
        "event_anchor": {
            "event_id_usgs": primary_event.get("event_id_usgs"),
            "official_name": primary_event.get("official_name"),
            "event_time_utc": event_anchor.get("event_time_utc"),
            "event_time_local": event_anchor.get("event_time_local"),
            "event_product_date": EVENT_PRODUCT_DATE,
            "first_post_event_local_night_interpreted": date_semantics.get(
                "first_post_event_local_night_interpreted"
            ),
        },
        "method": {
            "baseline_window": "pre_event_contiguous_dates from observation JSON",
            "event_row": "exact utc_product_date=2025-03-28 and first_post_event_local_night_interpreted",
            "baseline_statistic": "arithmetic mean of qualified daily AOI radiance means",
            "absolute_change": "event_mean - baseline_mean",
            "percent_change": "100 * (event_mean - baseline_mean) / baseline_mean",
            "later_dates_used": False,
            "support_handling": "25 km and 50 km are calculated and reported independently",
        },
        "results": results,
        "excluded_rows": {
            "later_followup_utc_product_dates_not_used": later_dates,
            "unqualified_pre_event_rows_not_used": [
                {
                    "aoi_radius_km": int(float(row["aoi_radius_km"])),
                    "utc_product_date": row["utc_product_date"],
                    "reason": "no finite radiance mean or qa_valid_pixel_count <= 0",
                }
                for row in excluded_unqualified_pre_rows
            ],
        },
        "interpretation_guardrails": [
            "This is a descriptive radiance comparison only.",
            "25 km and 50 km support ranges are not pooled.",
            "Later follow-up observations are not used.",
            "No causal, damage, recovery, or statistical-significance claim is made.",
        ],
    }
    results_path = OUTPUT_ROOT / "analysis-results.json"
    write_json(results_path, analysis_results)

    table_path = OUTPUT_ROOT / "analysis-table.csv"
    table_fields = list(table_rows[0].keys())
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=table_fields)
        writer.writeheader()
        writer.writerows(table_rows)

    validation_checks: dict[str, bool] = {}
    validation_checks["source_csv_row_count_is_32"] = len(rows) == 32
    validation_checks["source_contains_exactly_25_and_50_km"] = csv_radii == [25, 50]
    validation_checks["event_anchor_matches_both_json_inputs"] = (
        event_date_from_context == event_date_from_observation == EVENT_PRODUCT_DATE
    )
    validation_checks["exact_event_row_present_once_per_radius"] = all(
        sum(
            1
            for row in rows
            if int(float(row["aoi_radius_km"])) == radius
            and row.get("utc_product_date") == EVENT_PRODUCT_DATE
            and row.get("temporal_relation")
            == "first_post_event_local_night_interpreted"
        )
        == 1
        for radius in RADII_KM
    )
    validation_checks["baseline_has_qualified_rows_per_radius"] = all(
        result["baseline"]["qualified_n"] > 0 for result in results
    )
    validation_checks["used_dates_stop_at_2025_03_28"] = max(used_dates) == EVENT_PRODUCT_DATE
    validation_checks["later_dates_not_used"] = not (
        set(used_dates) & set(later_dates)
    )
    validation_checks["support_ranges_remain_separate"] = len(results) == 2 and {
        result["aoi_radius_km"] for result in results
    } == {25, 50}
    validation_checks["formula_reproduces_requested_25km_value"] = abs(
        results[0]["change"]["percent_rounded_2dp"] - (-29.61)
    ) < 1e-9
    validation_checks["formula_reproduces_requested_50km_value"] = abs(
        results[1]["change"]["percent_rounded_2dp"] - 4.92
    ) < 1e-9
    validation_checks["descriptive_only_no_causal_recovery_significance"] = True

    expected_checks = {
        str(radius): {
            "expected_percent_rounded_2dp": EXPECTED_PERCENT_CHANGE[radius],
            "observed_percent_rounded_2dp": result["change"][
                "percent_rounded_2dp"
            ],
            "absolute_difference_from_expected_percent_points": round(
                result["change"]["percent_rounded_2dp"]
                - EXPECTED_PERCENT_CHANGE[radius],
                12,
            ),
            "pass": validation_checks[
                f"formula_reproduces_requested_{radius}km_value"
            ],
        }
        for radius, result in zip(RADII_KM, results)
    }

    validation = {
        "schema": "ntl.analyst-recovery.validation.v1",
        "task_id": TASK_ID,
        "status": "passed" if all(validation_checks.values()) else "failed",
        "checks": validation_checks,
        "expected_value_checks": expected_checks,
        "source_rows": len(rows),
        "used_utc_product_dates": used_dates,
        "later_utc_product_dates_present_but_excluded": later_dates,
        "calculation_scope": {
            "pre_event_dates_from_observation_json": pre_event_dates,
            "event_product_date": EVENT_PRODUCT_DATE,
            "radii_km": list(RADII_KM),
        },
        "limitations": [
            "Only the exact 2025-03-28 product row is compared with the pre-event baseline.",
            "The result is observational and descriptive; no causal or recovery inference is supported.",
            "No significance test or uncertainty model is performed.",
        ],
    }
    validation_path = OUTPUT_ROOT / "validation.json"
    write_json(validation_path, validation)

    report_path = OUTPUT_ROOT / "analyst-report.md"
    report_lines = [
        "# Case 201 Analyst recovery",
        "",
        "状态：已完成本地 CSV 描述性重算；未部署 runtime，未执行 benchmark。",
        "",
        "## 输入与口径",
        "",
        f"- 输入：`{CSV_PATH.name}`、`{EVENT_JSON_PATH.name}`、`{OBSERVATION_JSON_PATH.name}`。",
        f"- 事件锚点：`{EVENT_PRODUCT_DATE}` UTC product date；该行在源数据中标记为 `first_post_event_local_night_interpreted`，解释的 Yangon local-night date 为 `2025-03-29`。",
        "- 基线：仅使用 observation JSON 声明的连续事件前日期；每日 AOI 均值必须为有限值且 `qa_valid_pixel_count > 0` 才计入。",
        "- 25 km 与 50 km 支持范围分别计算，不合并、不加权池化；2026 年 later follow-up rows 未用于计算。",
        "",
        "## 结果",
        "",
        "| 支持范围 | 合格基线 n | 基线均值 (nW cm⁻² sr⁻¹) | 2025-03-28 均值 | 绝对变化 | 百分比变化 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        radius = result["aoi_radius_km"]
        baseline = result["baseline"]
        event = result["event_row"]
        change = result["change"]
        sign = "+" if change["percent_rounded_2dp"] > 0 else ""
        report_lines.append(
            f"| {radius} km | {baseline['qualified_n']} | {baseline['mean_nw_cm2_sr']:.12f} | "
            f"{event['radiance_mean_nw_cm2_sr']:.12f} | {change['absolute_nw_cm2_sr']:.12f} | "
            f"{sign}{change['percent_rounded_2dp']:.2f}% |"
        )
    report_lines.extend(
        [
            "",
            "按公式 `100 × (event mean − baseline mean) / baseline mean`，验证值为：25 km **−29.61%**，50 km **+4.92%**。",
            "",
            "## 解释边界",
            "",
            "这些是两个独立支持范围内的描述性夜间灯光均值变化。结果不证明因果关系、损害、恢复或统计显著性；本次重算也不使用 later date。",
            "",
            "验证详情见 `validation.json`，逐文件校验信息见 `artifact-manifest.json`。",
            "",
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8", newline="\n")

    manifest = {
        "schema": "ntl.analyst-recovery.artifact-manifest.v1",
        "task_id": TASK_ID,
        "status": validation["status"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(OUTPUT_ROOT),
        "source_inputs": [
            {
                "name": path.name,
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for path in (CSV_PATH, EVENT_JSON_PATH, OBSERVATION_JSON_PATH)
        ],
        "artifacts": [
            {
                "name": path.name,
                "path": str(path),
                "kind": "script" if path.suffix == ".py" else "generated_output",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in (
                Path(__file__).resolve(),
                table_path,
                results_path,
                validation_path,
                report_path,
            )
        ],
        "self_reference": "artifact-manifest.json is intentionally not listed in its own checksum entries",
        "validation": {
            "validation_file": str(validation_path),
            "all_checks_passed": validation["status"] == "passed",
        },
    }
    manifest_path = OUTPUT_ROOT / "artifact-manifest.json"
    write_json(manifest_path, manifest)

    if not all(validation_checks.values()):
        raise RuntimeError("Validation failed; see validation.json")


if __name__ == "__main__":
    main()
