import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manager_module():
    module_path = ROOT / "agents" / "NTL_Knowledge_Base_manager.py"
    spec = importlib.util.spec_from_file_location("ntl_kb_manager_code_ingest", str(module_path))
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


def _write_tool_templates(tool_dir: Path):
    templates = {
        "GEE_download.py": "def ntl_download_tool(study_area, scale_level):\n    return study_area\n",
        "VNP46A2_angular_correction.py": "def VNP46A2_angular_correction_tool(study_area, scale_level, time_range_input):\n    return study_area\n",
        "NTL_raster_stats.py": "def NTL_raster_statistics(ntl_tif_path, shapefile_path, output_csv_path):\n    return output_csv_path\n",
        "NTL_trend_detection_tool.py": "def analyze_ntl_trend_masked_logic(raster_files, vector_file, out_prefix='NTL_Trend'):\n    return out_prefix\n",
        "NTL_anomaly_detection_tool.py": "def detect_ntl_anomaly(raster_files, target_index=None, k_sigma=3.0):\n    return k_sigma\n",
        "NPP_viirs_index_tool.py": "def compute_vnci_index(ndvi_tif, ntl_tif, output_tif):\n    return output_tif\n",
    }
    for name, content in templates.items():
        (tool_dir / name).write_text(content, encoding="utf-8")


def test_code_profile_ingestion_report_and_dedup(monkeypatch, tmp_path):
    manager = _load_manager_module()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(manager, "OpenAIEmbeddings", lambda model=None: object())
    monkeypatch.setattr(manager, "Chroma", _FakeChroma)

    code_guide = tmp_path / "code_guide"
    (code_guide / "GEE_dataset").mkdir(parents=True)
    (code_guide / "Geospatial_Code_GEE").mkdir(parents=True)
    (code_guide / "Geospatial_Code_geopanda_rasterio").mkdir(parents=True)
    (code_guide / "geopandas").mkdir(parents=True)
    (code_guide / "rasterio").mkdir(parents=True)

    (code_guide / "GEE_dataset" / "dataset_documents.json").write_text(
        json.dumps(
            [
                {
                    "Dataset_id": "Dataset_A",
                    "Name": "VIIRS Dataset",
                    "Snippet": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                    "Tags": "ntl,viirs",
                    "Description": "Monthly NTL dataset",
                },
                {
                    "Dataset_id": "Dataset_B",
                    "Name": "VNP46A2 Dataset",
                    "Snippet": "NASA/VIIRS/002/VNP46A2",
                    "Tags": "ntl,vnp46a2",
                    "Description": "Daily VNP46A2 dataset",
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (code_guide / "Geospatial_Code_GEE" / "module_a.py").write_text(
        "def gee_fn(x, y):\n    return x + y\n",
        encoding="utf-8",
    )
    duplicate_text = "Rasterio reprojection guide"
    (code_guide / "Geospatial_Code_geopanda_rasterio" / "dup_a.txt").write_text(
        duplicate_text,
        encoding="utf-8",
    )
    (code_guide / "rasterio" / "dup_b.txt").write_text(duplicate_text, encoding="utf-8")
    (code_guide / "geopandas" / "gpd.txt").write_text("GeoPandas overlay guide", encoding="utf-8")

    tool_dir = tmp_path / "tools"
    tool_dir.mkdir(parents=True)
    _write_tool_templates(tool_dir)

    db = manager.RAGDatabase(
        persistent_directory=str(tmp_path / "code_rag"),
        collection_name="Code_RAG",
    )
    report = db.create_database(
        profile="code",
        code_guide_dir=str(code_guide),
        tool_dir=str(tool_dir),
        include_gis_docs=True,
        reset=True,
    )

    assert report["records_ingested"] > 0
    assert report["final_collection_count"] > 0
    assert report["dedupe_removed_count"] >= 1
    assert "dataset_card" in report["doc_type_counts"]
    assert "code_symbol" in report["doc_type_counts"] or "code_module" in report["doc_type_counts"]
    assert "gis_guide" in report["doc_type_counts"]
    assert "tool_template" in report["doc_type_counts"]
    assert "code_guide" in report["source_bucket_counts"]
    assert "tools_latest" in report["source_bucket_counts"]
    assert "python" in report["language_counts"] or "text" in report["language_counts"]
