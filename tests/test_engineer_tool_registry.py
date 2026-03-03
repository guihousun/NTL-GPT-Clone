import ast
from pathlib import Path


def _extract_list_symbol_names(file_path: Path, list_name: str) -> list[str]:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == list_name and isinstance(node.value, ast.List):
                    names: list[str] = []
                    for item in node.value.elts:
                        if isinstance(item, ast.Name):
                            names.append(item.id)
                    return names
    raise AssertionError(f"{list_name} not found in {file_path}")


def test_engineer_tools_include_geodata_quick_check_for_pre_handoff_validation():
    init_py = Path(__file__).resolve().parent.parent / "tools" / "__init__.py"
    engineer_tools = _extract_list_symbol_names(init_py, "Engineer_tools")
    assert "geodata_quick_check_tool" in engineer_tools


def test_engineer_and_code_tool_boundaries_remain_lean():
    init_py = Path(__file__).resolve().parent.parent / "tools" / "__init__.py"
    engineer_tools = _extract_list_symbol_names(init_py, "Engineer_tools")
    code_tools = _extract_list_symbol_names(init_py, "Code_tools")

    assert "geodata_inspector_tool" not in engineer_tools
    assert "geodata_inspector_tool" in code_tools


def test_tool_registry_includes_ntl_vlm_tools():
    init_py = Path(__file__).resolve().parent.parent / "tools" / "__init__.py"
    engineer_tools = _extract_list_symbol_names(init_py, "Engineer_tools")
    expected = {
        "ntl_vlm_fetch_event_registry_tool",
        "ntl_vlm_build_scene_manifest_tool",
        "ntl_vlm_generate_tasks_tool",
        "ntl_vlm_generate_jobs_tool",
        "ntl_vlm_qc_tool",
        "ntl_vlm_evaluate_tool",
    }
    assert expected.issubset(set(engineer_tools))
