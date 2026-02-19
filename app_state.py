import streamlit as st
import uuid
from storage_manager import storage_manager

MODEL_OPTIONS = ["qwen3.5-plus", "gpt-5-mini", "gpt-5.1"]
RECURSION_LIMIT = 51
CHAT_CONTAINER_HEIGHT = 600
ANALYSIS_CONTAINER_HEIGHT = 600
LLM_REQUEST_TIMEOUT_S = 120


def init_app():
    # Cleanup legacy timeout controls removed from UI (manual interrupt only).
    for legacy_key in ("run_max_duration_s", "run_stall_timeout_s", "run_decision_pending"):
        if legacy_key in st.session_state:
            del st.session_state[legacy_key]

    st.session_state.setdefault("cfg_model", MODEL_OPTIONS[0])
    st.session_state.setdefault("initialized", False)
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("run_counter", 0)

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())[:12]

    st.session_state.user_workspace = storage_manager.get_workspace(st.session_state.thread_id)
    st.session_state.setdefault("analysis_logs", [])
    st.session_state.setdefault("analysis_history", [])
    st.session_state.setdefault("last_question", "")
    st.session_state.setdefault("is_running", False)
    st.session_state.setdefault("cancel_requested", False)
    st.session_state.setdefault("run_started_ts", None)
    st.session_state.setdefault("run_heartbeat_ts", None)
    st.session_state.setdefault("run_ended_ts", None)
    st.session_state.setdefault("runtime_recovered_notice", None)


def reset_chat():
    st.session_state.chat_history = []
    st.session_state.run_counter = 0
    st.session_state.cancel_requested = False
    st.session_state.run_started_ts = None
    st.session_state.run_heartbeat_ts = None
    st.session_state.run_ended_ts = None
    st.session_state.runtime_recovered_notice = None
