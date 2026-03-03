import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_exec_options", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_execute_strict_mode_blocks_preflight_without_env(monkeypatch):
    mod = _load_module()
    thread_id = f"thread_exec_strict_{uuid4().hex[:8]}"
    monkeypatch.delenv("NTL_PREFLIGHT_BLOCKING", raising=False)

    code = "import os\nos.system('git status')\nprint('should_not_run_when_strict')\n"
    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "strict_preflight_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(save)["status"] == "success"

    strict_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "strict_preflight_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    strict_json = json.loads(strict_exec)
    assert strict_json["status"] == "fail"
    assert strict_json.get("error_type") == "PreflightError"
    assert strict_json.get("execution_skipped") is True

    loose_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "strict_preflight_case.py", "strict_mode": False},
        config={"configurable": {"thread_id": thread_id}},
    )
    loose_json = json.loads(loose_exec)
    assert loose_json["status"] == "success"
    assert loose_json.get("execution_skipped") is False


def test_execute_script_location_prefers_inputs_when_requested():
    mod = _load_module()
    thread_id = f"thread_exec_location_{uuid4().hex[:8]}"

    out_save = mod.save_geospatial_script_tool.invoke(
        {"script_content": "print('from_outputs')\n", "script_name": "loc_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(out_save)["status"] == "success"

    in_path = Path(mod.storage_manager.resolve_input_path("loc_case.py", thread_id=thread_id))
    in_path.parent.mkdir(parents=True, exist_ok=True)
    in_path.write_text("print('from_inputs')\n", encoding="utf-8")

    run = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "loc_case.py", "script_location": "inputs", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(run)
    assert data["status"] == "success"
    assert "from_inputs" in data.get("stdout", "")
    assert data.get("script_location") == "inputs"


def test_execute_force_execute_bypasses_dedupe_skip():
    mod = _load_module()
    thread_id = f"thread_exec_force_{uuid4().hex[:8]}"

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": "print('force_run')\n", "script_name": "force_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(save)["status"] == "success"

    first = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "force_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    first_json = json.loads(first)
    assert first_json["status"] == "success"
    assert first_json.get("execution_skipped") is False

    second = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "force_case.py", "strict_mode": True, "force_execute": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    second_json = json.loads(second)
    assert second_json["status"] == "success"
    assert second_json.get("execution_skipped") is False
    assert second_json.get("already_executed") is None

