from pathlib import Path


def test_graph_factory_prompt_guides_shared_and_inputs_discovery_with_glob():
    content = (Path(__file__).resolve().parent.parent / "graph_factory.py").read_text(encoding="utf-8")
    assert "prefer file tools first (for example `glob`)" in content
    assert "/inputs/*" in content
    assert "/shared/*" in content
