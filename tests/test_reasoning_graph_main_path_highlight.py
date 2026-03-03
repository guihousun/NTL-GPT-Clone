import ast
import json
import re
import textwrap
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _load_functions(function_names):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    nodes = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}

    ns = {
        "re": re,
        "json": json,
        "textwrap": textwrap,
        "HumanMessage": HumanMessage,
        "AIMessage": AIMessage,
        "ToolMessage": ToolMessage,
        "_tr": (lambda zh, en: en),
    }
    for name in function_names:
        node = nodes.get(name)
        if node is None:
            raise RuntimeError(f"Function {name} not found in app_ui.py")
        exec(compile(ast.Module(body=[node], type_ignores=[]), filename=str(app_ui_path), mode="exec"), ns)
    return ns


def _build_payload(events, show_sub_steps=False):
    names = [
        "_extract_json",
        "_build_reasoning_sections",
        "_truncate_text",
        "_normalize_content_to_text",
        "_wrap_reasoning_label",
        "_message_preview",
        "_make_reasoning_node",
        "_agent_node_id",
        "_extract_tool_event",
        "_cluster_consecutive_tools",
        "_format_tool_cluster_label",
        "_compute_main_path_edges",
        "_kb_phase_specs",
        "_build_kb_progress_nodes_from_records",
        "_infer_transfer_target_agent",
        "_build_reasoning_graph_payload",
    ]
    ns = _load_functions(names)
    return ns["_build_reasoning_graph_payload"](events, show_sub_steps=show_sub_steps)


def test_main_path_marks_primary_edges_and_excludes_detail_edges():
    events = [
        {
            "messages": [
                HumanMessage(content="Need workflow"),
                AIMessage(content="I'll search and handoff", name="NTL_Engineer"),
                ToolMessage(content='{"status":"success","steps":[{"name":"s1","description":"d1"}]}', name="NTL_Knowledge_Base", tool_call_id="tc1"),
                ToolMessage(content='{"status":"ok"}', name="transfer_to_code_assistant", tool_call_id="tc2"),
                AIMessage(content="coding now", name="Code_Assistant"),
            ]
        }
    ]

    payload = _build_payload(events, show_sub_steps=True)
    main_ids = set(payload.get("main_edge_ids", []))
    assert main_ids, "main path edge ids should exist"

    edges = payload.get("edges", [])
    edge_by_id = {str((e.get("data") or {}).get("id")): e for e in edges}

    # Detail edges should not belong to main path.
    detail_ids = {
        str((e.get("data") or {}).get("id"))
        for e in edges
        if str(e.get("classes")) == "detail_edge"
    }
    assert detail_ids, "show_sub_steps=True should create detail edges"
    assert main_ids.isdisjoint(detail_ids)

    # Handoff edge should be treated as main path.
    handoff_ids = {
        str((e.get("data") or {}).get("id"))
        for e in edges
        if str(e.get("classes")) == "handoff_edge"
    }
    assert handoff_ids
    assert handoff_ids.issubset(main_ids)

    # Non-main edges should exist when details are enabled.
    non_main = [eid for eid in edge_by_id if eid not in main_ids]
    assert non_main


def test_return_edge_is_main_when_no_handoff_for_same_tool_node():
    events = [
        {
            "messages": [
                HumanMessage(content="Need retrieval"),
                AIMessage(content="call tool", name="NTL_Engineer"),
                ToolMessage(content='{"status":"success"}', name="tavily_search", tool_call_id="tc3"),
                AIMessage(content="done", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events, show_sub_steps=False)
    main_ids = set(payload.get("main_edge_ids", []))
    edges = payload.get("edges", [])
    return_edges = [
        e for e in edges if str(e.get("classes")) == "return_edge"
    ]
    assert return_edges
    for edge in return_edges:
        eid = str((edge.get("data") or {}).get("id"))
        assert eid in main_ids


def test_show_sub_steps_toggle_controls_detail_nodes():
    events = [
        {
            "messages": [
                HumanMessage(content="Need workflow"),
                AIMessage(content="search", name="NTL_Engineer"),
                ToolMessage(content='{"status":"success","steps":[{"name":"s1","description":"d1"}]}', name="NTL_Knowledge_Base", tool_call_id="tc4"),
            ]
        }
    ]
    payload_off = _build_payload(events, show_sub_steps=False)
    payload_on = _build_payload(events, show_sub_steps=True)
    detail_off = [e for e in payload_off.get("edges", []) if str(e.get("classes")) == "detail_edge"]
    detail_on = [e for e in payload_on.get("edges", []) if str(e.get("classes")) == "detail_edge"]
    assert not detail_off
    assert detail_on
