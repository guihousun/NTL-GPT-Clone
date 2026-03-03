from langchain_core.messages import ToolMessage

import app_ui


def test_dedupe_tool_messages_collapses_stream_duplicates():
    m1 = ToolMessage(content="ok", name="transfer_to_data_searcher", tool_call_id="tc1")
    m2 = ToolMessage(content="ok", name="transfer_to_data_searcher", tool_call_id="tc1")
    m3 = ToolMessage(content="ok", name="transfer_to_data_searcher", tool_call_id="tc2")

    out = app_ui._dedupe_tool_messages([m1, m2, m3])

    assert len(out) == 2
    assert out[0].tool_call_id == "tc1"
    assert out[1].tool_call_id == "tc2"
