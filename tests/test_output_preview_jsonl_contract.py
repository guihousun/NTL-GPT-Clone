from pathlib import Path


def test_output_preview_supports_jsonl_and_ndjson():
    source = Path("app_ui.py").read_text(encoding="utf-8-sig")
    assert 'suffix in [".jsonl", ".ndjson"]' in source
    assert "JSONL preview" in source
