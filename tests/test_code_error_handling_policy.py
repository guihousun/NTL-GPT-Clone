import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_error_policy", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_simple_error_policy_for_local_type_error():
    mod = _load_module()
    save_result = mod.save_geospatial_script_tool.invoke(
        {"script_content": "raise TypeError('bad args')\n", "script_name": "type_error_case.py", "overwrite": True},
        config={"configurable": {"thread_id": "thread_policy_simple"}},
    )
    save_data = json.loads(save_result)
    assert save_data["status"] == "success"
    result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "type_error_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": "thread_policy_simple"}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    policy = data.get("error_handling_policy")
    assert isinstance(policy, dict)
    assert policy.get("severity") == "simple"
    assert policy.get("should_handoff_to_engineer") is False
    assert policy.get("max_self_retries") == 1


def test_hard_error_policy_for_boundary_preflight_failure():
    mod = _load_module()
    code = "import ee\nregion=ee.Geometry.Rectangle([0,0,1,1])\nprint(region)\n"
    result = mod.GeoCode_COT_Validation_tool.invoke(
        {"code_block": code, "strict_mode": True},
        config={"configurable": {"thread_id": "thread_policy_hard"}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    assert data.get("error_type") == "PreflightError"
    policy = data.get("error_handling_policy")
    assert isinstance(policy, dict)
    assert policy.get("severity") == "hard"
    assert policy.get("should_handoff_to_engineer") is True
    assert policy.get("max_self_retries") == 0


def test_hard_error_policy_for_missing_script():
    mod = _load_module()
    result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "missing_script_for_policy.py", "strict_mode": True},
        config={"configurable": {"thread_id": "thread_policy_missing"}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    assert data.get("error_type") == "ScriptNotFoundError"
    policy = data.get("error_handling_policy")
    assert isinstance(policy, dict)
    assert policy.get("severity") == "hard"
    assert policy.get("should_handoff_to_engineer") is True
