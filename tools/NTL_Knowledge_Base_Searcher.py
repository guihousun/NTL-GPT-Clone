# ntl_knowledge_base_searcher.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import uuid
from functools import lru_cache
from typing import Annotated, Optional

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from tools.NTL_Knowledge_Base import (
    NTL_Code_Knowledge,
    NTL_Literature_Knowledge,
    NTL_Solution_Knowledge,
)
from utils.ntl_kb_aliases import (
    TOOL_ALIAS_MAP,
    normalize_tool_name,
    normalize_workflow_payload,
)


class State(TypedDict):
    messages: Annotated[list, add_messages]
    response_mode: Optional[str]  # auto | workflow | theory | code | mixed
    locale: Optional[str]  # en | zh, etc.
    need_citations: Optional[bool]
    intent_profile: Optional[dict]


TOOLS = [NTL_Literature_Knowledge, NTL_Solution_Knowledge, NTL_Code_Knowledge]


@lru_cache(maxsize=1)
def _tool_registry_snapshot() -> dict[str, str]:
    from tools import Code_tools, Engineer_tools, data_searcher_tools

    snapshot: dict[str, str] = {}
    for tool in Engineer_tools + data_searcher_tools + Code_tools:
        name = getattr(tool, "name", "")
        if not name or name == "NTL_Knowledge_Base":
            continue
        snapshot[name] = getattr(tool, "description", "No description provided.")
    return snapshot


def _tool_manual_str() -> str:
    items = [f"- **{name}**: {desc}" for name, desc in _tool_registry_snapshot().items()]
    return "\n".join(items)


def _extract_first_json_dict(text: str) -> tuple[dict | None, str]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        if isinstance(obj, dict):
            rest = text[:idx] + text[idx + end :]
            return obj, rest.strip()
    return None, text


def _extract_empty_store_status(content: str) -> dict | None:
    payload, _ = _extract_first_json_dict(content)
    if isinstance(payload, dict) and payload.get("status") == "empty_store":
        return payload
    return None


def _is_methodology_reproduction_query(query: str) -> bool:
    q = (query or "").lower()
    keywords = (
        "reproduce",
        "replicate",
        "methodology",
        "methods",
        "equation",
        "parameter setting",
        "experiment setup",
        "according to the paper",
        "paper method",
        "复现",
        "方法论",
        "方法",
        "公式",
        "参数设置",
        "实验设置",
        "按论文",
        "依据论文",
    )
    return any(keyword in q for keyword in keywords)


def _tool_priority_names(mode: str, query: str, intent_profile: dict | None = None) -> list[str]:
    m = (mode or "auto").lower()
    intent = intent_profile if isinstance(intent_profile, dict) else _fallback_intent_profile(query, m)
    if m == "theory":
        return [
            "NTL_Literature_Knowledge",
            "NTL_Solution_Knowledge",
            "NTL_Code_Knowledge",
        ]
    if intent.get("prefer_literature") or _is_methodology_reproduction_query(query):
        return [
            "NTL_Literature_Knowledge",
            "NTL_Code_Knowledge",
            "NTL_Solution_Knowledge",
        ]
    if m == "workflow":
        return [
            "NTL_Solution_Knowledge",
            "NTL_Code_Knowledge",
        ]
    if m in {"code", "mixed"}:
        return [
            "NTL_Code_Knowledge",
            "NTL_Solution_Knowledge",
        ]
    return [
        "NTL_Solution_Knowledge",
        "NTL_Code_Knowledge",
    ]


def _extract_latest_user_query(messages: list) -> str:
    for item in reversed(messages or []):
        if isinstance(item, tuple) and len(item) >= 2:
            role = str(item[0]).lower()
            if role in {"user", "human"}:
                return str(item[1])
        role = str(getattr(item, "type", "")).lower()
        if role in {"human", "user"}:
            return str(getattr(item, "content", ""))
    return ""


def _select_tools_by_priority(mode: str, query: str, intent_profile: dict | None = None) -> list[StructuredTool]:
    lookup = {tool.name: tool for tool in TOOLS}
    ordered_names = _tool_priority_names(mode, query, intent_profile)
    selected = [lookup[name] for name in ordered_names if name in lookup]
    return selected if selected else TOOLS


