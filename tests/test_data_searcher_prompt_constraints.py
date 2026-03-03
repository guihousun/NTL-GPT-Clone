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
    assert "Completion gate before final return" in content
    assert "estimated_image_count" in content
    assert "Do NOT return partial-year results." in content
    assert "output_files" in content
    assert "source-of-truth for file coverage" in content
    assert "do NOT trigger extra per-year downloads" in content
    assert "Single completion rule" in content
    assert "return one final structured JSON payload" in content


def test_data_searcher_prompt_uses_tavily_and_bigquery_for_socioeconomic():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "`China_Official_GDP_tool`" in content
    assert "`tavily_search`" in content
    assert "`Google_BigQuery_Search`" in content
    assert "Only pass `include_domains` to `tavily_search` when the user explicitly requires domain restriction." in content
    assert "pass a native list value (never a stringified list)." in content


def test_data_searcher_prompt_enforces_scope_and_handoff_boundary():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "You are a data acquisition agent, NOT a modeling/analysis agent" in content
    assert "Do NOT select regression models" in content
    assert "Do NOT call `transfer_back_to_ntl_engineer`" in content
    assert "transfer_to_ntl_engineer" in content
    assert "handoff_to_supervisor" in content
    assert "supervisor control resumes automatically" in content
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


def test_data_searcher_prompt_uses_conditional_boundary_strategy_for_lightweight_downloads():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Boundary Strategy (Conditional, not global-precheck)" in content
    assert "default to `NTL_download_tool` first and do NOT force pre-boundary retrieval." in content
    assert "failure/ambiguity gated" in content
    assert "daily <=14 or annual <=12 or monthly <=12" in content
    assert "validation_status` to `not_required`" in content


def test_data_searcher_prompt_uses_conditional_router_policy():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Conditional router rule" in content
    assert "router is not required" in content


def test_data_searcher_prompt_short_circuits_after_successful_direct_download():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Direct-download short-circuit (mandatory)" in content
    assert "you MAY skip `geodata_quick_check_tool`" in content
    assert "do NOT call `GEE_dataset_metadata_tool` or `GEE_catalog_discovery_tool`" in content
    assert "metadata_validation` to `not_required_local_analysis`" in content


def test_data_searcher_prompt_allows_compact_execution_plan_for_local_direct_download():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "Compact direct-download allowance" in content
    assert "may be compact" in content
    assert "Minimum required fields in compact mode" in content


def test_data_searcher_prompt_requires_retrieval_contract_v1_envelope():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Data_Searcher.py").read_text(
        encoding="utf-8"
    )
    assert "schema\": \"ntl.retrieval.contract.v1" in content
    assert "\"status\": \"complete|partial|failed\"" in content
    assert "\"task_level\": \"L1|L2|L3\"" in content
    assert "Contract consistency checks before final return" in content
    assert "If `status = complete`" in content
