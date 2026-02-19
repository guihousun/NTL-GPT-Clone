import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_convergence_guard", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_save_tool_reuses_existing_script_for_identical_content():
    mod = _load_module()
    thread_id = f"thread_save_dedupe_{uuid4().hex[:8]}"
    code = "print('dedupe_save_ok')\n"

    first = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "dedupe_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    first_json = json.loads(first)
    assert first_json["status"] == "success"

    second = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "dedupe_case.py", "overwrite": False},
        config={"configurable": {"thread_id": thread_id}},
    )
    second_json = json.loads(second)
    assert second_json["status"] == "success"
    assert second_json["script_name"] == first_json["script_name"]
    assert second_json["script_path"] == first_json["script_path"]
    assert second_json.get("dedupe", {}).get("reused_existing_script") is True


def test_execute_tool_skips_redundant_second_success_execution():
    mod = _load_module()
    thread_id = f"thread_exec_dedupe_{uuid4().hex[:8]}"
    code = "print('run_once_is_enough')\n"

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "execute_dedupe_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    save_json = json.loads(save)
    assert save_json["status"] == "success"

    first_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "execute_dedupe_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    first_json = json.loads(first_exec)
    assert first_json["status"] == "success"
    assert first_json.get("execution_skipped") is False

    second_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "execute_dedupe_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    second_json = json.loads(second_exec)
    assert second_json["status"] == "success"
    assert second_json.get("execution_skipped") is True
    assert second_json.get("already_executed") is True


def test_execute_tool_escalates_after_repeated_identical_failures():
    mod = _load_module()
    thread_id = f"thread_exec_repeat_fail_{uuid4().hex[:8]}"
    missing_name = f"missing_{uuid4().hex}.txt"
    code = (
        "from storage_manager import storage_manager\n"
        f"open(storage_manager.resolve_input_path('{missing_name}'), 'r', encoding='utf-8').read()\n"
    )

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "repeat_fail_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    save_json = json.loads(save)
    assert save_json["status"] == "success"

    first_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "repeat_fail_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    first_json = json.loads(first_exec)
    assert first_json["status"] == "fail"
    first_policy = first_json.get("error_handling_policy", {})
    assert first_policy.get("severity") == "simple"
    assert first_json.get("repeated_failure_signature_count") == 1

    second_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "repeat_fail_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    second_json = json.loads(second_exec)
    assert second_json["status"] == "fail"
    second_policy = second_json.get("error_handling_policy", {})
    assert second_policy.get("severity") == "hard"
    assert second_policy.get("should_handoff_to_engineer") is True
    assert second_policy.get("max_self_retries") == 0
    assert (second_json.get("repeated_failure_signature_count") or 0) >= 2

