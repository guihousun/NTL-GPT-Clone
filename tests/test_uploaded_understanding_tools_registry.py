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


def test_engineer_tools_include_uploaded_understanding_tools():
    init_py = Path(__file__).resolve().parent.parent / "tools" / "__init__.py"
    engineer_tools = _extract_list_symbol_names(init_py, "Engineer_tools")
    assert "uploaded_pdf_understanding_tool" in engineer_tools
    assert "uploaded_image_understanding_tool" in engineer_tools
    assert "uploaded_file_understanding_tool" in engineer_tools
