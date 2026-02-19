import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_manager_module():
    module_path = ROOT / "agents" / "NTL_Knowledge_Base_manager.py"
    spec = importlib.util.spec_from_file_location("ntl_kb_manager_code_smoke", str(module_path))
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


def test_code_rag_smoke_queries_have_retrievable_docs(monkeypatch, tmp_path):
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
                    "Dataset_id": "Dataset_1",
                    "Name": "VNP46A2 Nighttime Light",
                    "Snippet": "NASA/VIIRS/002/VNP46A2",
                    "Tags": "ntl,viirs,vnp46a2",
                    "Description": "Daily nighttime light dataset.",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (code_guide / "Geospatial_Code_GEE" / "module.py").write_text(
        "def gee_fn(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (code_guide / "Geospatial_Code_geopanda_rasterio" / "guide.txt").write_text(
        "Rasterio masking guide",
        encoding="utf-8",
    )
    (code_guide / "geopandas" / "guide.txt").write_text("GeoPandas overlay guide", encoding="utf-8")
    (code_guide / "rasterio" / "guide.txt").write_text("Rasterio reproject guide", encoding="utf-8")

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

    assert report["final_collection_count"] > 0
    queries = [
        "Download monthly NTL data via VIIRS",
        "How to perform VNP46A2 angular correction",
        "Compute VNCI from NDVI and NTL",
        "Run NTL raster statistics by shapefile",
        "Detect NTL anomaly in time-series rasters",
        "Analyze NTL trend with Mann-Kendall",
        "Mask raster using shapefile with rasterio",
        "Use geopandas overlay for spatial intersection",
        "Reproject raster data in Python",
        "Get Earth Engine dataset snippet for nighttime light",
    ]

    valid_buckets = {"code_guide", "tools_latest"}
    for query in queries:
        docs = db.vector_store.similarity_search(query, k=5)
        assert docs, f"No docs returned for query: {query}"
        assert any(doc.metadata.get("source_bucket") in valid_buckets for doc in docs)
