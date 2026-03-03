import streamlit as st

import app_logic


class _DummyThread:
    def __init__(self, target=None, args=(), kwargs=None, **_):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self.started = False

    def start(self):
        # Intentionally do not execute target so run stays "running".
        self.started = True


def _reset_runtime_state():
    st.session_state.clear()
    st.session_state["conversation"] = object()
    st.session_state["thread_id"] = "u1-thread-a"
    st.session_state["user_id"] = "u1"
    st.session_state["analysis_logs"] = []
    st.session_state["analysis_history"] = []
    st.session_state["chat_history"] = []
    st.session_state["ui_lang"] = "EN"
    st.session_state["injected_context_top_n"] = 4
    st.session_state["injected_context_max_chars"] = 6000
    with app_logic._RUN_REGISTRY_LOCK:
        app_logic._RUN_REGISTRY.clear()
        app_logic._THREAD_ACTIVE_RUN.clear()


def test_start_user_run_single_flight_per_thread(monkeypatch):
    _reset_runtime_state()
    monkeypatch.setattr(app_logic, "_build_injected_context_system_message", lambda *_: None)
    monkeypatch.setattr(app_logic.history_store, "append_chat_record", lambda *a, **k: None)
    monkeypatch.setattr(app_logic.history_store, "touch_thread_activity", lambda *a, **k: None)
    monkeypatch.setattr(app_logic.threading, "Thread", _DummyThread)

    first = app_logic.start_user_run("first question")
    second = app_logic.start_user_run("second question")

    assert first.get("started") is True
    assert second.get("started") is False
    assert second.get("reason") == "thread_run_in_progress"


def test_request_stop_active_run_sets_stop_flag():
    _reset_runtime_state()
    run_id = "run-stop-1"
    with app_logic._RUN_REGISTRY_LOCK:
        app_logic._RUN_REGISTRY[run_id] = {
            "run_id": run_id,
            "thread_id": "u1-thread-a",
            "state": "running",
            "stop_requested": False,
            "events": [],
            "next_seq": 1,
        }
        app_logic._THREAD_ACTIVE_RUN["u1-thread-a"] = run_id

    st.session_state["active_run_thread_id"] = "u1-thread-a"
    st.session_state["thread_id"] = "u1-thread-a"

    ok = app_logic.request_stop_active_run()

    assert ok is True
    with app_logic._RUN_REGISTRY_LOCK:
        assert app_logic._RUN_REGISTRY[run_id]["stop_requested"] is True
    assert st.session_state.get("cancel_requested") is True


def test_consume_active_run_events_updates_logs_and_finishes(monkeypatch):
    _reset_runtime_state()
    run_id = "run-consume-1"
    monkeypatch.setattr(app_logic, "_collect_recent_outputs", lambda *a, **k: None)
    with app_logic._RUN_REGISTRY_LOCK:
        app_logic._RUN_REGISTRY[run_id] = {
            "run_id": run_id,
            "thread_id": "u1-thread-a",
            "state": "success",
            "stop_requested": False,
            "events": [
                {
                    "seq": 1,
                    "run_id": run_id,
                    "thread_id": "u1-thread-a",
                    "ts": 1.0,
                    "kind": "reasoning_custom",
                    "payload": {"log_event": {"custom": [{"event_type": "kb_progress"}]}},
                },
                {
                    "seq": 2,
                    "run_id": run_id,
                    "thread_id": "u1-thread-a",
                    "ts": 2.0,
                    "kind": "done",
                    "payload": {"status": "success", "thread_id": "u1-thread-a", "elapsed_s": 1.0},
                },
            ],
            "next_seq": 3,
        }
        app_logic._THREAD_ACTIVE_RUN["u1-thread-a"] = run_id

    st.session_state["active_run_id"] = run_id
    st.session_state["active_run_thread_id"] = "u1-thread-a"
    st.session_state["run_last_rendered_event_seq"] = 0
    st.session_state["is_running"] = True

    consumed = app_logic.consume_active_run_events()

    assert consumed is True
    assert len(st.session_state.get("analysis_logs", [])) == 1
    assert st.session_state.get("is_running") is False
    assert st.session_state.get("active_run_id") is None
