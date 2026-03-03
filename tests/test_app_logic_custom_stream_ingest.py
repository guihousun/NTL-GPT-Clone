import app_logic


class _DummyConversation:
    def stream(self, state, config=None, stream_mode=None, subgraphs=True):
        del state, config, subgraphs
        assert isinstance(stream_mode, list)
        assert "custom" in stream_mode
        yield ((), "custom", {"event_type": "kb_progress", "phase": "knowledge_retrieval", "status": "running"})
        yield ((), "values", {"messages": []})


def test_iter_events_includes_custom_mode():
    conv = _DummyConversation()
    out = list(app_logic._iter_events(conv, {"messages": []}, {"configurable": {"thread_id": "t1"}}))
    modes = [mode for mode, payload, namespace in out]
    assert "custom" in modes
    custom_payloads = [payload for mode, payload, namespace in out if mode == "custom"]
    assert custom_payloads
    assert custom_payloads[0].get("event_type") == "kb_progress"
