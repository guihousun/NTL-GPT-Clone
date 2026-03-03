import pytest

import tools.NTL_Knowledge_Base_Searcher as kb_searcher


class _DummyMessage:
    def __init__(self, content):
        self.content = content


class _DummyGraphSuccess:
    def stream(self, *args, **kwargs):
        del args, kwargs
        yield {"messages": [_DummyMessage('{"intent_analysis":{"intent_type":"general_query"}}')]}


class _DummyGraphFail:
    def stream(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("upstream failure")
        yield  # pragma: no cover


def test_kb_searcher_emits_stream_progress_on_success(monkeypatch):
    emitted = []
    monkeypatch.setattr(kb_searcher, "graph", _DummyGraphSuccess())
    monkeypatch.setattr(kb_searcher, "_safe_stream_writer", lambda: emitted.append)

    out = kb_searcher._NTL_Knowledge_Searcher("test query", response_mode="theory")
    assert isinstance(out, str) and out

    phase_status = [(item.get("phase"), item.get("status")) for item in emitted]
    assert ("query_received", "done") in phase_status
    assert ("knowledge_retrieval", "running") in phase_status
    assert ("knowledge_retrieval", "done") in phase_status
    assert ("workflow_assembly", "done") in phase_status
    assert ("structured_output", "done") in phase_status


def test_kb_searcher_emits_error_progress_on_exception(monkeypatch):
    emitted = []
    monkeypatch.setattr(kb_searcher, "graph", _DummyGraphFail())
    monkeypatch.setattr(kb_searcher, "_safe_stream_writer", lambda: emitted.append)

    with pytest.raises(RuntimeError):
        kb_searcher._NTL_Knowledge_Searcher("test query", response_mode="theory")

    assert any(
        item.get("phase") == "structured_output" and item.get("status") == "error"
        for item in emitted
    )
