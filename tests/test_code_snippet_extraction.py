import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manager_module():
    module_path = ROOT / "agents" / "NTL_Knowledge_Base_manager.py"
    spec = importlib.util.spec_from_file_location("ntl_kb_manager_snippets", str(module_path))
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
        return {"ids": ids, "documents": [], "metadatas": []}

    def delete(self, ids):
        self._docs = []


class _FakeChroma:
    def __init__(self, **kwargs):
        self._collection = _FakeCollection()

    def add_documents(self, docs):
        self._collection._docs.extend(docs)

    def similarity_search(self, query, k=5):
        return self._collection._docs[:k]


def test_extract_python_symbols_contains_function_and_parameters(monkeypatch):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    db = manager.RAGDatabase(
        persistent_directory=str(ROOT / "tmp_code_extract"),
        collection_name="Code_RAG",
    )

    symbols = db._extract_python_symbols(ROOT / "tools" / "GEE_download.py")
    target = next((item for item in symbols if item["name"] == "ntl_download_tool"), None)
    assert target is not None
    assert "study_area" in target["signature"]
    assert "temporal_resolution" in target["signature"]
    assert "def ntl_download_tool" in target["code"]
