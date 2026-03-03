from pathlib import Path


def _read_engineer_prompt() -> str:
    return (Path(__file__).resolve().parent.parent / "agents" / "NTL_Engineer.py").read_text(
        encoding="utf-8"
    )


def test_ntl_engineer_prompt_keeps_kb_workflow_mode_requirements():
    content = _read_engineer_prompt()
    assert 'response_mode="workflow"' in content
    assert "need_citations=True" in content


def test_ntl_engineer_prompt_self_evolution_skill_is_not_python_module():
    content = _read_engineer_prompt()
    assert "/skills/workflow-self-evolution/" in content
    assert "NOT a Python module" in content
    assert "file I/O and tool calls" in content
    assert "INTEGRATION_EXAMPLE.md" in content
    assert "SELF-EVOLUTION (USER-CONFIRMED)" in content
    assert "ask user whether to run self-evolution updates" in content


def test_ntl_engineer_prompt_self_evolution_paths_are_explicit():
    content = _read_engineer_prompt()
    assert "metrics.json" in content
    assert "failure_log.jsonl" in content
    assert "learning_log.jsonl" in content
    assert "/skills/NTL-workflow-guidance/references/evolution_log.jsonl" in content


def test_ntl_engineer_prompt_prefers_direct_download_for_small_annual_monthly_requests():
    content = _read_engineer_prompt()
    assert "daily <=14 images" in content
    assert "annual <=12 images" in content
    assert "monthly <=12 images" in content
    assert "do NOT rewrite to a multi-year composite" in content
    assert "partial files for a requested annual/monthly range" in content
    assert "do NOT switch to Code_Assistant" in content
    assert "Coverage_check.expected_count > Coverage_check.actual_count" in content
    assert "missing_items" in content


def test_ntl_engineer_prompt_requires_conditional_router_usage():
    content = _read_engineer_prompt()
    assert "GEE_dataset_router_tool" in content
    assert "router is not required" in content


def test_ntl_engineer_prompt_keeps_data_searcher_and_code_assistant_role_split():
    content = _read_engineer_prompt()
    assert "Data_Searcher returns data and metadata only" in content
    assert "geoBoundaries (global admin boundaries)" in content
    assert "Regression/model selection is done by Code_Assistant" in content
    assert "required input files are missing/unreadable" in content
    assert "re-dispatch Data_Searcher" in content
    assert "You (NTL_Engineer) are responsible for initial script design" in content
    assert "Code_Assistant is responsible for validation/execution" in content


def test_ntl_engineer_prompt_enforces_vnp46a2_first_night_overpass_rule():
    content = _read_engineer_prompt()
    assert "first night after event" in content
    assert "epicenter local overpass timing" in content
    assert "first-night must be D+1 (not D)" in content


def test_ntl_engineer_prompt_enforces_task_level_routing_and_contract_version():
    content = _read_engineer_prompt()
    assert "TASK LEVEL ROUTING (MANDATORY" in content
    assert "L1 (download_only)" in content
    assert "L2 (analysis_with_tool)" in content
    assert "L3 (custom_or_algorithm_gap)" in content
    assert "`task_level`" in content
    assert "task_level_reason_codes" in content
    assert "intent.proposed_task_level" in content
    assert "TASK_LEVEL_CONFIRMATION: level=<L1|L2|L3>; reasons=[...]" in content
    assert "contract_version: ntl.retrieval.contract.v1" in content
    assert "schema: ntl.retrieval.contract.v1" in content


def test_ntl_engineer_prompt_declares_single_workflow_write_authority():
    content = _read_engineer_prompt()
    assert "single authority for workflow mutation" in content
    assert "proposal payload (`schema: ntl.workflow.evolution.proposal.v1`)" in content
    assert "Formal write targets (Engineer only)" in content
    assert "Section 3.2 defines evolution protocol; Section 6.1 defines write authority and formal mutation gate." in content


def test_ntl_engineer_prompt_covers_event_impact_variations():
    content = _read_engineer_prompt().lower()
    assert "earthquake" in content
    assert "flood" in content
    assert "wildfire" in content
    assert "conflict" in content
