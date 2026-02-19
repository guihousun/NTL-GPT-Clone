import os
import re
import time
from typing import Optional

import streamlit as st
from langchain_core.messages import AIMessage

import app_agents
import app_state
from storage_manager import current_thread_id, storage_manager


def should_recover_stale_run(
    is_running: bool,
    run_started_ts: Optional[float],
    heartbeat_ts: Optional[float],
    now_ts: Optional[float] = None,
    grace_s: int = 300,
) -> bool:
    """Detect stale running-state that can block next-turn interaction."""
    if not is_running:
        return False
    now = float(now_ts if now_ts is not None else time.time())
    grace = max(30, int(grace_s))

    candidates = []
    for ts in (heartbeat_ts, run_started_ts):
        if ts is None:
            continue
        try:
            candidates.append(float(ts))
        except Exception:
            continue

    if not candidates:
        return True

    last_ts = max(candidates)
    return (now - last_ts) > grace


def recover_runtime_health():
    """Self-heal stale run state after long runs or interrupted reruns."""
    is_running = bool(st.session_state.get("is_running", False))
    if not is_running:
        return

    run_started_ts = st.session_state.get("run_started_ts")
    run_heartbeat_ts = st.session_state.get("run_heartbeat_ts")
    grace_s = 300

    if should_recover_stale_run(
        is_running=is_running,
        run_started_ts=run_started_ts,
        heartbeat_ts=run_heartbeat_ts,
        grace_s=grace_s,
    ):
        st.session_state["is_running"] = False
        st.session_state["cancel_requested"] = False
        st.session_state["runtime_recovered_notice"] = (
            "Detected stale run state after a long task. "
            "Auto-recovered interaction so the next question can proceed."
        )


def _attach_time_cost_footer(answer_text: str, elapsed_s: float) -> str:
    """Append a subtle runtime footer at the end of an assistant response."""
    label = "本次回答耗时" if st.session_state.get("ui_lang") == "CN" else "Time cost"
    footer = (
        "<div style='margin-top:0.45rem;font-size:0.78rem;"
        "color:#94a3b8;line-height:1.2;'>"
        f"{label}: {elapsed_s:.2f}s"
        "</div>"
    )
    return f"{answer_text}\n\n{footer}"


def _is_timeout_error_text(text: str) -> bool:
    low = (text or "").lower()
    markers = [
        "readtimeout",
        "connecttimeout",
        "timed out",
        "timeouterror",
        "httpx.readtimeout",
    ]
    return any(marker in low for marker in markers)


def _build_runtime_error_notice(err: Exception) -> str:
    raw = str(err or "").strip()
    short = raw.split("Traceback", 1)[0].strip() if raw else "Unknown runtime error."
    if len(short) > 260:
        short = short[:260] + "..."
    is_cn = st.session_state.get("ui_lang") == "CN"

    if _is_timeout_error_text(raw):
        if is_cn:
            return (
                "运行在代理交接后发生超时（ReadTimeout），因此未产生最终结果。\n"
                f"错误摘要：`{short}`\n"
                "建议：重试一次；若持续出现，请提高模型请求超时或拆分任务。"
            )
        return (
            "The run timed out after agent handoff (ReadTimeout), so no final result was produced.\n"
            f"Error summary: `{short}`\n"
            "Suggestion: retry once; if it repeats, increase model timeout or split the task."
        )

    if is_cn:
        return (
            "运行在代理交接后失败，未产生最终结果。\n"
            f"错误摘要：`{short}`\n"
            "建议：检查最近工具输出与推理日志后重试。"
        )
    return (
        "The run failed after agent handoff and no final result was produced.\n"
        f"Error summary: `{short}`\n"
        "Suggestion: inspect recent tool outputs/reasoning logs and retry."
    )


def ensure_conversation_initialized():
    if not st.session_state.get("initialized"):
        return

    user_key = st.session_state.get("user_api_key")
    if not user_key:
        st.error("API Key is missing via session state.")
        return

    st.session_state.conversation = app_agents.get_ntl_graph(
        model_name=st.session_state["cfg_model"],
        api_key=user_key,
        request_timeout_s=int(getattr(app_state, "LLM_REQUEST_TIMEOUT_S", 120)),
        session_tag=st.session_state.thread_id,
    )


