from __future__ import annotations

import json

from tools.geocode_knowledge_tool import GEOCODE_RECIPES, retrieve_geocode_knowledge


def test_formal_recipe_output_is_snapshot_bound_and_uses_unified_runtime() -> None:
    payload = json.loads(
        retrieve_geocode_knowledge(
            "GEE daily and annual nighttime light statistics",
            top_k=6,
            include_runtime=True,
        )
    )

    assert payload["include_runtime"] is False
    assert payload["recipe_pool"]["runtime_curated_count"] == 0
    assert payload["recipe_pool"]["selected_runtime_count"] == 0
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "full_code_path" not in encoded
    assert "empyrean-caster-430308-m2" not in encoded
    for recipe in payload["matched_recipes"]:
        if "gee" in recipe.get("tags", []):
            assert "initialize_ee(ee_module=ee)" in recipe["code"]


def test_static_recipe_registry_contains_no_real_project_id() -> None:
    encoded = json.dumps(GEOCODE_RECIPES, ensure_ascii=False)
    assert "empyrean-caster-430308-m2" not in encoded
