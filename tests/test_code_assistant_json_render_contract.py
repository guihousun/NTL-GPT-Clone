from pathlib import Path


def test_code_assistant_uses_shape_based_helper_rendering():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "def _render_code_assistant_message(raw_content: str) -> None:" in text
    assert 'elif agent_name.lower() == "code_assistant":' in text
    assert "_render_code_assistant_message(msg_content)" in text


def test_code_assistant_helper_parses_json_and_falls_back_to_code():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "parsed, rest = _extract_json(raw_text)" in text
    assert "if isinstance(parsed, (dict, list)):" in text
    assert "st.json(_sanitize_paths_in_obj(parsed))" in text
    assert 'st.code(raw_text, language="python")' in text
    assert "task_summary" not in text


def test_non_target_reasoning_branches_remain_unchanged():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "render_data_searcher_output(msg_content)" in text
    assert "render_uploaded_understanding_output(msg.content, tool_name=str(msg.name or \"\"))" in text
    assert "render_kb_output(msg.content)" in text
