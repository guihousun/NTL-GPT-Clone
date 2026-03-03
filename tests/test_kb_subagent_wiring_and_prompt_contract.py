from pathlib import Path

from agents.NTL_Knowledge_Subagent import system_prompt_kb_searcher


def test_graph_factory_registers_kb_searcher_subagent():
    content = (Path(__file__).resolve().parent.parent / "graph_factory.py").read_text(
        encoding="utf-8"
    )
    assert "knowledge_base_subagent" in content
    assert '"name": "Knowledge_Base_Searcher"' in content
    assert '"tools": [NTL_Literature_Knowledge, NTL_Solution_Knowledge, NTL_Code_Knowledge]' in content
    assert "subagents=[data_searcher_subagent, code_assistant_subagent, knowledge_base_subagent]" in content


def test_kb_subagent_prompt_enforces_json_contract_and_generalized_variants():
    content = (Path(__file__).resolve().parent.parent / "agents" / "NTL_Knowledge_Subagent.py").read_text(
        encoding="utf-8"
    )
    assert "Return only JSON. No markdown. No code fences." in content
    assert '"schema": "ntl.kb.subagent.response.v1"' in content
    assert '"intent_analysis"' in content
    assert '"response"' in content
    assert '"steps"' in content
    assert "earthquake" in content
    assert "wildfire" in content
    assert "flood" in content


def test_kb_subagent_prompt_renders_available_tools_section():
    content = str(getattr(system_prompt_kb_searcher, "content", ""))
    assert "### Available Tools" in content
    assert "NTL_Solution_Knowledge" in content
    assert "NTL_Literature_Knowledge" in content
    assert "NTL_Code_Knowledge" in content


def test_kb_subagent_prompt_contains_tri_store_retrieval_and_normalization_rules():
    content = str(getattr(system_prompt_kb_searcher, "content", ""))
    assert "Retrieval Strategy (mandatory)" in content
    assert "Start with `NTL_Solution_Knowledge`" in content
    assert "Default budget: 1-2 tools; escalate to all 3" in content
    assert "Workflow/JSON Normalization Rules" in content
