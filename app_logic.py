import os
import re
import time
from typing import Optional

import streamlit as st
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

import app_agents
import app_state
import file_context_service
import history_store
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


def _collect_recent_outputs(seconds: int = 120, thread_id: Optional[str] = None):
    tid = str(thread_id or st.session_state.get("thread_id") or current_thread_id.get() or "debug")
    out_dir = storage_manager.get_workspace(tid) / "outputs"
    now = time.time()

    for f in out_dir.glob("*.png"):
        if now - os.path.getmtime(f) < seconds:
            st.session_state.chat_history.append(("assistant_img", str(f)))
            try:
                history_store.append_chat_record(tid, role="assistant_img", content=str(f), kind="image")
            except Exception:
                pass

    for f in out_dir.glob("*.csv"):
        if now - os.path.getmtime(f) < seconds:
            st.session_state.chat_history.append(("assistant_table", str(f)))
            try:
                history_store.append_chat_record(tid, role="assistant_table", content=str(f), kind="table")
            except Exception:
                pass

    latest_tif = None
    latest_mtime = -1
    for f in out_dir.glob("*.tif"):
        mtime = os.path.getmtime(f)
        if now - mtime < seconds and mtime > latest_mtime:
            latest_tif = f
            latest_mtime = mtime
    if latest_tif:
        st.session_state.current_map_tif = str(latest_tif)


def _build_injected_context_system_message(question: str, thread_id: str) -> Optional[str]:
    top_n = int(st.session_state.get("injected_context_top_n", 4) or 4)
    max_chars = int(st.session_state.get("injected_context_max_chars", 6000) or 6000)
    snippets = history_store.retrieve_relevant_context(
        thread_id=thread_id,
        query=question,
        top_n=max(1, min(8, top_n)),
        max_chars=max(1200, max_chars),
    )
    st.session_state["last_injected_context_used"] = snippets
    if not snippets:
        return None
    lines = [
        "User-provided file context snippets (retrieved by relevance).",
        "Use only if relevant to the current question. Cite the source file/page when used.",
    ]
    for i, item in enumerate(snippets, 1):
        source_file = str(item.get("source_file", "unknown"))
        page = item.get("page")
        page_text = f", page {page}" if page else ""
        score = item.get("score")
        score_text = f", score={score}" if score is not None else ""
        text = str(item.get("text", "")).strip()
        lines.append(f"[{i}] source={source_file}{page_text}{score_text}")
        lines.append(text)
    return "\n".join(lines)


def _extract_tool_usage(logs: list) -> tuple[list[str], dict]:
    sequence: list[str] = []
    counts: dict[str, int] = {}
    for event in logs or []:
        if not isinstance(event, dict):
            continue
        for msg in event.get("messages", []) or []:
            if not isinstance(msg, ToolMessage):
                continue
            name = str(getattr(msg, "name", "") or "tool").strip() or "tool"
            sequence.append(name)
            counts[name] = counts.get(name, 0) + 1
    return sequence, counts


def inject_selected_files_to_context(file_names: list[str], max_pages: int = 120) -> dict:
    thread_id = str(st.session_state.get("thread_id") or "debug")
    vlm_model_name = str(st.session_state.get("cfg_model") or "qwen3.5-plus")
    result = file_context_service.build_context_items_for_files(
        thread_id=thread_id,
        file_names=file_names,
        max_pages=max_pages,
        vlm_model_name=vlm_model_name,
        vlm_timeout_s=90,
    )
    items = result.get("items", []) or []
    merge_stats = {"inserted": 0, "updated": 0, "total": 0}
    if items:
        merge_stats = history_store.upsert_injected_context_items(thread_id, items)
    result["merge_stats"] = merge_stats
    result["injected_files"] = history_store.injected_file_overview(thread_id)
    return result


def clear_injected_context() -> None:
    thread_id = str(st.session_state.get("thread_id") or "debug")
    history_store.clear_injected_context(thread_id)


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


def _message_fingerprint(msg: BaseMessage) -> str:
    """Build a stable dedupe key for streamed message objects."""
    mid = getattr(msg, "id", None)
    if mid:
        return f"id:{mid}"

    msg_type = getattr(msg, "type", msg.__class__.__name__)
    msg_name = getattr(msg, "name", "")
    tool_call_id = getattr(msg, "tool_call_id", "")
    text = _chunk_to_text(msg).strip()
    return f"{msg_type}|{msg_name}|{tool_call_id}|{text}"


