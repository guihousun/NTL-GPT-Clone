import ast
from pathlib import Path


def _load_function(name):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    nodes = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}
    ns = {"_tr": (lambda zh, en: en)}
    for dep in ("_kb_phase_specs", "_build_kb_progress_nodes_from_records"):
        node = nodes.get(dep)
        if node is None:
            raise RuntimeError(f"Function {dep} not found")
        exec(compile(ast.Module(body=[node], type_ignores=[]), filename=str(app_ui_path), mode="exec"), ns)
    return ns[name]


def test_build_kb_progress_nodes_from_records_status_projection():
    fn = _load_function("_build_kb_progress_nodes_from_records")
    records = [
        {"event_type": "kb_progress", "phase": "query_received", "status": "done"},
        {"event_type": "kb_progress", "phase": "knowledge_retrieval", "status": "running"},
    ]
    nodes = fn(records)
    by_key = {n["key"]: n for n in nodes}
    assert by_key["query_received"]["done"] is True
    assert by_key["knowledge_retrieval"]["running"] is True
    assert by_key["structured_output"]["done"] is False