def _build_searcher_llm() -> ChatOpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY (or QWEN_API_KEY) is required for "
            "NTL_Knowledge_Base_Searcher qwen3.5-plus model."
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.5-plus"
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _count_matches(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _extract_first_json_list(text: str) -> tuple[list | None, str]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "[":
            continue
        try:
            obj, end = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        if isinstance(obj, list):
            rest = text[:idx] + text[idx + end :]
            return obj, rest.strip()
    return None, text


def _safe_json_loads(text: str):
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    payload, _ = _extract_first_json_dict(text)
    if isinstance(payload, dict):
        return payload
    lst, _ = _extract_first_json_list(text)
    if isinstance(lst, list):
        return lst
    return None


def _fallback_intent_profile(query: str, mode: str = "auto") -> dict:
    q = (query or "").lower()
    retrieval_like = _contains_any(q, ("download", "retrieve", "fetch", "collect", "obtain"))
    official_like = _contains_any(q, ("official", "authoritative", "usgs", "reliefweb", "government", "ocha", "un"))
    event_like = _contains_any(
        q,
        (
            "earthquake",
            "wildfire",
            "fire",
            "flood",
            "hurricane",
            "typhoon",
            "cyclone",
            "drought",
            "war",
            "conflict",
            "battle",
            "disaster",
            "emergency",
        ),
    )
    geospatial_like = _contains_any(
        q, ("gee", "earth engine", "viirs", "vnp46", "ntl", "antl", "radiance", "zonal", "raster")
    )
    analysis_like = _contains_any(
        q,
        (
            "assess",
            "assessment",
            "analysis",
            "impact",
            "damage",
            "compute",
            "calculate",
            "quantify",
            "pre-event",
            "post-event",
            "before event",
            "after event",
            "first night",
            "time series",
            "recovery",
        ),
    )
    if "_is_methodology_reproduction_query" in globals():
        methodology_like = bool(_is_methodology_reproduction_query(query))
    else:
        methodology_like = _contains_any(q, ("reproduce", "replicate", "method", "equation", "paper"))

    if methodology_like:
        intent_type = "methodology_reproduction"
    elif event_like and geospatial_like and analysis_like:
        intent_type = "event_impact_assessment"
    elif retrieval_like:
        intent_type = "data_retrieval"
    elif mode == "theory":
        intent_type = "theory_explanation"
    elif mode == "code":
        intent_type = "code_generation"
    else:
        intent_type = "general_query"

    return {
        "intent_type": intent_type,
        "requires_workflow": mode in {"workflow", "auto", "mixed"} or intent_type in {"event_impact_assessment", "data_retrieval"},
        "needs_official_sources": official_like or (event_like and analysis_like),
        "needs_geospatial_analysis": geospatial_like or intent_type == "event_impact_assessment",
        "needs_server_side_execution": geospatial_like and (analysis_like or event_like),
        "prefer_literature": methodology_like or mode == "theory",
        "prefer_code": mode in {"code", "mixed"} or geospatial_like,
        "prefer_solution": mode in {"workflow", "auto", "mixed"} and not methodology_like,
    }


def _normalize_intent_payload(payload, mode: str, query: str) -> dict:
    fallback = _fallback_intent_profile(query, mode)
    if not isinstance(payload, dict):
        return fallback

    normalized = dict(fallback)
    normalized.update(payload)

    bool_fields = (
        "requires_workflow",
        "needs_official_sources",
        "needs_geospatial_analysis",
        "needs_server_side_execution",
        "prefer_literature",
        "prefer_code",
        "prefer_solution",
    )
    for field in bool_fields:
        normalized[field] = bool(normalized.get(field, fallback[field]))

    intent_type = str(normalized.get("intent_type") or "").strip().lower()
    if not intent_type:
        intent_type = fallback["intent_type"]
    normalized["intent_type"] = intent_type
    return normalized


def _classify_query_intent_with_fallback(query: str, mode: str = "auto") -> dict:
    import os

    fallback = _fallback_intent_profile(query, mode)
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        return fallback

    prompt = (
        "Classify the user query intent for a geospatial/NTL workflow planner.\n"
        "Return JSON object only. No markdown, no commentary.\n\n"
        "Required keys:\n"
        "- intent_type: one of methodology_reproduction|event_impact_assessment|data_retrieval|theory_explanation|code_generation|general_query\n"
        "- requires_workflow: boolean\n"
        "- needs_official_sources: boolean\n"
        "- needs_geospatial_analysis: boolean\n"
        "- needs_server_side_execution: boolean\n"
        "- prefer_literature: boolean\n"
        "- prefer_code: boolean\n"
        "- prefer_solution: boolean\n\n"
        f"response_mode: {mode}\n"
        f"query: {query}"
    )

    try:
        llm = _build_searcher_llm()
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    txt = item.get("text")
                    if txt:
                        parts.append(str(txt))
            content = "\n".join(parts)
        elif not isinstance(content, str):
            content = str(content)

        parsed = _safe_json_loads(content)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            parsed = parsed[0]
        return _normalize_intent_payload(parsed, mode, query)
    except Exception:
        return fallback


def _is_event_analysis_intent(intent_profile: dict) -> bool:
    if not isinstance(intent_profile, dict):
        return False
    if str(intent_profile.get("intent_type", "")).lower() == "event_impact_assessment":
        return True
    return bool(
        intent_profile.get("needs_geospatial_analysis")
        and intent_profile.get("needs_server_side_execution")
        and intent_profile.get("needs_official_sources")
    )


def _infer_tool_from_intent(intent_profile: dict, valid_tools: set[str]) -> str:
    candidates: dict[str, int] = {}
    intent_type = str(intent_profile.get("intent_type", "")).lower()

    if "tavily_search" in valid_tools:
        score = 0
        if intent_profile.get("needs_official_sources"):
            score += 7
        if intent_type == "event_impact_assessment":
            score += 2
        if score > 0:
            candidates["tavily_search"] = score

    if "NTL_download_tool" in valid_tools:
        score = 0
        if intent_type == "data_retrieval":
            score += 8
        if intent_profile.get("needs_geospatial_analysis") and not intent_profile.get("needs_server_side_execution"):
            score += 3
        if intent_profile.get("needs_official_sources"):
            score -= 4
        if intent_type == "event_impact_assessment":
            score -= 4
        if score > 0:
            candidates["NTL_download_tool"] = score

    if "NTL_raster_statistics" in valid_tools and intent_profile.get("needs_geospatial_analysis"):
        candidates["NTL_raster_statistics"] = 3

    if not candidates:
        return ""
    return sorted(candidates.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _infer_tool_from_query(query: str, valid_tools: set[str], intent_profile: dict | None = None, mode: str = "auto") -> str:
    intent = intent_profile if isinstance(intent_profile, dict) else _classify_query_intent_with_fallback(query, mode)
    chosen = _infer_tool_from_intent(intent, valid_tools)
    if chosen:
        return chosen

    q = (query or "").lower()
    exact_mappings = (
        ("vnci", "VNCI_Compute"),
        ("administrative", "get_administrative_division_data"),
        ("boundary", "get_administrative_division_data"),
        ("zonal", "NTL_raster_statistics"),
        ("statistics", "NTL_raster_statistics"),
        ("trend", "Analyze_NTL_trend"),
        ("electrified", "Detect_Electrified_Areas_by_Thresholding"),
    )
    for marker, tool_name in exact_mappings:
        if marker in q and tool_name in valid_tools:
            return tool_name
    return ""


def _build_force_json_fallback_payload(
    user_query: str,
    valid_tools: set[str],
    intent_profile: dict | None = None,
    mode: str = "auto",
) -> dict:
    intent = intent_profile if isinstance(intent_profile, dict) else _classify_query_intent_with_fallback(user_query, mode)

    if _is_event_analysis_intent(intent):
        steps: list[dict] = []
        if "tavily_search" in valid_tools:
            steps.append(
                {
                    "type": "builtin_tool",
                    "name": "tavily_search",
                    "input": {
                        "query": (
                            "Retrieve authoritative event metadata from official sources "
                            "(event time, location/epicenter, intensity, and affected areas)."
                        )
                    },
                }
            )
        steps.extend(
            [
                {
                    "type": "geospatial_code",
                    "description": (
                        "Initialize GEE Python API and build an event-centric analysis region. "
                        "Select the appropriate daily NTL product (prefer VNP46A2 for VIIRS daily analyses) "
                        "and compute period statistics for pre-event baseline, first post-event overpass night, "
                        "and post-event recovery windows. For daily VNP46A2, determine first-night using event "
                        "time at epicenter local timezone: if event occurs after the local nightly overpass "
                        "(typically ~01:30 local), first-night must shift to local day D+1 (not D). "
                        "Record the rule and chosen first-night date in outputs. "
                        "Save daily/period metrics to "
                        "'outputs/event_daily_antl_metrics.csv'."
                    ),
                },
                {
                    "type": "geospatial_code",
                    "description": (
                        "Read 'outputs/event_daily_antl_metrics.csv' and compute impact/recovery indicators "
                        "dynamically using explicit formulas and assumptions. Save structured report to "
                        "'outputs/event_impact_assessment_report.json'."
                    ),
                },
            ]
        )
        return {
            "status": "ok",
            "task_id": "generated_event_analysis_workflow",
            "task_name": "Event impact assessment with GEE daily NTL",
            "category": "Generated",
            "description": "Intent-driven fallback workflow for event-impact geospatial analysis.",
            "steps": steps,
            "output": "outputs/event_impact_assessment_report.json",
        }

    fallback_tool = _infer_tool_from_query(user_query, valid_tools, intent_profile=intent, mode=mode)
    if fallback_tool:
        return {
            "status": "ok",
            "task_id": "generated_text_fallback_workflow",
            "task_name": f"Run {fallback_tool}",
            "category": "Generated",
            "description": "Generated from non-JSON model output to keep workflow contract stable.",
            "steps": [
                {
                    "type": "builtin_tool",
                    "name": fallback_tool,
                    "input": {},
                }
            ],
            "output": "",
        }

    return {
        "status": "no_valid_tool",
        "reason": (
            "Model returned non-JSON workflow output and no fallback tool "
            "could be inferred from intent."
        ),
        "sources": [],
    }


def _build_kb_response_contract(
    payload: dict,
    mode: str = "workflow",
    intent_profile: dict | None = None,
    supplementary_text: str = "",
) -> dict:
    if not isinstance(payload, dict):
        payload = {"status": "error", "reason": "Invalid payload type."}

    workflow = payload.get("workflow")
    if not isinstance(workflow, dict):
        if any(k in payload for k in ("task_id", "task_name", "category", "description", "steps", "output")):
            workflow = {
                "task_id": payload.get("task_id", ""),
                "task_name": payload.get("task_name", ""),
                "category": payload.get("category", ""),
                "description": payload.get("description", ""),
                "steps": payload.get("steps", []),
                "output": payload.get("output", ""),
            }
        else:
            workflow = {}

    status = str(payload.get("status") or ("ok" if workflow else "error")).strip().lower()
    reason = str(payload.get("reason") or "").strip()
    message = str(payload.get("message") or reason).strip()
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        sources = [sources] if sources else []

    intent = intent_profile if isinstance(intent_profile, dict) else {}
    contract = {
        "schema": "ntl.kb.response.v2",
        "status": status,
        "mode": mode,
        "intent": intent,
        "message": message,
        "reason": reason,
        "sources": sources,
        "workflow": workflow,
    }

    for key in ("task_id", "task_name", "category", "description", "steps", "output"):
        value = workflow.get(key)
        if value is None or value == "":
            value = payload.get(key)
        if value is not None and value != "":
            contract[key] = value

    if "steps" not in contract or not isinstance(contract.get("steps"), list):
        contract["steps"] = []
    if "output" not in contract:
        contract["output"] = ""

    if supplementary_text:
        contract["supplementary_text"] = supplementary_text
    return contract


def _validate_and_normalize_workflow_output(
    content: str,
    user_query: str = "",
    allow_trailing_text: bool = False,
    force_json: bool = False,
    intent_profile: dict | None = None,
    response_mode: str = "workflow",
) -> str:
    valid_tools = set(_tool_registry_snapshot().keys())
    intent = intent_profile if isinstance(intent_profile, dict) else _classify_query_intent_with_fallback(
        user_query, response_mode
    )
    data, rest = _extract_first_json_dict(content)
    if not isinstance(data, dict):
        if force_json:
            data = _build_force_json_fallback_payload(
                user_query,
                valid_tools,
                intent_profile=intent,
                mode=response_mode,
            )
        else:
            data = {
                "status": "error",
                "reason": "Model returned non-JSON output.",
                "message": "workflow payload unavailable for this request",
                "sources": [],
            }
        return json.dumps(
            _build_kb_response_contract(
                data,
                mode=response_mode,
                intent_profile=intent,
                supplementary_text=rest if allow_trailing_text and rest else "",
            ),
            ensure_ascii=False,
            indent=2,
        )
    if data.get("status") == "no_valid_tool":
        return json.dumps(
            _build_kb_response_contract(
                data,
                mode=response_mode,
                intent_profile=intent,
                supplementary_text=rest if allow_trailing_text and rest else "",
            ),
            ensure_ascii=False,
            indent=2,
        )

    if "steps" not in data and "tool_name" in data:
        normalized_tool = normalize_tool_name(str(data.get("tool_name", "")).strip())
        parameters = data.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}

        data = {
            "task_id": "generated_tool_workflow",
            "task_name": f"Run {normalized_tool or 'tool'}",
            "category": "Generated",
            "description": "Generated single-tool workflow from tool_name payload.",
            "steps": [
                {
                    "type": "builtin_tool",
                    "name": normalized_tool,
                    "input": parameters,
                }
            ],
            "output": data.get("output", ""),
        }
    elif "steps" not in data:
        embedded_workflow = data.get("workflow")
        embedded_steps = embedded_workflow.get("steps") if isinstance(embedded_workflow, dict) else None
        if isinstance(embedded_workflow, dict) and isinstance(embedded_steps, (list, dict)):
            promoted = dict(data)
            for key in ("task_id", "task_name", "category", "description", "steps", "output", "result", "sources"):
                if key not in promoted and key in embedded_workflow:
                    promoted[key] = embedded_workflow.get(key)
            if "steps" not in promoted:
                promoted["steps"] = embedded_steps
            if "output" not in promoted and "output" in embedded_workflow:
                promoted["output"] = embedded_workflow.get("output")
            data = promoted
        elif force_json:
            data = _build_force_json_fallback_payload(
                user_query,
                valid_tools,
                intent_profile=intent,
                mode=response_mode,
            )
            if data.get("status") == "ok" and isinstance(data, dict):
                data["task_id"] = "generated_dict_fallback_workflow"
        else:
            return json.dumps(
                _build_kb_response_contract(
                    data,
                    mode=response_mode,
                    intent_profile=intent,
                    supplementary_text=rest if allow_trailing_text and rest else "",
                ),
                ensure_ascii=False,
                indent=2,
            )

    normalized, invalid_names = normalize_workflow_payload(data, valid_tools)
    if invalid_names:
        fallback_tool = _infer_tool_from_query(
            user_query,
            valid_tools,
            intent_profile=intent,
            mode=response_mode,
        )
        if fallback_tool:
            for step in normalized.get("steps", []):
                if step.get("type") != "builtin_tool":
                    continue
                step_name = str(step.get("name", ""))
                # Only patch placeholder/empty tool ids; preserve explicit model-selected names.
                if (
                    step_name.startswith("builtin_tool_step_")
                    or not step_name
                    or step_name in {"tool", "builtin_tool"}
                ):
                    step["name"] = fallback_tool
            # Re-check after fallback replacement.
            normalized, invalid_names = normalize_workflow_payload(normalized, valid_tools)

    if invalid_names and force_json:
        steps = normalized.get("steps", []) if isinstance(normalized, dict) else []
        has_detailed_geospatial_steps = any(
            isinstance(step, dict) and step.get("type") in {"geospatial_code", "code"} for step in steps
        )
        if has_detailed_geospatial_steps:
            invalid_set = set(invalid_names)
            patched_steps = []
            fallback_tool = _infer_tool_from_query(
                user_query,
                valid_tools,
                intent_profile=intent,
                mode=response_mode,
            )
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if step.get("type") == "builtin_tool" and str(step.get("name", "")) in invalid_set:
                    if fallback_tool:
                        fixed = dict(step)
                        fixed["name"] = fallback_tool
                        patched_steps.append(fixed)
                    # If no fallback tool exists, drop only invalid builtin step and preserve the rest.
                    continue
                patched_steps.append(step)
            if patched_steps:
                normalized["steps"] = patched_steps
                normalized, invalid_names = normalize_workflow_payload(normalized, valid_tools)

    if invalid_names:
        if force_json:
            data = _build_force_json_fallback_payload(
                user_query,
                valid_tools,
                intent_profile=intent,
                mode=response_mode,
            )
        else:
            data = {
                "status": "no_valid_tool",
                "reason": (
                    "Invalid or unavailable tool names after normalization: "
                    + ", ".join(sorted(set(invalid_names)))
                ),
                "sources": [],
            }
        return json.dumps(
            _build_kb_response_contract(
                data,
                mode=response_mode,
                intent_profile=intent,
                supplementary_text=rest if allow_trailing_text and rest else "",
            ),
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps(
        _build_kb_response_contract(
            normalized,
            mode=response_mode,
            intent_profile=intent,
            supplementary_text=rest if allow_trailing_text and rest else "",
        ),
        ensure_ascii=False,
        indent=2,
    )


def agent(state: State):
    mode = (state.get("response_mode") or "auto").lower()
    need_citations = bool(state.get("need_citations", True))
    locale = state.get("locale", "en")
    user_query = _extract_latest_user_query(state.get("messages", []))
    intent_profile = state.get("intent_profile")
    if not isinstance(intent_profile, dict):
        intent_profile = _classify_query_intent_with_fallback(user_query, mode)
    selected_tools = _select_tools_by_priority(mode, user_query, intent_profile=intent_profile)
    priority_names = [tool.name for tool in selected_tools]
    priority_text = " -> ".join(priority_names)
    intent_label = str(intent_profile.get("intent_type", "general_query"))
    intent_profile_json = json.dumps(intent_profile, ensure_ascii=False)

    alias_lines = "\n".join(
        f"- `{legacy}` -> `{canonical}`" for legacy, canonical in sorted(TOOL_ALIAS_MAP.items())
    )

    system_prompt_text = SystemMessage(
        f"""
You are the NTL Knowledge Base Agent.
Your mission is to generate grounded NTL workflows/theory/code using only registered tools.

### NTL Stores
1. Literature Store: theory, formulas, scientific definitions
2. Solution Store: workflows, tool usage, datasets, parameter patterns
3. Code Store: concise Python/GEE snippets

Detected Query Intent: {intent_label}
Intent Profile JSON: {intent_profile_json}
Current Tool Priority: {priority_text}

### AVAILABLE TOOL MANUAL (STRICT REGISTRY)
You MUST ONLY use these tool names in workflow steps:
{_tool_manual_str()}

### LEGACY TOOL NAME ALIASES
When retrieval returns legacy names, convert them to canonical names:
{alias_lines}

### RESPONSE MODES
1) workflow: Return strict JSON object only (no markdown code fences).
2) theory: concise grounded bullets.
3) code: minimal runnable code snippet.
4) mixed: workflow JSON + theory bullets + short code.

### RULES
- Do not invent tool names outside registry.
- If a required parameter is missing, you MUST use safe defaults/placeholders and state them clearly.
- NEVER return `no_valid_tool` only because parameters are missing.
- `no_valid_tool` is allowed only when no tool in the registry can be mapped to the user intent.
- If the query asks methodology/equations/reproduction, you MUST prioritize `NTL_Literature_Knowledge` first.
- In `workflow` mode for non-reproduction queries, avoid literature retrieval to reduce noisy context.
- Otherwise in `code`/`mixed` mode, you MUST try `NTL_Code_Knowledge` first for executable snippets.
- If `NTL_Code_Knowledge` returns `{{"status":"empty_store","store":"Code_RAG",...}}`, you MUST clearly state:
  `code corpus unavailable` and suggest rebuilding `Code_RAG`.
- If no valid tool can be mapped, return:
  {{"status":"no_valid_tool","reason":"...","sources":[]}}
- If `NTL_Solution_Knowledge` returns a relevant workflow JSON (e.g., with detailed steps/windows/formulas),
  you MUST preserve those details in your final workflow instead of replacing them with generic templates.
- Prefer adapting retrieved workflow details (task_id, step descriptions, output paths, formulas)
  and only use generic fallback steps when retrieval details are unavailable.
- For disaster/event tasks using daily VNP46A2, treat "first night after event" as the first post-event
  nighttime overpass at epicenter local time. If event time is after local nightly overpass (~01:30 local),
  use local day D+1 for first-night (not day D), and state this rule explicitly in workflow text.

Language: {locale}
Citations Required: {need_citations}
Current Mode: {mode}
"""
    )

    prompt_template = ChatPromptTemplate.from_messages([system_prompt_text] + state["messages"])
    formatted_prompt = prompt_template.format_prompt()

    llm_gpt = _build_searcher_llm()
    model = llm_gpt.bind_tools(selected_tools)
    response = model.invoke(formatted_prompt)

    return {
        "messages": [response],
        "response_mode": mode,
        "need_citations": need_citations,
        "locale": locale,
        "intent_profile": intent_profile,
    }


workflow = StateGraph(State)
workflow.add_node("agent", agent)
workflow.add_node("tools", ToolNode(tools=TOOLS))
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": END})
workflow.add_edge("tools", "agent")
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)


class NTL_Knowledge_Searcher_Input(BaseModel):
    query: str = Field(..., description="Your question plus brief context.")
    response_mode: str = Field(
        default="auto",
        description="One of: auto|workflow|theory|code|mixed",
    )
    locale: str = Field(default="en", description="Output language preference (e.g., en|zh).")
    need_citations: bool = Field(
        default=True,
        description="Whether to include simple store/doc citations.",
    )


def _NTL_Knowledge_Searcher(
    query: str,
    response_mode: str = "auto",
    locale: str = "en",
    need_citations: bool = True,
) -> str:
    mode = (response_mode or "auto").lower()
    intent_profile = _classify_query_intent_with_fallback(query, mode)
    unique_id = str(uuid.uuid4())[:8]
    events = graph.stream(
        input={
            "messages": [("user", query)],
            "response_mode": response_mode,
            "locale": locale,
            "need_citations": need_citations,
            "intent_profile": intent_profile,
        },
        config={"configurable": {"thread_id": f"rag_{unique_id}"}, "recursion_limit": 25},
        stream_mode="values",
    )

    final_answer = ""
    for event in events:
        content = event["messages"][-1].content
        if isinstance(content, str):
            final_answer = content
        else:
            final_answer = json.dumps(content, ensure_ascii=False)

    empty_store_payload = _extract_empty_store_status(final_answer)
    if empty_store_payload and empty_store_payload.get("store") == "Code_RAG":
        notice = (
            "code corpus unavailable: Code_RAG currently has no indexed documents. "
            "Rebuild command: conda run -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py "
            "--profile code --code-guide-dir RAG/code_guide --tool-dir tools "
            "--persist-dir RAG/Code_RAG --collection-name Code_RAG --reset "
            "--report-path RAG/Code_RAG/rebuild_report.json"
        )
        if mode == "code":
            return notice
        if mode in {"mixed", "workflow", "auto"}:
            return json.dumps(
                _build_kb_response_contract(
                    {
                        "status": "code_corpus_unavailable",
                        "reason": notice,
                        "sources": [],
                    },
                    mode=mode,
                    intent_profile=intent_profile,
                ),
                ensure_ascii=False,
                indent=2,
            )

    if mode in {"workflow", "auto", "mixed"}:
        return _validate_and_normalize_workflow_output(
            final_answer,
            query,
            allow_trailing_text=mode == "mixed",
            force_json=mode in {"workflow", "auto"},
            intent_profile=intent_profile,
            response_mode=mode,
        )
    return final_answer


NTL_Knowledge_Base = StructuredTool.from_function(
    func=_NTL_Knowledge_Searcher,
    name="NTL_Knowledge_Base",
    description=(
        "Retrieve grounded knowledge for Nighttime Light (NTL) tasks from three internal stores:\n"
        "- Literature (theory, equations)\n"
        "- Solution (workflows, tools, datasets)\n"
        "- Code (concise Python/GEE snippets)\n\n"
        "Supports response modes: workflow | theory | code | mixed | auto."
    ),
    args_schema=NTL_Knowledge_Searcher_Input,
)
