from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path("user_data")
USERS_DIR = BASE_DIR / "_users"
RESERVED_USER_IDS = {"guest", "debug", "default", "anonymous"}


def _now_ts() -> int:
    return int(time.time())


def _safe_read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_user_id(user_name: str) -> str:
    raw = (user_name or "").strip().lower()
    if not raw:
        return "guest"
    value = re.sub(r"\s+", "_", raw)
    value = re.sub(r"[^a-z0-9_\-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_-")
    return value[:40] or "guest"


def is_reserved_user_id(user_id: str) -> bool:
    return normalize_user_id(user_id) in RESERVED_USER_IDS


def is_reserved_user_name(user_name: str) -> bool:
    return is_reserved_user_id(user_name)


def generate_anonymous_user_id() -> str:
    return f"anon-{uuid.uuid4().hex[:8]}"


def generate_thread_id(user_id: str) -> str:
    uid = normalize_user_id(user_id)[:8]
    return f"{uid}-{uuid.uuid4().hex[:6]}"


def _user_dir(user_id: str) -> Path:
    return USERS_DIR / normalize_user_id(user_id)


def _threads_index_path(user_id: str) -> Path:
    return _user_dir(user_id) / "threads_index.json"


def ensure_user_profile(user_id: str, user_name: str = "") -> Path:
    uid = normalize_user_id(user_id)
    udir = _user_dir(uid)
    udir.mkdir(parents=True, exist_ok=True)
    profile_path = udir / "profile.json"
    profile = _safe_read_json(profile_path, {})
    profile.update(
        {
            "user_id": uid,
            "user_name": (user_name or uid).strip() or uid,
            "updated_at": _now_ts(),
        }
    )
    if "created_at" not in profile:
        profile["created_at"] = _now_ts()
    _safe_write_json(profile_path, profile)
    if not _threads_index_path(uid).exists():
        _safe_write_json(_threads_index_path(uid), {"threads": []})
    return udir


def bind_thread_to_user(user_id: str, thread_id: str, meta: Optional[Dict[str, Any]] = None) -> None:
    uid = normalize_user_id(user_id)
    ensure_user_profile(uid)
    idx_path = _threads_index_path(uid)
    payload = _safe_read_json(idx_path, {"threads": []})
    rows = payload.get("threads", [])
    if not isinstance(rows, list):
        rows = []
    ts = _now_ts()
    entry = None
    for item in rows:
        if isinstance(item, dict) and str(item.get("thread_id", "")) == str(thread_id):
            entry = item
            break
    if entry is None:
        entry = {"thread_id": str(thread_id), "created_at": ts}
        rows.append(entry)
    entry["updated_at"] = ts
    entry["workspace"] = str((BASE_DIR / str(thread_id)).as_posix())
    if meta:
        for key, value in meta.items():
            entry[key] = value
    payload["threads"] = rows
    _safe_write_json(idx_path, payload)


def touch_thread_activity(
    user_id: str,
    thread_id: str,
    last_question: str = "",
    last_answer_excerpt: str = "",
) -> None:
    meta = {}
    if last_question:
        meta["last_question"] = str(last_question)[:240]
    if last_answer_excerpt:
        meta["last_answer_excerpt"] = str(last_answer_excerpt)[:400]
    bind_thread_to_user(user_id, thread_id, meta=meta)


