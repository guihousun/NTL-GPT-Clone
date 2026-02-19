import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "langgraph_case_runner.py"
    spec = importlib.util.spec_from_file_location("langgraph_case_runner_for_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load langgraph_case_runner module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_analyze_messages_detects_partial_transfer_and_years():
    mod = _load_module()
    messages = [
        {
            "type": "tool",
            "name": "GEE_dataset_router_tool",
            "content": json.dumps(
                {
                    "estimated_image_count": 6,
                    "recommended_execution_mode": "direct_download",
                }
            ),
        },
        {
            "type": "tool",
            "name": "NTL_download_tool",
            "content": json.dumps({"output_files": ["ntl_2015.tif", "ntl_2016.tif"]}),
        },
        {
            "type": "ai",
            "name": "Data_Searcher",
            "tool_calls": [{"name": "transfer_back_to_ntl_engineer", "args": {}}],
        },
    ]
    analysis = mod.analyze_messages(messages)
    assert analysis["expected_image_count"] == 6
    assert analysis["router_recommended_mode"] == "direct_download"
    assert analysis["detected_years"] == [2015, 2016]
    assert analysis["partial_transfer_detected"] is True
    assert analysis["tool_calls_by_name"]["NTL_download_tool"] == 1


def test_analyze_messages_tracks_ordered_tool_calls():
    mod = _load_module()
    messages = [
        {
            "type": "ai",
            "name": "NTL_Engineer",
            "tool_calls": [{"name": "transfer_to_data_searcher", "args": {}}],
        },
        {
            "type": "tool",
            "name": "transfer_to_data_searcher",
            "content": "ok",
        },
        {
            "type": "ai",
            "name": "Data_Searcher",
            "tool_calls": [{"name": "NTL_download_tool", "args": {"time_range_input": "2015 to 2020"}}],
        },
        {
            "type": "tool",
            "name": "NTL_download_tool",
            "content": json.dumps({"output_files": [f"ntl_{y}.tif" for y in range(2015, 2021)]}),
        },
    ]
    analysis = mod.analyze_messages(messages)
    assert len(analysis["ordered_tool_calls"]) == 2
    assert analysis["ordered_tool_calls"][0]["tool"] == "transfer_to_data_searcher"
    assert analysis["ordered_tool_calls"][1]["tool"] == "NTL_download_tool"
    assert analysis["detected_years"] == [2015, 2016, 2017, 2018, 2019, 2020]
