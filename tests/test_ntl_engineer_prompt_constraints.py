from pathlib import Path


def test_ntl_engineer_prompt_enforces_workflow_mode_for_kb():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert 'response_mode="workflow"' in content
    assert "need_citations=True" in content


def test_ntl_engineer_prompt_prefers_direct_download_for_small_annual_monthly_requests():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "annual <=12 images" in content
    assert "monthly <=24 images" in content
    assert "do NOT rewrite to a multi-year composite" in content
    assert "partial files for a requested annual/monthly range" in content
    assert "do NOT switch to Code_Assistant" in content
    assert "Coverage_check.expected_count > Coverage_check.actual_count" in content
    assert "missing_items" in content


def test_ntl_engineer_prompt_keeps_data_searcher_data_only_scope():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "Data_Searcher returns data and metadata only" in content
    assert "regression/model selection is done by Code_Assistant" in content
    assert "required input files are missing/unreadable" in content
    assert "re-dispatch Data_Searcher" in content


def test_ntl_engineer_prompt_enforces_engineer_design_code_assistant_execution_split():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "You (NTL_Engineer) are responsible for initial script design" in content
    assert "Code_Assistant is responsible for validation/execution" in content
    assert "revised script draft" in content


def test_ntl_engineer_prompt_enforces_vnp46a2_first_night_overpass_rule():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "first night after event" in content
    assert "epicenter local overpass timing" in content
    assert "first-night must be D+1 (not D)" in content
