"""Independent Q19 window cross-check; Codex-subagent simulation only."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from statistics import fmean


INPUT_CSV = Path(
    r"vault/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q19-tehran-city-longseries/daily-vnp46a2.csv"
)
OUTPUT_DIR = Path(__file__).resolve().parent

WINDOWS = (
    ("w1", date(2026, 1, 1), date(2026, 2, 27)),
    ("w2", date(2026, 2, 28), date(2026, 4, 7)),
    ("w3", date(2026, 4, 8), date(2026, 4, 21)),
    ("w4", date(2026, 4, 22), date(2026, 7, 31)),
)
EXPECTED_BASELINE_N = {"strict": 47, "permissive": 48}


def load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date_utc", "qa_mode", "qualified", "mean"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        for raw in reader:
            qualified = (raw["qualified"] or "").strip().lower() == "true"
            mean_raw = (raw["mean"] or "").strip()
            if qualified and not mean_raw:
                raise ValueError(
                    f"qualified=true row has an empty mean: {raw.get('date_utc')} / {raw.get('qa_mode')}"
                )
            rows.append(
                {
                    "date": date.fromisoformat((raw["date_utc"] or "").strip()),
                    "qa_mode": (raw["qa_mode"] or "").strip().lower(),
                    "qualified": qualified,
                    "mean": float(mean_raw) if mean_raw else None,
                }
            )
    return rows


def compute(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    result_rows: list[dict[str, object]] = []
    baseline_checks: dict[str, dict[str, object]] = {}
    for qa_mode, expected_n in EXPECTED_BASELINE_N.items():
        qualified = [
            row
            for row in rows
            if row["qa_mode"] == qa_mode
            and bool(row["qualified"])
            and row["mean"] is not None
        ]
        first_start, first_end = WINDOWS[0][1], WINDOWS[0][2]
        first_window = [
            row
            for row in qualified
            if first_start <= row["date"] <= first_end
        ]
        actual_n = len(first_window)
        baseline_checks[qa_mode] = {
            "expected_n": expected_n,
            "actual_n": actual_n,
            "matches": actual_n == expected_n,
        }
        if actual_n != expected_n:
            raise AssertionError(
                f"{qa_mode} baseline n={actual_n}; expected n={expected_n}"
            )

        first_mean = fmean(float(row["mean"]) for row in first_window)
        for window_name, start, end in WINDOWS:
            selected = [
                row
                for row in qualified
                if start <= row["date"] <= end
            ]
            mean_mean = fmean(float(row["mean"]) for row in selected) if selected else None
            relative_pct = (
                (mean_mean - first_mean) / first_mean * 100.0
                if mean_mean is not None
                else None
            )
            result_rows.append(
                {
                    "qa_mode": qa_mode,
                    "window": window_name,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "n": len(selected),
                    "mean_mean": mean_mean,
                    "relative_to_first_pct": relative_pct,
                    "baseline_n": expected_n,
                }
            )
    metadata = {
        "simulation_scope": "Codex-subagent simulation only",
        "input_csv": str(INPUT_CSV),
        "windows_inclusive_utc": [
            {"window": name, "start_date": start.isoformat(), "end_date": end.isoformat()}
            for name, start, end in WINDOWS
        ],
        "relative_definition": "100 * (window mean(mean) - w1 mean(mean)) / w1 mean(mean)",
        "baseline_checks": baseline_checks,
    }
    return result_rows, metadata


def write_outputs(result_rows: list[dict[str, object]], metadata: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "crosscheck.csv"
    fieldnames = [
        "qa_mode",
        "window",
        "start_date",
        "end_date",
        "n",
        "mean_mean",
        "relative_to_first_pct",
        "baseline_n",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result_rows:
            serialized = dict(row)
            for key in ("mean_mean", "relative_to_first_pct"):
                if serialized[key] is not None:
                    serialized[key] = f"{float(serialized[key]):.12f}"
            writer.writerow(serialized)

    json_path = OUTPUT_DIR / "crosscheck.json"
    payload = {**metadata, "rows": result_rows}
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_lines = [
        "# Q19 analyst cross-check",
        "",
        "Codex-subagent simulation only; this is an independent recomputation from the specified daily CSV.",
        "",
        f"Input: `{INPUT_CSV}`",
        "",
        "Qualified rows are filtered by `qualified=true`; windows are inclusive UTC date ranges. `relative_to_first_pct` is 100 × (window mean − w1 mean) / w1 mean, within the same QA mode.",
        "",
        "## Baseline checks",
        "",
        "| QA mode | expected n | recomputed n | status |",
        "|---|---:|---:|---|",
    ]
    for qa_mode in ("strict", "permissive"):
        check = metadata["baseline_checks"][qa_mode]
        status = "PASS" if check["matches"] else "FAIL"
        report_lines.append(
            f"| {qa_mode} | {check['expected_n']} | {check['actual_n']} | {status} |"
        )
    report_lines.extend(
        [
            "",
            "## Window results",
            "",
            "| QA mode | window | n | mean(mean) | relative to w1 (%) |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in result_rows:
        report_lines.append(
            f"| {row['qa_mode']} | {row['window']} ({row['start_date']}..{row['end_date']}) | {row['n']} | {float(row['mean_mean']):.6f} | {float(row['relative_to_first_pct']):.6f} |"
        )
    report_lines.append("")
    (OUTPUT_DIR / "report.md").write_text("\n".join(report_lines), encoding="utf-8")


def main() -> None:
    result_rows, metadata = compute(load_rows())
    write_outputs(result_rows, metadata)
    print(json.dumps(metadata["baseline_checks"], ensure_ascii=False, sort_keys=True))
    for row in result_rows:
        print(
            row["qa_mode"],
            row["window"],
            row["n"],
            f"{float(row['mean_mean']):.12f}",
            f"{float(row['relative_to_first_pct']):.12f}",
        )


if __name__ == "__main__":
    main()
