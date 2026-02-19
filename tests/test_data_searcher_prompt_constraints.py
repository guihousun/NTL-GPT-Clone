from pathlib import Path


def test_data_searcher_prompt_enforces_single_call_full_range_download():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Single-call policy for lightweight ranges" in content
    assert "call `NTL_download_tool` ONCE" in content
    assert '"time_range_input": "2015 to 2020"' in content


def test_data_searcher_prompt_enforces_completion_gate_before_transfer():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Completion gate before transfer_back" in content
    assert "estimated_image_count" in content
    assert "Do NOT transfer back after partial years." in content
    assert "output_files" in content
    assert "source-of-truth for file coverage" in content
    assert "do NOT trigger extra per-year downloads" in content
    assert "Single handoff rule" in content
    assert "exactly ONCE" in content


def test_data_searcher_prompt_uses_tavily_and_bigquery_for_socioeconomic():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "`China_Official_GDP_tool`" in content
    assert "`tavily_search`" in content
    assert "`Google_BigQuery_Search`" in content


def test_data_searcher_prompt_enforces_scope_and_handoff_boundary():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "You are a data acquisition agent, NOT a modeling/analysis agent" in content
    assert "Do NOT select regression models" in content
    assert "use ONLY `transfer_back_to_ntl_engineer`" in content
    assert "Never call execution/analysis tools owned by other agents" in content


def test_data_searcher_prompt_enforces_gee_python_api_server_side_policy():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "GEE Python API" in content
    assert "enforce `gee_server_side` planning" in content
    assert "do NOT call `NTL_download_tool` for primary processing" in content


def test_data_searcher_prompt_enforces_vnp46a2_first_night_overpass_rule():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Event first-night timing rule for daily VNP46A2 (MANDATORY)" in content
    assert "VNP46A2 nightly overpass is typically around local 01:30." in content
    assert "first-night MUST be local day D+1, not D." in content
