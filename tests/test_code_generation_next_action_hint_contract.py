import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_next_action_hint", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dedupe_success_hint_uses_auto_return_not_transfer_tool_name():
    mod = _load_module()
    thread_id = f"thread_next_hint_{uuid4().hex[:8]}"
    code = "print('next_hint_ok')\n"

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "next_hint_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    save_json = json.loads(save)
    assert save_json["status"] == "success"

    first_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "next_hint_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(first_exec)["status"] == "success"

    second_exec = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "next_hint_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    second_json = json.loads(second_exec)
    assert second_json["status"] == "success"
    assert second_json.get("execution_skipped") is True
    hint = second_json.get("next_action_hint", "")
    assert hint == "return_to_supervisor_auto"
    assert "transfer" not in hint.lower()
    assert "handoff" not in hint.lower()

