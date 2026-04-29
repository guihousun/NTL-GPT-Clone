from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import history_store
from runtime_governance import thread_workspace_quota_bytes, user_workspace_quota_bytes
from storage_manager import storage_manager


LOCAL_ADMIN_ACTOR = str(os.getenv("NTL_LOCAL_ADMIN_ACTOR", "") or "").strip() or "local_admin"
WORKSPACE_SECTIONS = ("inputs", "outputs", "memory")


def format_bytes(num_bytes: int) -> str:
    size = max(0, int(num_bytes or 0))
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_ts(ts: int | float | None) -> str:
    try:
        value = int(ts or 0)
    except Exception:
        value = 0
    if value <= 0:
        return "-"
    return datetime.fromtimestamp(value, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _safe_thread_id(thread_id: str) -> str:
    tid = str(thread_id or "").strip()
    if not tid:
        raise ValueError("Thread ID is required.")
    return tid


def _section_snapshot(path: Path) -> dict[str, Any]:
    bytes_used = storage_manager._tree_size_bytes(path)
    file_count = 0
    if path.exists():
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    file_count += 1
            except Exception:
                continue
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": bytes_used,
        "bytes_label": format_bytes(bytes_used),
        "file_count": file_count,
    }


def get_thread_workspace_snapshot(thread_id: str) -> dict[str, Any]:
    tid = _safe_thread_id(thread_id)
    workspace = storage_manager.get_workspace(tid)
    history_dir = workspace / "history"
    sections = {
        "inputs": _section_snapshot(workspace / "inputs"),
        "outputs": _section_snapshot(workspace / "outputs"),
        "memory": _section_snapshot(workspace / "memory"),
        "history": _section_snapshot(history_dir),
    }
    total_bytes = sum(int(item["bytes"]) for item in sections.values())
    return {
        "thread_id": tid,
        "workspace_path": str(workspace),
        "total_bytes": total_bytes,
        "total_bytes_label": format_bytes(total_bytes),
        "thread_quota_bytes": int(thread_workspace_quota_bytes() or 0),
        "thread_quota_label": format_bytes(int(thread_workspace_quota_bytes() or 0)),
        "sections": sections,
    }


def get_platform_workspace_snapshot() -> dict[str, Any]:
    base_dir = storage_manager.base_dir
    thread_dirs: list[Path] = []
    users_meta_dir = base_dir / "_users"
    for child in base_dir.iterdir() if base_dir.exists() else []:
        try:
            if not child.is_dir():
                continue
            if child.name == "_users":
                continue
            thread_dirs.append(child)
        except Exception:
            continue
    total_bytes = sum(storage_manager._tree_size_bytes(path) for path in thread_dirs)
    users_meta_bytes = storage_manager._tree_size_bytes(users_meta_dir)
    return {
        "base_dir": str(base_dir),
        "shared_dir": str(storage_manager.shared_dir),
        "thread_workspace_count": len(thread_dirs),
        "thread_workspaces_bytes": total_bytes,
        "thread_workspaces_bytes_label": format_bytes(total_bytes),
        "users_meta_bytes": users_meta_bytes,
        "users_meta_bytes_label": format_bytes(users_meta_bytes),
    }


def _audit(admin_user_id: str, target_user_id: str, action: str, *, reason: str = "", payload: dict[str, Any] | None = None) -> None:
    fn = getattr(history_store, "_append_admin_audit", None)
    if callable(fn):
        fn(
            admin_user_id=str(admin_user_id or LOCAL_ADMIN_ACTOR),
            target_user_id=str(target_user_id or ""),
            action=str(action or ""),
            reason=str(reason or ""),
            payload=payload or {},
        )


