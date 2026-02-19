import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manager_module():
    module_path = ROOT / "agents" / "NTL_Knowledge_Base_manager.py"
    spec = importlib.util.spec_from_file_location("ntl_kb_manager_literature_ingest", str(module_path))
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
        return {
            "ids": ids,
            "documents": [doc.page_content for doc in self._docs],
            "metadatas": [doc.metadata for doc in self._docs],
        }

    def delete(self, ids):
        remove_ids = {int(x) for x in ids}
        self._docs = [doc for idx, doc in enumerate(self._docs) if idx not in remove_ids]


class _FakeChroma:
    def __init__(self, **kwargs):
        self._collection = _FakeCollection()

    def add_documents(self, docs):
        self._collection._docs.extend(docs)

    def similarity_search(self, query, k=5):
        return self._collection._docs[:k]


def test_literature_profile_ingestion_with_structured_metadata(monkeypatch, tmp_path):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    class _FakePDFLoader:
        def __init__(self, file_path):
            self.file_path = file_path

        def load(self):
            name = Path(self.file_path).name
            if "Wang" in name:
                pages = [
                    "Nighttime light urbanization model based on VIIRS.",
                    "Method compares annual VIIRS NTL intensity trends.",
                ]
            else:
                pages = [
                    "Nighttime light urbanization model based on VIIRS.",
                    "夜间灯光研究展示城市空间结构变化。",
                ]
            return [
                manager.Document(
                    page_content=page,
                    metadata={"source": self.file_path, "page": idx},
                )
                for idx, page in enumerate(pages)
            ]

    monkeypatch.setattr(manager, "PyPDFLoader", _FakePDFLoader)

    literature_dir = tmp_path / "literature_base"
    (literature_dir / "group_a").mkdir(parents=True)
    (literature_dir / "group_b").mkdir(parents=True)
    (literature_dir / "group_a" / "Wang et al - 2024 - Nighttime light urbanization study.pdf").write_bytes(b"")
    (literature_dir / "group_b" / "张三 等 - 2021 - 夜间灯光城市分析.pdf").write_bytes(b"")

    report_path = tmp_path / "Literature_RAG" / "rebuild_report.json"
    db = manager.RAGDatabase(
        persistent_directory=str(tmp_path / "Literature_RAG"),
        collection_name="Literature_RAG",
    )
    report = db.create_database(
        profile="literature",
        literature_dir=str(literature_dir),
        reset=True,
        report_path=str(report_path),
    )

    assert report["profile"] == "literature"
    assert report["records_ingested"] > 0
    assert report["final_collection_count"] > 0
    assert report["dedupe_removed_count"] >= 1
    assert "literature_paper" in report["doc_type_counts"]
    assert "literature_pdf" in report["source_bucket_counts"]
    assert report_path.exists()

    report_json = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_json["collection_name"] == "Literature_RAG"
    assert report_json["profile"] == "literature"

    metadatas = db.vector_store._collection.get(include=["metadatas"])["metadatas"]
    assert metadatas
    required_fields = {
        "source_file",
        "doc_type",
        "language",
        "title",
        "year",
        "section_type",
        "topic_tags",
        "quality_tier",
    }
    for metadata in metadatas:
        assert required_fields.issubset(metadata.keys())
        assert metadata["doc_type"] == "literature_paper"
        assert metadata["source_bucket"] == "literature_pdf"
        assert metadata["quality_tier"] in {"high", "medium", "low"}
        assert metadata["title"]
        assert metadata["section_type"] in {
            "methods",
            "equations",
            "data",
            "results",
            "discussion",
            "general",
        }

    years = {item["year"] for item in metadatas}
    assert {"2024", "2021"} & years
    languages = {item["language"] for item in metadatas}
    assert "en" in languages or "zh" in languages
    assert all(
        "references" not in doc.page_content.lower()
        for doc in db.vector_store._collection._docs
    )


def test_arg_parser_supports_literature_profile():
    manager = _load_manager_module()
    parser = manager._build_arg_parser()
    args = parser.parse_args(["--profile", "literature"])
    assert args.profile == "literature"
    assert hasattr(args, "literature_dir")


def test_literature_ingestion_stops_after_references_heading(monkeypatch, tmp_path):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    class _FakePDFLoader:
        def __init__(self, file_path):
            self.file_path = file_path

        def load(self):
            pages = [
                "Methods: We compute ANTL and compare event windows.\nReferences\n[1] Example reference line.",
                "[2] Another reference-only page that should be skipped.",
            ]
            return [
                manager.Document(
                    page_content=page,
                    metadata={"source": self.file_path, "page": idx},
                )
                for idx, page in enumerate(pages)
            ]

    monkeypatch.setattr(manager, "PyPDFLoader", _FakePDFLoader)

    literature_dir = tmp_path / "literature_base"
    literature_dir.mkdir(parents=True)
    (literature_dir / "A et al - 2024 - Event impact with nighttime light.pdf").write_bytes(b"")

    db = manager.RAGDatabase(
        persistent_directory=str(tmp_path / "Literature_RAG"),
        collection_name="Literature_RAG",
    )
    report = db.create_database(
        profile="literature",
        literature_dir=str(literature_dir),
        reset=True,
    )

    assert report["records_ingested"] > 0
    docs = db.vector_store._collection._docs
    assert docs
    merged = "\n".join(doc.page_content for doc in docs).lower()
    assert "methods" in merged
    assert "references" not in merged
    assert "another reference-only page" not in merged


def test_literature_profile_ingests_markdown_cards(monkeypatch, tmp_path):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    class _FakePDFLoader:
        def __init__(self, file_path):
            self.file_path = file_path

        def load(self):
            return [
                manager.Document(
                    page_content="Nighttime light baseline paper content.",
                    metadata={"source": self.file_path, "page": 0},
                )
            ]

    monkeypatch.setattr(manager, "PyPDFLoader", _FakePDFLoader)

    literature_dir = tmp_path / "literature_base"
    literature_dir.mkdir(parents=True)
    (literature_dir / "A et al - 2024 - Baseline NTL paper.pdf").write_bytes(b"")
    (literature_dir / "Yu et al - 2025 - STARS nighttime light method.md").write_text(
        "# STARS\n\nDOI: 10.1016/j.rse.2025.114720\n\nAbstract: A novel gap-filling method for SDGSAT-1 nighttime light imagery.",
        encoding="utf-8",
    )

    db = manager.RAGDatabase(
        persistent_directory=str(tmp_path / "Literature_RAG"),
        collection_name="Literature_RAG",
    )
    report = db.create_database(
        profile="literature",
        literature_dir=str(literature_dir),
        reset=True,
    )

    assert report["records_ingested"] > 0
    assert report["source_bucket_counts"].get("literature_pdf", 0) > 0
    assert report["source_bucket_counts"].get("literature_text", 0) > 0

    metadatas = db.vector_store._collection.get(include=["metadatas"])["metadatas"]
    assert any(m.get("source_bucket") == "literature_text" for m in metadatas)
