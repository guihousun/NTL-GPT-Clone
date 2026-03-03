from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import app_ui


def test_extract_chat_input_text_and_files_from_str():
    text, files = app_ui._extract_chat_input_text_and_files("  hello  ")
    assert text == "hello"
    assert files == []


def test_extract_chat_input_text_and_files_from_object():
    f = SimpleNamespace(name="a.png")
    payload = SimpleNamespace(text="问这个图", files=[f])
    text, files = app_ui._extract_chat_input_text_and_files(payload)
    assert text == "问这个图"
    assert len(files) == 1
    assert getattr(files[0], "name", "") == "a.png"


def test_save_chat_input_files_to_workspace_dedupe(tmp_path, monkeypatch):
    workspace = tmp_path / "user_data" / "t1"
    (workspace / "inputs").mkdir(parents=True, exist_ok=True)
    (workspace / "inputs" / "shot.png").write_bytes(b"old")

    monkeypatch.setattr(app_ui.storage_manager, "get_workspace", lambda tid: workspace)
    f = SimpleNamespace(name="shot.png", getbuffer=lambda: b"new")
    result = app_ui._save_chat_input_files_to_workspace([f], "t1")
    saved = result.get("saved", [])
    assert saved == ["shot_1.png"]
    assert (workspace / "inputs" / "shot_1.png").read_bytes() == b"new"


def test_save_chat_input_files_to_workspace_multimodal_dict(tmp_path, monkeypatch):
    workspace = tmp_path / "user_data" / "t2"
    (workspace / "inputs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_ui.storage_manager, "get_workspace", lambda tid: workspace)

    payload = {
        "name": "paste.png",
        "type": "image/png",
        "size": 3,
        "data": base64.b64encode(b"abc").decode("ascii"),
    }
    result = app_ui._save_chat_input_files_to_workspace([payload], "t2")
    saved = result.get("saved", [])
    assert saved == ["paste.png"]
    assert (workspace / "inputs" / "paste.png").read_bytes() == b"abc"