def list_user_threads(user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    uid = normalize_user_id(user_id)
    rows = _safe_read_json(_threads_index_path(uid), {"threads": []}).get("threads", [])
    if not isinstance(rows, list):
        return []
    normalized = [item for item in rows if isinstance(item, dict) and item.get("thread_id")]
    normalized.sort(key=lambda x: int(x.get("updated_at", 0) or 0), reverse=True)
    if limit > 0:
        normalized = normalized[:limit]
    return normalized


def _history_dir(thread_id: str) -> Path:
    path = BASE_DIR / str(thread_id) / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chat_jsonl_path(thread_id: str) -> Path:
    return _history_dir(thread_id) / "chat_history.jsonl"


def _turn_summary_jsonl_path(thread_id: str) -> Path:
    return _history_dir(thread_id) / "turn_summary.jsonl"


def _context_index_path(thread_id: str) -> Path:
    return _history_dir(thread_id) / "context_index.json"


def append_chat_record(thread_id: str, role: str, content: str, kind: str = "text") -> None:
    row = {
        "ts": _now_ts(),
        "role": str(role),
        "kind": str(kind),
        "content": str(content or ""),
    }
    _safe_append_jsonl(_chat_jsonl_path(thread_id), row)


def load_chat_records(thread_id: str, limit: int = 300) -> List[Dict[str, Any]]:
    path = _chat_jsonl_path(thread_id)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except Exception:
                    continue
    except Exception:
        return []
    if limit > 0 and len(rows) > limit:
        return rows[-limit:]
    return rows


def append_turn_summary(thread_id: str, summary: Dict[str, Any]) -> None:
    row = {"ts": _now_ts()}
    row.update(summary or {})
    _safe_append_jsonl(_turn_summary_jsonl_path(thread_id), row)


def load_injected_context_items(thread_id: str) -> List[Dict[str, Any]]:
    payload = _safe_read_json(_context_index_path(thread_id), {"items": []})
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and str(x.get("text", "")).strip()]


def save_injected_context_items(thread_id: str, items: List[Dict[str, Any]]) -> None:
    payload = {"updated_at": _now_ts(), "items": items}
    _safe_write_json(_context_index_path(thread_id), payload)


def clear_injected_context(thread_id: str) -> None:
    save_injected_context_items(thread_id, [])


def upsert_injected_context_items(thread_id: str, items: List[Dict[str, Any]]) -> Dict[str, int]:
    current = load_injected_context_items(thread_id)
    key_to_row: Dict[str, Dict[str, Any]] = {}
    for row in current:
        key = f"{row.get('source_file','')}|{row.get('signature','')}|{row.get('chunk_idx','')}"
        key_to_row[key] = row
    inserted = 0
    updated = 0
    for row in items:
        key = f"{row.get('source_file','')}|{row.get('signature','')}|{row.get('chunk_idx','')}"
        if key in key_to_row:
            key_to_row[key] = row
            updated += 1
        else:
            key_to_row[key] = row
            inserted += 1
    merged = list(key_to_row.values())
    merged.sort(key=lambda x: int(x.get("created_at", 0) or 0))
    save_injected_context_items(thread_id, merged)
    return {"inserted": inserted, "updated": updated, "total": len(merged)}


def injected_file_overview(thread_id: str) -> List[Dict[str, Any]]:
    rows = load_injected_context_items(thread_id)
    by_file: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        f = str(row.get("source_file", "")).strip()
        if not f:
            continue
        item = by_file.setdefault(
            f,
            {"source_file": f, "file_type": row.get("file_type", "unknown"), "chunks": 0, "updated_at": 0},
        )
        item["chunks"] += 1
        item["updated_at"] = max(int(item.get("updated_at", 0) or 0), int(row.get("created_at", 0) or 0))
    out = list(by_file.values())
    out.sort(key=lambda x: int(x.get("updated_at", 0) or 0), reverse=True)
    return out


def _fallback_similarity_scores(query: str, docs: List[str]) -> List[float]:
    q_tokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
    if not q_tokens:
        return [0.0 for _ in docs]
    scores: List[float] = []
    for text in docs:
        d_tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
        if not d_tokens:
            scores.append(0.0)
            continue
        inter = len(q_tokens.intersection(d_tokens))
        scores.append(inter / max(1, len(q_tokens)))
    return scores


def _extract_file_mentions(query: str) -> List[str]:
    text = str(query or "").strip().lower()
    if not text:
        return []
    matches = re.findall(
        r"([a-z0-9_\-\u4e00-\u9fff]+\.(?:png|jpg|jpeg|webp|bmp|pdf|tif|tiff))",
        text,
        flags=re.IGNORECASE,
    )
    uniq = []
    seen = set()
    for m in matches:
        key = str(m).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    return uniq


def _normalize_for_filename_match(text: str) -> str:
    t = str(text or "").strip().lower()
    return re.sub(r"\s+", "", t)


