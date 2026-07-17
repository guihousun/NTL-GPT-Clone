from unittest.mock import patch

import app_ui


def test_known_auth_error_uses_chinese_translation() -> None:
    with patch.object(app_ui, "_tr", side_effect=lambda zh, en: zh):
        message = app_ui._localized_auth_error(
            ValueError("Password must be at least 8 characters.")
        )

    assert message == "密码至少需要 8 个字符。"


def test_known_auth_error_preserves_english_translation() -> None:
    with patch.object(app_ui, "_tr", side_effect=lambda zh, en: en):
        message = app_ui._localized_auth_error(
            ValueError("That username is already registered.")
        )

    assert message == "That username is already registered."


def test_unknown_auth_error_is_not_rewritten() -> None:
    with patch.object(app_ui, "_tr", side_effect=lambda zh, en: zh):
        message = app_ui._localized_auth_error(RuntimeError("Unexpected auth failure."))

    assert message == "Unexpected auth failure."


def test_pending_thread_selection_is_applied_before_widget_render() -> None:
    state = {}
    with patch.object(app_ui.st, "session_state", state):
        app_ui._queue_sidebar_thread_selection("thread-new")
        selected = app_ui._apply_pending_sidebar_thread_selection(
            ["thread-old", "thread-new"]
        )

    assert selected == "thread-new"
    assert state[app_ui._SIDEBAR_THREAD_SELECTOR_KEY] == "thread-new"
    assert app_ui._PENDING_SIDEBAR_THREAD_SELECTOR_KEY not in state


def test_invalid_pending_thread_selection_does_not_override_widget() -> None:
    state = {
        app_ui._SIDEBAR_THREAD_SELECTOR_KEY: "thread-old",
        app_ui._PENDING_SIDEBAR_THREAD_SELECTOR_KEY: "thread-deleted",
    }
    with patch.object(app_ui.st, "session_state", state):
        selected = app_ui._apply_pending_sidebar_thread_selection(["thread-old"])

    assert selected is None
    assert state[app_ui._SIDEBAR_THREAD_SELECTOR_KEY] == "thread-old"
    assert app_ui._PENDING_SIDEBAR_THREAD_SELECTOR_KEY not in state
