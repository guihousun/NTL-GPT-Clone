import ast
from pathlib import Path


def _load_function(function_name: str):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    lines = source.splitlines()

    namespace = {"json": __import__("json")}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            exec(fn_source, namespace)
            return namespace[function_name]
    raise RuntimeError(f"Function {function_name} not found in app_ui.py")


def test_stage_classifier_maps_draft_validate_and_success():
    classify = _load_function("_classify_code_assistant_stage")

    assert classify("save_geospatial_script_tool", {"status": "success"}) == "Draft Received"
    assert classify("GeoCode_COT_Validation_tool", "{}") == "Validate/Execute"
    assert classify("execute_geospatial_script_tool", '{"status":"success"}') == "Success"


def test_stage_classifier_maps_escalation_variants():
    classify = _load_function("_classify_code_assistant_stage")

    assert classify("execute_geospatial_script_tool", '{"status":"fail"}') == "Escalate"
    assert classify("final_geospatial_code_execution_tool", {"status": "needs_engineer_decision"}) == "Escalate"
    assert classify("transfer_back_to_ntl_engineer", "") == "Escalate"
