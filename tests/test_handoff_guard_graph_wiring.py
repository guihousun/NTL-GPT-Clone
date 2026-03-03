from pathlib import Path


def test_graph_factory_wires_handoff_guard_before_summarization_for_subagents():
    content = (Path(__file__).resolve().parent.parent / "graph_factory.py").read_text(encoding="utf-8")
    assert "handoff_guard_middleware = SubagentHandoffGuardMiddleware()" in content
    assert "middleware=[handoff_guard_middleware, summarization_middleware]" in content
