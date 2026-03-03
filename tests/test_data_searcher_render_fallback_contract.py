from pathlib import Path


def test_data_searcher_render_has_non_contract_fallback_before_schema_a_card():
    text = Path("app_ui.py").read_text(encoding="utf-8")
    assert "looks_like_geospatial_contract" in text
    assert "Data Searcher (" in text
    assert "View Raw JSON" in text
    assert "Geospatial Data Acquisition" in text
