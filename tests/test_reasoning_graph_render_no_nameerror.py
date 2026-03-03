import ast
import json
import re
import textwrap
import uuid
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _load_functions(function_names):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    nodes = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}

    class _FakeStreamlit:
        def __init__(self):
            self.captions = []
            self.writes = []

        def caption(self, text):
            self.captions.append(text)

        def write(self, text):
            self.writes.append(text)

    class _FakeComponents:
        def __init__(self):
            self.html_calls = []

        def html(self, html, height=None, scrolling=False):
            self.html_calls.append((html, height, scrolling))

    ns = {
        "re": re,
        "json": json,
        "textwrap": textwrap,
        "uuid": uuid,
        "HumanMessage": HumanMessage,
        "AIMessage": AIMessage,
        "ToolMessage": ToolMessage,
        "st": _FakeStreamlit(),
        "components": _FakeComponents(),
        "_tr": (lambda zh, en: en),
    }
    for name in function_names:
        node = nodes.get(name)
        if node is None:
            raise RuntimeError(f"Function {name} not found in app_ui.py")
        exec(compile(ast.Module(body=[node], type_ignores=[]), filename=str(app_ui_path), mode="exec"), ns)
    return ns


def test_render_reasoning_map_no_name_error_for_fullscreen_template():
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
        "_escape_dot_label",
        "_build_reasoning_dot",
        "_json_for_html_script",
        "render_reasoning_map",
    ]
    ns = _load_functions(names)
    render = ns["render_reasoning_map"]
    fake_components = ns["components"]

    events = [
        {
            "messages": [
                HumanMessage(content="test"),
                AIMessage(content="response", name="NTL_Engineer"),
            ]
        }
    ]

    render(events)
    assert fake_components.html_calls, "components.html should be called without NameError"


def test_render_reasoning_map_includes_reflow_hooks():
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
        "_escape_dot_label",
        "_build_reasoning_dot",
        "_json_for_html_script",
        "render_reasoning_map",
    ]
    ns = _load_functions(names)
    render = ns["render_reasoning_map"]
    fake_components = ns["components"]

    events = [{"messages": [HumanMessage(content="x"), AIMessage(content="y", name="NTL_Engineer")]}]
    render(events)
    html, _, _ = fake_components.html_calls[-1]
    assert "setTimeout(() => {" in html
    assert "ResizeObserver" in html
    assert "MutationObserver" in html
    assert "visibilitychange" in html
