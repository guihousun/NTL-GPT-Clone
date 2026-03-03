from pathlib import Path


def test_handle_userinput_pins_run_thread_id_for_full_run():
    source = Path("app_logic.py").read_text(encoding="utf-8-sig")
    assert 'run_thread_id = str(st.session_state.get("thread_id") or "debug")' in source
    assert 'st.session_state["active_run_thread_id"] = run_thread_id' in source
    assert '"configurable": {"thread_id": run_thread_id}' in source
    assert "token = current_thread_id.set(run_thread_id)" in source
    assert "_collect_recent_outputs(seconds=120, thread_id=run_thread_id)" in source
