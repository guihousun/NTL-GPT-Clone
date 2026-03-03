import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_virtual_path_runtime", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_execute_runtime_maps_shared_virtual_path_to_base_data():
    mod = _load_module()
    thread_id = f"thread_shared_runtime_{uuid4().hex[:8]}"

    shared_abs = Path(mod.storage_manager.resolve_input_path("/shared/runtime_mapping_probe.txt", thread_id=thread_id))
    shared_abs.parent.mkdir(parents=True, exist_ok=True)
    shared_abs.write_text("shared-ok", encoding="utf-8")

    code = (
        "with open('/shared/runtime_mapping_probe.txt', 'r', encoding='utf-8') as f:\n"
        "    print(f.read())\n"
    )
    saved = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "shared_runtime_mapping.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(saved)["status"] == "success"

    result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "shared_runtime_mapping.py", "strict_mode": True, "force_execute": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert "shared-ok" in data.get("stdout", "")
    rewrite = data.get("runtime_path_rewrite") or {}
    assert rewrite.get("applied") is True
    assert int(rewrite.get("mapping_count") or 0) >= 1


def test_execute_runtime_maps_data_raw_virtual_path_to_workspace_inputs():
    mod = _load_module()
    thread_id = f"thread_data_raw_runtime_{uuid4().hex[:8]}"

    workspace_input = Path(mod.storage_manager.resolve_input_path("runtime_variant_probe.txt", thread_id=thread_id))
    workspace_input.parent.mkdir(parents=True, exist_ok=True)
    workspace_input.write_text("variant-ok", encoding="utf-8")

    code = (
        "with open('/data/raw/runtime_variant_probe.txt', 'r', encoding='utf-8') as f:\n"
        "    print(f.read())\n"
    )
    saved = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "data_raw_runtime_mapping.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(saved)["status"] == "success"

    result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "data_raw_runtime_mapping.py", "strict_mode": True, "force_execute": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert "variant-ok" in data.get("stdout", "")


def test_preflight_blocks_write_to_shared_virtual_path():
    mod = _load_module()
    thread_id = f"thread_shared_write_block_{uuid4().hex[:8]}"

    code = "with open('/shared/blocked_write.txt', 'w', encoding='utf-8') as f:\n    f.write('x')\n"
    saved = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "shared_write_block.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(saved)["status"] == "success"

    result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "shared_write_block.py", "strict_mode": True, "force_execute": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    assert data.get("error_type") == "PreflightError"
    assert "/shared" in str(data.get("error_message", "")).lower()
