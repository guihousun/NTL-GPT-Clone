import ast
from pathlib import Path


def _load_function_from_app_ui(function_name: str):
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    lines = source.splitlines()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            namespace = {}
            exec(fn_source, namespace)
            return namespace[function_name]
    raise RuntimeError(f"Function {function_name} not found in app_ui.py")


def test_normalize_kb_payload_supports_alias_fields_and_workflow_steps():
    normalize = _load_function_from_app_ui("_normalize_kb_payload")
    payload = {
        "task": "Retrieve annual NTL",
        "type": "Data Retrieval",
        "result": "outputs/ntl_2015_2020.tif",
        "workflow": {
            "steps": {
                "1": {"type": "builtin_tool", "name": "NTL_download_tool", "input": {"year": 2015}},
                "2": {"type": "builtin_tool", "name": "NTL_download_tool", "input": {"year": 2016}},
            }
        },
    }

    normalized = normalize(payload)
    assert normalized["task_name"] == "Retrieve annual NTL"
    assert normalized["category"] == "Data Retrieval"
    assert normalized["output"] == "outputs/ntl_2015_2020.tif"
    assert isinstance(normalized["steps"], list)
    assert len(normalized["steps"]) == 2
    assert normalized["steps"][0]["name"] == "NTL_download_tool"


def test_normalize_kb_payload_keeps_reason_message_for_fallback_render():
    normalize = _load_function_from_app_ui("_normalize_kb_payload")
    payload = {
        "status": "empty_store",
        "store": "Code_RAG",
        "reason": "Code_RAG currently has no indexed documents.",
        "message": "code corpus unavailable",
    }

    normalized = normalize(payload)
    assert normalized["status"] == "empty_store"
    assert "reason" in normalized
    assert "message" in normalized
    assert normalized["steps"] == []


def test_normalize_kb_payload_supports_unified_contract_schema():
    normalize = _load_function_from_app_ui("_normalize_kb_payload")
    payload = {
        "schema": "ntl.kb.response.v2",
        "status": "ok",
        "mode": "workflow",
        "intent": {"intent_type": "event_impact_assessment"},
        "workflow": {
            "task_id": "generated_event_analysis_workflow",
            "task_name": "Event impact assessment with GEE daily NTL",
            "category": "Generated",
            "description": "workflow from contract",
            "steps": [
                {"type": "builtin_tool", "name": "tavily_search", "input": {"query": "official source"}}
            ],
            "output": "outputs/event_impact_assessment_report.json",
        },
    }

    normalized = normalize(payload)
    assert normalized["schema"] == "ntl.kb.response.v2"
    assert normalized["status"] == "ok"
    assert normalized["task_id"] == "generated_event_analysis_workflow"
    assert normalized["task_name"] == "Event impact assessment with GEE daily NTL"
    assert normalized["output"] == "outputs/event_impact_assessment_report.json"
    assert isinstance(normalized["steps"], list)
    assert normalized["steps"][0]["name"] == "tavily_search"


def test_normalize_kb_payload_exposes_kb_preliminary_task_level_fields():
    normalize = _load_function_from_app_ui("_normalize_kb_payload")
    payload = {
        "schema": "ntl.kb.response.v2",
        "status": "ok",
        "intent": {
            "intent_type": "data_retrieval",
            "proposed_task_level": "L1",
            "task_level_reason_codes": ["built_in_tool_matched", "download_only"],
            "task_level_confidence": 0.91,
        },
        "workflow": {
            "task_id": "demo",
            "task_name": "Demo",
            "steps": [],
        },
    }
    normalized = normalize(payload)
    assert normalized["proposed_task_level"] == "L1"
    assert normalized["task_level_reason_codes"] == ["built_in_tool_matched", "download_only"]
    assert normalized["task_level_confidence"] == 0.91


def test_normalize_kb_payload_supports_kb_subagent_schema_v1():
    normalize = _load_function_from_app_ui("_normalize_kb_payload")
    payload = {
        "schema": "ntl.kb.subagent.response.v1",
        "status": "ok",
        "intent_analysis": {
            "intent_type": "data_retrieval",
            "proposed_task_level": "L1",
            "task_level_reason_codes": ["built_in_tool_matched", "download_only"],
            "task_level_confidence": 0.92,
        },
        "response": {
            "task_id": "DMSP_Shanghai_2009_2010",
            "task_name": "Retrieve DMSP-OLS annual NTL data for Shanghai 2009-2010",
            "category": "Data Retrieval",
            "description": "Download DMSP-OLS annual composite data",
            "steps": [
                {
                    "type": "builtin_tool",
                    "name": "NTL_download_tool",
                    "input": {"study_area": "上海市", "time_range_input": "2009 to 2010"},
                }
            ],
            "output": "outputs/Shanghai_DMSP_2009_2010.tif",
        },
    }

    normalized = normalize(payload)
    assert normalized["task_id"] == "DMSP_Shanghai_2009_2010"
    assert normalized["task_name"].startswith("Retrieve DMSP-OLS")
    assert normalized["proposed_task_level"] == "L1"
    assert normalized["task_level_reason_codes"] == ["built_in_tool_matched", "download_only"]
    assert normalized["task_level_confidence"] == 0.92
    assert isinstance(normalized["steps"], list)
    assert normalized["steps"][0]["name"] == "NTL_download_tool"
