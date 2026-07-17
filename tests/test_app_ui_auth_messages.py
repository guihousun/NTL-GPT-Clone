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
