#!/usr/bin/env python
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage

# Ensure project root is importable when script is run from subdirectory.
sys.path.append(str(Path(__file__).resolve().parents[2]))

import app_agents
import app_state
from storage_manager import current_thread_id, storage_manager


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _chunk_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text")
                if txt:
                    parts.append(str(txt))
        return "".join(parts)
    return str(content) if content is not None else ""


def _extract_last_ai_text(messages: List[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _chunk_to_text(msg.content).strip()
            if text:
                return text
    return ""


def _parse_tool_issues(messages: List[Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        payload = _safe_json_loads(msg.content)
        if not isinstance(payload, dict):
            continue

        status = str(payload.get("status", "")).lower()
        if status in {"fail", "error"}:
            issues.append(
                {
                    "tool": str(getattr(msg, "name", "tool")),
                    "error_type": str(payload.get("error_type", "UnknownError")),
                    "error_message": str(payload.get("error_message", "")),
                    "traceback": str(payload.get("traceback", "")),
                }
            )
    return issues


def _classify_issue(issues: List[Dict[str, str]], timeout: bool, exception: Optional[Exception]) -> Dict[str, str]:
    if exception is not None:
        return {
            "issue_type": "runtime_exception",
            "reason": f"{type(exception).__name__}: {exception}",
        }
    if timeout:
        return {
            "issue_type": "timeout",
            "reason": "Stream run exceeded max duration.",
        }
    if not issues:
        return {
            "issue_type": "none_detected",
            "reason": "No fail-status tool response captured.",
        }

    first = issues[0]
    et = first.get("error_type", "UnknownError")
    em = first.get("error_message", "")
    et_low = et.lower()
    em_low = em.lower()

    if "preflight" in et_low:
        tp = "protocol_preflight_error"
    elif "filenotfound" in et_low or "no such file" in em_low:
        tp = "input_path_error"
    elif "ee" in et_low or "earth engine" in em_low:
        tp = "gee_execution_error"
    elif "crs" in em_low or "projection" in em_low:
        tp = "crs_projection_error"
    elif "auth" in em_low or "permission" in em_low:
        tp = "auth_or_permission_error"
    else:
        tp = "execution_error"

    reason = f"{et}: {em}".strip()
    return {
        "issue_type": tp,
        "reason": reason[:500],
    }


def _api_key_for_model(model: str) -> str:
    if "qwen" in model.lower():
        return os.getenv("DASHSCOPE_API_KEY", "").strip()
    return os.getenv("OPENAI_API_KEY", "").strip()


def run_one(model: str, case_id: int, case_text: str, exp_id: str, max_duration_s: int = 300) -> Dict[str, Any]:
    key = _api_key_for_model(model)
    if not key:
        return {
            "exp_id": exp_id,
            "model": model,
            "case_id": case_id,
            "success": False,
            "issue_type": "missing_api_key",
            "reason": "Required API key not found in environment.",
            "runtime_s": 0.0,
            "output_files": "",
            "attempt_count": 1,
            "attempts_used": 1,
        }

    thread_id = f"{exp_id}_{model.replace('.', '_').replace('-', '_')}_{case_id}"
    token = current_thread_id.set(thread_id)

    workspace = storage_manager.get_workspace(thread_id)
    in_dir = workspace / "inputs"
    out_dir = workspace / "outputs"
    before_in_files = {f.name for f in in_dir.glob("*.*")} if in_dir.exists() else set()
    before_out_files = {f.name for f in out_dir.glob("*.*")} if out_dir.exists() else set()

    run_root = Path("experiments/parallel_eval/runs") / exp_id / model / "worker_01" / f"case_{case_id}"
    _ensure_dir(run_root)

    timeout = False
    exception: Optional[Exception] = None
    final_messages: List[Any] = []
    event_counter = 0
    start = time.time()

    try:
        graph = app_agents.get_ntl_graph(
            model_name=model,
            api_key=key,
            request_timeout_s=int(getattr(app_state, "LLM_REQUEST_TIMEOUT_S", 120)),
            session_tag=thread_id,
        )

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": int(getattr(app_state, "RECURSION_LIMIT", 31)),
        }
        state = {"messages": [{"role": "user", "content": case_text}]}

        events = graph.stream(state, config=config, stream_mode="values")
        for event in events:
            event_counter += 1
            if time.time() - start > max_duration_s:
                timeout = True
                break
            if isinstance(event, dict) and isinstance(event.get("messages"), list):
                final_messages = event["messages"]

    except Exception as exc:  # noqa: BLE001
        exception = exc

    runtime_s = round(time.time() - start, 2)

    after_in_files = {f.name for f in in_dir.glob("*.*")} if in_dir.exists() else set()
    after_out_files = {f.name for f in out_dir.glob("*.*")} if out_dir.exists() else set()
    new_in_files = sorted(list(after_in_files - before_in_files))
    new_out_files = sorted(list(after_out_files - before_out_files))
    new_files = sorted(new_in_files + new_out_files)

    issues = _parse_tool_issues(final_messages)
    cls = _classify_issue(issues, timeout, exception)
    last_ai = _extract_last_ai_text(final_messages)

    case_result = {
        "exp_id": exp_id,
        "model": model,
        "worker": "worker_01",
        "case_id": case_id,
        "category": "",
        "success": len(issues) == 0 and (exception is None) and (not timeout),
        "attempt_count": 1,
        "attempts_used": 1,
        "hallucination": False,
        "execution_error": cls["issue_type"] not in {"none_detected"},
        "issue_type": cls["issue_type"],
        "reason": cls["reason"],
        "runtime_s": runtime_s,
        "event_count": event_counter,
        "input_files_count": len(new_in_files),
        "output_files_count": len(new_out_files),
        "new_input_files": new_in_files,
        "new_output_files": new_out_files,
        "output_files": new_files,
    }

    # Heuristic hallucination flag: claims output but produced no files
    if ("output" in (last_ai or "").lower() or "csv" in (last_ai or "").lower()) and len(new_files) == 0:
        case_result["hallucination"] = True

    # Persist artifacts
    (run_root / "final_answer.md").write_text(last_ai or "", encoding="utf-8")
    (run_root / "issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "case_result.json").write_text(json.dumps(case_result, ensure_ascii=False, indent=2), encoding="utf-8")

    current_thread_id.reset(token)
    return {
        **case_result,
        "output_files": ";".join(new_files),
    }


def main() -> None:
    load_dotenv()
    exp_id = f"three_model_single_case_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"

    case_bank = pd.read_csv("experiments/parallel_eval/benchmark/canonical_70_cases.csv")
    case_map = {int(r["id"]): str(r["case"]) for _, r in case_bank.iterrows()}

    plan = [
        ("qwen3-max-2026-01-23", 1),
        ("gpt-5-mini", 35),
        ("qwen-plus-2025-12-01", 70),
    ]

    rows: List[Dict[str, Any]] = []
    for model, case_id in plan:
        case_text = case_map.get(case_id, "")
        if not case_text:
            rows.append(
                {
                    "exp_id": exp_id,
                    "model": model,
                    "case_id": case_id,
                    "success": False,
                    "issue_type": "missing_case",
                    "reason": "Case not found in canonical_70_cases.csv",
                    "runtime_s": 0.0,
                    "output_files": "",
                    "attempt_count": 1,
                    "attempts_used": 1,
                }
            )
            continue

        print(f"Running model={model}, case_id={case_id}")
        row = run_one(model, case_id, case_text, exp_id=exp_id, max_duration_s=300)
        rows.append(row)

    out_dir = Path("experiments/parallel_eval/analysis")
    _ensure_dir(out_dir)
    df = pd.DataFrame(rows)
    csv_path = out_dir / f"{exp_id}_report.csv"
    json_path = out_dir / f"{exp_id}_report.json"
    md_path = out_dir / f"{exp_id}_report.md"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 3-Model Single-Case Smoke Report\n",
        f"exp_id: `{exp_id}`\n",
        "\n",
        "| model | case_id | success | issue_type | reason | runtime_s | output_files_count |",
        "|---|---:|---:|---|---|---:|---:|",
    ]
    for _, r in df.iterrows():
        reason = str(r.get("reason", "")).replace("|", " ")[:160]
        lines.append(
            f"| {r['model']} | {int(r['case_id'])} | {bool(r['success'])} | {r['issue_type']} | {reason} | {float(r['runtime_s']):.2f} | {int(r.get('output_files_count', 0))} |"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("Saved:")
    print(csv_path)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
