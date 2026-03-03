from pathlib import Path


def test_sidebar_requires_username_before_activation():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "Create a username first before activation and history-thread access." in source
    assert "disabled=not username_ready" in source


def test_sidebar_mentions_reserved_anonymous_name():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert "guest/debug/default/anonymous" in source


def test_sidebar_user_input_default_is_blank_for_anonymous_session():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert 'st.session_state.get("user_name", "")' in source
    assert 'st.session_state.get("user_name", "anonymous")' not in source