def _match_sources_by_normalized_query(query: str, source_names: List[str]) -> List[str]:
    q_norm = _normalize_for_filename_match(query)
    if not q_norm:
        return []
    out: List[str] = []
    seen = set()
    for name in source_names:
        n = str(name or "").strip()
        if not n:
            continue
        n_norm = _normalize_for_filename_match(n)
        if n_norm and n_norm in q_norm:
            key = n.lower()
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _looks_like_image_question(query: str) -> bool:
    q = str(query or "").strip().lower()
    if not q:
        return False
    image_markers = [
        "图片",
        "图像",
        "照片",
        "截图",
        "这张图",
        "看图",
        "image",
        "picture",
        "photo",
        "screenshot",
    ]
    return any(tok in q for tok in image_markers)


def retrieve_relevant_context(
    thread_id: str,
    query: str,
    top_n: int = 4,
    max_chars: int = 6000,
    min_score: float = 0.01,
) -> List[Dict[str, Any]]:
    items = load_injected_context_items(thread_id)
    if not items:
        return []
    query_text = str(query or "").strip()
    query_lower = query_text.lower()

    # File mention shortcut: if user explicitly asks about a file, prioritize that file's chunks.
    mentioned_files = set(_extract_file_mentions(query_text))
    if not mentioned_files:
        mentioned_files = set(
            _match_sources_by_normalized_query(
                query_text,
                [str(x.get("source_file", "")) for x in items if isinstance(x, dict)],
            )
        )
    if mentioned_files:
        file_hits = []
        for item in items:
            source = str(item.get("source_file", "")).strip().lower()
            if source and source in mentioned_files:
                file_hits.append(item)
        if file_hits:
            file_hits.sort(key=lambda x: int(x.get("created_at", 0) or 0), reverse=True)
            out: List[Dict[str, Any]] = []
            chars = 0
            for item in file_hits:
                if len(out) >= max(1, int(top_n)):
                    break
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                if chars + len(text) > max_chars and out:
                    break
                chars += len(text)
                row = dict(item)
                row["score"] = 1.0
                out.append(row)
            if out:
                return out

    docs = [str(x.get("text", "")) for x in items]
    scores: List[float]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = vec.fit_transform(docs + [query])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        scores = [float(s) for s in sims]
    except Exception:
        scores = _fallback_similarity_scores(query, docs)

    adjusted_scores: List[float] = []
    for idx, base in enumerate(scores):
        item = items[idx]
        source = str(item.get("source_file", "")).strip().lower()
        boost = 0.0
        if source and source in query_lower:
            boost += 0.85
        if source:
            stem = Path(source).stem.lower()
            if stem and stem in query_lower:
                boost += 0.45
        adjusted_scores.append(float(base) + boost)

    ranked = sorted(enumerate(adjusted_scores), key=lambda x: x[1], reverse=True)
    out: List[Dict[str, Any]] = []
    char_count = 0
    for idx, score in ranked:
        if len(out) >= max(1, int(top_n)):
            break
        if score < float(min_score):
            continue
        item = items[idx]
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        if char_count + len(text) > max_chars and out:
            break
        char_count += len(text)
        row = dict(item)
        row["score"] = round(float(score), 4)
        out.append(row)

    # Image-question fallback: if no semantic hit, use latest injected image snippet(s).
    if not out and _looks_like_image_question(query_text):
        image_items = [x for x in items if str(x.get("file_type", "")).lower() == "image"]
        if image_items:
            image_items.sort(key=lambda x: int(x.get("created_at", 0) or 0), reverse=True)
            chars = 0
            for item in image_items:
                if len(out) >= max(1, int(top_n)):
                    break
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                if chars + len(text) > max_chars and out:
                    break
                chars += len(text)
                row = dict(item)
                row["score"] = 0.2
                out.append(row)
    return out


def thread_exists(thread_id: str) -> bool:
    return (BASE_DIR / str(thread_id)).exists()


def thread_workspace(thread_id: str) -> Path:
    return BASE_DIR / str(thread_id)


def file_signature(path: Path) -> str:
    st = path.stat()
    return f"{path.name}:{int(st.st_mtime)}:{int(st.st_size)}"


def user_display_name(user_id: str) -> str:
    profile = _safe_read_json(_user_dir(user_id) / "profile.json", {})
    name = str(profile.get("user_name", "")).strip()
    return name or normalize_user_id(user_id)
