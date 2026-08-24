"""Run the established Q19 VNP46A2 extractor into a new Case 202 package.

The source implementation remains unchanged.  This adapter supplies an
updated Case 202 identity and a full-baseline context record, then invokes the
same bounded GEE daily-reduction workflow in this new directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


CASE_ID = "Case202-tehran-latest-vnp46a2"
ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT.parents[1]
SOURCE_DIR = WORK_ROOT / "experiments" / "paper-case-multiagent-2026-08-13" / "Q19-tehran-city-longseries"
SOURCE_EXTRACTOR = SOURCE_DIR / "extract_tehran_daily_vnp46a2.py"
SOURCE_EVENT_CONTEXT = SOURCE_DIR / "event-context.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_reused_event_context(output_dir: Path) -> None:
    source = json.loads(SOURCE_EVENT_CONTEXT.read_text(encoding="utf-8"))
    source["case_id"] = CASE_ID
    source["as_of_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source["context_reuse"] = {
        "source_path": str(SOURCE_EVENT_CONTEXT),
        "source_sha256": sha256(SOURCE_EVENT_CONTEXT),
        "scope": "Existing source-reported timeline markers reused for a live imagery extension; no new event-source search was performed.",
    }
    source["analysis_windows"] = [
        {
            "window_id": "pre_conflict_baseline",
            "start_date_inclusive": "2026-01-01",
            "end_date_inclusive": "2026-02-27",
            "filter_interval_utc": "[2026-01-01T00:00:00Z, 2026-02-28T00:00:00Z)",
            "label": "Pre-conflict baseline",
            "interpretation": "Fixed descriptive comparison window.",
        },
        {
            "window_id": "conflict_evaluation",
            "start_date_inclusive": "2026-02-28",
            "end_date_inclusive": "2026-04-07",
            "filter_interval_utc": "[2026-02-28T00:00:00Z, 2026-04-08T00:00:00Z)",
            "label": "Conflict evaluation",
            "interpretation": "Fixed descriptive comparison window.",
        },
        {
            "window_id": "ceasefire_evaluation",
            "start_date_inclusive": "2026-04-08",
            "end_date_inclusive": "2026-04-21",
            "filter_interval_utc": "[2026-04-08T00:00:00Z, 2026-04-22T00:00:00Z)",
            "label": "Ceasefire evaluation",
            "interpretation": "Fixed evaluation window; 22 April is not interpreted as a ceasefire-end date.",
        },
        {
            "window_id": "extended_monitoring",
            "start_date_inclusive": "2026-04-22",
            "end_date_inclusive": None,
            "filter_interval_utc": "[2026-04-22T00:00:00Z, latest strict-qualified product date plus one day)",
            "label": "Extended monitoring",
            "interpretation": "Neutral later span; not a homogeneous ceasefire, recovery, or peace period.",
        },
    ]
    write_json(output_dir / "event-context.json", source)
    shutil.copy2(SOURCE_EVENT_CONTEXT, output_dir / "inputs" / "event-context-source-2026-08-13.json")


def load_extractor():
    spec = importlib.util.spec_from_file_location("case202_q19_extractor", SOURCE_EXTRACTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load source extractor: {SOURCE_EXTRACTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CASE_ID = CASE_ID
    module.START_DATE = date(2026, 1, 1)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--probe-month", help="Run a bounded YYYY-MM live GEE probe only")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not SOURCE_EXTRACTOR.is_file() or not SOURCE_EVENT_CONTEXT.is_file():
        raise FileNotFoundError("The accepted Q19 extractor or EventContext is unavailable")
    build_reused_event_context(output_dir)
    extractor = load_extractor()
    result = extractor.probe_one_month(output_dir, args.probe_month) if args.probe_month else extractor.run_live(output_dir)
    print(json.dumps(result if isinstance(result, dict) else {"status": "completed"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
