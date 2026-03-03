from pathlib import Path


def test_collect_recent_outputs_accepts_thread_id_and_uses_it():
    source = Path("app_logic.py").read_text(encoding="utf-8-sig")
    assert "def _collect_recent_outputs(seconds: int = 120, thread_id: Optional[str] = None):" in source
    assert 'out_dir = storage_manager.get_workspace(tid) / "outputs"' in source


def test_handle_userinput_passes_current_thread_to_recent_outputs():
    source = Path("app_logic.py").read_text(encoding="utf-8-sig")
    assert "_collect_recent_outputs(seconds=120, thread_id=run_thread_id)" in source
