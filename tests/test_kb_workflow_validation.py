from utils.ntl_kb_aliases import normalize_workflow_payload


def test_legacy_tool_names_are_normalized_to_canonical_names():
    payload = {
        "task_id": "QX",
        "task_name": "Legacy naming workflow",
        "category": "Test",
        "description": "legacy",
        "steps": [
            {"type": "builtin_tool", "name": "Get_Boundary_AMap_China", "input": {}},
            {"type": "builtin_tool", "name": "Geocode_China", "input": {}},
            {"type": "builtin_tool", "name": "VNCI_Calculation", "input": {}},
        ],
        "output": "ok",
    }
    valid = {
        "get_administrative_division_data",
        "geocode_tool",
        "VNCI_Compute",
    }
    normalized, invalid = normalize_workflow_payload(payload, valid)
    assert not invalid
    names = [step["name"] for step in normalized["steps"]]
    assert names == [
        "get_administrative_division_data",
        "geocode_tool",
        "VNCI_Compute",
    ]


def test_unavailable_tool_is_reported():
    payload = {
        "task_id": "QY",
        "task_name": "Unknown tool workflow",
        "category": "Test",
        "description": "invalid",
        "steps": [{"type": "builtin_tool", "name": "NotARealTool", "input": {}}],
        "output": "none",
    }
    normalized, invalid = normalize_workflow_payload(payload, {"some_other_tool"})
    assert normalized["steps"][0]["name"] == "NotARealTool"
    assert invalid == ["NotARealTool"]


def test_step_tool_name_and_input_parameters_are_normalized():
    payload = {
        "task_id": "QZ",
        "task_name": "Qwen style workflow",
        "category": "Test",
        "description": "qwen",
        "steps": [
            {
                "type": "builtin_tool",
                "tool_name": "tavily_search",
                "input_parameters": {"query": "USGS Myanmar earthquake"},
            },
            {
                "type": "builtin_tool",
                "tool_name": "NTL_download_tool",
                "input_parameters": {"study_area": "Myanmar", "temporal_resolution": "daily"},
            },
        ],
        "output": "ok",
    }
    valid = {"tavily_search", "NTL_download_tool"}
    normalized, invalid = normalize_workflow_payload(payload, valid)
    assert not invalid
    assert normalized["steps"][0]["name"] == "tavily_search"
    assert normalized["steps"][0]["input"]["query"] == "USGS Myanmar earthquake"
    assert normalized["steps"][1]["name"] == "NTL_download_tool"
    assert normalized["steps"][1]["input"]["study_area"] == "Myanmar"


def test_step_tool_and_parameters_schema_are_normalized_with_code_step():
    payload = {
        "task_id": "QA",
        "task_name": "Qwen tool schema workflow",
        "category": "Test",
        "description": "qwen tool",
        "steps": [
            {
                "type": "builtin_tool",
                "tool": "NTL_Mean_Composite",
                "parameters": {"input_files": ["a.tif", "b.tif"], "output_file": "mean.tif"},
                "action": "compute mean composite",
            },
            {
                "type": "builtin_tool",
                "tool": "geospatial_code",
                "action": "calculate change ratio and export report",
            },
        ],
        "output": "ok",
    }
    valid = {"NTL_Mean_Composite"}
    normalized, invalid = normalize_workflow_payload(payload, valid)
    assert not invalid
    assert normalized["steps"][0]["name"] == "NTL_Mean_Composite"
    assert normalized["steps"][0]["input"]["output_file"] == "mean.tif"
    assert normalized["steps"][1]["type"] == "geospatial_code"
    assert normalized["steps"][1]["name"].startswith("geospatial_code_step_")
