"""Regression checks for the import-free, low-priority runtime tool catalog."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = REPO_ROOT / "RAG" / "runtime_tool_catalog" / "build_runtime_tool_catalog.py"


def _load_builder():
    specification = importlib.util.spec_from_file_location("runtime_tool_catalog_builder", BUILDER_PATH)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _all_strings(key)
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)


def test_catalog_is_deterministic_and_preserves_runtime_boundaries(tmp_path: Path) -> None:
    builder = _load_builder()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_paths = builder.write_catalog(REPO_ROOT, first_dir)
    second_paths = builder.write_catalog(REPO_ROOT, second_dir)

    assert first_paths["manifest"].read_bytes() == second_paths["manifest"].read_bytes()
    assert first_paths["cards"].read_bytes() == second_paths["cards"].read_bytes()
    manifest = json.loads(first_paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["catalog_format"] == "ntl-gpt.runtime-tool-catalog.v1"
    assert manifest["authority"]["activation"] == "not_enabled_by_this_build"
    assert manifest["counts"]["registered_exports"] == len(manifest["tools"])
    assert manifest["counts"]["tool_cards"] == manifest["counts"]["four_role_exposed_exports"]
    assert manifest["groups"]["single_agent_tools"]
    assert {"NTL_Engineer", "NTL_Data_Searcher", "NTL_Analyst", "NTL_Event_Tracker"} <= set(manifest["roles"])
    assert all(tool["source_file"].startswith("tools/") for tool in manifest["tools"])
    cards = [json.loads(line) for line in first_paths["cards"].read_text(encoding="utf-8").splitlines()]
    assert len(cards) == manifest["counts"]["tool_cards"]
    assert all(card["roles"] for card in cards)
    assert "wrap_tool_json_safe" not in {card["tool_export"] for card in cards}
    assert next(
        tool for tool in manifest["tools"] if tool["export_name"] == "wrap_tool_json_safe"
    )["runtime_exposure"] == "not_exposed_to_four_role_runtime"
    tool_by_export = {tool["export_name"]: tool for tool in manifest["tools"]}
    gif_fields = {
        field["name"]: field
        for field in tool_by_export["official_vj_dnb_gif_tool"]["input_schema"]["fields"]
    }
    assert gif_fields["output_root"] == {
        "name": "output_root",
        "annotation": "str",
        "required": False,
        "default": "official_vj_dnb_gif_runs",
        "description": "Output subfolder under workspace outputs/.",
    }

    rendered = json.dumps(manifest, ensure_ascii=False)
    assert "Code_RAG" not in rendered
    assert not re.search(r"\bBV1-\d{3}\b", rendered)
    assert "gold_answer" not in rendered.lower()
    assert not any(re.search(r"(?i)[a-z]:[\\/]", item) for item in _all_strings(manifest))
    assert not any(
        re.search(r"(?i)/(?:home|users|mnt|tmp|var|private|opt)/", item)
        for item in _all_strings(manifest)
    )
