import ast
import re
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _load_functions(function_names):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    nodes = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}

    ns = {
        "re": re,
        "HumanMessage": HumanMessage,
        "AIMessage": AIMessage,
        "ToolMessage": ToolMessage,
    }
    for name in function_names:
        node = nodes.get(name)
        if node is None:
            raise RuntimeError(f"Function {name} not found in app_ui.py")
        exec(compile(ast.Module(body=[node], type_ignores=[]), filename=str(app_ui_path), mode="exec"), ns)
    return ns


def _build_payload(events):
    names = [
        "_truncate_text",
        "_agent_node_id",
        "_infer_transfer_target_agent",
        "_build_reasoning_sections",
        "_build_reasoning_graph_payload",
    ]
    ns = _load_functions(names)
    return ns["_build_reasoning_graph_payload"](events, show_sub_steps=False)


def _tool_labels(payload):
    labels = []
    for node in payload.get("nodes", []):
        data = node.get("data", {})
        if data.get("kind") == "tool":
            labels.append(str(data.get("label", "")))
    return labels


def test_compacts_repeated_tool_calls_under_same_ai_anchor():
    events = [
        {
            "messages": [
                HumanMessage(content="run"),
                AIMessage(content="step 1", name="Code_Assistant"),
                ToolMessage(content='{"ok":true}', name="ls", tool_call_id="t1"),
                AIMessage(content="step 2", name="Code_Assistant"),
                ToolMessage(content='{"ok":true}', name="ls", tool_call_id="t2"),
            ]
        }
    ]
    payload = _build_payload(events)
    labels = _tool_labels(payload)
    ls_labels = [x for x in labels if " ls" in f" {x}"]
    assert len(ls_labels) == 1
    assert "#1-2 ls*2" in ls_labels[0]


def test_does_not_compact_across_different_ai_anchor_non_target_variation():
    events = [
        {
            "messages": [
                HumanMessage(content="run"),
                AIMessage(content="engineer call", name="NTL_Engineer"),
                ToolMessage(content='{"ok":true}', name="ls", tool_call_id="t1"),
                AIMessage(content="handoff", name="Code_Assistant"),
                ToolMessage(content='{"ok":true}', name="ls", tool_call_id="t2"),
            ]
        }
    ]
    payload = _build_payload(events)
    labels = _tool_labels(payload)
    ls_labels = [x for x in labels if " ls" in f" {x}"]
    assert len(ls_labels) == 2
