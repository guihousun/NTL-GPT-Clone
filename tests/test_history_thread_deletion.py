from __future__ import annotations

from pathlib import Path

import history_store


def _set_store_root(monkeypatch, root: Path):
    monkeypatch.setattr(history_store, "BASE_DIR", root)
    monkeypatch.setattr(history_store, "USERS_DIR", root / "_users")


def test_delete_user_thread_removes_index_and_workspace(monkeypatch, tmp_path: Path):
    root = tmp_path / "user_data"
    _set_store_root(monkeypatch, root)

    user_id = "tester"
    thread_id = history_store.generate_thread_id(user_id)
    history_store.bind_thread_to_user(user_id, thread_id, meta={"last_question": "hello"})
    history_store.append_chat_record(thread_id, role="user", content="hello")
    workspace = history_store.thread_workspace(thread_id)
    (workspace / "outputs").mkdir(parents=True, exist_ok=True)
    (workspace / "outputs" / "a.txt").write_text("x", encoding="utf-8")

    out = history_store.delete_user_thread(user_id, thread_id, delete_workspace=True)

    assert out["deleted"] is True
    assert out["index_removed"] is True
    assert out["workspace_removed"] is True
    assert thread_id not in [x.get("thread_id") for x in history_store.list_user_threads(user_id, limit=100)]


def test_delete_unknown_thread_keeps_other_threads_non_target_variation(monkeypatch, tmp_path: Path):
    root = tmp_path / "user_data"
    _set_store_root(monkeypatch, root)

    user_id = "tester"
    keep_tid = history_store.generate_thread_id(user_id)
    history_store.bind_thread_to_user(user_id, keep_tid, meta={"last_question": "keep"})
    missing_tid = "tester-unknown"

    out = history_store.delete_user_thread(user_id, missing_tid, delete_workspace=True)

    assert out["deleted"] is False
    thread_ids = [x.get("thread_id") for x in history_store.list_user_threads(user_id, limit=100)]
    assert keep_tid in thread_ids

