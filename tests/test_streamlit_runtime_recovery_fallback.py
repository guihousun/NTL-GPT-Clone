import types

import Streamlit as streamlit_entry


def test_safe_recover_runtime_health_calls_available_function(monkeypatch):
    called = {"v": 0}

    def _recover():
        called["v"] += 1

    monkeypatch.setattr(streamlit_entry, "app_logic", types.SimpleNamespace(recover_runtime_health=_recover))
    assert streamlit_entry._safe_recover_runtime_health() is True
    assert called["v"] == 1


def test_safe_recover_runtime_health_skips_when_missing(monkeypatch):
    monkeypatch.setattr(streamlit_entry, "app_logic", types.SimpleNamespace())
    assert streamlit_entry._safe_recover_runtime_health() is False
