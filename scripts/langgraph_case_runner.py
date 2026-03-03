from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

os.environ.setdefault("MPLBACKEND", "Agg")
try:
    import matplotlib

    matplotlib.use("Agg", force=True)
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from graph_factory import build_ntl_graph
from storage_manager import current_thread_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig").strip()


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _normalize_expect_years(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list) and value:
        vals = [str(v).strip() for v in value if str(v).strip()]
        return ",".join(vals) if vals else None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _extract_year_range_from_query(query: str) -> Optional[Tuple[int, int]]:
    text = query.lower()
    patterns = [
        r"from\s+(19\d{2}|20\d{2})\s+to\s+(19\d{2}|20\d{2})",
        r"between\s+(19\d{2}|20\d{2})\s+and\s+(19\d{2}|20\d{2})",
        r"\b(19\d{2}|20\d{2})\s*[-–—]\s*(19\d{2}|20\d{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        start, end = int(m.group(1)), int(m.group(2))
        if end >= start:
            return start, end
    return None


def _looks_like_download_query(query: str) -> bool:
    text = query.lower()
    has_download_verb = any(k in text for k in ["download", "retrieve", "get "])
    has_data_object = any(k in text for k in ["ntl", "viirs", "imagery", "image", "raster", "vnp46"])
    return has_download_verb and has_data_object


def _infer_case_expectations(query: str, label: str = "", category: str = "") -> Dict[str, Any]:
    q = query.lower()
    l = (label or "").lower()
    c = (category or "").lower()
    year_range = _extract_year_range_from_query(query)
    looks_download = _looks_like_download_query(query)
    is_composite_like = any(k in q for k in ["composite", "average", "mean"]) and "not a composite" not in q
    is_statistics_like = any(k in q for k in ["calculate", "statistics", "trend", "anomaly", "growth", "compare"])
    is_annual_like = any(k in q for k in ["annual", "yearly", "each year"]) or "annual" in l
    is_retrieval_category = "data retrieval and preprocessing" in c

    expect_years: Optional[str] = None
    expect_direct_download = False
    expect_no_partial_transfer = False

    if year_range and looks_download:
        start, end = year_range
        span = end - start + 1
        if 1 <= span <= 12:
            expect_years = f"{start}-{end}"

    if looks_download and is_retrieval_category and not is_composite_like and not is_statistics_like:
        if is_annual_like and year_range:
            start, end = year_range
            span = end - start + 1
            if 1 <= span <= 12:
                expect_direct_download = True
                expect_no_partial_transfer = True
        elif "monthly" in q:
            expect_direct_download = True

    return {
        "expect_years": expect_years,
        "expect_direct_download": expect_direct_download,
        "expect_no_partial_transfer": expect_no_partial_transfer,
    }


def _load_case_file(path: str, auto_expect: bool = True) -> List[Dict[str, Any]]:
    p = Path(path)
    ext = p.suffix.lower()
    cases: List[Dict[str, Any]]
    if ext == ".csv":
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cases = [dict(row) for row in reader]
    else:
        raw = p.read_text(encoding="utf-8-sig")
        if ext in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("YAML case file requires PyYAML installed.") from exc
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)

        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            cases = data["cases"]
        elif isinstance(data, list):
            cases = data
        else:
            raise ValueError("Case file must be a list/object('cases') or a CSV file.")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Case #{idx} is not an object.")
        query = str(item.get("query") or item.get("Case") or "").strip()
        if not query:
            raise ValueError(f"Case #{idx} missing non-empty 'query'.")
        category = str(item.get("category") or item.get("Category") or "").strip()
        label = str(item.get("label") or item.get("Label") or "").strip()
        case_id = str(
            item.get("id")
            or item.get("case_id")
            or item.get("Unnamed: 0")
            or f"case_{idx}"
        ).strip()
        inferred = _infer_case_expectations(query=query, label=label, category=category) if auto_expect else {}
        expect_years = _normalize_expect_years(item.get("expect_years"))
        if expect_years is None:
            expect_years = _normalize_expect_years(inferred.get("expect_years"))
        normalized.append(
            {
                "id": case_id,
                "query": query,
                "category": category or None,
                "label": label or None,
                "expect_years": expect_years,
                "expect_direct_download": _parse_bool(
                    item.get("expect_direct_download"),
                    default=bool(inferred.get("expect_direct_download", False)),
                ),
                "expect_no_partial_transfer": _parse_bool(
                    item.get("expect_no_partial_transfer"),
                    default=bool(inferred.get("expect_no_partial_transfer", False)),
                ),
            }
        )
    return normalized


