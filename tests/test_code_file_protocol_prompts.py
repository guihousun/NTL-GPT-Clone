from agents.NTL_Code_Assistant import Code_Assistant_system_prompt_text
from agents.NTL_Engineer import system_prompt_text


def test_code_assistant_prompt_requires_file_based_execution_tools():
    prompt = Code_Assistant_system_prompt_text.content
    assert "execute_geospatial_script_tool" in prompt
    assert "method owner" in prompt
    assert "Engineer-first trust rule (mandatory)" in prompt
    assert "Do NOT call `GeoCode_Knowledge_Recipes_tool` before the first file-based execution attempt." in prompt
    assert "At most ONE recipe retrieval per task branch" in prompt
    assert "Maximum 1 retry" in prompt
    assert "read-before-execute" in prompt
    assert "first failure -> validation chain" in prompt
    assert "max one light fix retry" in prompt
    assert "overwrite=true" in prompt
    assert "do not create redundant v2/v3 names by default" in prompt
    assert "One-shot Light Fix Scope (Mandatory)" in prompt
    assert "Allowed light-fix categories" in prompt
    assert "Disallowed for light-fix" in prompt
    assert "CRS/projection/geometry topology mismatches" in prompt
    assert "GEE auth/quota/project initialization failures" in prompt
    assert "Convergence rule (mandatory)" in prompt
    assert "Do NOT call any transfer/handoff tool toward engineer/supervisor" in prompt
    assert "transfer_to_ntl_engineer" in prompt
    assert "handoff_to_supervisor" in prompt


def test_code_assistant_prompt_is_proposal_only_for_workflow_evolution():
    prompt = Code_Assistant_system_prompt_text.content
    assert "you may directly edit" not in prompt.lower()
    assert "MUST NOT directly edit workflow or evolution log files" in prompt
    assert "ntl.workflow.evolution.proposal.v1" in prompt
    assert "target_task_id" in prompt
    assert "artifact_audit_pass" in prompt


def test_code_assistant_prompt_prefers_geoboundaries_for_global_gee_boundaries():
    prompt = Code_Assistant_system_prompt_text.content
    assert "WM/geoLab/geoBoundaries/600/ADM0-ADM4" in prompt
    assert "Do NOT introduce legacy GAUL dataset paths" in prompt


def test_engineer_prompt_requires_script_metadata_review():
    prompt = system_prompt_text.content
    assert "draft_script_name" in prompt
    assert "file-first execution protocol" in prompt
    assert "initial script design" in prompt
    assert "execution_objective" in prompt
    assert "save before handoff" in prompt
    assert "exact saved filename" in prompt
