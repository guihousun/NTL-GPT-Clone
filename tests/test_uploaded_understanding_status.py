from __future__ import annotations

import importlib
from pathlib import Path

uut = importlib.import_module("tools.uploaded_file_understanding_tool")


def test_uploaded_pdf_understanding_status_success(monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    try:
        monkeypatch.setattr(
            uut.file_context_service,
            "build_context_items_for_files",
            lambda **kwargs: {"items": [], "warnings": []},
        )
        monkeypatch.setattr(
            uut.history_store,
            "retrieve_relevant_context",
            lambda **kwargs: [
                {
                    "source_file": "demo.pdf",
                    "file_type": "pdf",
                    "page": 2,
                    "score": 0.92,
                    "text": "Matched snippet",
                }
            ],
        )
        result = uut.uploaded_pdf_understanding_tool_fn(
            query="what is in demo.pdf", file_names="demo.pdf", top_n=4
        )
        assert result["status"] == "success"
        assert len(result.get("snippets", [])) == 1
    finally:
        uut.current_thread_id.reset(token)


def test_uploaded_pdf_understanding_status_context_injected_no_match(monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    try:
        monkeypatch.setattr(
            uut.file_context_service,
            "build_context_items_for_files",
            lambda **kwargs: {
                "items": [{"text": "parsed text", "source_file": "demo.pdf", "chunk_idx": 0}],
                "warnings": [],
            },
        )
        monkeypatch.setattr(
            uut.history_store,
            "upsert_injected_context_items",
            lambda thread_id, items: {"inserted": 1, "updated": 0, "total": 1},
        )
        monkeypatch.setattr(
            uut.history_store,
            "retrieve_relevant_context",
            lambda **kwargs: [],
        )
        result = uut.uploaded_pdf_understanding_tool_fn(
            query="unrelated question", file_names="demo.pdf", top_n=4
        )
        assert result["status"] == "context_injected_no_match"
        assert result.get("merge_stats", {}).get("total") == 1
    finally:
        uut.current_thread_id.reset(token)


def test_uploaded_pdf_understanding_status_no_relevant_snippet(monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    try:
        monkeypatch.setattr(
            uut.file_context_service,
            "build_context_items_for_files",
            lambda **kwargs: {"items": [], "warnings": []},
        )
        monkeypatch.setattr(
            uut.history_store,
            "retrieve_relevant_context",
            lambda **kwargs: [],
        )
        result = uut.uploaded_pdf_understanding_tool_fn(
            query="unrelated question", file_names="demo.pdf", top_n=4
        )
        assert result["status"] == "no_relevant_snippet"
    finally:
        uut.current_thread_id.reset(token)


def test_uploaded_image_understanding_auto_multi_pick_for_plural_query(tmp_path, monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    captured = {}
    try:
        workspace = tmp_path / "user_data" / "test-thread"
        input_dir = workspace / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "img_a.png").write_bytes(b"a")
        (input_dir / "img_b.png").write_bytes(b"b")
        (input_dir / "doc.pdf").write_bytes(b"pdf")

        monkeypatch.setattr(uut.storage_manager, "get_workspace", lambda tid: workspace)

        def _fake_build(**kwargs):
            captured["file_names"] = list(kwargs.get("file_names", []))
            return {"items": [], "warnings": []}

        monkeypatch.setattr(uut.file_context_service, "build_context_items_for_files", _fake_build)
        monkeypatch.setattr(uut.history_store, "retrieve_relevant_context", lambda **kwargs: [])

        uut.uploaded_image_understanding_tool_fn(query="请分析我上传的两张图片", file_names=None, top_n=4)
        assert len(captured.get("file_names", [])) == 2
    finally:
        uut.current_thread_id.reset(token)


def test_uploaded_image_understanding_default_single_pick_for_singular_query(tmp_path, monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    captured = {}
    try:
        workspace = tmp_path / "user_data" / "test-thread"
        input_dir = workspace / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "img_a.png").write_bytes(b"a")
        (input_dir / "img_b.png").write_bytes(b"b")

        monkeypatch.setattr(uut.storage_manager, "get_workspace", lambda tid: workspace)

        def _fake_build(**kwargs):
            captured["file_names"] = list(kwargs.get("file_names", []))
            return {"items": [], "warnings": []}

        monkeypatch.setattr(uut.file_context_service, "build_context_items_for_files", _fake_build)
        monkeypatch.setattr(uut.history_store, "retrieve_relevant_context", lambda **kwargs: [])

        uut.uploaded_image_understanding_tool_fn(query="请分析我上传的图片", file_names=None, top_n=4)
        assert len(captured.get("file_names", [])) == 1
    finally:
        uut.current_thread_id.reset(token)


def test_uploaded_image_understanding_can_pick_outputs_when_requested(tmp_path, monkeypatch):
    token = uut.current_thread_id.set("test-thread")
    captured = {}
    try:
        workspace = tmp_path / "user_data" / "test-thread"
        input_dir = workspace / "inputs"
        output_dir = workspace / "outputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "result_map.png").write_bytes(b"png")

        monkeypatch.setattr(uut.storage_manager, "get_workspace", lambda tid: workspace)

        def _fake_build(**kwargs):
            captured["file_names"] = list(kwargs.get("file_names", []))
            captured["workspace_lookup"] = kwargs.get("workspace_lookup")
            return {"items": [], "warnings": []}

        monkeypatch.setattr(uut.file_context_service, "build_context_items_for_files", _fake_build)
        monkeypatch.setattr(uut.history_store, "retrieve_relevant_context", lambda **kwargs: [])

        result = uut.uploaded_image_understanding_tool_fn(
            query="请分析刚生成的输出图像",
            workspace_lookup="outputs",
            top_n=4,
        )
        assert result["status"] in {"no_relevant_snippet", "context_injected_no_match"}
        assert captured.get("workspace_lookup") == "outputs"
        assert captured.get("file_names") == ["result_map.png"]
    finally:
        uut.current_thread_id.reset(token)
