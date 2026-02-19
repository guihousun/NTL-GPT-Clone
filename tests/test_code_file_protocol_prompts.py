from agents.NTL_Code_Assistant import Code_Assistant_system_prompt_text
from agents.NTL_Engineer import system_prompt_text


def test_code_assistant_prompt_requires_file_based_execution_tools():
    prompt = Code_Assistant_system_prompt_text.content
    assert "save_geospatial_script_tool" in prompt
    assert "execute_geospatial_script_tool" in prompt
    assert "method owner" in prompt
    assert "Engineer-first trust rule (mandatory)" in prompt
    assert "Do NOT call `GeoCode_Knowledge_Recipes_tool` before the first file-based execution attempt." in prompt
    assert "At most ONE recipe retrieval per task branch" in prompt
    assert "Maximum 1 retry" in prompt
    assert "Convergence rule (mandatory)" in prompt
    assert "transfer_back_to_ntl_engineer" in prompt


def test_engineer_prompt_requires_script_metadata_review():
    prompt = system_prompt_text.content
    assert "script_name" in prompt
    assert "script_path" in prompt
    assert "file-first execution protocol" in prompt
    assert "initial script design" in prompt
    assert "revised script draft" in prompt
