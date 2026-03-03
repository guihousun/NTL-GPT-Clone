from __future__ import annotations

import history_store


def _patch_store_root(tmp_path, monkeypatch):
    base_dir = tmp_path / "user_data"
    monkeypatch.setattr(history_store, "BASE_DIR", base_dir)
    monkeypatch.setattr(history_store, "USERS_DIR", base_dir / "_users")
    return base_dir


def test_user_thread_binding_and_listing(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    user_id = history_store.normalize_user_id("Alice Chen")
    history_store.ensure_user_profile(user_id, "Alice Chen")

    tid = history_store.generate_thread_id(user_id)
    history_store.bind_thread_to_user(user_id, tid, meta={"last_question": "run annual ntl"})
    rows = history_store.list_user_threads(user_id, limit=10)

    assert rows, "thread listing should not be empty after binding"
    assert rows[0]["thread_id"] == tid
    assert rows[0].get("workspace", "").endswith(tid)


def test_injected_context_retrieval_topn(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    thread_id = "alice-123abc"
    items = [
        {
            "source_file": "report_a.pdf",
            "signature": "a:1:10",
            "chunk_idx": 0,
            "created_at": 1,
            "text": "Shanghai annual GDP from 2013 to 2022 in billion yuan.",
            "file_type": "pdf",
        },
        {
            "source_file": "report_b.pdf",
            "signature": "b:1:10",
            "chunk_idx": 0,
            "created_at": 2,
            "text": "Wuhan lockdown period ANTL comparison and temporal differences.",
            "file_type": "pdf",
        },
    ]
    merge = history_store.upsert_injected_context_items(thread_id, items)
    assert merge["total"] == 2

    shanghai_hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query="What is Shanghai GDP in 2022?",
        top_n=1,
        max_chars=2000,
    )
    assert len(shanghai_hits) == 1
    assert shanghai_hits[0]["source_file"] == "report_a.pdf"

    wuhan_hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query="analyze Wuhan lockdown ANTL changes",
        top_n=1,
        max_chars=2000,
    )
    assert len(wuhan_hits) == 1
    assert wuhan_hits[0]["source_file"] == "report_b.pdf"


def test_retrieval_prefers_explicit_filename_mentions(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    thread_id = "user-001"
    history_store.upsert_injected_context_items(
        thread_id,
        [
            {
                "source_file": "t6.png",
                "signature": "img:1:1",
                "chunk_idx": 0,
                "created_at": 10,
                "text": "This image contains a warning sign in Chinese.",
                "file_type": "image",
            },
            {
                "source_file": "other.pdf",
                "signature": "pdf:1:1",
                "chunk_idx": 0,
                "created_at": 9,
                "text": "Unrelated context about raster metadata.",
                "file_type": "pdf",
            },
        ],
    )
    hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query="t6.png写了什么东西？",
        top_n=1,
        max_chars=2000,
    )
    assert len(hits) == 1
    assert hits[0]["source_file"] == "t6.png"


def test_retrieval_filename_match_with_spaces_and_brackets(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    thread_id = "user-003"
    filename = "第十一届中国研究生智慧城市技术与创意设计大赛全国总决赛拟入围名单（排名不分先后）.pdf"
    history_store.upsert_injected_context_items(
        thread_id,
        [
            {
                "source_file": filename,
                "signature": "pdf:3:1",
                "chunk_idx": 0,
                "created_at": 30,
                "text": "拟入围项目包括低空经济、机器人与智慧城市治理等方向。",
                "file_type": "pdf",
            }
        ],
    )
    # Query variant intentionally includes whitespace before extension, a common UI typing pattern.
    query = "第十一届中国研究生智慧城市技术与创意设计大赛全国总决赛拟入围名单（排名不分先后） .pdf里是什么内容"
    hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query=query,
        top_n=1,
        max_chars=2000,
    )
    assert len(hits) == 1
    assert hits[0]["source_file"] == filename


def test_retrieval_filename_match_english_with_spaces(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    thread_id = "user-004"
    filename = "Report Final v2.pdf"
    history_store.upsert_injected_context_items(
        thread_id,
        [
            {
                "source_file": filename,
                "signature": "pdf:4:1",
                "chunk_idx": 0,
                "created_at": 31,
                "text": "This report contains annual NTL trend comparison results.",
                "file_type": "pdf",
            }
        ],
    )
    query = "Please summarize Report Final v2 .pdf"
    hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query=query,
        top_n=1,
        max_chars=2000,
    )
    assert len(hits) == 1
    assert hits[0]["source_file"] == filename


def test_retrieval_image_question_fallback_when_similarity_low(tmp_path, monkeypatch):
    _patch_store_root(tmp_path, monkeypatch)
    thread_id = "user-002"
    history_store.upsert_injected_context_items(
        thread_id,
        [
            {
                "source_file": "scene.jpg",
                "signature": "img:2:1",
                "chunk_idx": 0,
                "created_at": 20,
                "text": "A nighttime city skyline with bright roads and river reflections.",
                "file_type": "image",
            }
        ],
    )
    hits = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query="这张图里有什么？",
        top_n=1,
        max_chars=2000,
    )
    assert len(hits) == 1
    assert hits[0]["source_file"] == "scene.jpg"
