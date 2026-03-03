from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import app_logic


def test_collect_new_messages_from_nested_payload_shapes():
    payload = {
        "NTL_Engineer": {
            "messages": [
                AIMessage(content="Engineer planning", name="NTL_Engineer"),
            ]
        },
        "Data_Searcher": {
            "update": {
                "messages": [
                    ToolMessage(content="tool ok", name="geodata_quick_check_tool", tool_call_id="tc1"),
                ]
            }
        },
    }

    out = app_logic._collect_new_messages(payload, seen_fingerprints=set())
    assert len(out) == 2
    assert isinstance(out[0], AIMessage)
    assert isinstance(out[1], ToolMessage)


def test_collect_new_messages_deduplicates_seen_messages():
    msg = HumanMessage(content="same question")
    seen = {app_logic._message_fingerprint(msg)}
    payload = {"messages": [msg]}

    out = app_logic._collect_new_messages(payload, seen_fingerprints=seen)
    assert out == []
