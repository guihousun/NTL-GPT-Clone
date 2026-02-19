from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))


def compute_lead_days(official_latest_date: str | None, gee_latest_date: str | None) -> int | None:
    if not official_latest_date or not gee_latest_date:
        return None
    try:
        off = datetime.strptime(official_latest_date, "%Y-%m-%d")
        gee = datetime.strptime(gee_latest_date, "%Y-%m-%d")
    except ValueError:
        return None
    return (off - gee).days


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official Daily NTL fast-path experiment runner.")
    parser.add_argument("--study-area", required=True, help="Administrative area name, e.g., 上海市 / Yangon, Myanmar.")
    parser.add_argument(
        "--sources",
        default="nrt_priority",
        help="Comma-separated source list or profile name: nrt_priority.",
    )
    parser.add_argument("--mode", default="latest", choices=["latest", "range"], help="latest or range")
    parser.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD) for range mode.")
    parser.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD) for range mode.")
    parser.add_argument(
        "--workspace",
        default="experiments/official_daily_ntl_fastpath/workspace",
        help="Workspace root for this experiment.",
    )
    parser.add_argument("--is-in-china", default=None, choices=["true", "false"], help="Optional explicit region flag.")
    parser.add_argument(
        "--earthdata-token-env",
        default="EARTHDATA_TOKEN",
        help="Environment variable name for Earthdata bearer token.",
    )
    return parser.parse_args()


def _parse_mode_dates(mode: str, start_date: str | None, end_date: str | None) -> tuple[str, str]:
    if mode == "latest":
        end_dt = datetime.now(UTC).date()
        start_dt = end_dt - timedelta(days=45)
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    if not start_date or not end_date:
        raise ValueError("range mode requires --start-date and --end-date (YYYY-MM-DD).")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_dt < start_dt:
        raise ValueError("end-date must not be earlier than start-date.")
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _normalize_is_in_china(raw: str | None) -> bool | None:
    if raw is None:
        return None
    key = raw.strip().lower()
    if key == "true":
        return True
    if key == "false":
        return False
    return None


def _write_report_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source",
        "status",
        "latest_available_date",
        "gee_latest_date",
        "lead_days_vs_gee",
        "image_output",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source": row.get("source"),
                    "status": row.get("status"),
                    "latest_available_date": row.get("latest_available_date"),
                    "gee_latest_date": row.get("gee_latest_date"),
                    "lead_days_vs_gee": row.get("lead_days_vs_gee"),
                    "image_output": ";".join(row.get("image_output", [])),
                    "notes": row.get("notes", ""),
                }
            )


def run() -> dict[str, Any]:
    from experiments.official_daily_ntl_fastpath.boundary_resolver import resolve_boundary
    from experiments.official_daily_ntl_fastpath.cmr_client import (
        group_granules_by_day,
        latest_granule_day,
        resolve_token,
        search_granules,
        select_latest_day_entries,
    )
    from experiments.official_daily_ntl_fastpath.gee_baseline import query_gee_latest_date_for_bbox
    from experiments.official_daily_ntl_fastpath.gridded_pipeline import process_gridded_day
    from experiments.official_daily_ntl_fastpath.noaa20_feasibility import evaluate_noaa20_feasibility
    from experiments.official_daily_ntl_fastpath.source_registry import get_source_spec, parse_sources_arg

    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    is_in_china = _normalize_is_in_china(args.is_in_china)
    boundary = resolve_boundary(study_area=args.study_area, workspace=workspace, is_in_china=is_in_china)
    start_date, end_date = _parse_mode_dates(args.mode, args.start_date, args.end_date)
    sources = parse_sources_arg(args.sources)

    gee_latest, gee_err = query_gee_latest_date_for_bbox(boundary.bbox)
    token = resolve_token(args.earthdata_token_env)
    token_present = bool(token)

    rows: list[dict[str, Any]] = []
    for source in sources:
        spec = get_source_spec(source)
        if spec.processing_mode == "feasibility_only":
            feasibility = evaluate_noaa20_feasibility(
                short_name=source,
                bbox=boundary.bbox,
                start_date=start_date,
                end_date=end_date,
                workspace=workspace,
                token_present=token_present,
                night_only=spec.night_only,
            )
            latest_date = feasibility.get("latest_available_date") or feasibility.get("latest_night_date")
            row = {
                "source": source,
                "status": feasibility.get("status", "unknown"),
                "latest_available_date": latest_date,
                "gee_latest_date": gee_latest,
                "lead_days_vs_gee": compute_lead_days(latest_date, gee_latest),
                "image_output": [],
                "notes": (
                    "feasibility_only; "
                    + feasibility.get("compatibility", {}).get("reason", "")
                    + (f" gee_error={gee_err}" if gee_err else "")
                ),
            }
            rows.append(row)
            continue

        granules = search_granules(
            short_name=source,
            start_date=start_date,
            end_date=end_date,
            bbox=boundary.bbox,
            page_size=200,
        )
        latest_date = latest_granule_day(granules, night_only=spec.night_only)
        if args.mode == "latest":
            day, entries = select_latest_day_entries(granules, night_only=spec.night_only)
            selected = {day: entries} if day and entries else {}
        else:
            selected = group_granules_by_day(granules, night_only=spec.night_only)

        image_outputs: list[str] = []
        notes: list[str] = []
        status = "no_data"

        if not selected:
            status = "no_data"
        elif not token_present:
            status = "auth_missing"
            notes.append(f"{args.earthdata_token_env} missing; metadata-only mode.")
        else:
            day_statuses: list[str] = []
            for day in sorted(selected.keys()):
                result = process_gridded_day(
                    source=source,
                    day=day,
                    entries=selected[day],
                    variable_candidates=spec.variable_candidates,
                    roi_gdf=boundary.gdf,
                    workspace=workspace,
                    earthdata_token=token,
                )
                day_statuses.append(str(result.get("status")))
                if result.get("output_path"):
                    image_outputs.append(str(result["output_path"]))
                if result.get("notes"):
                    notes.append(str(result["notes"]))

            if image_outputs:
                status = "ok"
            else:
                status = day_statuses[0] if day_statuses else "failed"

        if gee_err:
            notes.append(f"gee_error={gee_err}")
        rows.append(
            {
                "source": source,
                "status": status,
                "latest_available_date": latest_date,
                "gee_latest_date": gee_latest,
                "lead_days_vs_gee": compute_lead_days(latest_date, gee_latest),
                "image_output": image_outputs,
                "notes": " | ".join(dict.fromkeys(notes)),
            }
        )

    report = {
        "study_area": args.study_area,
        "boundary_source": boundary.boundary_source,
        "boundary_path": str(boundary.boundary_path),
        "bbox": boundary.bbox,
        "mode": args.mode,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "gee_latest_date": gee_latest,
        "gee_error": gee_err,
        "token_env": args.earthdata_token_env,
        "token_present": token_present,
        "sources": rows,
    }

    json_path = workspace / "outputs" / "availability_report.json"
    csv_path = workspace / "outputs" / "availability_report.csv"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report_csv(rows, csv_path)

    print(str(json_path))
    print(str(csv_path))
    return report


if __name__ == "__main__":
    run()
