import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "geocode_knowledge_tool.py"
    spec = importlib.util.spec_from_file_location("geocode_knowledge_tool_runtime_mix_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load geocode_knowledge_tool module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_geocode_recipe_runtime_enabled_includes_runtime_pool():
    mod = _load_module()
    payload = mod.GeoCode_Knowledge_Recipes_tool.invoke(
        {
            "query": "Calculate Shanghai district ANTL zonal stats in 2020 with amap boundary",
            "top_k": 4,
            "library_focus": "gee",
            "include_runtime": True,
        }
    )
    data = json.loads(payload)
    assert data["include_runtime"] is True
    assert data["recipe_pool"]["runtime_curated_count"] >= 0
    assert data["recipe_pool"]["selected_runtime_count"] <= 4
    if data["recipe_pool"]["runtime_curated_count"] > 0:
        assert any(item.get("source") == "runtime_curated" for item in data["matched_recipes"])


def test_geocode_recipe_runtime_disabled_keeps_static_only():
    mod = _load_module()
    payload = mod.GeoCode_Knowledge_Recipes_tool.invoke(
        {
            "query": "Need gee zonal stats recipe for districts",
            "top_k": 3,
            "library_focus": "gee",
            "include_runtime": False,
        }
    )
    data = json.loads(payload)
    assert data["include_runtime"] is False
    assert data["recipe_pool"]["runtime_curated_count"] == 0
    assert data["recipe_pool"]["selected_runtime_count"] == 0
    assert all(item.get("source") != "runtime_curated" for item in data["matched_recipes"])


def test_runtime_recipe_code_is_compacted_to_avoid_bloat():
    mod = _load_module()
    runtime = mod._load_runtime_recipes()
    for item in runtime:
        assert len(item.get("code", "")) <= mod.RUNTIME_CODE_MAX_CHARS + 120