def _iter_message_lists(payload):
    """Yield all message lists from top-level or nested stream payload shapes."""
    if isinstance(payload, dict):
        msgs = payload.get("messages")
        if isinstance(msgs, list):
            yield msgs
        for value in payload.values():
            yield from _iter_message_lists(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _iter_message_lists(item)


def _collect_new_messages(payload, seen_fingerprints: set[str]) -> list[BaseMessage]:
    """Collect unseen LangChain messages from an arbitrary stream payload."""
    delta: list[BaseMessage] = []
    for msg_list in _iter_message_lists(payload):
        if not isinstance(msg_list, list):
            continue
        for msg in msg_list:
            if not isinstance(msg, BaseMessage):
                continue
            fp = _message_fingerprint(msg)
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)
            delta.append(msg)
    return delta


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


def _extract_meaningful_ai_text(messages, preferred_agents: Optional[list[str]] = None) -> Optional[str]:
    if not isinstance(messages, list):
        return None
    preferred = {
        str(name or "").strip().lower()
        for name in (preferred_agents or [])
        if str(name or "").strip()
    }
    fallback = None
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
                if preferred and msg_name in preferred:
                    return text
                if fallback is None:
                    fallback = text
    return fallback


def _get_state_messages(conversation, config):
    try:
        snapshot = conversation.get_state(config=config)
        values = getattr(snapshot, "values", None)
        if isinstance(values, dict):
            messages = values.get("messages", [])
            if isinstance(messages, list):
                return messages
    except Exception:
        pass
    return []


def _start_stream(conversation, state, config, stream_mode, subgraphs=True):
    # Compatibility: some wrappers may not accept subgraphs keyword.
    try:
        return conversation.stream(state, config=config, stream_mode=stream_mode, subgraphs=subgraphs)
    except TypeError:
        return conversation.stream(state, config=config, stream_mode=stream_mode)


def _iter_events(conversation, state, config):
    """Yield normalized (mode, payload, namespace) from graph stream."""
    yielded = False
    try:
        events = _start_stream(
            conversation,
            state,
            config,
            stream_mode=["messages", "values", "updates", "custom"],
            subgraphs=True,
        )
        for item in events:
            yielded = True
            if isinstance(item, tuple):
                if len(item) == 3:
                    namespace, mode, payload = item
                    if isinstance(mode, str) and mode in {"messages", "values", "updates", "custom"}:
                        yield mode, payload, namespace
                        continue
                if len(item) == 2:
                    left, right = item
                    if isinstance(left, str) and left in {"messages", "values", "updates", "custom"}:
                        yield left, right, ()
                        continue
                    if isinstance(right, str) and right in {"messages", "values", "updates", "custom"}:
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