def list_dashboard_users(limit: int = 100) -> list[dict[str, Any]]:
    rows = history_store.list_admin_users(limit=limit)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        user_id = str(row.get("user_id") or "")
        threads = history_store.list_user_threads(user_id, limit=0)
        thread_ids = [str(item.get("thread_id") or "").strip() for item in threads if item.get("thread_id")]
        snapshot = storage_manager.user_quota_snapshot(thread_ids, additional_bytes=0)
        enriched.append(
            {
                **row,
                "workspace_usage_bytes": int(snapshot.get("usage_bytes") or 0),
                "workspace_usage_label": format_bytes(int(snapshot.get("usage_bytes") or 0)),
                "workspace_limit_bytes": int(snapshot.get("limit_bytes") or 0),
                "workspace_limit_label": format_bytes(int(snapshot.get("limit_bytes") or 0)),
                "created_at_label": format_ts(int(row.get("created_at") or 0)),
                "updated_at_label": format_ts(int(row.get("updated_at") or 0)),
                "last_login_at_label": format_ts(int(row.get("last_login_at") or 0)),
                "gee_validated_at_label": format_ts(int(row.get("gee_validated_at") or 0)),
            }
        )
    return enriched


def get_user_detail(user_id: str) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("User ID is required.")
    users = list_dashboard_users(limit=500)
    user = next((row for row in users if str(row.get("user_id") or "") == uid), None)
    if user is None:
        raise ValueError("Unknown user_id.")
    threads = history_store.list_user_threads(uid, limit=0)
    thread_rows: list[dict[str, Any]] = []
    for row in threads:
        tid = str(row.get("thread_id") or "").strip()
        snapshot = get_thread_workspace_snapshot(tid)
        thread_rows.append(
            {
                **row,
                "workspace_snapshot": snapshot,
                "created_at_label": format_ts(int(row.get("created_at") or 0)),
                "updated_at_label": format_ts(int(row.get("updated_at") or 0)),
            }
        )
    user_snapshot = storage_manager.user_quota_snapshot([row["thread_id"] for row in threads if row.get("thread_id")], additional_bytes=0)
    return {
        "user": user,
        "threads": thread_rows,
        "workspace_usage_bytes": int(user_snapshot.get("usage_bytes") or 0),
        "workspace_usage_label": format_bytes(int(user_snapshot.get("usage_bytes") or 0)),
        "workspace_limit_bytes": int(user_snapshot.get("limit_bytes") or 0),
        "workspace_limit_label": format_bytes(int(user_snapshot.get("limit_bytes") or 0)),
    }


def clear_thread_section(
    user_id: str,
    thread_id: str,
    section: str,
    *,
    admin_user_id: str = LOCAL_ADMIN_ACTOR,
    reason: str = "",
) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    tid = _safe_thread_id(thread_id)
    target_section = str(section or "").strip().lower()
    if target_section not in WORKSPACE_SECTIONS:
        raise ValueError(f"Unsupported workspace section: {section}")

    workspace = storage_manager.get_workspace(tid)
    section_path = workspace / target_section
    deleted_count = 0
    deleted_bytes = 0
    if section_path.exists():
        for child in list(section_path.iterdir()):
            try:
                deleted_bytes += storage_manager._tree_size_bytes(child) if child.is_dir() else int(child.stat().st_size)
            except Exception:
                pass
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=False)
            else:
                child.unlink(missing_ok=True)
            deleted_count += 1
    _audit(
        admin_user_id,
        uid,
        f"clear_thread_{target_section}",
        reason=reason,
        payload={"thread_id": tid, "section": target_section, "deleted_entries": deleted_count, "deleted_bytes": deleted_bytes},
    )
    return {
        "user_id": uid,
        "thread_id": tid,
        "section": target_section,
        "deleted_entries": deleted_count,
        "deleted_bytes": deleted_bytes,
        "deleted_bytes_label": format_bytes(deleted_bytes),
    }


def delete_thread_as_admin(
    user_id: str,
    thread_id: str,
    *,
    admin_user_id: str = LOCAL_ADMIN_ACTOR,
    reason: str = "",
) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    tid = _safe_thread_id(thread_id)
    result = history_store.delete_user_thread(uid, tid, delete_workspace=True)
    _audit(
        admin_user_id,
        uid,
        "delete_thread",
        reason=reason,
        payload={"thread_id": tid, **result},
    )
    return result


def reset_user_password_as_admin(
    user_id: str,
    new_password: str,
    *,
    admin_user_id: str = LOCAL_ADMIN_ACTOR,
    reason: str = "",
) -> dict[str, Any]:
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("User ID is required.")
    return history_store.reset_user_password(
        uid,
        str(new_password or ""),
        admin_user_id=admin_user_id,
        reason=reason,
    )
