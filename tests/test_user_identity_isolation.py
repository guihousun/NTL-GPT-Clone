from pathlib import Path

import history_store


def test_generate_anonymous_user_id_is_not_reserved():
    uid = history_store.generate_anonymous_user_id()
    assert uid.startswith("anon-")
    assert not history_store.is_reserved_user_id(uid)


def test_generate_thread_id_for_anonymous_user_is_not_guest_prefixed():
    uid = history_store.generate_anonymous_user_id()
    tid = history_store.generate_thread_id(uid)
    assert not tid.startswith("guest-")


def test_app_state_uses_anonymous_default_not_guest():
    source = Path("app_state.py").read_text(encoding="utf-8-sig")
    assert 'setdefault("user_name", "guest")' not in source
    assert "generate_anonymous_user_id" in source
