from pathlib import Path


def test_graph_factory_wires_handoff_guard_into_subagents():
    content = (Path(__file__).resolve().parent.parent / "graph_factory.py").read_text(encoding="utf-8")
    assert "SubagentHandoffGuardMiddleware" in content
    assert "handoff_guard_middleware = SubagentHandoffGuardMiddleware()" in content
    assert "middleware=[handoff_guard_middleware, summarization_middleware]" in content

