from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ntl_toolkit.core import gee_download


ROOT = Path(__file__).resolve().parents[1]


class _FakeEe:
    def __init__(self) -> None:
        self.projects: list[str] = []

    def Initialize(self, *, project: str) -> None:  # noqa: N802 - Earth Engine API shape
        self.projects.append(project)


def test_core_initializer_requires_explicit_project(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeEe()
    monkeypatch.setitem(__import__("sys").modules, "ee", fake)

    with pytest.raises(RuntimeError, match="GEE_PROJECT_NOT_CONFIGURED"):
        gee_download._initialize_ee(None)

    assert gee_download._initialize_ee("runtime-project") is fake
    assert fake.projects == ["runtime-project"]


@pytest.mark.parametrize(
    "relative_path",
    [
        "packages/ntl_toolkit/src/ntl_toolkit/core/gee_download.py",
        "packages/ntl_toolkit/src/ntl_toolkit/core/gee_batch.py",
        "tools/GEE_generic_download.py",
        "tools/GEE_batch_export.py",
    ],
)
def test_download_and_batch_surfaces_have_no_interactive_or_projectless_init(relative_path: str) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "ee.Authenticate(" not in source
    assert "empyrean-caster-430308-m2" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "Initialize":
            continue
        assert any(keyword.arg == "project" for keyword in node.keywords), relative_path


def test_model_facing_generic_download_and_batch_schemas_do_not_expose_project() -> None:
    from tools.GEE_batch_export import GEEBatchExportInput, GEEExportStatusInput
    from tools.GEE_generic_download import GEERasterDownloadInput

    assert "project" not in GEERasterDownloadInput.model_json_schema()["properties"]
    assert "project" not in GEEBatchExportInput.model_json_schema()["properties"]
    assert "project" not in GEEExportStatusInput.model_json_schema()["properties"]
