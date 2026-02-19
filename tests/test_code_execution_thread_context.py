import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_ctx", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validation_tool_uses_thread_id_from_config():
    mod = _load_module()
    code = (
        "from storage_manager import storage_manager\n"
        "print(storage_manager.resolve_output_path('ctx_check.txt'))\n"
    )
    result = mod.GeoCode_COT_Validation_tool.invoke(
        {"code_block": code, "strict_mode": True},
        config={"configurable": {"thread_id": "thread_ctx_test"}},
    )
    data = json.loads(result)
    assert data["status"] == "pass"
    assert "thread_ctx_test" in data.get("stdout", "")
    assert "debug" not in data.get("stdout", "")


def test_final_execution_tool_uses_thread_id_from_config():
    mod = _load_module()
    code = (
        "from storage_manager import storage_manager\n"
        "print(storage_manager.resolve_output_path('ctx_check_final.txt'))\n"
    )
    result = mod.final_geospatial_code_execution_tool.invoke(
        {"final_geospatial_code": code, "strict_mode": True},
        config={"configurable": {"thread_id": "thread_ctx_final"}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert "thread_ctx_final" in data.get("stdout", "")
    assert "debug" not in data.get("stdout", "")
