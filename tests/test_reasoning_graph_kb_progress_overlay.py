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


def _build_payload(events):
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
    return ns["_build_reasoning_graph_payload"](events, show_sub_steps=False)


def test_graph_shows_kb_progress_nodes_before_final_tool_message():
    events = [
        {"messages": [HumanMessage(content="q"), AIMessage(content="calling kb", name="NTL_Engineer")]},
        {"kb_progress": [{"event_type": "kb_progress", "phase": "knowledge_retrieval", "status": "running"}]},
    ]
    payload = _build_payload(events)
    node_ids = [str((n.get("data") or {}).get("id")) for n in payload.get("nodes", [])]
    assert any(node_id.startswith("kbp_") for node_id in node_ids)


def test_graph_hides_kb_progress_nodes_after_final_tool_message_exists():
    events = [
        {"messages": [HumanMessage(content="q"), AIMessage(content="calling kb", name="NTL_Engineer")]},
        {"kb_progress": [{"event_type": "kb_progress", "phase": "knowledge_retrieval", "status": "running"}]},
        {"messages": [ToolMessage(content='{"status":"ok"}', name="NTL_Knowledge_Base", tool_call_id="tc1")]},
    ]
    payload = _build_payload(events)
    node_ids = [str((n.get("data") or {}).get("id")) for n in payload.get("nodes", [])]
    assert not any(node_id.startswith("kbp_") for node_id in node_ids)
    kb_nodes = [n for n in payload.get("nodes", []) if str((n.get("data") or {}).get("id")) == "tc_1"]
    assert kb_nodes
    kb_node = kb_nodes[0]
    assert str(kb_node.get("classes")) == "tool_kb"
    assert "Tool:" not in str((kb_node.get("data") or {}).get("label", ""))


def test_graph_hides_transfer_tool_nodes_and_connects_agents_directly():
    events = [
        {
            "messages": [
                HumanMessage(content="handoff"),
                AIMessage(content="call transfer", name="NTL_Engineer"),
                ToolMessage(content='{"status":"ok"}', name="transfer_to_data_searcher", tool_call_id="tc1"),
            ]
        }
    ]
    payload = _build_payload(events)
    transfer_nodes = [n for n in payload.get("nodes", []) if str((n.get("data") or {}).get("id")) == "tc_1"]
    assert not transfer_nodes
    edge_set = {
        (str((e.get("data") or {}).get("source")), str((e.get("data") or {}).get("target")), str(e.get("classes")))
        for e in payload.get("edges", [])
    }
    assert ("ai_ntl_engineer", "ai_data_searcher", "handoff_edge") in edge_set
