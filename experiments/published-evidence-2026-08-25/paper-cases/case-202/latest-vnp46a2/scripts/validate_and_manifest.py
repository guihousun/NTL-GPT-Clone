"""Independently re-read Case 202 outputs and refresh its artifact manifest.

This validator does not contact external services or alter any scientific
input. It recomputes the displayed strict-QA window summaries from the saved
daily table, checks the separately recorded availability endpoints, and hashes
the versioned evidence package.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
START = pd.Timestamp("2026-01-01")
WINDOWS = {
    "pre_conflict_baseline": (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-27")),
    "conflict_evaluation": (pd.Timestamp("2026-02-28"), pd.Timestamp("2026-04-07")),
    "ceasefire_evaluation": (pd.Timestamp("2026-04-08"), pd.Timestamp("2026-04-21")),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_daily() -> pd.DataFrame:
    table = pd.read_csv(ROOT / "daily-vnp46a2.csv", parse_dates=["date_utc"])
    table["qualified_bool"] = table["qualified"].astype(str).str.lower().eq("true")
    table["image_available_bool"] = table["image_available"].astype(str).str.lower().eq("true")
    table["mean"] = pd.to_numeric(table["mean"], errors="coerce")
    return table


def validate() -> dict[str, Any]:
    daily = load_daily()
    result_path = OUTPUTS / "analysis-results.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    checkpoint = json.loads((ROOT / "gee-checkpoint.json").read_text(encoding="utf-8"))
    cmr = json.loads((ROOT / "qa" / "cmr-availability.json").read_text(encoding="utf-8"))
    strict = daily.loc[(daily["qa_mode"] == "strict") & daily["qualified_bool"]].copy()
    strict_latest = strict["date_utc"].max()
    global_latest = daily.loc[daily["image_available_bool"], "date_utc"].max()
    checkpoint_latest = pd.Timestamp(checkpoint["live_latest_image_date_utc"])
    checkpoint_strict = pd.Timestamp(checkpoint["latest_strict_qualified_date_utc"])
    windows = {
        **WINDOWS,
        "extended_monitoring": (pd.Timestamp("2026-04-22"), checkpoint_latest),
    }
    reported = {row["window_id"]: row for row in result["strict_primary_window_summary"]}
    checks: dict[str, bool] = {
        "daily_has_exactly_two_qa_rows_per_utc_day": not daily.duplicated(["date_utc", "qa_mode"]).any(),
        "unqualified_rows_have_no_numeric_radiance": not daily.loc[~daily["qualified_bool"], "mean"].notna().any(),
        "latest_global_collection_image_matches_checkpoint": global_latest == checkpoint_latest,
        "latest_strict_city_observation_matches_checkpoint": strict_latest == checkpoint_strict,
        "cmr_latest_tehran_tile_is_recorded": bool(cmr.get("latest_product_date_utc")) and bool(cmr.get("queried_at_utc")),
        "result_distinguishes_global_and_strict_endpoints": (
            result["availability"]["live_latest_collection_image_date_utc"] == checkpoint_latest.date().isoformat()
            and result["availability"]["latest_strict_qualified_date_utc"] == checkpoint_strict.date().isoformat()
        ),
    }
    post_strict = daily.loc[
        (daily["date_utc"] > checkpoint_strict)
        & (daily["date_utc"] <= checkpoint_latest)
    ]
    checks["post_strict_collection_dates_remain_explicit_non_numeric_gaps"] = (
        not post_strict.empty
        and not post_strict["qualified_bool"].any()
        and not post_strict["mean"].notna().any()
    )
    refresh_path = ROOT / "qa" / "august-live-refresh.json"
    if refresh_path.is_file():
        refresh = json.loads(refresh_path.read_text(encoding="utf-8"))
        checks["august_live_refresh_passed"] = (
            refresh.get("status") == "passed"
            and refresh.get("latest_strict_qualified_date_utc") == checkpoint_strict.date().isoformat()
        )
    recomputed: dict[str, dict[str, float | int | str]] = {}
    baseline_start, baseline_end = WINDOWS["pre_conflict_baseline"]
    baseline = strict.loc[(strict["date_utc"] >= baseline_start) & (strict["date_utc"] <= baseline_end), "mean"]
    baseline_mean = float(baseline.mean())
    for window_id, (start, end) in windows.items():
        chosen = strict.loc[(strict["date_utc"] >= start) & (strict["date_utc"] <= end), "mean"]
        mean = float(chosen.mean())
        pct = (mean - baseline_mean) / baseline_mean * 100.0
        recorded = reported.get(window_id, {})
        recomputed[window_id] = {
            "start_date_utc": start.date().isoformat(),
            "end_date_utc": end.date().isoformat(),
            "strict_qualified_days": int(chosen.shape[0]),
            "mean_of_daily_means": mean,
            "relative_change_vs_baseline_percent": pct,
        }
        checks[f"{window_id}_matches_saved_result"] = (
            abs(float(recorded.get("mean_of_daily_means", float("nan"))) - mean) < 1e-10
            and abs(float(recorded.get("relative_change_vs_baseline_percent", float("nan"))) - pct) < 1e-10
            and recorded.get("end_date_utc") == end.date().isoformat()
        )
    figure_files = [OUTPUTS / f"case202-tehran-latest-timeseries{suffix}" for suffix in (".svg", ".pdf", ".png", ".tiff")]
    checks["all_four_figure_exports_exist_and_are_nonempty"] = all(path.is_file() and path.stat().st_size > 0 for path in figure_files)
    payload = {
        "schema_version": "ntl.case202.engineer-validation.v1",
        "case_id": "Case202-tehran-latest-vnp46a2",
        "validated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "recomputed_strict_window_summary": recomputed,
        "inputs": {
            "daily_vnp46a2_csv_sha256": sha256(ROOT / "daily-vnp46a2.csv"),
            "analysis_results_json_sha256": sha256(result_path),
            "cmr_availability_json_sha256": sha256(ROOT / "qa" / "cmr-availability.json"),
        },
    }
    return payload


def manifest() -> dict[str, Any]:
    experiments_root = ROOT.parent
    old_root = experiments_root / "paper-case-multiagent-2026-08-13" / "Q19-tehran-city-longseries"
    rerun_root = experiments_root / "paper-case-codex-subagent-rerun-2026-08-17"
    items = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "artifact-manifest.json" or "__pycache__" in path.parts:
            continue
        items.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    external = []
    for path in (
        old_root / "extract_tehran_daily_vnp46a2.py",
        rerun_root / "role-outputs" / "analyst-recovery" / "q19-analysis-results.json",
        rerun_root / "role-outputs" / "event-tracker" / "q19-event-context.json",
    ):
        if path.is_file():
            external.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path), "purpose": "read-only reused source or prior evidence"})
    return {
        "schema_version": "ntl.case202.artifact-manifest.v1",
        "case_id": "Case202-tehran-latest-vnp46a2",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "package_files": items,
        "read_only_external_inputs": external,
        "scope": "Paper-case evidence extension only; excluded from formal 200-task benchmark and no manuscript or Draw.io artifact was modified.",
    }


def main() -> int:
    validation = validate()
    write_json(ROOT / "qa" / "engineer-validation.json", validation)
    write_json(ROOT / "artifact-manifest.json", manifest())
    print(json.dumps({"status": validation["status"], "check_count": len(validation["checks"]), "artifact_count": len(manifest()["package_files"])}, ensure_ascii=False))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
