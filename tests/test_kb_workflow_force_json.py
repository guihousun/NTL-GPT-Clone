import ast
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base_Searcher.py"


def _load_validation_functions():
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    def _normalize_workflow_payload_stub(payload, valid_tool_names):
        invalid = []
        steps = payload.get("steps", []) if isinstance(payload, dict) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("type") == "builtin_tool":
                name = str(step.get("name", ""))
                if name not in valid_tool_names:
                    invalid.append(name)
        return payload, invalid

    namespace = {
        "json": json,
        "os": os,
        "_tool_registry_snapshot": lambda: {
            "NTL_download_tool": "download viirs yearly images",
            "NTL_raster_statistics": "zonal statistics tool",
            "tavily_search": "official source search",
        },
        "normalize_tool_name": lambda name: name,
        "normalize_workflow_payload": _normalize_workflow_payload_stub,
    }
    wanted = {
        "_extract_first_json_dict",
        "_extract_first_json_list",
        "_safe_json_loads",
        "_contains_any",
        "_count_matches",
        "_is_methodology_reproduction_query",
        "_fallback_intent_profile",
        "_propose_task_level_fallback",
        "_normalize_task_level_payload",
        "_classify_task_level_with_fallback",
        "_augment_intent_with_task_level",
        "_repair_non_json_output_with_llm",
        "_normalize_intent_payload",
        "_classify_query_intent_with_fallback",
        "_infer_tool_from_intent",
        "_infer_tool_from_query",
        "_is_event_analysis_intent",
        "_build_force_json_fallback_payload",
        "_build_kb_response_contract",
        "_build_non_executable_workflow_payload",
        "_validate_and_normalize_workflow_output",
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            exec(fn_source, namespace)
    return namespace["_validate_and_normalize_workflow_output"]


def test_workflow_validation_forces_json_when_model_returns_plain_text():
    validate = _load_validation_functions()
    result = validate(
        "I will download annual VIIRS imagery year by year and process it.",
        user_query="download annual ntl from 2015 to 2020",
        force_json=True,
    )
    payload = json.loads(result)
    assert payload["schema"] == "ntl.kb.response.v2"
    assert payload["status"] == "no_valid_tool"
    assert "could be inferred from intent" in (payload.get("reason") or "")
    assert payload.get("workflow", {}) == {}


def test_workflow_validation_builds_multistep_event_gee_fallback():
    validate = _load_validation_functions()
    result = validate(
        "Use official sources and then perform ANTL assessment.",
        user_query=(
            "Assess wildfire impact using daily VNP46A2 imagery. "
            "Retrieve official reports and compute pre/post-event ANTL "
            "with the GEE Python API."
        ),
        force_json=True,
    )
    payload = json.loads(result)
    assert payload["schema"] == "ntl.kb.response.v2"
    assert payload["status"] == "ok"
    assert payload["workflow"]["task_id"] == "generated_event_analysis_workflow"
    assert len(payload["workflow"]["steps"]) >= 2
    assert payload["workflow"]["steps"][0]["name"] == "tavily_search"
    geospatial_steps = [step for step in payload["workflow"]["steps"] if step.get("type") == "geospatial_code"]
    assert geospatial_steps
    rule_text = " ".join(step.get("description", "") for step in geospatial_steps)
    assert "first post-event overpass night" in rule_text
    assert "local day D+1" in rule_text


def test_workflow_validation_event_fallback_keeps_first_night_rule_for_non_earthquake():
    validate = _load_validation_functions()
    result = validate(
        "Use official sources and then perform ANTL assessment.",
        user_query=(
            "Assess conflict impact using daily VNP46A2 imagery. "
            "Retrieve official reports and compute pre/post-event ANTL "
            "with the GEE Python API."
        ),
        force_json=True,
    )
    payload = json.loads(result)
    assert payload["schema"] == "ntl.kb.response.v2"
    assert payload["status"] == "ok"
    assert payload["workflow"]["task_id"] == "generated_event_analysis_workflow"
    geospatial_steps = [step for step in payload["workflow"]["steps"] if step.get("type") == "geospatial_code"]
    assert geospatial_steps
    rule_text = " ".join(step.get("description", "") for step in geospatial_steps)
    assert "first post-event overpass night" in rule_text
    assert "local day D+1" in rule_text


def test_workflow_validation_preserves_nested_solution_workflow_details():
    validate = _load_validation_functions()
    content = json.dumps(
        {
            "schema": "ntl.kb.response.v2",
            "status": "ok",
            "workflow": {
                "task_id": "Q20",
                "task_name": "Earthquake Impact Assessment in Myanmar using Daily NTL (2025)",
                "category": "Application and Modeling > Disaster monitoring",
                "description": "Detailed workflow from Solution_RAG.",
                "steps": [
                    {
                        "type": "builtin_tool",
                        "name": "tavily_search",
                        "input": {
                            "query": "2025 Myanmar earthquake official USGS ReliefWeb epicenter magnitude event time"
                        },
                    },
                    {
                        "type": "geospatial_code",
                        "name": "geospatial_code_step_2",
                        "description": "Compute ANTL for pre-event, first-night, and post-event windows.",
                    },
                ],
                "output": "outputs/Impact_Assessment_Report.json",
            },
        }
    )
    result = validate(content, user_query="Myanmar earthquake ANTL assessment", force_json=True)
    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["task_id"] == "Q20"
    assert payload["workflow"]["task_id"] == "Q20"
    assert payload["workflow"]["output"] == "outputs/Impact_Assessment_Report.json"


def test_workflow_validation_keeps_agent_step_titles_when_tool_names_are_invalid():
    validate = _load_validation_functions()
    content = json.dumps(
        {
            "task_id": "wuhan_lockdown_antl",
            "task_name": "Wuhan lockdown ANTL comparison",
            "category": "Generated",
            "description": "Compare ANTL between 2020 lockdown and 2019 baseline.",
            "steps": [
                {
                    "type": "builtin_tool",
                    "name": "Choose appropriate NTL dataset based on temporal resolution needs",
                    "description": "Select VNP46A2 daily product and set windows.",
                },
                {
                    "type": "builtin_tool",
                    "name": "Apply quality control and corrections before aggregation",
                    "description": "Mask clouds and unstable pixels.",
                },
            ],
            "output": "outputs/wuhan_antl_compare.csv",
        }
    )
    result = validate(content, user_query="Wuhan lockdown ANTL compare", force_json=True)
    payload = json.loads(result)
    assert payload["schema"] == "ntl.kb.response.v2"
    assert payload["status"] == "no_valid_tool"
    workflow_steps = payload["workflow"]["steps"]
    assert workflow_steps
    assert workflow_steps[0]["type"] == "analysis_step"
    assert "Choose appropriate NTL dataset" in workflow_steps[0]["name"]
    assert workflow_steps[1]["type"] == "analysis_step"
    assert "Apply quality control and corrections before aggregation" in workflow_steps[1]["name"]


def test_workflow_validation_emits_kb_preliminary_task_level():
    validate = _load_validation_functions()
    result = validate(
        "Use existing tools to identify the district with highest ANTL in Shanghai.",
        user_query="Identify the district in Shanghai with the highest ANTL in a 2022 NPP-VIIRS-like image.",
        force_json=True,
    )
    payload = json.loads(result)
    assert payload["schema"] == "ntl.kb.response.v2"
    assert payload.get("proposed_task_level") in {"L1", "L2", "L3"}
    assert isinstance(payload.get("task_level_reason_codes"), list)
    assert isinstance(payload.get("task_level_confidence"), (int, float))
    intent = payload.get("intent", {})
    assert intent.get("task_level_proposal_source") == "NTL_Knowledge_Base_Searcher"


def test_task_level_classifier_prompt_contains_pixel_level_boundary_rule():
    source = TARGET.read_text(encoding="utf-8")
    assert "Pixel-level extremum tasks" in source
    assert "District/city-level zonal stats with direct built-in support are L2." in source
