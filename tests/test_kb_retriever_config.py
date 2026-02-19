from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base.py"


def test_retriever_uses_score_threshold_and_explicit_embedding_model():
    code = TARGET.read_text(encoding="utf-8")
    assert 'search_type="similarity_score_threshold"' in code
    assert '"score_threshold": score_threshold' in code
    assert '"k": k' in code
    assert 'OpenAIEmbeddings(model="text-embedding-3-small")' in code
    assert "as_retriever(k=" not in code

