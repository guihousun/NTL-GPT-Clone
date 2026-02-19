import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_filemode", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_save_geospatial_script_tool_writes_utf8_script_to_thread_workspace():
    mod = _load_module()
    code = "print('utf8_script_persistence_ok')\n"
    result = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "utf8_script.py", "overwrite": True},
        config={"configurable": {"thread_id": "thread_script_save"}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert data["script_name"] == "utf8_script.py"
    assert "thread_script_save" in data["script_path"]
    saved_path = Path(data["script_path"])
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == code


def test_execute_geospatial_script_tool_executes_by_script_name():
    mod = _load_module()
    save_result = mod.save_geospatial_script_tool.invoke(
        {
            "script_content": "print('execute_by_file_ok')\n",
            "script_name": "execute_case.py",
            "overwrite": True,
        },
        config={"configurable": {"thread_id": "thread_script_exec"}},
    )
    save_json = json.loads(save_result)
    assert save_json["status"] == "success"

    exec_result = mod.execute_geospatial_script_tool.invoke(
        {"script_name": "execute_case.py", "strict_mode": True},
        config={"configurable": {"thread_id": "thread_script_exec"}},
    )
    exec_json = json.loads(exec_result)
    assert exec_json["status"] == "success"
    assert "execute_by_file_ok" in exec_json.get("stdout", "")
    assert exec_json["script_name"] == "execute_case.py"
    assert "thread_script_exec" in exec_json["script_path"]


def test_final_execution_auto_persists_script_file():
    mod = _load_module()
    result = mod.final_geospatial_code_execution_tool.invoke(
        {"final_geospatial_code": "print('final_execution_ok')", "strict_mode": True},
        config={"configurable": {"thread_id": "thread_final_save"}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert data["script_name"].endswith(".py")
    assert "thread_final_save" in data["script_path"]
    saved_path = Path(data["script_path"])
    assert saved_path.exists()
    assert "final_execution_ok" in saved_path.read_text(encoding="utf-8")


def test_success_execution_auto_archives_into_code_guide_runtime(monkeypatch, tmp_path):
    mod = _load_module()
    runtime_dir = tmp_path / "RAG" / "code_guide" / "tools_latest_runtime"
    monkeypatch.setenv("NTL_CODE_GUIDE_RUNTIME_DIR", str(runtime_dir))

    result = mod.final_geospatial_code_execution_tool.invoke(
        {"final_geospatial_code": "print('archive_me')", "strict_mode": True},
        config={"configurable": {"thread_id": "thread_archive_case"}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    archive = data.get("code_guide_archive", {})
    assert archive.get("archived") is True

    archive_script_path = Path(archive["archive_script_path"])
    archive_meta_path = Path(archive["archive_metadata_path"])
    archive_manifest_path = Path(archive["archive_manifest_path"])

    assert archive_script_path.exists()
    assert archive_meta_path.exists()
    assert archive_manifest_path.exists()
    assert "archive_me" in archive_script_path.read_text(encoding="utf-8")
