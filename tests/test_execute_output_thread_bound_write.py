import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_thread_bound", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_execute_tool_forces_thread_bound_resolve_output_path():
    mod = _load_module()
    thread_id = f"thread_bound_exec_{uuid4().hex[:8]}"
    code = (
        "from storage_manager import storage_manager, current_thread_id\n"
        "current_thread_id.set('debug')\n"
        "print(storage_manager.resolve_output_path('thread_bound_probe.csv'))\n"
    )

    save_result = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "thread_bound_probe.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    save_json = json.loads(save_result)
    assert save_json["status"] == "success"

    exec_result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "thread_bound_probe.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    exec_json = json.loads(exec_result)
    assert exec_json["status"] == "success"
    stdout = exec_json.get("stdout", "")
    assert thread_id in stdout
    assert "\\user_data\\debug\\outputs\\thread_bound_probe.csv" not in stdout.replace("/", "\\")
