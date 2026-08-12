from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _json_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "schema": "conflict_city_ntl.cli.v1",
        "status": "fail",
        "error_code": error_code,
        "error": message,
    }


def _load_json_argument(raw: str, *, label: str) -> Any:
    value = str(raw or "").strip()
    if not value:
        return None

    candidate = value[1:] if value.startswith("@") else value
    path = Path(candidate).expanduser()
    if value.startswith("@") or path.is_file():
        try:
            value = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValueError(f"Could not read {label} JSON file {path}: {exc}") from exc

    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid inline JSON or a readable JSON file: {exc}") from exc


def _validate_iso_date(raw: str, *, label: str) -> str:
    value = str(raw or "").strip()
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format, got {value!r}.") from exc
    return value


def _normalise_result(result: Any) -> dict[str, Any] | list[Any]:
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return {
                "schema": "conflict_city_ntl.cli.v1",
                "status": "success",
                "result": result,
            }
        if isinstance(parsed, (dict, list)):
            return parsed
    return {
        "schema": "conflict_city_ntl.cli.v1",
        "status": "success",
        "result": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve or load authorized structured conflict-event records, then rank all tied "
            "maximum cities in Iran and Israel by retrieved source attack-record count."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--live",
        action="store_true",
        help="Query the configured live structured source. Requires --acknowledge-source-terms.",
    )
    source.add_argument(
        "--input-events",
        default="",
        help="Authorized local CSV or JSON event snapshot to normalize and rank.",
    )
    parser.add_argument("--thread-id", default="", help="Current NTL-GPT thread/workspace identifier.")
    parser.add_argument("--start-date", required=True, help="Inclusive event-window start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive event-window cutoff date, YYYY-MM-DD.")
    parser.add_argument(
        "--city-aliases-json",
        default="",
        help="Inline JSON object, JSON file path, or @file containing versioned city aliases.",
    )
    parser.add_argument(
        "--event-types-json",
        default="",
        help="Inline JSON list, JSON file path, or @file containing the eligible attack-record taxonomy.",
    )
    parser.add_argument(
        "--acknowledge-source-terms",
        action="store_true",
        help="Explicitly acknowledge that live-source terms/permissions have been checked and accepted.",
    )
    parser.add_argument(
        "--output-root",
        default="conflict_city_ntl_runs",
        help="Workspace-relative directory under outputs/ used by the registered core function.",
    )
    parser.add_argument(
        "--run-label",
        "--output-prefix",
        dest="run_label",
        default="",
        help="Optional workspace-safe run label; --output-prefix is retained as an alias.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        start_date = _validate_iso_date(args.start_date, label="start_date")
        end_date = _validate_iso_date(args.end_date, label="end_date")
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date.")

        if args.live and not args.acknowledge_source_terms:
            payload = _json_error(
                "source_terms_not_acknowledged",
                "Live retrieval is disabled until --acknowledge-source-terms is explicitly supplied.",
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            return 2

        city_aliases = _load_json_argument(args.city_aliases_json, label="city_aliases")
        if city_aliases is not None and not isinstance(city_aliases, dict):
            raise ValueError("city_aliases JSON must be an object mapping aliases to canonical city names.")

        event_types = _load_json_argument(args.event_types_json, label="event_types")
        if event_types is not None and not isinstance(event_types, list):
            raise ValueError("event_types JSON must be a list defining the fixed taxonomy.")

        from tools.conflict_city_events import run_conflict_city_event_retrieval

        config = {"configurable": {"thread_id": args.thread_id}} if args.thread_id else None
        result = run_conflict_city_event_retrieval(
            events_path=args.input_events or "",
            output_root=args.output_root,
            run_label=args.run_label,
            event_window_start=start_date,
            event_window_end=end_date,
            countries_csv="Iran,Israel",
            eligible_event_types_json=(
                json.dumps(event_types, ensure_ascii=False) if event_types is not None else ""
            ),
            city_aliases_json=json.dumps(city_aliases or {}, ensure_ascii=False),
            source_terms_acknowledged=bool(args.acknowledge_source_terms),
            config=config,
        )
        payload = _normalise_result(result)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        if not isinstance(payload, dict) or payload.get("status") != "complete":
            return 1
        return 0
    except Exception as exc:
        payload = _json_error("cli_error", str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
