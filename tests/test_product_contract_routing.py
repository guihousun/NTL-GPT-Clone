from __future__ import annotations

import json
from pathlib import Path

from agents.NTL_Data_Searcher import (
    hierarchical_system_prompt_data_searcher,
    system_prompt_data_searcher,
)
from tools import GEE_specialist_toolkit as toolkit
from tools import data_searcher_tools


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SELECTION_SKILL = (
    ROOT / ".ntl-gpt" / "skills" / "data_searcher" / "dataset-and-product-selection" / "SKILL.md"
)


def test_data_searcher_product_contract_is_explicit_and_segment_aware() -> None:
    """Prompt/Skill policy protects arbitrary requested product segments."""
    texts = (
        PRODUCT_SELECTION_SKILL.read_text(encoding="utf-8"),
        str(system_prompt_data_searcher.content),
        str(hierarchical_system_prompt_data_searcher.content),
    )

    for text in texts:
        assert "product-segment ledger" in text
        assert "avg_vis" in text
        assert "stable_lights" in text
        assert "PRODUCT_CONTRACT_CONFLICT" in text
        assert "substitute collection, band, sensor, or year range" in text


def test_explicit_dmsp_band_survives_provider_free_planning(
    monkeypatch,
) -> None:
    """A caller's band is preserved; a nearby DMSP semantic is not substituted."""

    def no_live_provider(*_args, **_kwargs):
        raise AssertionError("validate_live=False must not contact a metadata provider")

    monkeypatch.setattr(toolkit, "gee_dataset_metadata", no_live_provider)
    payload = json.loads(
        toolkit.gee_request_plan(
            query="Retrieve annual DMSP observations for a requested administrative area.",
            dataset_id="NOAA/DMSP-OLS/NIGHTTIME_LIGHTS",
            dataset_name="DMSP-OLS",
            bands=["avg_vis"],
            start_date="2005",
            end_date="2010",
            temporal_resolution="annual",
            validate_live=False,
        )
    )

    selected = payload["dataset"]["selected"]
    assert selected["dataset_id"] == "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS"
    assert selected["bands"] == ["avg_vis"]
    assert selected["default_bands"] == ["avg_vis"]
    assert "stable_lights" not in selected["bands"]


def test_data_searcher_has_a_schema_preserving_exact_band_route() -> None:
    """The generic direct-download route can carry an exact selected band."""
    tools_by_name = {tool.name: tool for tool in data_searcher_tools}
    schema = tools_by_name["GEE_raster_download_tool"].args_schema.model_json_schema()

    assert {"dataset_id", "bands", "bbox", "out_name"} <= set(schema["properties"])
    assert "bands" in schema["required"]
