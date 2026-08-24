#!/usr/bin/env python
"""Formal Q18 descriptive analysis from Engineer-accepted inputs only.

This script intentionally does not open benchmark outputs, gold answers, old
summaries, manuscript values, or legacy analysis scripts. It produces a
non-causal, spatial-sensitivity-aware description for 25 km and 50 km AOIs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
EVENT_PATH = HERE / "formal-event-context.json"
PACKAGE_PATH = HERE / "formal-observation-package.json"
INPUT_CSV_PATH = HERE / "formal-q18-analysis-ready.csv"
INPUT_VALIDATION_PATH = HERE / "formal-q18-validation.json"
RESULTS_PATH = HERE / "formal-analysis-results.json"
TABLE_PATH = HERE / "formal-analysis-table.csv"
PREVIEW_PATH = HERE / "formal-analysis-preview.png"
LOG_PATH = HERE / "formal-analyst-log.md"

PRE_START = "2025-03-21"
PRE_END = "2025-03-27"
FIRST_POST_UTC = "2025-03-28"
FIRST_POST_LOCAL_NIGHT = "2025-03-29"
AOI_RADII = (25, 50)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_or_none(value: Any) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    if number.is_integer() and isinstance(value, (int, np.integer)):
        return int(number)
    return number


def round_or_none(value: Any, digits: int = 10) -> float | None:
    clean = finite_or_none(value)
    if clean is None:
        return None
    return round(float(clean), digits)


def load_and_validate_inputs() -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame, dict[str, Any]]:
    with EVENT_PATH.open("r", encoding="utf-8") as stream:
        event = json.load(stream)
    with PACKAGE_PATH.open("r", encoding="utf-8") as stream:
        package = json.load(stream)
    with INPUT_VALIDATION_PATH.open("r", encoding="utf-8") as stream:
        validation = json.load(stream)
    frame = pd.read_csv(INPUT_CSV_PATH)

    assert event["task_id"] == "Q18-myanmar-earthquake"
    assert event["primary_event"]["origin_time_utc"] == "2025-03-28T06:20:52Z"
    assert event["primary_event"]["origin_time_local"] == "2025-03-28T12:50:52+06:30"
    assert event["primary_event"]["local_timezone"] == "Asia/Yangon"
    assert event["primary_event"]["magnitude"]["value"] == 7.7
    assert event["primary_event"]["magnitude"]["type_code"] == "mww"
    assert event["primary_event"]["epicenter"]["coordinate_order_lon_lat"] == [95.936, 22.011]
    assert package["task_id"] == "Q18-myanmar-earthquake"
    assert validation["checks"]["historical_outputs_not_read"] is True
    assert len(frame) == 32
    assert set(frame["aoi_radius_km"].astype(int)) == set(AOI_RADII)
    assert frame["utc_product_date"].notna().all()
    assert not frame.duplicated(["utc_product_date", "aoi_radius_km"]).any()

    numeric_columns = [
        "aoi_radius_km",
        "aoi_pixel_count",
        "qa_valid_pixel_count",
        "qa_valid_fraction",
        "radiance_mean_nw_cm2_sr",
        "radiance_median_nw_cm2_sr",
        "radiance_std_nw_cm2_sr",
        "radiance_min_nw_cm2_sr",
        "radiance_p05_nw_cm2_sr",
        "radiance_p95_nw_cm2_sr",
        "radiance_max_nw_cm2_sr",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    assert (frame["qa_valid_pixel_count"] <= frame["aoi_pixel_count"]).all()
    assert frame["qa_valid_fraction"].between(0, 1).all()
    missing_means = frame["radiance_mean_nw_cm2_sr"].isna()
    assert (frame.loc[missing_means, "qa_valid_pixel_count"] == 0).all()
    assert frame.loc[~missing_means, "radiance_mean_nw_cm2_sr"].map(math.isfinite).all()

    post = frame[frame["utc_product_date"] == FIRST_POST_UTC]
    assert len(post) == 2
    assert set(post["interpreted_local_night_date_asia_yangon"]) == {FIRST_POST_LOCAL_NIGHT}
    assert post["radiance_mean_nw_cm2_sr"].notna().all()
    return event, package, frame, validation


def daily_record(row: pd.Series) -> dict[str, Any]:
    return {
        "utc_product_date": row["utc_product_date"],
        "local_night_date_asia_yangon": row["interpreted_local_night_date_asia_yangon"],
        "qa_valid_pixel_count": int(row["qa_valid_pixel_count"]),
        "aoi_pixel_count": int(row["aoi_pixel_count"]),
        "qa_valid_fraction": round_or_none(row["qa_valid_fraction"]),
        "radiance_mean_nw_cm2_sr": round_or_none(row["radiance_mean_nw_cm2_sr"]),
        "radiance_median_nw_cm2_sr": round_or_none(row["radiance_median_nw_cm2_sr"]),
        "radiance_within_day_std_nw_cm2_sr": round_or_none(row["radiance_std_nw_cm2_sr"]),
    }


def analyze_aoi(frame: pd.DataFrame, radius: int) -> dict[str, Any]:
    subset = frame[frame["aoi_radius_km"].astype(int) == radius].copy()
    pre_all = subset[
        subset["utc_product_date"].between(PRE_START, PRE_END, inclusive="both")
    ].sort_values("utc_product_date")
    assert len(pre_all) == 7
    pre_valid = pre_all[pre_all["radiance_mean_nw_cm2_sr"].notna()].copy()
    post = subset[subset["utc_product_date"] == FIRST_POST_UTC]
    assert len(post) == 1
    post_row = post.iloc[0]

    pre_values = pre_valid["radiance_mean_nw_cm2_sr"].to_numpy(dtype=float)
    n = len(pre_values)
    assert n >= 2
    baseline_mean = float(np.mean(pre_values))
    baseline_median = float(np.median(pre_values))
    baseline_std = float(np.std(pre_values, ddof=1))
    post_mean = float(post_row["radiance_mean_nw_cm2_sr"])
    delta = post_mean - baseline_mean
    pct_delta = 100.0 * delta / baseline_mean
    z_like = delta / baseline_std if baseline_std > 0 else None

    less = int(np.sum(pre_values < post_mean))
    equal = int(np.sum(pre_values == post_mean))
    empirical_percentile = 100.0 * (less + 0.5 * equal) / n
    combined_rank_ascending = 1 + less

    loo_means = []
    loo_deltas = []
    loo_pct_deltas = []
    for index in range(n):
        loo_baseline = float(np.mean(np.delete(pre_values, index)))
        loo_delta = post_mean - loo_baseline
        loo_means.append(loo_baseline)
        loo_deltas.append(loo_delta)
        loo_pct_deltas.append(100.0 * loo_delta / loo_baseline)

    late = subset[subset["temporal_relation"] == "late_followup_observation"].sort_values(
        "utc_product_date"
    )
    late_available = late[late["radiance_mean_nw_cm2_sr"].notna()]
    late_fractions = late["qa_valid_fraction"].to_numpy(dtype=float)
    late_means = late_available["radiance_mean_nw_cm2_sr"].to_numpy(dtype=float)

    return {
        "aoi_radius_km": radius,
        "baseline": {
            "utc_product_window": [PRE_START, PRE_END],
            "aggregation_unit": "equal-weighted daily AOI radiance means after strict QA",
            "calendar_days_in_window": 7,
            "valid_daily_mean_n": n,
            "missing_daily_mean_n": 7 - n,
            "mean_of_daily_means_nw_cm2_sr": round(baseline_mean, 10),
            "median_of_daily_means_nw_cm2_sr": round(baseline_median, 10),
            "sample_std_of_daily_means_nw_cm2_sr": round(baseline_std, 10),
            "daily_observations": [daily_record(row) for _, row in pre_all.iterrows()],
        },
        "first_post_event_local_night": {
            "utc_product_date": FIRST_POST_UTC,
            "interpreted_local_night_date_asia_yangon": FIRST_POST_LOCAL_NIGHT,
            "mean_nw_cm2_sr": round(post_mean, 10),
            "median_nw_cm2_sr": round(float(post_row["radiance_median_nw_cm2_sr"]), 10),
            "qa_valid_pixel_count": int(post_row["qa_valid_pixel_count"]),
            "aoi_pixel_count": int(post_row["aoi_pixel_count"]),
            "qa_valid_fraction": round(float(post_row["qa_valid_fraction"]), 10),
        },
        "first_night_relative_to_baseline": {
            "absolute_mean_difference_nw_cm2_sr": round(delta, 10),
            "percent_mean_difference": round(pct_delta, 10),
            "z_like_location_using_pre_daily_sample_std": round_or_none(z_like),
            "empirical_percentile_among_pre_daily_means": round(empirical_percentile, 10),
            "ascending_rank_if_inserted_among_pre_values": combined_rank_ascending,
            "combined_rank_denominator": n + 1,
            "leave_one_day_out_baseline_mean_range_nw_cm2_sr": [
                round(min(loo_means), 10),
                round(max(loo_means), 10),
            ],
            "leave_one_day_out_absolute_difference_range_nw_cm2_sr": [
                round(min(loo_deltas), 10),
                round(max(loo_deltas), 10),
            ],
            "leave_one_day_out_percent_difference_range": [
                round(min(loo_pct_deltas), 10),
                round(max(loo_pct_deltas), 10),
            ],
            "diagnostic_limit": (
                "Small-n descriptive location diagnostics only; neither the z-like value nor the "
                "rank is a significance test or causal estimate."
            ),
        },
        "late_followup_observations": {
            "label": "late follow-up observations",
            "calendar_days": len(late),
            "days_with_valid_mean": len(late_available),
            "days_without_valid_mean": len(late) - len(late_available),
            "qa_valid_fraction_range": [round(float(np.min(late_fractions)), 10), round(float(np.max(late_fractions)), 10)],
            "qa_valid_fraction_mean": round(float(np.mean(late_fractions)), 10),
            "available_radiance_mean_range_nw_cm2_sr": (
                [round(float(np.min(late_means)), 10), round(float(np.max(late_means)), 10)]
                if len(late_means)
                else [None, None]
            ),
            "daily_observations": [daily_record(row) for _, row in late.iterrows()],
            "interpretation_limit": (
                "These isolated observations occur about 16 months later and have unstable strict-QA "
                "coverage. Season, lunar illumination, weather, land-cover/development change, and the "
                "long interval are confounded; they are not a recovery trajectory or recovery rate."
            ),
        },
    }


def write_tidy_table(frame: pd.DataFrame, analyses: dict[int, dict[str, Any]]) -> None:
    fields = [
        "record_type",
        "aoi_radius_km",
        "utc_product_date",
        "local_night_date_asia_yangon",
        "qa_valid_pixel_count",
        "aoi_pixel_count",
        "qa_valid_fraction",
        "radiance_mean_nw_cm2_sr",
        "radiance_median_nw_cm2_sr",
        "baseline_mean_of_daily_means_nw_cm2_sr",
        "baseline_median_of_daily_means_nw_cm2_sr",
        "baseline_daily_mean_sample_std_nw_cm2_sr",
        "first_night_absolute_difference_nw_cm2_sr",
        "first_night_percent_difference",
        "z_like_location",
        "empirical_percentile_among_pre_daily_means",
        "note",
    ]
    rows: list[dict[str, Any]] = []
    for radius in AOI_RADII:
        analysis = analyses[radius]
        baseline = analysis["baseline"]
        comparison = analysis["first_night_relative_to_baseline"]
        subset = frame[frame["aoi_radius_km"].astype(int) == radius].sort_values("utc_product_date")
        for _, item in subset.iterrows():
            relation = item["temporal_relation"]
            if relation == "pre_event_local_night":
                record_type = "pre_event_daily_observation"
            elif relation == "first_post_event_local_night_interpreted":
                record_type = "first_post_event_local_night"
            else:
                record_type = "late_followup_observation"
            rows.append(
                {
                    "record_type": record_type,
                    "aoi_radius_km": radius,
                    "utc_product_date": item["utc_product_date"],
                    "local_night_date_asia_yangon": item["interpreted_local_night_date_asia_yangon"],
                    "qa_valid_pixel_count": int(item["qa_valid_pixel_count"]),
                    "aoi_pixel_count": int(item["aoi_pixel_count"]),
                    "qa_valid_fraction": round_or_none(item["qa_valid_fraction"]),
                    "radiance_mean_nw_cm2_sr": round_or_none(item["radiance_mean_nw_cm2_sr"]),
                    "radiance_median_nw_cm2_sr": round_or_none(item["radiance_median_nw_cm2_sr"]),
                    "baseline_mean_of_daily_means_nw_cm2_sr": (
                        baseline["mean_of_daily_means_nw_cm2_sr"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "baseline_median_of_daily_means_nw_cm2_sr": (
                        baseline["median_of_daily_means_nw_cm2_sr"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "baseline_daily_mean_sample_std_nw_cm2_sr": (
                        baseline["sample_std_of_daily_means_nw_cm2_sr"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "first_night_absolute_difference_nw_cm2_sr": (
                        comparison["absolute_mean_difference_nw_cm2_sr"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "first_night_percent_difference": (
                        comparison["percent_mean_difference"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "z_like_location": (
                        comparison["z_like_location_using_pre_daily_sample_std"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "empirical_percentile_among_pre_daily_means": (
                        comparison["empirical_percentile_among_pre_daily_means"]
                        if record_type == "first_post_event_local_night"
                        else None
                    ),
                    "note": (
                        "Missing: zero strict-QA valid pixels; not treated as zero radiance."
                        if pd.isna(item["radiance_mean_nw_cm2_sr"])
                        else (
                            "About 16 months later; descriptive late follow-up only, not recovery."
                            if record_type == "late_followup_observation"
                            else ""
                        )
                    ),
                }
            )

    with TABLE_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})


def make_preview(frame: pd.DataFrame, analyses: dict[int, dict[str, Any]]) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 6.8), constrained_layout=True)
    colors = {25: "#1874CD", 50: "#2E8B57"}
    for row_index, radius in enumerate(AOI_RADII):
        subset = frame[frame["aoi_radius_km"].astype(int) == radius].copy()
        event_window = subset[subset["utc_product_date"].between(PRE_START, FIRST_POST_UTC)].copy()
        event_window["date"] = pd.to_datetime(event_window["utc_product_date"])
        pre = event_window[event_window["utc_product_date"] != FIRST_POST_UTC]
        post = event_window[event_window["utc_product_date"] == FIRST_POST_UTC]
        ax = axes[row_index, 0]
        ax.plot(
            pre["date"],
            pre["radiance_mean_nw_cm2_sr"],
            color=colors[radius],
            marker="o",
            linewidth=1.6,
            label="Pre-event daily mean",
        )
        missing = pre[pre["radiance_mean_nw_cm2_sr"].isna()]
        if not missing.empty:
            ax.scatter(
                missing["date"],
                np.zeros(len(missing)),
                marker="x",
                s=45,
                color="#777777",
                label="No strict-QA pixels (missing)",
                zorder=5,
            )
        baseline = analyses[radius]["baseline"]["mean_of_daily_means_nw_cm2_sr"]
        ax.axhline(baseline, color="#555555", linestyle="--", linewidth=1.1, label="Pre-event baseline")
        ax.scatter(
            post["date"],
            post["radiance_mean_nw_cm2_sr"],
            color="#C0392B",
            marker="D",
            s=52,
            label="First post-event local night",
            zorder=6,
        )
        pct = analyses[radius]["first_night_relative_to_baseline"]["percent_mean_difference"]
        ax.annotate(
            f"{pct:+.1f}%",
            (post["date"].iloc[0], post["radiance_mean_nw_cm2_sr"].iloc[0]),
            xytext=(-2, 12),
            textcoords="offset points",
            ha="right",
            color="#922B21",
            fontweight="bold",
        )
        ax.set_title(f"{radius} km AOI: event-window daily means")
        ax.set_ylabel("Radiance (nW cm$^{-2}$ sr$^{-1}$)")
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
        ax.tick_params(axis="x", rotation=30)
        ax.legend(loc="best", frameon=False)

        late = subset[subset["temporal_relation"] == "late_followup_observation"].copy()
        late["date"] = pd.to_datetime(late["utc_product_date"])
        ax_late = axes[row_index, 1]
        sizes = 22 + 115 * late["qa_valid_fraction"].to_numpy(dtype=float)
        available = late[late["radiance_mean_nw_cm2_sr"].notna()]
        available_sizes = sizes[late["radiance_mean_nw_cm2_sr"].notna().to_numpy()]
        ax_late.scatter(
            available["date"],
            available["radiance_mean_nw_cm2_sr"],
            s=available_sizes,
            color=colors[radius],
            alpha=0.55,
            edgecolor="white",
            linewidth=0.5,
            label="Available mean (size = QA coverage)",
        )
        late_missing = late[late["radiance_mean_nw_cm2_sr"].isna()]
        if not late_missing.empty:
            ax_late.scatter(
                late_missing["date"],
                np.zeros(len(late_missing)),
                marker="x",
                s=45,
                color="#777777",
                label="No strict-QA pixels (missing)",
            )
        ax_late.set_title(f"{radius} km AOI: late follow-up observations")
        ax_late.set_ylabel("Radiance (nW cm$^{-2}$ sr$^{-1}$)")
        ax_late.grid(axis="y", color="#DDDDDD", linewidth=0.7)
        ax_late.tick_params(axis="x", rotation=30)
        ax_late.legend(loc="best", frameon=False)

    fig.suptitle(
        "Myanmar earthquake case: strict-QA nighttime-light observations\n"
        "Late follow-up is shown separately and is not a recovery trajectory",
        fontsize=12,
        fontweight="bold",
    )
    fig.savefig(PREVIEW_PATH, dpi=220, facecolor="white")
    plt.close(fig)


def main() -> None:
    event, package, frame, input_validation = load_and_validate_inputs()
    analyses = {radius: analyze_aoi(frame, radius) for radius in AOI_RADII}

    directions = {
        radius: (
            "decrease"
            if analyses[radius]["first_night_relative_to_baseline"]["absolute_mean_difference_nw_cm2_sr"] < 0
            else "increase"
            if analyses[radius]["first_night_relative_to_baseline"]["absolute_mean_difference_nw_cm2_sr"] > 0
            else "no_change"
        )
        for radius in AOI_RADII
    }
    direction_consistent = len(set(directions.values())) == 1

    write_tidy_table(frame, analyses)
    make_preview(frame, analyses)

    generated_at = datetime.now(timezone.utc).isoformat()
    results: dict[str, Any] = {
        "schema": "ntl.q18.formal-analysis.v2",
        "task_id": "Q18-myanmar-earthquake",
        "role": "NTL Analyst",
        "status": "complete_descriptive_noncausal",
        "generated_at_utc": generated_at,
        "formal_inputs_only": True,
        "event_anchor": {
            "usgs_event_id": event["primary_event"]["event_id_usgs"],
            "origin_time_utc": event["primary_event"]["origin_time_utc"],
            "origin_time_local": event["primary_event"]["origin_time_local"],
            "timezone": event["primary_event"]["local_timezone"],
            "magnitude": event["primary_event"]["magnitude"]["display"],
            "epicenter_wgs84_lon_lat": event["primary_event"]["epicenter"]["coordinate_order_lon_lat"],
            "subsequent_earthquake_source_conflict_preserved": True,
        },
        "date_semantics": {
            "pre_event_utc_product_dates": [PRE_START, PRE_END],
            "first_post_event_utc_product_date": FIRST_POST_UTC,
            "first_post_event_interpreted_local_night_asia_yangon": FIRST_POST_LOCAL_NIGHT,
            "statement": (
                "The 2025-03-28 UTC product is interpreted as the first post-event local night, "
                "2025-03-29 in Asia/Yangon; this is a product-date convention rather than an "
                "instantaneous measurement at the mainshock time."
            ),
        },
        "analysis_contract": {
            "baseline": "Equal-weighted valid daily AOI radiance means for 2025-03-21 through 2025-03-27 UTC; missing days are excluded, never assigned zero.",
            "comparison": "First post-event local-night mean minus the pre-event mean of daily means.",
            "diagnostics": "Sample-standard-deviation z-like location, empirical rank, and leave-one-day-out ranges; descriptive only.",
            "late_followup": "Listed separately; no line is drawn across the approximately 16-month gap and no recovery rate is estimated.",
        },
        "aoi_results": {str(radius): analyses[radius] for radius in AOI_RADII},
        "spatial_sensitivity": {
            "first_night_direction_by_aoi": {str(key): value for key, value in directions.items()},
            "direction_consistent_between_25km_and_50km": direction_consistent,
            "interpretation": (
                "The first-night direction is consistent across AOIs."
                if direction_consistent
                else (
                    "The 25 km and 50 km AOIs show opposite first-night directions relative to "
                    "their own pre-event baselines. Therefore the result is spatial-scale sensitive "
                    "and does not support a scale-robust change claim."
                )
            ),
        },
        "claim_boundary": {
            "supported": (
                "A transparent descriptive comparison of strict-QA nighttime-light observations "
                "for two AOI radii."
            ),
            "not_supported": [
                "earthquake causation",
                "power outage inference",
                "physical damage inference",
                "recovery trajectory or recovery rate",
                "statistical significance from the small pre-event sample",
            ],
            "confounders": [
                "cloud and QA coverage",
                "season and weather",
                "lunar illumination",
                "land-cover and development change",
                "the approximately 16-month interval to late follow-up observations",
                "the source-conflicted strong subsequent earthquake reported within minutes",
            ],
        },
        "validation": {
            "input_validation_checks_inherited_and_rechecked": input_validation["checks"],
            "event_and_local_date_semantics_rechecked": True,
            "core_differences_independently_recomputed": True,
            "missing_values_serialized_as_json_null_and_csv_blank": True,
            "nan_or_inf_emitted": False,
            "outputs_reopened": False,
            "input_hashes_sha256": {
                EVENT_PATH.name: sha256(EVENT_PATH),
                PACKAGE_PATH.name: sha256(PACKAGE_PATH),
                INPUT_CSV_PATH.name: sha256(INPUT_CSV_PATH),
                INPUT_VALIDATION_PATH.name: sha256(INPUT_VALIDATION_PATH),
            },
            "output_hashes_sha256_excluding_results_json": {
                TABLE_PATH.name: sha256(TABLE_PATH),
                PREVIEW_PATH.name: sha256(PREVIEW_PATH),
            },
        },
        "provenance": {
            "observation_package_schema": package["schema"],
            "historical_outputs_read": False,
            "gold_or_benchmark_outputs_read": False,
            "legacy_script_read": False,
        },
    }

    with RESULTS_PATH.open("w", encoding="utf-8") as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

    # Reopen every produced artifact and independently recompute the core deltas.
    with RESULTS_PATH.open("r", encoding="utf-8") as stream:
        reopened = json.load(stream)
    reopened_table = pd.read_csv(TABLE_PATH)
    assert len(reopened_table) == len(frame)
    assert PREVIEW_PATH.stat().st_size > 10_000
    for radius in AOI_RADII:
        pre_values = frame[
            (frame["aoi_radius_km"].astype(int) == radius)
            & frame["utc_product_date"].between(PRE_START, PRE_END)
        ]["radiance_mean_nw_cm2_sr"].dropna().to_numpy(dtype=float)
        post_value = float(
            frame[
                (frame["aoi_radius_km"].astype(int) == radius)
                & (frame["utc_product_date"] == FIRST_POST_UTC)
            ]["radiance_mean_nw_cm2_sr"].iloc[0]
        )
        recomputed_delta = post_value - float(np.mean(pre_values))
        saved_delta = reopened["aoi_results"][str(radius)]["first_night_relative_to_baseline"][
            "absolute_mean_difference_nw_cm2_sr"
        ]
        assert math.isclose(recomputed_delta, saved_delta, rel_tol=0, abs_tol=1e-9)

    reopened["validation"]["outputs_reopened"] = True
    reopened["validation"]["core_differences_independently_recomputed"] = True
    with RESULTS_PATH.open("w", encoding="utf-8") as stream:
        json.dump(reopened, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

    hashes = {
        "run_formal_q18_analysis.py": sha256(Path(__file__)),
        EVENT_PATH.name: sha256(EVENT_PATH),
        PACKAGE_PATH.name: sha256(PACKAGE_PATH),
        INPUT_CSV_PATH.name: sha256(INPUT_CSV_PATH),
        INPUT_VALIDATION_PATH.name: sha256(INPUT_VALIDATION_PATH),
        RESULTS_PATH.name: sha256(RESULTS_PATH),
        TABLE_PATH.name: sha256(TABLE_PATH),
        PREVIEW_PATH.name: sha256(PREVIEW_PATH),
    }

    lines = [
        "# Q18 Formal NTL Analyst Log",
        "",
        f"- Completed (UTC): `{generated_at}`",
        "- Role: `NTL Analyst`",
        "- Supervisor: `NTL Engineer`",
        "- Status: `complete_descriptive_noncausal`",
        "- Formal inputs only: yes",
        "- Historical summaries, manuscript values, benchmark outputs/Gold, and legacy scripts read: no",
        "",
        "## Fixed analysis",
        "",
        f"- Pre-event baseline: valid daily means from `{PRE_START}` to `{PRE_END}` UTC, equally weighted.",
        "- A zero-valid-pixel day is missing and was not converted to zero radiance.",
        f"- First post-event local night: `{FIRST_POST_UTC}` UTC product, interpreted as `{FIRST_POST_LOCAL_NIGHT}` Asia/Yangon.",
        "- AOIs: 25 km primary and 50 km spatial-sensitivity support.",
        "- Late 2026-07 observations are listed separately and are not treated as recovery.",
        "",
        "## Core results",
        "",
    ]
    for radius in AOI_RADII:
        item = reopened["aoi_results"][str(radius)]
        base = item["baseline"]
        post = item["first_post_event_local_night"]
        comp = item["first_night_relative_to_baseline"]
        lines.append(
            f"- **{radius} km:** baseline mean `{base['mean_of_daily_means_nw_cm2_sr']:.6f}` "
            f"(n={base['valid_daily_mean_n']}, sample SD `{base['sample_std_of_daily_means_nw_cm2_sr']:.6f}`); "
            f"first-night mean `{post['mean_nw_cm2_sr']:.6f}`; difference "
            f"`{comp['absolute_mean_difference_nw_cm2_sr']:+.6f}` "
            f"(`{comp['percent_mean_difference']:+.2f}%`)."
        )
    lines.extend(
        [
            "",
            f"Spatial-direction consistency: `{reopened['spatial_sensitivity']['direction_consistent_between_25km_and_50km']}`.",
            reopened["spatial_sensitivity"]["interpretation"],
            "",
            "These are descriptive nighttime-light observations. They do not establish outage, damage, earthquake causation, statistical significance, or recovery.",
            "",
            "## Validation",
            "",
            "- Reopened JSON, CSV, and PNG: passed.",
            "- Recomputed both core differences from the formal input CSV: passed.",
            "- JSON NaN/Inf protection (`allow_nan=False`): passed.",
            "- Missing values use JSON `null` and blank CSV cells: passed.",
            "- Mainshock/local-date semantics rechecked: passed.",
            "",
            "## SHA-256",
            "",
        ]
    )
    lines.extend([f"- `{name}`: `{digest}`" for name, digest in hashes.items()])
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- The pre-event sample is small (six valid daily means at 25 km; seven at 50 km).",
            "- QA coverage varies by date and is extremely unstable in the late follow-up subset.",
            "- Season, lunar illumination, weather, land-cover/development change, and the long interval remain confounded.",
            "- A strong subsequent earthquake was reported within minutes, but the supplied sources conflict on its magnitude; the conflict is preserved.",
            "",
        ]
    )
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": "complete_descriptive_noncausal",
        "results": str(RESULTS_PATH),
        "table": str(TABLE_PATH),
        "preview": str(PREVIEW_PATH),
        "log": str(LOG_PATH),
        "core": {
            str(radius): reopened["aoi_results"][str(radius)]["first_night_relative_to_baseline"]
            for radius in AOI_RADII
        },
        "spatial_sensitivity": reopened["spatial_sensitivity"],
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