def _collect_recent_outputs(seconds: int = 120):
    out_dir = storage_manager.get_workspace() / "outputs"
    now = time.time()

    for f in out_dir.glob("*.png"):
        if now - os.path.getmtime(f) < seconds:
            st.session_state.chat_history.append(("assistant_img", str(f)))

    for f in out_dir.glob("*.csv"):
        if now - os.path.getmtime(f) < seconds:
            st.session_state.chat_history.append(("assistant_table", str(f)))

    latest_tif = None
    latest_mtime = -1
    for f in out_dir.glob("*.tif"):
        mtime = os.path.getmtime(f)
        if now - mtime < seconds and mtime > latest_mtime:
            latest_tif = f
            latest_mtime = mtime
    if latest_tif:
        st.session_state.current_map_tif = str(latest_tif)


def _chunk_to_text(chunk) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item.get("text")))
                elif item.get("text"):
                    parts.append(str(item.get("text")))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _is_transfer_message(text: str) -> bool:
    if not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    patterns = [
        r"^successfully transferred to\b",
        r"^transferred to\b",
        r"^successfully handed off to\b",
        r"^handed off to\b",
        r"^routing to\b",
    ]
    return any(re.match(p, t) for p in patterns)


def _extract_meaningful_ai_text(messages) -> Optional[str]:
    if not isinstance(messages, list):
        return None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            msg_name = (getattr(msg, "name", None) or "").lower()
            if "(streaming)" in msg_name:
                continue
            text = _chunk_to_text(msg).strip()
            text = re.sub(
                r"^\s*\*{0,2}\s*(Data_Searcher|Code_Assistant)\s*\(streaming\)\s*\*{0,2}\s*:?\s*\n?",
                "",
                text,
                flags=re.IGNORECASE | re.MULTILINE,
            ).strip()
            if text and not _is_transfer_message(text):
                return text
    return None


def _start_stream(conversation, state, config, stream_mode, subgraphs=True):
    # Compatibility: some wrappers may not accept subgraphs keyword.
    try:
        return conversation.stream(state, config=config, stream_mode=stream_mode, subgraphs=subgraphs)
    except TypeError:
        return conversation.stream(state, config=config, stream_mode=stream_mode)


def _get_existing_message_count(conversation, config) -> int:
    """Get persisted message count for current thread to avoid re-rendering old rounds."""
    try:
        snapshot = conversation.get_state(config=config)
        values = getattr(snapshot, "values", None)
        if isinstance(values, dict):
            msgs = values.get("messages", [])
            if isinstance(msgs, list):
                return len(msgs)
    except Exception:
        pass
    return 0


def _iter_events(conversation, state, config):
    """Yield normalized (mode, payload, namespace) from graph stream."""
    yielded = False
    try:
        events = _start_stream(
            conversation,
            state,
            config,
            stream_mode=["messages", "values", "updates"],
            subgraphs=True,
        )
        for item in events:
            yielded = True
            if isinstance(item, tuple):
                if len(item) == 3:
                    namespace, mode, payload = item
                    if isinstance(mode, str) and mode in {"messages", "values", "updates"}:
                        yield mode, payload, namespace
                        continue
                if len(item) == 2:
                    left, right = item
                    if isinstance(left, str) and left in {"messages", "values", "updates"}:
                        yield left, right, ()
                        continue
                    if isinstance(right, str) and right in {"messages", "values", "updates"}:
                        yield right, left, ()
                        continue
                    if hasattr(left, "content") and isinstance(right, dict):
                        yield "messages", (left, right), ()
                        continue
                    if isinstance(left, tuple) and isinstance(right, tuple) and len(right) == 2:
                        if hasattr(right[0], "content") and isinstance(right[1], dict):
                            yield "messages", right, left
                            continue
                    if isinstance(left, tuple) and isinstance(right, dict):
                        yield "values", right, left
                        continue
            if isinstance(item, dict) and "messages" in item:
                yield "values", item, ()
            else:
                yield "updates", item, ()
    except Exception:
        if yielded:
            raise
        events = _start_stream(conversation, state, config, stream_mode="values", subgraphs=True)
        for item in events:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], tuple):
                yield "values", item[1], item[0]
            else:
                yield "values", item, ()


