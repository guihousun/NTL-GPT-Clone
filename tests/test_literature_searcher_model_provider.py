from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base_Searcher.py"


def test_searcher_uses_qwen35_plus_via_dashscope():
    code = TARGET.read_text(encoding="utf-8")
    assert 'model="qwen3.5-plus"' in code
    assert 'base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"' in code
    assert "DASHSCOPE_API_KEY" in code
    assert "init_chat_model(\"openai:gpt-4.1-mini\"" not in code
