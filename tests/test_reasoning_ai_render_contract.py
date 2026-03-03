from pathlib import Path


def test_reasoning_ai_render_skips_empty_and_keeps_first_heading():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "effective_messages = []" in text
    assert "if not msg_content.strip():" in text
    assert "render_label_ai(agent_name)" in text
    assert "if not effective_messages:" in text


def test_code_assistant_stage_caption_removed():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert "Code_Assistant Stage:" not in text


def test_kb_render_migrated_to_knowledge_base_subagent_ai_messages():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert 'agent_name.lower() == "knowledge_base_searcher"' in text
    assert 'knowledge_base_subagent' in text
    assert "render_kb_output(msg_content)" in text
    assert 'if msg.name and "NTL_Knowledge_Base" in msg.name:' in text
    assert "KB output is now rendered on Knowledge_Base_Searcher AI messages." in text


def test_existing_data_searcher_and_code_assistant_render_paths_remain():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    assert 'agent_name.lower() == "data_searcher"' in text
    assert "render_data_searcher_output(msg_content)" in text
    assert 'agent_name.lower() == "code_assistant"' in text
    assert "_render_code_assistant_message(msg_content)" in text
