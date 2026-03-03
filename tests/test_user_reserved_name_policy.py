import history_store


def test_reserved_user_names_are_blocked():
    assert history_store.is_reserved_user_name("guest")
    assert history_store.is_reserved_user_name("Guest")
    assert history_store.is_reserved_user_name("debug")
    assert history_store.is_reserved_user_name("default")
    assert history_store.is_reserved_user_name("anonymous")


def test_non_reserved_user_name_is_allowed():
    assert not history_store.is_reserved_user_name("alice")
    assert not history_store.is_reserved_user_name("research_team_01")
