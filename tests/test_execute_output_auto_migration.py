import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_auto_migration", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_execute_tool_auto_migrates_cross_workspace_outputs(monkeypatch):
    mod = _load_module()
    thread_id = f"thread_auto_migrate_{uuid4().hex[:8]}"
    debug_file = (Path("user_data") / "debug" / "outputs" / "auto_migrate_case.csv").resolve()
    debug_file.parent.mkdir(parents=True, exist_ok=True)
    debug_file.write_text("x,y\n1,2\n", encoding="utf-8")

    save_result = mod.save_geospatial_script_tool.invoke(
        {"script_content": "print('ok')\n", "script_name": "auto_migrate_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(save_result)["status"] == "success"

    def _fake_execute(code_block):
        del code_block
        return True, f"Saved to: {debug_file}", None, None, None

    monkeypatch.setattr(mod, "_execute_code", _fake_execute)

    exec_result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "auto_migrate_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(exec_result)
    assert data["status"] == "success"
    assert data.get("cross_workspace_recovered") is True
    migrated = data.get("auto_migrated_files") or []
    assert migrated
    dst = (Path("user_data") / thread_id / "outputs" / "auto_migrate_case.csv").resolve()
    assert dst.exists()
    assert dst.read_text(encoding="utf-8").strip() == "x,y\n1,2".strip()
    audit = data.get("artifact_audit", {})
    assert audit.get("auto_migration_attempted") is True
    assert audit.get("auto_migration_success") is True
    assert not audit.get("migration_failures")


def test_execute_tool_returns_success_with_warnings_when_auto_migration_fails(monkeypatch):
    mod = _load_module()
    thread_id = f"thread_auto_migrate_fail_{uuid4().hex[:8]}"
    debug_file = (Path("user_data") / "debug" / "outputs" / "auto_migrate_fail.csv").resolve()
    debug_file.parent.mkdir(parents=True, exist_ok=True)
    debug_file.write_text("x\n1\n", encoding="utf-8")

    save_result = mod.save_geospatial_script_tool.invoke(
        {"script_content": "print('ok')\n", "script_name": "auto_migrate_fail.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    assert json.loads(save_result)["status"] == "success"

    def _fake_execute(code_block):
        del code_block
        return True, f"Saved to: {debug_file}", None, None, None

    monkeypatch.setattr(mod, "_execute_code", _fake_execute)

    def _raise_copy(src, dst):
        del src, dst
        raise RuntimeError("copy blocked")

    monkeypatch.setattr(mod.shutil, "copy2", _raise_copy)

    exec_result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "auto_migrate_fail.py", "strict_mode": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(exec_result)
    assert data["status"] == "success_with_warnings"
    assert data.get("warning_type") == "CrossWorkspaceOutputWarning"
    assert data.get("warnings")
    assert data.get("cross_workspace_recovered") is False
    audit = data.get("artifact_audit", {})
    assert audit.get("auto_migration_attempted") is True
    assert audit.get("auto_migration_success") is False
    assert audit.get("migration_failures")
