import re
from pathlib import Path


def test_app_ui_has_no_implicit_workspace_lookup():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "storage_manager.get_workspace()" not in source


def test_output_preview_uses_session_thread_workspace():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert re.search(
        r"workspace\s*=\s*storage_manager\.get_workspace\(\s*st\.session_state\.get\([\"']thread_id[\"']\s*,\s*[\"']debug[\"']\)\s*\)",
        source,
    )


def test_workspace_mismatch_notice_uses_path_redaction_helpers():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "_to_ui_relative_path(" in source
    assert "_sanitize_paths_in_obj(" in source