def handle_userinput(user_question, reasoning_placeholder, chat_container):
    import app_ui

    prev_logs = st.session_state.get("analysis_logs", [])
    if prev_logs:
        history = st.session_state.setdefault("analysis_history", [])
        history.append(
            {
                "question": st.session_state.get("last_question", ""),
                "logs": list(prev_logs),
                "created_at": int(time.time()),
            }
        )
        if len(history) > 12:
            st.session_state["analysis_history"] = history[-12:]

    st.session_state.analysis_logs = []
    st.session_state["last_question"] = user_question
    st.session_state["is_running"] = True
    st.session_state["cancel_requested"] = False

    wait_placeholder = chat_container.empty()
    with wait_placeholder.container():
        app_ui.render_label_human(user_question)
        st.caption("Thinking and analyzing...")

    state = {"messages": [{"role": "user", "content": user_question}]}
    config = {
        "configurable": {"thread_id": st.session_state.thread_id},
        "recursion_limit": app_state.RECURSION_LIMIT,
    }
    baseline_messages_len = _get_existing_message_count(st.session_state.conversation, config)

    start_ts = time.time()
    st.session_state["run_started_ts"] = start_ts
    st.session_state["run_heartbeat_ts"] = start_ts

    final_answer = None
    last_event = None
    interrupted_reason = None
    run_exception = None

    token = current_thread_id.set(st.session_state.thread_id)
    try:
        with reasoning_placeholder.container():
            with st.container(height=600):
                with st.expander("Reasoning Flow", expanded=False):
                    timeline_placeholder = st.empty()
                    previous_messages_len = baseline_messages_len

                    try:
                        for mode, payload, namespace in _iter_events(st.session_state.conversation, state, config):
                            now = time.time()
                            st.session_state["run_heartbeat_ts"] = now
                            if st.session_state.get("cancel_requested", False):
                                st.warning("Run interrupted by user request.")
                                interrupted_reason = "user_cancel"
                                break

                            if mode == "messages":
                                if isinstance(payload, tuple) and len(payload) == 2:
                                    chunk, metadata = payload
                                    text_piece = _chunk_to_text(chunk)
                                    if text_piece:
                                        st.session_state["run_heartbeat_ts"] = now

                            elif mode == "updates":
                                st.session_state["run_heartbeat_ts"] = now

                            elif isinstance(payload, dict) and "messages" in payload:
                                event = payload
                                msg_list = event.get("messages", [])
                                if isinstance(msg_list, list):
                                    current_len = len(msg_list)
                                    if current_len > previous_messages_len:
                                        delta_messages = msg_list[previous_messages_len:current_len]
                                        previous_messages_len = current_len
                                        if delta_messages:
                                            st.session_state["run_heartbeat_ts"] = now
                                            delta_event = {"messages": delta_messages}
                                            st.session_state.analysis_logs.append(delta_event)
                                            with timeline_placeholder.container():
                                                app_ui.render_reasoning_content(st.session_state.analysis_logs)
                                            last_event = event
                                            candidate = _extract_meaningful_ai_text(event.get("messages"))
                                            if candidate:
                                                final_answer = candidate
                    except Exception as err:
                        run_exception = err
                        st.error(f"Run failed: {err}")
    finally:
        current_thread_id.reset(token)
        st.session_state["is_running"] = False
        st.session_state["cancel_requested"] = False
        st.session_state["run_ended_ts"] = time.time()

    if not final_answer and last_event and "messages" in last_event:
        final_answer = _extract_meaningful_ai_text(last_event.get("messages"))

    elapsed_s = max(0.0, time.time() - start_ts)

    if final_answer:
        st.session_state.chat_history.append(("assistant", _attach_time_cost_footer(final_answer, elapsed_s)))
        _collect_recent_outputs(seconds=120)
        if run_exception:
            st.session_state.chat_history.append(
                ("assistant", _attach_time_cost_footer(_build_runtime_error_notice(run_exception), elapsed_s))
            )
    elif run_exception:
        st.session_state.chat_history.append(
            ("assistant", _attach_time_cost_footer(_build_runtime_error_notice(run_exception), elapsed_s))
        )
    elif interrupted_reason:
        st.session_state.chat_history.append(
            (
                "assistant",
                _attach_time_cost_footer(
                    f"Run interrupted ({interrupted_reason}). Please refine the task or retry.",
                    elapsed_s,
                ),
            )
        )
    elif last_event and "messages" in last_event:
        st.session_state.chat_history.append(
            (
                "assistant",
                _attach_time_cost_footer(
                    "Run finished without a final answer from the main agent. Please retry.",
                    elapsed_s,
                ),
            )
        )

    st.rerun()
