"""Independent Engineer validation for Case 201's role handoffs and results."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


TOLERANCE = 1e-9


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    q18 = root.parent / "paper-case-multiagent-2026-08-13" / "Q18-myanmar-earthquake" / "formal-25km-50km-20260817"
    event = load_json(root / "role-outputs" / "event-tracker" / "first-night-decision.json")
    data = load_json(root / "role-outputs" / "data-searcher" / "product-eligibility.json")
    analyst = load_json(root / "role-outputs" / "analyst-recovery" / "analysis-results.json")
    test_run = load_json(root / "validation" / "contract-test-result.json")
    version = load_json(root / "skill" / "gee-ntl-date-boundary-handling.version.json")
    with (q18 / "formal-q18-analysis-ready.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    checks: list[dict] = []
    checks.append({
        "id": "contract_tests_passed",
        "passed": test_run["passed"] is True,
        "observed": test_run["returncode"],
    })
    runtime_skill = Path(version["runtime_source_path"])
    checks.append({
        "id": "runtime_skill_hash_matches_frozen_record",
        "passed": runtime_skill.is_file() and sha256(runtime_skill).lower() == version["runtime_source_sha256"].lower(),
    })
    execution = event["execution"]
    checks.extend([
        {"id": "event_utc", "passed": execution["event_time_utc"] == "2025-03-28T06:20:52Z"},
        {"id": "event_local_yangon", "passed": execution["local_time_context"]["event_time_local"] == "2025-03-28T12:50:52+06:30"},
        {"id": "local_first_night", "passed": execution["local_first_night"]["date"] == "2025-03-29"},
        {"id": "utc_product_date", "passed": execution["utc_product_mapping"]["utc_product_date"] == "2025-03-28"},
        {"id": "no_later_fallback_event", "passed": execution["exact_date_gate"]["later_date_fallback_used"] is False},
        {"id": "data_exact_date_gate", "passed": data["decision"]["status"] == "eligible_exact_first_night_observation" and data["decision"]["later_date_fallback_used"] is False},
    ])

    expected: dict[int, dict[str, float | int]] = {}
    for radius in (25, 50):
        radius_rows = [row for row in rows if int(row["aoi_radius_km"]) == radius]
        baseline = [
            float(row["radiance_mean_nw_cm2_sr"])
            for row in radius_rows
            if row["temporal_relation"] == "pre_event_local_night"
            and row["radiance_mean_nw_cm2_sr"]
            and int(row["qa_valid_pixel_count"]) > 0
        ]
        exact = [
            row for row in radius_rows
            if row["utc_product_date"] == "2025-03-28"
            and row["temporal_relation"] == "first_post_event_local_night_interpreted"
        ]
        if len(exact) != 1:
            raise RuntimeError(f"expected one exact first-night row for {radius} km")
        event_mean = float(exact[0]["radiance_mean_nw_cm2_sr"])
        baseline_mean = sum(baseline) / len(baseline)
        pct = 100 * (event_mean - baseline_mean) / baseline_mean
        expected[radius] = {"n": len(baseline), "baseline": baseline_mean, "event": event_mean, "pct": pct}

    by_radius = {int(item["aoi_radius_km"]): item for item in analyst["results"]}
    for radius, values in expected.items():
        item = by_radius[radius]
        passed = (
            item["baseline"]["qualified_n"] == values["n"]
            and close(item["baseline"]["mean_nw_cm2_sr"], values["baseline"])
            and close(item["event_row"]["radiance_mean_nw_cm2_sr"], values["event"])
            and close(item["change"]["percent"], values["pct"])
            and item["event_row"]["utc_product_date"] == "2025-03-28"
        )
        checks.append({"id": f"analyst_{radius}km_recompute", "passed": passed, "expected": values})

    payload = {
        "schema_version": "ntl.case201.engineer-validation.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execution_context": "Codex-subagent workflow simulation; not deployed runtime or benchmark evidence.",
        "checks": checks,
        "expected_results": expected,
        "overall_pass": all(check["passed"] for check in checks),
    }
    output = root / "validation" / "engineer-validation.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not payload["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
