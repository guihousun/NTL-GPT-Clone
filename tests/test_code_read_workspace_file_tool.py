import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_read_file_tool", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_read_workspace_file_reads_saved_py_from_outputs():
    mod = _load_module()
    thread_id = f"thread_read_py_{uuid4().hex[:8]}"
    code = "print('hello from read tool')\n"

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "read_case.py", "overwrite": True},
        config={"configurable": {"thread_id": thread_id}},
    )
    save_json = json.loads(save)
    assert save_json["status"] == "success"

    read = mod.read_workspace_file_tool.invoke(
        {"file_name": "read_case.py", "location": "auto"},
        config={"configurable": {"thread_id": thread_id}},
    )
    read_json = json.loads(read)
    assert read_json["status"] == "success"
    assert read_json["location"] == "outputs"
    assert read_json["file_name"] == "read_case.py"
    assert read_json["content"] == code
    assert read_json["line_count"] >= 1
    assert read_json["bytes"] == len(code.encode("utf-8"))


def test_read_workspace_file_reads_json_or_md_from_inputs():
    mod = _load_module()
    thread_id = f"thread_read_inputs_{uuid4().hex[:8]}"
    md_name = "note_case.md"
    json_name = "meta_case.json"
    md_text = "# title\n\nhello\n"
    json_text = '{"k":"v"}\n'

    md_path = Path(mod.storage_manager.resolve_input_path(md_name, thread_id=thread_id))
    json_path = Path(mod.storage_manager.resolve_input_path(json_name, thread_id=thread_id))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    json_path.write_text(json_text, encoding="utf-8")

    md_result = mod.read_workspace_file_tool.invoke(
        {"file_name": md_name, "location": "inputs"},
        config={"configurable": {"thread_id": thread_id}},
    )
    md_json = json.loads(md_result)
    assert md_json["status"] == "success"
    assert md_json["location"] == "inputs"
    assert md_json["content"] == md_text

    json_result = mod.read_workspace_file_tool.invoke(
        {"file_name": json_name, "location": "auto"},
        config={"configurable": {"thread_id": thread_id}},
    )
    json_json = json.loads(json_result)
    assert json_json["status"] == "success"
    assert json_json["location"] == "inputs"
    assert json_json["content"] == json_text


def test_read_workspace_file_reads_csv_from_inputs():
    mod = _load_module()
    thread_id = f"thread_read_csv_{uuid4().hex[:8]}"
    path = Path(mod.storage_manager.resolve_input_path("table.csv", thread_id=thread_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_text = "a,b\n1,2\n"
    path.write_text(csv_text, encoding="utf-8")

    result = mod.read_workspace_file_tool.invoke(
        {"file_name": "table.csv", "location": "inputs"},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert data["location"] == "inputs"
    assert data["content"] == csv_text
    assert data["content_format"] == "text/plain"


def test_read_workspace_file_reads_xlsx_as_csv_text():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    mod = _load_module()
    thread_id = f"thread_read_xlsx_{uuid4().hex[:8]}"
    path = Path(mod.storage_manager.resolve_input_path("table.xlsx", thread_id=thread_id))
    path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({"a": [1, 3], "b": [2, 4]})
    df.to_excel(path, index=False, engine="openpyxl")

    result = mod.read_workspace_file_tool.invoke(
        {"file_name": "table.xlsx", "location": "inputs"},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "success"
    assert data["location"] == "inputs"
    assert "a,b" in data["content"]
    assert "1,2" in data["content"]
    assert data["content_format"] == "text/csv"


def test_read_workspace_file_rejects_non_supported_extensions():
    mod = _load_module()
    thread_id = f"thread_read_block_{uuid4().hex[:8]}"
    path = Path(mod.storage_manager.resolve_input_path("image.png", thread_id=thread_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    result = mod.read_workspace_file_tool.invoke(
        {"file_name": "image.png", "location": "inputs"},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    assert data["error_type"] == "UnsupportedFileTypeError"


def test_read_workspace_file_fails_when_missing():
    mod = _load_module()
    thread_id = f"thread_read_missing_{uuid4().hex[:8]}"
    result = mod.read_workspace_file_tool.invoke(
        {"file_name": "missing_case.py", "location": "auto"},
        config={"configurable": {"thread_id": thread_id}},
    )
    data = json.loads(result)
    assert data["status"] == "fail"
    assert data["error_type"] == "FileNotFoundError"


def test_read_workspace_file_is_thread_scoped():
    mod = _load_module()
    owner_thread = f"thread_read_owner_{uuid4().hex[:8]}"
    other_thread = f"thread_read_other_{uuid4().hex[:8]}"
    code = "print('thread scoped')\n"

    save = mod.save_geospatial_script_tool.invoke(
        {"script_content": code, "script_name": "thread_scope_case.py", "overwrite": True},
        config={"configurable": {"thread_id": owner_thread}},
    )
    save_json = json.loads(save)
    assert save_json["status"] == "success"

    read_other = mod.read_workspace_file_tool.invoke(
        {"file_name": "thread_scope_case.py", "location": "auto"},
        config={"configurable": {"thread_id": other_thread}},
    )
    read_other_json = json.loads(read_other)
    assert read_other_json["status"] == "fail"
    assert read_other_json["error_type"] == "FileNotFoundError"
