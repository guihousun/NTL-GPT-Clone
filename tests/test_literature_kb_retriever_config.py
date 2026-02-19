from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base.py"


def test_literature_retriever_uses_precision_friendly_config():
    code = TARGET.read_text(encoding="utf-8")
    assert "NTL_Literature_Knowledge = _build_retriever_tool(" in code
    assert "k=3," in code
    assert "score_threshold=0.3," in code
