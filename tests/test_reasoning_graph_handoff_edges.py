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


def _edge_set(payload):
    out = set()
    for edge in payload.get("edges", []):
        data = edge.get("data", {})
        out.add((data.get("source"), data.get("target"), edge.get("classes")))
    return out


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
    return ns["_build_reasoning_graph_payload"](events)


def test_transfer_to_code_assistant_uses_handoff_edge_without_noisy_return():
    events = [
        {
            "messages": [
                HumanMessage(content="Need coding help."),
                AIMessage(content="I will handoff to coder.", name="NTL_Engineer"),
                ToolMessage(content='{"status":"ok"}', name="transfer_to_code_assistant", tool_call_id="tc1"),
                AIMessage(content="Generating code...", name="Code_Assistant"),
            ]
        }
    ]
    payload = _build_payload(events)
    edges = _edge_set(payload)

    assert ("ai_ntl_engineer", "ai_code_assistant", "handoff_edge") in edges
    assert ("ai_ntl_engineer", "tc_1", "tool_call_edge") not in edges
    assert ("tc_1", "ai_code_assistant", "handoff_edge") not in edges
    assert ("ai_ntl_engineer", "ai_code_assistant", "flow") not in edges

    tool_nodes = [n for n in payload.get("nodes", []) if str((n.get("data") or {}).get("id")) == "tc_1"]
    assert not tool_nodes


def test_regular_tool_call_returns_to_same_agent():
    events = [
        {
            "messages": [
                HumanMessage(content="Search data."),
                AIMessage(content="Calling search tool.", name="NTL_Engineer"),
                ToolMessage(content='{"status":"ok"}', name="tavily_search", tool_call_id="tc2"),
                AIMessage(content="Got search results.", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    edges = _edge_set(payload)

    assert ("ai_ntl_engineer", "tc_1", "tool_call_edge") in edges
    assert ("tc_1", "ai_ntl_engineer", "return_edge") in edges
    assert ("tc_1", "ai_ntl_engineer", "handoff_edge") not in edges


def test_synthetic_handoff_back_messages_are_ignored():
    events = [
        {
            "messages": [
                HumanMessage(content="Return to engineer."),
                AIMessage(
                    content="Transferring back to NTL_Engineer",
                    name="Data_Searcher",
                    tool_calls=[{"name": "transfer_back_to_ntl_engineer", "args": {}, "id": "synthetic"}],
                    response_metadata={"__is_handoff_back": True},
                ),
                ToolMessage(
                    content="Successfully transferred back to NTL_Engineer",
                    name="transfer_back_to_ntl_engineer",
                    tool_call_id="synthetic",
                    response_metadata={"__is_handoff_back": True},
                ),
                AIMessage(content="Done. Returning.", name="Data_Searcher"),
                ToolMessage(
                    content='{"status":"ok"}',
                    name="transfer_back_to_ntl_engineer",
                    tool_call_id="real1",
                ),
                AIMessage(content="Received.", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    tool_details = [
        node.get("data", {}).get("detail", "")
        for node in payload.get("nodes", [])
        if node.get("classes") == "tool"
    ]
    transfer_back_nodes = [x for x in tool_details if "transfer_back_to_ntl_engineer" in x]
    assert len(transfer_back_nodes) == 0


def test_ai_to_ai_auto_return_is_rendered_as_handoff_edge():
    events = [
        {
            "messages": [
                HumanMessage(content="Need coding and then summary."),
                AIMessage(content="handoff to coder", name="NTL_Engineer"),
                ToolMessage(content='{"status":"ok"}', name="transfer_to_code_assistant", tool_call_id="tc_a"),
                AIMessage(content="working on code", name="Code_Assistant"),
                ToolMessage(content='{"status":"success"}', name="save_geospatial_script_tool", tool_call_id="tc_b"),
                AIMessage(content="returning result to engineer", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    edges = _edge_set(payload)
    assert ("ai_ntl_engineer", "ai_code_assistant", "handoff_edge") in edges
    assert ("ai_code_assistant", "ai_ntl_engineer", "handoff_edge") in edges
