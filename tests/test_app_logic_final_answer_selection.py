from langchain_core.messages import AIMessage, HumanMessage

import app_logic


def test_extract_meaningful_ai_text_prefers_engineer_when_requested():
    messages = [
        HumanMessage(content="q"),
        AIMessage(content="Code result", name="Code_Assistant"),
        AIMessage(content="Engineer final summary", name="NTL_Engineer"),
    ]

    answer = app_logic._extract_meaningful_ai_text(
        messages,
        preferred_agents=["NTL_Engineer"],
    )
    assert answer == "Engineer final summary"


def test_extract_meaningful_ai_text_falls_back_to_latest_non_transfer():
    messages = [
        AIMessage(content="Older answer", name="NTL_Engineer"),
        AIMessage(content="Latest answer", name="Code_Assistant"),
    ]

    answer = app_logic._extract_meaningful_ai_text(messages)
    assert answer == "Latest answer"


def test_extract_meaningful_ai_text_ignores_transfer_markers():
    messages = [
        AIMessage(content="Valid answer", name="Data_Searcher"),
        AIMessage(content="Successfully transferred to NTL_Engineer", name="Code_Assistant"),
    ]

    answer = app_logic._extract_meaningful_ai_text(messages)
    assert answer == "Valid answer"