def _msg_get(msg: Any, key: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _msg_type(msg: Any) -> str:
    t = _msg_get(msg, "type", None)
    if isinstance(t, str) and t:
        return t
    role = _msg_get(msg, "role", None)
    return role if isinstance(role, str) else ""


def _msg_name(msg: Any) -> str:
    name = _msg_get(msg, "name", None)
    return name if isinstance(name, str) else ""


def _msg_content(msg: Any) -> str:
    content = _msg_get(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content)


def _msg_tool_calls(msg: Any) -> List[Dict[str, Any]]:
    calls = _msg_get(msg, "tool_calls", None)
    if isinstance(calls, list):
        out: List[Dict[str, Any]] = []
        for c in calls:
            if isinstance(c, dict):
                out.append(c)
        return out
    return []


def _msg_response_metadata(msg: Any) -> Dict[str, Any]:
    md = _msg_get(msg, "response_metadata", None)
    if isinstance(md, dict):
        return md
    akw = _msg_get(msg, "additional_kwargs", None)
    if isinstance(akw, dict):
        nested = akw.get("response_metadata")
        if isinstance(nested, dict):
            return nested
    return {}


def _is_handoff_back_control_message(msg: Any) -> bool:
    md = _msg_response_metadata(msg)
    return bool(md.get("__is_handoff_back"))


def _parse_json_content(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_years_from_files(files: Iterable[str]) -> List[int]:
    years: set[int] = set()
    for f in files:
        for y in re.findall(r"(19\d{2}|20\d{2})", f):
            years.add(int(y))
    return sorted(years)


def _parse_years_expectation(value: str) -> List[int]:
    text = value.strip()
    if re.fullmatch(r"\d{4}", text):
        return [int(text)]
    m = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", text)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if end < start:
            raise ValueError("expect-years range end must be >= start.")
        return list(range(start, end + 1))
    if re.fullmatch(r"\d{4}(,\d{4})*", text):
        return [int(x) for x in text.split(",")]
    raise ValueError("expect-years must be 'YYYY-YYYY' or 'YYYY,YYYY,...'.")


def classify_langsmith_error(error_text: str, root_status: str) -> Dict[str, Any]:
    text = (error_text or "").strip()
    root = (root_status or "").strip().lower()
    if text.startswith("ParentCommand(Command(") and root == "success":
        return {"kind": "handoff_control_flow", "blocking": False}
    return {"kind": "execution_error", "blocking": True}


def analyze_messages(messages: List[Any]) -> Dict[str, Any]:
    tool_calls_counter: Counter[str] = Counter()
    ordered_tool_calls: List[Dict[str, Any]] = []
    downloaded_files: List[str] = []
    downloaded_files_seen: set[str] = set()
    transfer_events: List[Dict[str, Any]] = []
    expected_count: Optional[int] = None
    router_mode: Optional[str] = None

    for idx, msg in enumerate(messages, start=1):
        if _is_handoff_back_control_message(msg):
            # Ignore supervisor-generated synthetic back-handoff messages.
            continue

        name = _msg_name(msg)
        mtype = _msg_type(msg)
        content = _msg_content(msg)
        tool_calls = _msg_tool_calls(msg)

        if tool_calls:
            caller = name or mtype or "assistant"
            for call in tool_calls:
                call_name = str(call.get("name", "")).strip()
                if not call_name:
                    continue
                tool_calls_counter[call_name] += 1
                ordered_tool_calls.append(
                    {
                        "message_index": idx,
                        "caller": caller,
                        "tool": call_name,
                    }
                )
                if caller == "Data_Searcher" and call_name == "transfer_back_to_ntl_engineer":
                    transfer_events.append(
                        {
                            "message_index": idx,
                            "kind": "ai_handoff",
                            "downloaded_count_at_transfer": len(downloaded_files_seen),
                        }
                    )

        if mtype == "tool" and name:
            tool_calls_counter[name] += 1

            if name == "GEE_dataset_router_tool":
                parsed = _parse_json_content(content)
                if parsed:
                    if isinstance(parsed.get("estimated_image_count"), int):
                        expected_count = int(parsed["estimated_image_count"])
                    mode = parsed.get("recommended_execution_mode")
                    if isinstance(mode, str):
                        router_mode = mode

            if name == "NTL_download_tool":
                parsed = _parse_json_content(content)
                if parsed and isinstance(parsed.get("output_files"), list):
                    for f in parsed["output_files"]:
                        if isinstance(f, str) and f not in downloaded_files_seen:
                            downloaded_files_seen.add(f)
                            downloaded_files.append(f)

            if name == "transfer_back_to_ntl_engineer":
                transfer_events.append(
                    {
                        "message_index": idx,
                        "kind": "tool_handoff",
                        "downloaded_count_at_transfer": len(downloaded_files_seen),
                    }
                )

    detected_years = _extract_years_from_files(downloaded_files)
    partial_transfer_detected = any(
        expected_count is not None and e["downloaded_count_at_transfer"] < expected_count for e in transfer_events
    )

    return {
        "message_count": len(messages),
        "tool_calls_by_name": dict(tool_calls_counter),
        "ordered_tool_calls": ordered_tool_calls,
        "downloaded_files": downloaded_files,
        "detected_years": detected_years,
        "expected_image_count": expected_count,
        "router_recommended_mode": router_mode,
        "transfer_events": transfer_events,
        "partial_transfer_detected": partial_transfer_detected,
    }


def evaluate_assertions(
    analysis: Dict[str, Any],
    expect_years: Optional[str] = None,
    expect_direct_download: bool = False,
    expect_no_partial_transfer: bool = False,
) -> Tuple[Dict[str, Dict[str, Any]], str]:
    assertions: Dict[str, Dict[str, Any]] = {}

    if expect_years:
        years_needed = _parse_years_expectation(expect_years)
        years_have = set(analysis.get("detected_years", []))
        missing = [y for y in years_needed if y not in years_have]
        ok = len(missing) == 0
        assertions["expect_years"] = {"pass": ok, "required": years_needed, "missing": missing}

    if expect_direct_download:
        router_mode = analysis.get("router_recommended_mode")
        tools = analysis.get("tool_calls_by_name", {})
        has_download = int(tools.get("NTL_download_tool", 0)) > 0
        has_code_exec = int(tools.get("execute_geospatial_script_tool", 0)) > 0 or int(
            tools.get("transfer_to_code_assistant", 0)
        ) > 0
        ok = router_mode == "direct_download" and has_download and not has_code_exec
        assertions["expect_direct_download"] = {
            "pass": ok,
            "router_mode": router_mode,
            "has_download_tool": has_download,
            "has_code_assistant_path": has_code_exec,
        }

    if expect_no_partial_transfer:
        partial = bool(analysis.get("partial_transfer_detected"))
        assertions["expect_no_partial_transfer"] = {"pass": not partial, "partial_transfer_detected": partial}

    if not assertions:
        return assertions, "INCONCLUSIVE"

    overall = "PASS" if all(v.get("pass") for v in assertions.values()) else "FAIL"
    return assertions, overall


def classify_runtime_error(error_text: str) -> Dict[str, Any]:
    text = (error_text or "").strip()
    lower = text.lower()
    if not lower:
        return {"kind": "non_design_error", "subkind": "unknown", "blocking": True, "suggested_fix": "Inspect runtime logs for stacktrace and retry."}

    patterns: List[Tuple[str, str, str]] = [
        ("api_key_missing", "missing api key", "Set required API key env vars in `.env` and rerun."),
        ("api_key_missing", "missing api key in env var", "Set required API key env vars in `.env` and rerun."),
        ("auth_error", "unauthorized", "Check API key validity and provider account permissions."),
        ("auth_error", "authentication", "Check API key validity and provider account permissions."),
        ("network_error", "timed out", "Retry with larger `--request-timeout` and verify network connectivity."),
        ("network_error", "timeout", "Retry with larger `--request-timeout` and verify network connectivity."),
        ("network_error", "connection", "Verify network/proxy and external API endpoint reachability."),
        ("dependency_error", "importerror", "Install missing dependency in conda env and rerun."),
        ("dependency_error", "modulenotfounderror", "Install missing dependency in conda env and rerun."),
        ("filesystem_error", "filenotfounderror", "Ensure required input files exist under the case thread workspace."),
        ("filesystem_error", "permissionerror", "Fix filesystem permissions for workspace read/write."),
        ("rate_limit", "rate limit", "Add backoff/retry or lower concurrency, then rerun failed cases."),
    ]
    for subkind, token, fix in patterns:
        if token in lower:
            return {"kind": "non_design_error", "subkind": subkind, "blocking": True, "suggested_fix": fix}

    if "recursion_limit" in lower or "graphrecursionerror" in lower:
        return {
            "kind": "non_design_error",
            "subkind": "recursion_limit",
            "blocking": True,
            "suggested_fix": "Increase `--recursion-limit` or tighten agent/tool stopping conditions.",
        }

    return {
        "kind": "non_design_error",
        "subkind": "unknown",
        "blocking": True,
        "suggested_fix": "Inspect stacktrace and tool logs, then patch the failing component.",
    }


def classify_case_issue_bucket(report: Dict[str, Any]) -> str:
    runtime_error = report.get("runtime_error")
    if isinstance(runtime_error, dict) and runtime_error.get("kind") == "non_design_error":
        return "non_design_error"

    langsmith = report.get("langsmith", {})
    if isinstance(langsmith, dict):
        for err in langsmith.get("errors_classified", []) or []:
            if isinstance(err, dict) and err.get("blocking") is True:
                return "non_design_error"

    if report.get("final") == "FAIL":
        return "model_design_error"
    return "none"


def build_batch_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    pass_count = sum(1 for r in results if r.get("final") == "PASS")
    fail_count = sum(1 for r in results if r.get("final") == "FAIL")
    inc_count = sum(1 for r in results if r.get("final") == "INCONCLUSIVE")
    error_count = sum(1 for r in results if r.get("final") == "ERROR")
    non_design_count = sum(1 for r in results if r.get("issue_bucket") == "non_design_error")
    model_design_count = sum(1 for r in results if r.get("issue_bucket") == "model_design_error")

    assertion_cases = [r for r in results if isinstance(r.get("assertions"), dict) and r.get("assertions")]
    assertion_case_count = len(assertion_cases)
    assertion_pass_case_count = sum(1 for r in assertion_cases if r.get("final") == "PASS")

    category_rollup: Dict[str, Dict[str, int]] = {}
    non_design_subkind_counter: Counter[str] = Counter()
    for r in results:
        meta = r.get("meta", {}) if isinstance(r.get("meta"), dict) else {}
        category = str(meta.get("category") or "uncategorized")
        row = category_rollup.setdefault(
            category,
            {"total": 0, "pass": 0, "fail": 0, "inconclusive": 0, "error": 0},
        )
        row["total"] += 1
        final = r.get("final")
        if final == "PASS":
            row["pass"] += 1
        elif final == "FAIL":
            row["fail"] += 1
        elif final == "ERROR":
            row["error"] += 1
        else:
            row["inconclusive"] += 1

        if r.get("issue_bucket") == "non_design_error":
            runtime_error = r.get("runtime_error")
            if isinstance(runtime_error, dict):
                non_design_subkind_counter[str(runtime_error.get("subkind") or "unknown")] += 1

    return {
        "total_cases": total,
        "pass": pass_count,
        "fail": fail_count,
        "inconclusive": inc_count,
        "error": error_count,
        "non_design_error": non_design_count,
        "model_design_error": model_design_count,
        "execution_success_rate": round((total - non_design_count) / total, 4) if total else 0.0,
        "assertion_case_count": assertion_case_count,
        "assertion_pass_case_count": assertion_pass_case_count,
        "assertion_pass_rate": round(assertion_pass_case_count / assertion_case_count, 4) if assertion_case_count else 0.0,
        "category_rollup": category_rollup,
        "non_design_subkinds": dict(non_design_subkind_counter),
    }


def _extract_user_query_from_run_inputs(inputs: Any) -> str:
    if not isinstance(inputs, dict):
        return ""
    msgs = inputs.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    return content
    text = inputs.get("input")
    return text if isinstance(text, str) else ""


def _fetch_langsmith_summary(
    query: str,
    thread_id: str,
    started_at: datetime,
    ended_at: datetime,
    project_name: Optional[str],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "langsmith_fetch_skipped": False,
        "project": project_name,
        "trace_id": None,
        "root_status": None,
        "errors_raw": [],
        "errors_classified": [],
    }
    try:
        from langsmith import Client
    except Exception as exc:  # noqa: BLE001
        result["langsmith_fetch_skipped"] = True
        result["skip_reason"] = f"langsmith import failed: {exc}"
        return result

    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    api_url = os.getenv("LANGCHAIN_ENDPOINT") or os.getenv("LANGSMITH_ENDPOINT")
    if not api_key or not api_url or not project_name:
        result["langsmith_fetch_skipped"] = True
        result["skip_reason"] = "Missing LANGSMITH/LANGCHAIN env configuration."
        return result

    try:
        client = Client(api_key=api_key, api_url=api_url)
        window_start = started_at - timedelta(minutes=5)
        roots = []
        for run in client.list_runs(project_name=project_name, start_time=window_start, limit=100):
            run_id = str(getattr(run, "id", ""))
            trace_id = str(getattr(run, "trace_id", ""))
            if not run_id or run_id != trace_id:
                continue
            run_start = getattr(run, "start_time", None)
            if run_start and run_start > ended_at + timedelta(minutes=15):
                continue
            run_query = _extract_user_query_from_run_inputs(getattr(run, "inputs", None))
            if run_query.strip() != query.strip():
                continue
            score = abs((run_start - started_at).total_seconds()) if run_start else 999999
            roots.append((score, run))

        if not roots:
            result["langsmith_fetch_skipped"] = True
            result["skip_reason"] = "No matching root trace found in time window."
            return result

        roots.sort(key=lambda x: x[0])
        root = roots[0][1]
        trace_id = str(getattr(root, "trace_id", ""))
        result["trace_id"] = trace_id
        result["root_status"] = getattr(root, "status", None)

        related = list(client.list_runs(project_name=project_name, trace_id=trace_id, limit=100))
        raw_errors: List[Dict[str, Any]] = []
        for r in related:
            err = str(getattr(r, "error", "") or "").strip()
            status = str(getattr(r, "status", "") or "").lower()
            if err or status in {"error", "failed"}:
                raw_errors.append(
                    {
                        "run_id": str(getattr(r, "id", "")),
                        "name": str(getattr(r, "name", "")),
                        "status": str(getattr(r, "status", "")),
                        "error": err,
                    }
                )
        result["errors_raw"] = raw_errors
        root_status = str(result.get("root_status") or "")
        result["errors_classified"] = [
            {
                **e,
                **classify_langsmith_error(e.get("error", ""), root_status),
            }
            for e in raw_errors
        ]
        return result
    except Exception as exc:  # noqa: BLE001
        result["langsmith_fetch_skipped"] = True
        result["skip_reason"] = f"LangSmith fetch failed: {exc}"
        return result


def _serialize_message(msg: Any) -> Dict[str, Any]:
    data = {
        "type": _msg_type(msg),
        "name": _msg_name(msg),
        "content": _msg_content(msg),
    }
    tool_calls = _msg_tool_calls(msg)
    if tool_calls:
        data["tool_calls"] = tool_calls
    tool_call_id = _msg_get(msg, "tool_call_id", None)
    if isinstance(tool_call_id, str) and tool_call_id:
        data["tool_call_id"] = tool_call_id
    msg_id = _msg_get(msg, "id", None)
    if isinstance(msg_id, str) and msg_id:
        data["id"] = msg_id
    return data


def _resolve_api_key(provider: str, api_key_env: Optional[str]) -> Tuple[str, str]:
    default_env = "DASHSCOPE_API_KEY" if provider == "qwen" else "OPENAI_API_KEY"
    key_env = api_key_env or default_env
    key = os.getenv(key_env, "")
    if not key:
        raise RuntimeError(f"Missing API key in env var: {key_env}")
    return key_env, key


def _stream_graph(graph: Any, state: Dict[str, Any], config: Dict[str, Any], stream_mode: str) -> None:
    for _ in graph.stream(state, config=config, stream_mode=stream_mode):
        pass


@dataclass
class CaseConfig:
    case_id: str
    query: str
    category: Optional[str]
    label: Optional[str]
    expect_years: Optional[str]
    expect_direct_download: bool
    expect_no_partial_transfer: bool


def run_case(
    case: CaseConfig,
    model: str,
    provider: str,
    api_key: str,
    request_timeout: int,
    recursion_limit: int,
    stream_mode: str,
    thread_id: str,
    graph_name: str,
    fetch_langsmith: bool,
    langsmith_project: Optional[str],
) -> Dict[str, Any]:
    graph = build_ntl_graph(
        model_name=model,
        api_key=api_key,
        request_timeout_s=request_timeout,
        graph_name=graph_name,
    )

    state = {"messages": [{"role": "user", "content": case.query}]}
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}
    started_at = _utcnow()
    start_perf = time.perf_counter()

    token = current_thread_id.set(thread_id)
    try:
        _stream_graph(graph, state=state, config=config, stream_mode=stream_mode)
    finally:
        current_thread_id.reset(token)

    duration_s = round(time.perf_counter() - start_perf, 3)
    ended_at = _utcnow()

    snapshot = graph.get_state(config=config)
    values = getattr(snapshot, "values", {}) or {}
    messages = values.get("messages", []) if isinstance(values, dict) else []
    analysis = analyze_messages(messages if isinstance(messages, list) else [])
    assertions, final = evaluate_assertions(
        analysis=analysis,
        expect_years=case.expect_years,
        expect_direct_download=case.expect_direct_download,
        expect_no_partial_transfer=case.expect_no_partial_transfer,
    )

    langsmith = (
        _fetch_langsmith_summary(
            query=case.query,
            thread_id=thread_id,
            started_at=started_at,
            ended_at=ended_at,
            project_name=langsmith_project,
        )
        if fetch_langsmith
        else {"langsmith_fetch_skipped": True, "skip_reason": "--no-langsmith-fetch"}
    )

    report = {
        "meta": {
            "case_id": case.case_id,
            "query": case.query,
            "category": case.category,
            "label": case.label,
            "expect_years": case.expect_years,
            "expect_direct_download": case.expect_direct_download,
            "expect_no_partial_transfer": case.expect_no_partial_transfer,
            "provider": provider,
            "model": model,
            "thread_id": thread_id,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        },
        "execution": {
            "duration_s": duration_s,
            "message_count": analysis["message_count"],
            "tool_calls_by_name": analysis["tool_calls_by_name"],
            "ordered_tool_calls": analysis["ordered_tool_calls"],
            "router_recommended_mode": analysis.get("router_recommended_mode"),
            "expected_image_count": analysis.get("expected_image_count"),
        },
        "artifacts": {
            "downloaded_files": analysis["downloaded_files"],
            "detected_years": analysis["detected_years"],
        },
        "handoff": {
            "transfer_events": analysis["transfer_events"],
            "partial_transfer_detected": analysis["partial_transfer_detected"],
        },
        "assertions": assertions,
        "langsmith": langsmith,
        "runtime_error": None,
        "final": final,
        "messages": messages,
    }
    report["issue_bucket"] = classify_case_issue_bucket(report)
    return report


def _default_thread_id(prefix: str = "case") -> str:
    return f"{prefix}_{int(time.time())}"


def _dump_messages(path: Path, reports: List[Dict[str, Any]]) -> None:
    payload: Dict[str, Any] = {"cases": []}
    for item in reports:
        raw_msgs = item.get("messages", [])
        msg_list = raw_msgs if isinstance(raw_msgs, list) else []
        payload["cases"].append(
            {
                "case_id": item.get("meta", {}).get("case_id"),
                "thread_id": item.get("meta", {}).get("thread_id"),
                "messages": [_serialize_message(m) for m in msg_list],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct LangGraph case runner (without Streamlit UI).")
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--query-file", type=str, default=None)
    parser.add_argument("--case-file", type=str, default=None)
    parser.add_argument("--model", type=str, default="qwen3.5-plus")
    parser.add_argument("--provider", type=str, choices=["qwen", "openai"], default="qwen")
    parser.add_argument("--api-key-env", type=str, default=None)
    parser.add_argument("--thread-id", type=str, default=None)
    parser.add_argument("--recursion-limit", type=int, default=45)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--stream-mode", type=str, choices=["values", "messages", "updates"], default="values")
    parser.add_argument("--out-json", type=str, default=None)
    parser.add_argument("--dump-messages", action="store_true")
    parser.add_argument("--langsmith-project", type=str, default=None)
    parser.add_argument("--no-langsmith-fetch", action="store_true")
    parser.add_argument("--expect-years", type=str, default=None)
    parser.add_argument("--expect-direct-download", action="store_true")
    parser.add_argument("--expect-no-partial-transfer", action="store_true")
    parser.add_argument("--auto-expect", action="store_true", default=True)
    parser.add_argument("--no-auto-expect", dest="auto_expect", action="store_false")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--start-case", type=int, default=1, help="1-based start index for case-file runs.")
    parser.add_argument("--end-case", type=int, default=None, help="1-based end index (inclusive) for case-file runs.")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


def _build_case_list(args: argparse.Namespace) -> List[CaseConfig]:
    if args.case_file:
        cases = _load_case_file(args.case_file, auto_expect=bool(args.auto_expect))
        built_all = [
            CaseConfig(
                case_id=c["id"],
                query=c["query"],
                category=c.get("category"),
                label=c.get("label"),
                expect_years=c.get("expect_years"),
                expect_direct_download=bool(c.get("expect_direct_download", False)),
                expect_no_partial_transfer=bool(c.get("expect_no_partial_transfer", False)),
            )
            for c in cases
        ]
        start_idx = max(1, int(args.start_case or 1))
        end_idx = int(args.end_case) if args.end_case is not None else len(built_all)
        end_idx = min(len(built_all), end_idx)
        if end_idx < start_idx:
            raise ValueError("--end-case must be >= --start-case.")
        built = built_all[start_idx - 1 : end_idx]
        if args.max_cases is not None and args.max_cases > 0:
            return built[: args.max_cases]
        return built

    if args.query and args.query_file:
        raise ValueError("Use either --query or --query-file, not both.")

    query = args.query if args.query else (_read_text(args.query_file) if args.query_file else "")
    if not query.strip():
        raise ValueError("One of --query / --query-file / --case-file is required.")

    return [
        CaseConfig(
            case_id="case_1",
            query=query,
            category=None,
            label=None,
            expect_years=args.expect_years,
            expect_direct_download=args.expect_direct_download,
            expect_no_partial_transfer=args.expect_no_partial_transfer,
        )
    ]


def _build_report_payload(
    *,
    args: argparse.Namespace,
    key_env: str,
    project: Optional[str],
    results: List[Dict[str, Any]],
    base_thread: str,
    is_partial: bool,
) -> Dict[str, Any]:
    metrics = build_batch_metrics(results)
    pass_count = int(metrics["pass"])
    fail_count = int(metrics["fail"])
    inc_count = int(metrics["inconclusive"])
    err_count = int(metrics["error"])
    batch_final = "FAIL" if (fail_count or err_count) else ("PASS" if pass_count else "INCONCLUSIVE")
    if is_partial:
        batch_final = f"PARTIAL_{batch_final}"

    return {
        "meta": {
            "created_at": _utcnow().isoformat(),
            "provider": args.provider,
            "model": args.model,
            "api_key_env": key_env,
            "langsmith_project": project,
            "case_count": len(results),
            "base_thread_id": base_thread,
            "is_partial": is_partial,
        },
        "summary": {
            "pass": pass_count,
            "fail": fail_count,
            "inconclusive": inc_count,
            "error": err_count,
            "final": batch_final,
        },
        "metrics": metrics,
        "results": [{k: v for k, v in r.items() if k != "messages"} for r in results],
    }


def _write_report_checkpoint(
    out_path: Path,
    *,
    args: argparse.Namespace,
    key_env: str,
    project: Optional[str],
    results: List[Dict[str, Any]],
    base_thread: str,
    is_partial: bool,
) -> Dict[str, Any]:
    payload = _build_report_payload(
        args=args,
        key_env=key_env,
        project=project,
        results=results,
        base_thread=base_thread,
        is_partial=is_partial,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv(dotenv_path=".env", override=False)
    args = parse_args(argv)
    cases = _build_case_list(args)
    key_env, api_key = _resolve_api_key(args.provider, args.api_key_env)

    project = args.langsmith_project or os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT")
    base_thread = args.thread_id or _default_thread_id()
    graph_name = "NTL-GPT"
    out_default = f"reports/langgraph_case_{base_thread}.json"
    out_path = Path(args.out_json or out_default)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        thread_id = base_thread if len(cases) == 1 else f"{base_thread}_{idx}"
        try:
            report = run_case(
                case=case,
                model=args.model,
                provider=args.provider,
                api_key=api_key,
                request_timeout=args.request_timeout,
                recursion_limit=args.recursion_limit,
                stream_mode=args.stream_mode,
                thread_id=thread_id,
                graph_name=graph_name,
                fetch_langsmith=not args.no_langsmith_fetch,
                langsmith_project=project,
            )
        except Exception as exc:  # noqa: BLE001
            started_at = _utcnow()
            ended_at = _utcnow()
            runtime_error = {
                "message": str(exc),
                **classify_runtime_error(str(exc)),
            }
            report = {
                "meta": {
                    "case_id": case.case_id,
                    "query": case.query,
                    "category": case.category,
                    "label": case.label,
                    "expect_years": case.expect_years,
                    "expect_direct_download": case.expect_direct_download,
                    "expect_no_partial_transfer": case.expect_no_partial_transfer,
                    "provider": args.provider,
                    "model": args.model,
                    "thread_id": thread_id,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                },
                "execution": {
                    "duration_s": 0.0,
                    "message_count": 0,
                    "tool_calls_by_name": {},
                    "ordered_tool_calls": [],
                    "router_recommended_mode": None,
                    "expected_image_count": None,
                },
                "artifacts": {"downloaded_files": [], "detected_years": []},
                "handoff": {"transfer_events": [], "partial_transfer_detected": False},
                "assertions": {},
                "langsmith": {"langsmith_fetch_skipped": True, "skip_reason": "case_runtime_exception"},
                "runtime_error": runtime_error,
                "final": "ERROR",
                "messages": [],
            }
            report["issue_bucket"] = classify_case_issue_bucket(report)
            if args.fail_fast:
                results.append(report)
                print(f"[{case.case_id}] final=ERROR issue=non_design_error error={str(exc)}", flush=True)
                break

        results.append(report)
        print(
            f"[{case.case_id}] final={report['final']} "
            f"issue={report.get('issue_bucket', 'none')} "
            f"years={report.get('artifacts', {}).get('detected_years', [])} "
            f"trace={report.get('langsmith', {}).get('trace_id')}",
            flush=True,
        )
        _write_report_checkpoint(
            out_path,
            args=args,
            key_env=key_env,
            project=project,
            results=results,
            base_thread=base_thread,
            is_partial=(idx < len(cases)),
        )

    payload = _write_report_checkpoint(
        out_path,
        args=args,
        key_env=key_env,
        project=project,
        results=results,
        base_thread=base_thread,
        is_partial=False,
    )
    metrics = payload["metrics"]
    batch_final = payload["summary"]["final"]

    if args.dump_messages:
        dump_path = out_path.with_suffix(".messages.json")
        _dump_messages(dump_path, results)
        print(f"messages_dump={dump_path}", flush=True)

    print(f"report={out_path}", flush=True)
    print(
        "metrics: "
        f"total={metrics['total_cases']} pass={metrics['pass']} fail={metrics['fail']} "
        f"error={metrics['error']} non_design={metrics['non_design_error']} "
        f"model_design={metrics['model_design_error']} assertion_pass_rate={metrics['assertion_pass_rate']}",
        flush=True,
    )
    print(f"final={batch_final}", flush=True)
    return 0 if batch_final != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
