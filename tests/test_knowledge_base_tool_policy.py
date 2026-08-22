from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

import graph_factory
import tools.NTL_Knowledge_Base as knowledge_base
import tools.NTL_Knowledge_Base_Searcher as knowledge_base_searcher
from tools.NTL_Knowledge_Base import NTL_Code_Knowledge
from tools.NTL_Knowledge_Base_Searcher import NTL_Knowledge_Base, TOOLS


def test_workflow_mode_requires_confirmed_skill_gap() -> None:
    payload = json.loads(
        NTL_Knowledge_Base.invoke(
            {
                "query": "Build an NTL workflow",
                "response_mode": "workflow",
                "skill_gap_confirmed": False,
            }
        )
    )

    assert payload["status"] == "skill_first_required"


def test_graph_registers_knowledge_base_as_tool_not_subagent() -> None:
    source = (Path(__file__).resolve().parents[1] / "graph_factory.py").read_text(encoding="utf-8")

    assert "knowledge_base_subagent" not in source
    assert "system_prompt_kb_searcher" not in source
    assert "_knowledge_base_tool()" in source
    assert "tools=[*engineer_tools, *ENGINEER_CONTRACT_TOOLS, _knowledge_base_tool()]" in source
    assert '"name": "NTL_Data_Searcher"' in source
    assert '"name": "NTL_Analyst"' in source
    assert '"name": "NTL_Event_Tracker"' in source


def test_formal_knowledge_base_excludes_legacy_code_rag() -> None:
    names = {getattr(tool, "name", "") for tool in TOOLS}
    assert names == {"NTL_Literature_Knowledge", "NTL_Solution_Knowledge"}
    assert "NTL_Code_Knowledge" not in names
    disabled = json.loads(NTL_Code_Knowledge.invoke({"query": "old GEE initialization"}))
    assert disabled["status"] == "disabled_store"
    assert disabled["store"] == "Code_RAG"


def test_knowledge_base_agent_invokes_provider_with_concrete_messages(monkeypatch) -> None:
    received = []

    class FakeModel:
        def bind_tools(self, _tools):
            return self

        def invoke(self, payload):
            received.append(payload)
            return AIMessage(content='{"intent_analysis": {}, "response": {}}')

    monkeypatch.setattr(knowledge_base_searcher, "_build_searcher_llm", lambda: FakeModel())

    result = knowledge_base_searcher.agent(
        {
            "messages": [HumanMessage(content="Explain a nighttime-light method.")],
            "response_mode": "theory",
            "need_citations": False,
            "locale": "en",
        }
    )

    assert result["messages"]
    assert len(received) == 1
    assert isinstance(received[0], list)
    assert all(hasattr(message, "content") for message in received[0])


def test_supplemental_knowledge_failure_is_recoverable(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        knowledge_base_searcher,
        "NTL_Knowledge_Base",
        SimpleNamespace(invoke=unavailable),
    )

    result = graph_factory._invoke_knowledge_base("Which local tool should I use?")

    assert result["status"] == "knowledge_unavailable"
    assert result["error_type"] == "RuntimeError"
    assert "provider unavailable" not in result["message"]


def test_store_open_is_lazy_and_never_requests_collection_creation(tmp_path, monkeypatch) -> None:
    calls = []

    class EmptyCollection:
        def count(self):
            return 0

    class FakeChroma:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self._collection = EmptyCollection()

    monkeypatch.setattr(knowledge_base, "Chroma", FakeChroma)
    store_dir = tmp_path / "read_only_store"
    store_dir.mkdir()
    tool = knowledge_base._build_retriever_tool(
        collection_name="Test_RAG",
        persist_directory=str(store_dir),
        tool_name="Test_Knowledge",
        description="test store",
        embeddings=object(),
        k=1,
        score_threshold=0.3,
    )

    # Registering the tool must not open a persistent Chroma database.
    assert calls == []
    payload = json.loads(tool.invoke({"query": "test query"}))

    assert payload["status"] == "empty_store"
    assert calls[0]["create_collection_if_not_exists"] is False


def test_readonly_store_returns_safe_nonblocking_payload(tmp_path, monkeypatch) -> None:
    class ReadonlyChroma:
        def __init__(self, **_kwargs):
            raise RuntimeError(
                "attempt to write a readonly database at C:\\private\\RAG\\chroma.sqlite3"
            )

    monkeypatch.setattr(knowledge_base, "Chroma", ReadonlyChroma)
    store_dir = tmp_path / "read_only_store"
    store_dir.mkdir()
    tool = knowledge_base._build_retriever_tool(
        collection_name="Test_RAG",
        persist_directory=str(store_dir),
        tool_name="Test_Knowledge",
        description="test store",
        embeddings=object(),
        k=1,
        score_threshold=0.3,
    )

    payload = json.loads(tool.invoke({"query": "test query"}))
    serialized = json.dumps(payload)

    assert payload["status"] == "knowledge_unavailable"
    assert payload["store"] == "Test_RAG"
    assert payload["error_type"] == "RuntimeError"
    assert "C:\\private" not in serialized
    assert "readonly database" not in serialized


def test_searcher_failure_returns_safe_nonblocking_payload(monkeypatch) -> None:
    class BrokenGraph:
        @staticmethod
        def stream(*_args, **_kwargs):
            raise RuntimeError("SQLite failure at D:\\private\\RAG\\chroma.sqlite3")

    monkeypatch.setattr(knowledge_base_searcher, "graph", BrokenGraph())

    payload = json.loads(
        knowledge_base_searcher._NTL_Knowledge_Searcher(
            "Explain a nighttime-light method.",
            response_mode="theory",
        )
    )
    serialized = json.dumps(payload)

    assert payload["status"] == "knowledge_unavailable"
    assert payload["error_type"] == "RuntimeError"
    assert "D:\\private" not in serialized
    assert "SQLite failure" not in serialized
