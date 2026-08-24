"""Recompute Case 202 windows and render the latest-available line chart.

The chart is a style-only adaptation of the accepted Tehran time-series: it
uses the same UTC windows, actual strict-QA daily means, and the author-set
14-calendar-day / three-observation display rule.  It does not interpolate
daily radiance or change the event-selection contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile


CASE_ID = "Case202-tehran-latest-vnp46a2"
ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT.parents[1]
LEGACY_RESULTS = (
    WORK_ROOT
    / "experiments"
    / "paper-case-codex-subagent-rerun-2026-08-17"
    / "role-outputs"
    / "analyst-recovery"
    / "q19-analysis-results.json"
)
START = pd.Timestamp("2026-01-01")
WINDOWS = (
    ("pre_conflict_baseline", "Pre-conflict baseline", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-27"), "#E8F1FF"),
    ("conflict_evaluation", "Conflict evaluation", pd.Timestamp("2026-02-28"), pd.Timestamp("2026-04-07"), "#FFE5E5"),
    ("ceasefire_evaluation", "Ceasefire evaluation", pd.Timestamp("2026-04-08"), pd.Timestamp("2026-04-21"), "#E8F5E9"),
)
EXTENDED_COLOR = "#EEEEEE"
DAILY_GREY = "#9EA5AD"
ROLLING_BLUE = "#1A5AA3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_bool(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().eq("true")


def load_daily(root: Path) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    daily = pd.read_csv(root / "daily-vnp46a2.csv", parse_dates=["date_utc"])
    daily["image_available_bool"] = as_bool(daily["image_available"])
    daily["qualified_bool"] = as_bool(daily["qualified"])
    daily["mean"] = pd.to_numeric(daily["mean"], errors="coerce")
    daily["valid_fraction"] = pd.to_numeric(daily["valid_fraction"], errors="coerce")
    if daily.duplicated(["date_utc", "qa_mode"]).any():
        raise RuntimeError("Daily table has duplicate UTC-date / QA-mode keys")
    if daily["date_utc"].min() != START:
        raise RuntimeError("Daily table does not begin on the frozen 2026-01-01 UTC baseline")
    invalid = daily.loc[~daily["qualified_bool"], "mean"].notna()
    if invalid.any():
        raise RuntimeError("Unqualified rows contain numerical radiance values")
    latest_image = daily.loc[daily["image_available_bool"], "date_utc"].max()
    strict = daily.loc[(daily["qa_mode"] == "strict") & daily["qualified_bool"]].copy()
    latest_strict = strict["date_utc"].max()
    if pd.isna(latest_image) or pd.isna(latest_strict):
        raise RuntimeError("No image or strict-qualified observation is available")
    return daily, latest_image, latest_strict


def summarize_mode(
    daily: pd.DataFrame,
    mode: str,
    collection_end: pd.Timestamp,
    latest_strict: pd.Timestamp,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mode_rows = daily.loc[daily["qa_mode"] == mode].copy()
    baseline = mode_rows.loc[
        (mode_rows["date_utc"] >= WINDOWS[0][2])
        & (mode_rows["date_utc"] <= WINDOWS[0][3])
        & mode_rows["qualified_bool"]
    ]
    baseline_mean = float(baseline["mean"].mean())
    spans = [*WINDOWS, ("extended_monitoring", "Extended monitoring", pd.Timestamp("2026-04-22"), collection_end, EXTENDED_COLOR)]
    for window_id, label, start, end, _color in spans:
        selected = mode_rows.loc[
            (mode_rows["date_utc"] >= start)
            & (mode_rows["date_utc"] <= end)
            & mode_rows["qualified_bool"]
        ]
        mean = float(selected["mean"].mean()) if len(selected) else None
        pct = ((mean - baseline_mean) / baseline_mean * 100.0) if mean is not None else None
        rows.append(
            {
                "qa_mode": mode,
                "window_id": window_id,
                "label": label,
                "start_date_utc": start.date().isoformat(),
                "end_date_utc": end.date().isoformat(),
                "inclusive_calendar_days": int((end - start).days + 1),
                "image_available_days": int(mode_rows.loc[(mode_rows["date_utc"] >= start) & (mode_rows["date_utc"] <= end), "image_available_bool"].sum()),
                "qualified_days": int(len(selected)),
                "mean_of_daily_means": mean,
                "relative_change_vs_baseline_percent": pct,
                "valid_fraction_mean": float(selected["valid_fraction"].mean()) if len(selected) else None,
                "valid_fraction_median": float(selected["valid_fraction"].median()) if len(selected) else None,
                "analysis_collection_endpoint_utc": collection_end.date().isoformat(),
                "analysis_uses_latest_strict_qualified_date": latest_strict.date().isoformat(),
                "no_imputation": True,
            }
        )
    return rows


def plot_gap_aware_daily(ax: plt.Axes, observed: pd.Series) -> None:
    values = observed.loc[observed.notna()].sort_index()
    ax.scatter(values.index, values.values, color=DAILY_GREY, s=11, zorder=3, linewidths=0)
    for (previous_date, previous_value), (current_date, current_value) in zip(values.iloc[:-1].items(), values.iloc[1:].items()):
        gap = current_date - previous_date
        ax.plot(
            [previous_date, current_date],
            [previous_value, current_value],
            color=DAILY_GREY,
            linewidth=0.75 if gap.days == 1 else 0.65,
            linestyle="-" if gap.days == 1 else (0, (2, 2)),
            alpha=0.84 if gap.days == 1 else 0.72,
            zorder=2,
        )
def configure_plot_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            # Author-requested 1.5× enlargement for the remaining figure text.
            "font.size": 12.0,
            "axes.labelsize": 12.6,
            "xtick.labelsize": 10.8,
            "ytick.labelsize": 10.8,
            "axes.linewidth": 0.75,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "legend.frameon": False,
        }
    )


def make_figure(
    root: Path,
    strict: pd.DataFrame,
    collection_end: pd.Timestamp,
    latest_strict: pd.Timestamp,
) -> tuple[list[Path], dict[str, Any]]:
    configure_plot_style()
    observed = strict.set_index("date_utc")["mean"].astype(float).sort_index()
    # The x-axis reaches the live GEE collection endpoint. Observed values stop
    # at the last strict-qualified date; the later dates remain explicit gaps.
    calendar = pd.date_range(START, collection_end, freq="D")
    actual_daily = observed.reindex(calendar)
    rolling = actual_daily.rolling("14D", min_periods=3).mean()
    # The summary terminates at the last actual strict-qualified observation;
    # it is never projected into dates with no strict-qualified source value.
    rolling = rolling.where(rolling.index <= latest_strict)

    width_mm = 183.0
    height_mm = 80.0
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, height_mm / 25.4), dpi=600)
    # Keep the standalone plot compositing-ready for the author's Draw.io
    # layout: canvas and axes carry no opaque white rectangle.
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")
    for _id, _label, start, end, color in WINDOWS:
        ax.axvspan(start, end + pd.Timedelta(days=1), color=color, zorder=0)
    ax.axvspan(pd.Timestamp("2026-04-22"), collection_end + pd.Timedelta(days=1), color=EXTENDED_COLOR, zorder=0)
    plot_gap_aware_daily(ax, actual_daily)
    ax.plot(
        rolling.index,
        rolling.values,
        color=ROLLING_BLUE,
        linewidth=1.65,
        zorder=4,
    )
    last_observed = actual_daily.loc[actual_daily.notna()]
    last_rolling = rolling.loc[rolling.notna()]
    if collection_end > latest_strict and not last_rolling.empty:
        # Both terminal dashed segments are visual-only.  The grey line carries
        # the final actual daily observation to the live collection endpoint;
        # the blue line does the same for the final supported 14-day estimate.
        # Neither is an imputed ANTL value or part of the window summaries.
        ax.plot(
            [last_observed.index[-1], collection_end],
            [float(last_observed.iloc[-1]), float(last_observed.iloc[-1])],
            color=DAILY_GREY,
            linewidth=0.65,
            linestyle=(0, (2, 2)),
            alpha=0.72,
            zorder=3.5,
        )
        ax.plot(
            [last_rolling.index[-1], collection_end],
            [float(last_rolling.iloc[-1]), float(last_rolling.iloc[-1])],
            color=ROLLING_BLUE,
            linewidth=1.45,
            linestyle=(0, (3, 2)),
            alpha=0.90,
            zorder=4,
        )

    # End exactly at the current collection endpoint so the terminal connector
    # visibly reaches the final available product day rather than stopping in
    # a one-day blank margin.
    ax.set_xlim(START, collection_end)
    visible = actual_daily.loc[actual_daily.notna()]
    spread = float(visible.max() - visible.min())
    pad = max(2.0, spread * 0.07)
    ax.set_ylim(max(0.0, float(visible.min()) - pad), float(visible.max()) + pad)
    ax.set_ylabel("ANTL (nW cm$^{-2}$ sr$^{-1}$)")
    ax.set_xlabel("UTC product day, 2026")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(axis="y", color="#D6D6D6", linewidth=0.45, zorder=0)

    # Legend and event annotations are deliberately omitted: the author will
    # place those explanatory elements in the surrounding Draw.io composition.
    fig.subplots_adjust(left=0.135, right=0.988, top=0.96, bottom=0.245)

    outputs = root / "outputs"
    outputs.mkdir(exist_ok=True)
    stem = outputs / "case202-tehran-latest-timeseries"
    paths = []
    for suffix in (".svg", ".pdf", ".png"):
        path = stem.with_suffix(suffix)
        kwargs: dict[str, Any] = {"bbox_inches": "tight", "pad_inches": 0, "transparent": True}
        if suffix == ".png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        paths.append(path)
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba()).copy()
    tiff_path = stem.with_suffix(".tiff")
    tifffile.imwrite(
        tiff_path,
        rgba,
        photometric="rgb",
        extrasamples="UNASSALPHA",
        resolution=(600, 600),
        resolutionunit="INCH",
        metadata=None,
    )
    paths.append(tiff_path)
    plt.close(fig)
    return paths, {
        "style_reuse": "Style-only inheritance from the prior Tehran line-chart family; statistical inputs and endpoint were recomputed.",
        "annotation_policy": "No in-plot legend, event label, or event marker is rendered at the author's request; those explanatory elements belong to the surrounding Draw.io composition.",
        "rolling_display": "Trailing 14-calendar-day mean of actual strict-QA daily means, with min_periods=3. No daily value interpolation is performed.",
        "post_qualification_gap_connector": "Grey and blue horizontal dashed continuations extend the final actual daily observation and final supported 14-day mean, respectively, to the live GEE collection endpoint. They are visual missing-data connectors only, not observed or imputed ANTL values, and are excluded from all statistics.",
        "gap_connector": "Thin dashed grey segments connect consecutive observed daily means separated by more than one UTC day, including a terminal horizontal segment to the live collection endpoint; they are visual continuity only.",
        "display_endpoint_collection_image_date_utc": collection_end.date().isoformat(),
        "latest_strict_qualified_date_utc": latest_strict.date().isoformat(),
    }


def build_results(
    root: Path,
    daily: pd.DataFrame,
    summary: pd.DataFrame,
    latest_image: pd.Timestamp,
    latest_strict: pd.Timestamp,
    paths: list[Path],
    figure_notes: dict[str, Any],
) -> dict[str, Any]:
    legacy = json.loads(LEGACY_RESULTS.read_text(encoding="utf-8"))
    strict_summary = summary.loc[summary["qa_mode"] == "strict"].to_dict(orient="records")
    legacy_windows = {row["window_id"]: row for row in legacy["strict_primary"]["windows"]}
    legacy_key = {
        "pre_conflict_baseline": "baseline",
        "conflict_evaluation": "conflict",
        "ceasefire_evaluation": "ceasefire_evaluation",
        "extended_monitoring": "extended_monitoring",
    }
    change = {}
    for row in strict_summary:
        previous = legacy_windows.get(legacy_key[row["window_id"]])
        change[row["window_id"]] = {
            "prior_mean_of_daily_means": previous.get("mean_of_daily_means") if previous else None,
            "current_mean_of_daily_means": row["mean_of_daily_means"],
            "mean_difference": (
                row["mean_of_daily_means"] - previous["mean_of_daily_means"]
                if previous and row["mean_of_daily_means"] is not None
                else None
            ),
            "prior_relative_change_vs_baseline_percent": previous.get("relative_change_vs_baseline_percent") if previous else None,
            "current_relative_change_vs_baseline_percent": row["relative_change_vs_baseline_percent"],
        }
    return {
        "schema_version": "ntl.case202.tehran-latest-analysis.v1",
        "case_id": CASE_ID,
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "time_basis": "UTC product day",
        "product": {"collection_id": "NASA/VIIRS/002/VNP46A2", "band": "DNB_BRDF_Corrected_NTL", "gap_filled_band_used": False},
        "aoi": "Existing geoBoundaries City of Tehran ADM2 / canonical Shahrestan polygon; no event-point buffer.",
        "availability": {
            "live_latest_collection_image_date_utc": latest_image.date().isoformat(),
            "latest_strict_qualified_date_utc": latest_strict.date().isoformat(),
            "calendar_days_through_latest_collection_image": int((latest_image - START).days + 1),
            "calendar_days_through_latest_strict_qualified_observation": int((latest_strict - START).days + 1),
            "strict_qualified_days": int(((daily["qa_mode"] == "strict") & daily["qualified_bool"]).sum()),
            "permissive_qualified_days": int(((daily["qa_mode"] == "permissive") & daily["qualified_bool"]).sum()),
        },
        "strict_primary_window_summary": strict_summary,
        "permissive_sensitivity_window_summary": summary.loc[summary["qa_mode"] == "permissive"].to_dict(orient="records"),
        "comparison_with_2026_08_17": change,
        "figure": {"artifacts": [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for path in paths], **figure_notes},
        "validation": {
            "daily_rows": int(len(daily)),
            "daily_unique_keys": not daily.duplicated(["date_utc", "qa_mode"]).any(),
            "unqualified_rows_have_no_radiance": not daily.loc[~daily["qualified_bool"], "mean"].notna().any(),
            "strict_window_rows": len(strict_summary),
            "fixed_window_definitions_unchanged": all(row["end_date_utc"] in {"2026-02-27", "2026-04-07", "2026-04-21"} for row in strict_summary[:3]),
            "no_imputation": True,
        },
        "limitations": [
            "The post-2026-04-21 span is a neutral extended-monitoring period, not a uniform ceasefire, recovery, or peace phase.",
            "Nighttime-light observations do not establish conflict causation, damage, outage, recovery, or a statistically significant effect.",
            "The AOI is a geoBoundaries ADM2 canonical Shahrestan reporting unit, not a municipality or functional urban footprint.",
            "Event-timeline context remains in the evidence record and is intentionally not rendered in the standalone line chart.",
        ],
    }


def run(root: Path) -> None:
    daily, latest_image, latest_strict = load_daily(root)
    summaries = [
        *summarize_mode(daily, "strict", latest_image, latest_strict),
        *summarize_mode(daily, "permissive", latest_image, latest_strict),
    ]
    summary = pd.DataFrame(summaries)
    output_dir = root / "outputs"
    output_dir.mkdir(exist_ok=True)
    summary.to_csv(output_dir / "analysis-window-summary.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    strict = daily.loc[(daily["qa_mode"] == "strict") & daily["qualified_bool"]].copy()
    paths, figure_notes = make_figure(root, strict, latest_image, latest_strict)
    results = build_results(root, daily, summary, latest_image, latest_strict, paths, figure_notes)
    write_json(output_dir / "analysis-results.json", results)
    qa = {
        "schema_version": "ntl.case202.analysis-qa.v1",
        "passed": all(results["validation"].values()),
        "checks": results["validation"],
        "source_daily_csv_sha256": sha256(root / "daily-vnp46a2.csv"),
        "result_sha256": sha256(output_dir / "analysis-results.json"),
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    write_json(root / "qa" / "analysis-qa.json", qa)
    if not qa["passed"]:
        raise RuntimeError("Analysis validation did not pass")
    print(json.dumps({"latest_image_utc": latest_image.date().isoformat(), "latest_strict_qualified_utc": latest_strict.date().isoformat(), "strict_summary": results["strict_primary_window_summary"], "figure": [p.name for p in paths]}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
