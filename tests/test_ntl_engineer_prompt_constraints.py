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
    assert "daily <=14 images" in content
    assert "annual <=12 images" in content
    assert "monthly <=12 images" in content
    assert "do NOT rewrite to a multi-year composite" in content
    assert "partial files for a requested annual/monthly range" in content
    assert "do NOT switch to Code_Assistant" in content
    assert "Coverage_check.expected_count > Coverage_check.actual_count" in content
    assert "missing_items" in content


def test_ntl_engineer_prompt_requires_conditional_router_usage():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "GEE_dataset_router_tool" in content
    assert "router is not required" in content


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
    assert "Handoff packet guard (mandatory)" in content
    assert "draft_script_name" in content
    assert "draft_code" in content
    assert "required_inputs" in content
    assert "expected_outputs" in content
    assert "execution_objective" in content
    assert "saved_script_name" in content
    assert "saved_script_path" in content
    assert "save before handoff" in content
    assert "read_workspace_file_tool" in content
    assert "DO NOT call `transfer_to_code_assistant`" in content
    assert "Do not output filler text like \"I am waiting for Code_Assistant\"" in content


def test_ntl_engineer_prompt_enforces_vnp46a2_first_night_overpass_rule():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "first night after event" in content
    assert "epicenter local overpass timing" in content
    assert "first-night must be D+1 (not D)" in content


def test_ntl_engineer_prompt_boundary_recheck_only_mandatory_for_execution_path():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "BOUNDARY RECHECK (EXECUTION-PATH MANDATORY)" in content
    assert "Before execution/analysis handoff to Code_Assistant" in content
    assert "Download-only bypass" in content
    assert "boundary `confirmed` is NOT required to finish." in content


def test_ntl_engineer_prompt_enforces_task_level_routing_and_contract_version():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "TASK LEVEL ROUTING (MANDATORY" in content
    assert "L1 (download_only)" in content
    assert "L2 (analysis_with_tool)" in content
    assert "L3 (custom_or_algorithm_gap)" in content


def test_ntl_engineer_prompt_declares_single_workflow_write_authority():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )
    assert "single authority for workflow mutation" in content
    assert "Code_Assistant" in content
    assert "proposal payload (`schema: ntl.workflow.evolution.proposal.v1`)" in content
    assert "Formal write targets (Engineer only)" in content
    assert "`task_level`" in content
    assert "task_level_reason_codes" in content
    assert "intent.proposed_task_level" in content
    assert "TASK_LEVEL_CONFIRMATION: level=<L1|L2|L3>; reasons=[...]" in content
    assert "contract_version: ntl.retrieval.contract.v1" in content
    assert "schema: ntl.retrieval.contract.v1" in content
