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


def _tool_labels(payload):
    labels = []
    for node in payload.get("nodes", []):
        data = node.get("data", {})
        if data.get("kind") == "tool":
            labels.append(str(data.get("label", "")))
    return labels


def test_consecutive_same_tool_is_clustered_with_seq_and_last_status():
    events = [
        {
            "messages": [
                HumanMessage(content="Run retrieval"),
                AIMessage(content="calling tools", name="NTL_Engineer"),
                ToolMessage(content='{"status":"success"}', name="NTL_download_tool", tool_call_id="t1"),
                ToolMessage(content='{"status":"fail"}', name="NTL_download_tool", tool_call_id="t2"),
                AIMessage(content="done", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    labels = _tool_labels(payload)
    joined = "\n".join(labels)
    assert "NTL_download_tool" in joined
    assert "#1,#2" in joined
    assert "x2" in joined
    assert "last=fail" in joined
    assert "last=unknown" not in joined
    assert "last=ok" not in joined
    assert "Tool:" in joined
    assert sum("NTL_download_tool" in x for x in labels) == 1


def test_non_consecutive_same_tool_is_not_clustered():
    events = [
        {
            "messages": [
                HumanMessage(content="Run retrieval"),
                AIMessage(content="calling tools", name="NTL_Engineer"),
                ToolMessage(content='{"status":"success"}', name="NTL_download_tool", tool_call_id="t1"),
                ToolMessage(content='{"status":"success"}', name="geodata_quick_check_tool", tool_call_id="t2"),
                ToolMessage(content='{"status":"success"}', name="NTL_download_tool", tool_call_id="t3"),
                AIMessage(content="done", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    labels = _tool_labels(payload)
    download_labels = [x for x in labels if "NTL_download_tool" in x]
    assert len(download_labels) == 2
    assert any("#1" in x for x in download_labels)
    assert any("#3" in x for x in download_labels)
    assert all("| x1" not in x for x in download_labels)


def test_single_call_tools_do_not_show_x1_suffix():
    events = [
        {
            "messages": [
                HumanMessage(content="Run once"),
                AIMessage(content="call one tool", name="NTL_Engineer"),
                ToolMessage(content='{"status":"ok"}', name="tavily_search", tool_call_id="t1"),
                AIMessage(content="done", name="NTL_Engineer"),
            ]
        }
    ]
    payload = _build_payload(events)
    labels = _tool_labels(payload)
    assert any("tavily_search" in x for x in labels)
    assert all("| x1" not in x for x in labels)
