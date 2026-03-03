from pathlib import Path


def test_sidebar_does_not_implicitly_bind_unknown_current_thread():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "history_store.bind_thread_to_user(current_user_id, current_tid)" not in source
    assert "if current_tid not in thread_ids:" in source
    assert "app_state.set_active_thread(thread_ids[0])" in source


def test_sidebar_still_binds_user_selected_thread():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "history_store.bind_thread_to_user(current_user_id, selected_tid)" in source
