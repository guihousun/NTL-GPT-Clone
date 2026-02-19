import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manager_module():
    module_path = ROOT / "agents" / "NTL_Knowledge_Base_manager.py"
    spec = importlib.util.spec_from_file_location("ntl_kb_manager", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Knowledge_Base_manager module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeCollection:
    def __init__(self):
        self._docs = []

    def count(self):
        return len(self._docs)

    def get(self, include=None, where=None):
        ids = [str(i) for i in range(len(self._docs))]
        metadatas = [doc.metadata for doc in self._docs]
        return {"ids": ids, "metadatas": metadatas}

    def delete(self, ids):
        id_set = {int(x) for x in ids}
        self._docs = [doc for idx, doc in enumerate(self._docs) if idx not in id_set]


class _FakeChroma:
    def __init__(self, **kwargs):
        self._collection = _FakeCollection()

    def add_documents(self, docs):
        self._collection._docs.extend(docs)

    def similarity_search(self, query, k=5):
        return self._collection._docs[:k]


def test_ingestion_rebuild_from_guidence_json(monkeypatch, tmp_path):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    db = manager.RAGDatabase(
        persistent_directory=str(tmp_path / "solution_rag"),
        collection_name="Solution_RAG",
    )
    report = db.create_database(
        json_folder=str(ROOT / "RAG" / "guidence_json"),
        reset=True,
    )

    # tools.json (26) + Workflow.json (30) should be ingested after flatten/validation.
    assert report["records_ingested"] >= 56
    assert report["final_collection_count"] >= 56
    assert report["records_seen"] >= 56