def handle_userinput(
    user_question,
    reasoning_placeholder,
    chat_container,
    reasoning_graph_placeholder=None,
    reasoning_graph_show_sub_steps=False,
):
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

    with chat_container.container():
        app_ui.render_label_human(user_question)
        st.caption("Thinking and analyzing...")

    run_thread_id = str(st.session_state.get("thread_id") or "debug")
    context_system_msg = _build_injected_context_system_message(user_question, run_thread_id)
    state_messages = []
    if context_system_msg:
        state_messages.append({"role": "system", "content": context_system_msg})
    state_messages.append({"role": "user", "content": user_question})
    state = {"messages": state_messages}
    st.session_state["active_run_thread_id"] = run_thread_id
    config = {
        "configurable": {"thread_id": run_thread_id},
        "recursion_limit": app_state.RECURSION_LIMIT,
    }

    start_ts = time.time()
    st.session_state["run_started_ts"] = start_ts
    st.session_state["run_heartbeat_ts"] = start_ts

    final_answer = None
    last_event = None
    interrupted_reason = None
    run_exception = None
    try:
        history_store.append_chat_record(run_thread_id, role="user", content=user_question, kind="text")
        history_store.touch_thread_activity(st.session_state.get("user_id", "guest"), run_thread_id, last_question=user_question)
    except Exception:
        pass

    token = current_thread_id.set(run_thread_id)
    try:
        with reasoning_placeholder.container():
            with st.container(height=600):
                with st.expander("Reasoning Flow", expanded=False):
                    timeline_placeholder = st.empty()
                    map_placeholder = st.empty()
                    seen_message_fingerprints: set[str] = set()
                    for existing_msg in _get_state_messages(st.session_state.conversation, config):
                        if isinstance(existing_msg, BaseMessage):
                            seen_message_fingerprints.add(_message_fingerprint(existing_msg))

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

                            elif mode == "custom":
                                st.session_state["run_heartbeat_ts"] = now
                                if isinstance(payload, dict):
                                    if payload.get("event_type") == "kb_progress":
                                        st.session_state.analysis_logs.append({"kb_progress": [payload]})
                                    else:
                                        st.session_state.analysis_logs.append({"custom": [payload]})
                                    with timeline_placeholder.container():
                                        app_ui.render_reasoning_content(st.session_state.analysis_logs)
                                    if reasoning_graph_placeholder is not None:
                                        with reasoning_graph_placeholder.container():
                                            with st.expander("Reasoning Graph", expanded=True):
                                                app_ui.render_reasoning_map(
                                                    st.session_state.analysis_logs,
                                                    interactive=False,
                                                    show_sub_steps=reasoning_graph_show_sub_steps,
                                                )

                            else:
                                delta_messages = _collect_new_messages(payload, seen_message_fingerprints)
                                if delta_messages:
                                    st.session_state["run_heartbeat_ts"] = now
                                    delta_event = {"messages": delta_messages}
                                    st.session_state.analysis_logs.append(delta_event)
                                    with timeline_placeholder.container():
                                        app_ui.render_reasoning_content(st.session_state.analysis_logs)
                                    if reasoning_graph_placeholder is not None:
                                        with reasoning_graph_placeholder.container():
                                            with st.expander("Reasoning Graph", expanded=True):
                                                app_ui.render_reasoning_map(
                                                    st.session_state.analysis_logs,
                                                    interactive=False,
                                                    show_sub_steps=reasoning_graph_show_sub_steps,
                                                )
                                    last_event = delta_event
                                    candidate = _extract_meaningful_ai_text(delta_messages)
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

    preferred_agents = ["NTL_Engineer"]
    if not final_answer and last_event and "messages" in last_event:
        final_answer = _extract_meaningful_ai_text(
            last_event.get("messages"), preferred_agents=preferred_agents
        )

    state_messages = _get_state_messages(st.session_state.conversation, config)
    preferred_from_state = _extract_meaningful_ai_text(
        state_messages, preferred_agents=preferred_agents
    )
    if preferred_from_state:
        final_answer = preferred_from_state
    elif not final_answer:
        final_answer = _extract_meaningful_ai_text(state_messages)

    elapsed_s = max(0.0, time.time() - start_ts)

    if final_answer:
        final_with_footer = _attach_time_cost_footer(final_answer, elapsed_s)
        st.session_state.chat_history.append(("assistant", final_with_footer))
        try:
            history_store.append_chat_record(run_thread_id, role="assistant", content=final_with_footer, kind="text")
        except Exception:
            pass
        _collect_recent_outputs(seconds=120, thread_id=run_thread_id)
        if run_exception:
            err_text = _attach_time_cost_footer(_build_runtime_error_notice(run_exception), elapsed_s)
            st.session_state.chat_history.append(("assistant", err_text))
            try:
                history_store.append_chat_record(run_thread_id, role="assistant", content=err_text, kind="text")
            except Exception:
                pass
    elif run_exception:
        err_text = _attach_time_cost_footer(_build_runtime_error_notice(run_exception), elapsed_s)
        st.session_state.chat_history.append(("assistant", err_text))
        try:
            history_store.append_chat_record(run_thread_id, role="assistant", content=err_text, kind="text")
        except Exception:
            pass
    elif interrupted_reason:
        interrupted_text = _attach_time_cost_footer(
            f"Run interrupted ({interrupted_reason}). Please refine the task or retry.",
            elapsed_s,
        )
        st.session_state.chat_history.append(("assistant", interrupted_text))
        try:
            history_store.append_chat_record(run_thread_id, role="assistant", content=interrupted_text, kind="text")
        except Exception:
            pass
    elif last_event and "messages" in last_event:
        no_final_text = _attach_time_cost_footer(
            "Run finished without a final answer from the main agent. Please retry.",
            elapsed_s,
        )
        st.session_state.chat_history.append(("assistant", no_final_text))
        try:
            history_store.append_chat_record(run_thread_id, role="assistant", content=no_final_text, kind="text")
        except Exception:
            pass

    try:
        sequence, counts = _extract_tool_usage(st.session_state.get("analysis_logs", []))
        status = "success" if final_answer else ("error" if run_exception else ("interrupted" if interrupted_reason else "partial"))
        history_store.append_turn_summary(
            run_thread_id,
            {
                "user_id": st.session_state.get("user_id", "guest"),
                "thread_id": run_thread_id,
                "question": user_question,
                "final_answer_excerpt": str(final_answer or "")[:300],
                "tool_sequence": sequence,
                "tool_calls_by_name": counts,
                "status": status,
                "duration_s": round(elapsed_s, 3),
            },
        )
        history_store.touch_thread_activity(
            st.session_state.get("user_id", "guest"),
            run_thread_id,
            last_question=user_question,
            last_answer_excerpt=str(final_answer or "")[:240],
        )
    except Exception:
        pass

    st.rerun()
