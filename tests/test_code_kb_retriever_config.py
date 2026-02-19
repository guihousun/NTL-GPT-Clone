from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base.py"


def test_code_retriever_uses_updated_k_and_threshold():
    code = TARGET.read_text(encoding="utf-8")
    assert 'tool_name="NTL_Code_Knowledge"' in code
    assert "k=8" in code
    assert "score_threshold=0.22" in code
    assert 'search_type="similarity_score_threshold"' in code
