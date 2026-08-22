"""Provider-free regression checks for stable registered-tool parameter policy."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def test_default_first_policy_is_present_in_both_specialist_prompts() -> None:
    analyst = _normalized(_read("agents/NTL_Analyst.py"))
    data_searcher = _normalized(_read("agents/NTL_Data_Searcher.py"))

    for text in (analyst, data_searcher):
        assert "default-first policy" in text
        assert "only its required inputs" in text or "only required inputs" in text
        assert "stable defaults apply" in text
        assert "do not guess, restate, or tune every default parameter" in text
        assert "resolved_parameters" in text
        assert "authoritative" in text

    # Data Searcher has both matched Single-Agent and four-role prompt templates.
    assert data_searcher.count("stable registered-tool default-first policy") == 2


def test_default_first_policy_preserves_explicit_contract_override_boundary() -> None:
    sources = (
        "agents/NTL_Analyst.py",
        "agents/NTL_Data_Searcher.py",
        ".ntl-gpt/skills/analyst/ntl-statistics-and-time-series/SKILL.md",
        ".ntl-gpt/skills/data_searcher/dataset-and-product-selection/SKILL.md",
    )

    for source in sources:
        text = _normalized(_read(source))
        assert "override" in text
        assert "explicit" in text
        assert "schema-required scientific input" in text
        assert "expected result" in text
        assert "resolved_parameters" in text
        assert "omitted default" in text


def test_standard_zonal_statistics_use_the_registered_method_before_custom_code() -> None:
    analyst = _normalized(_read("agents/NTL_Analyst.py"))
    skill = _normalized(_read(".ntl-gpt/skills/analyst/ntl-statistics-and-time-series/SKILL.md"))
    graph = _normalized(_read("graph_factory.py"))

    for text in (analyst, skill):
        assert "ntl_raster_statistics" in text
        assert "standard zonal nighttime-light metric" in text
        assert "ad hoc reprojection" in text

    # Full delegates to Analyst; matched Single-Agent invokes the same method.
    assert graph.count("standard zonal nighttime-light metric supported by `ntl_raster_statistics`") == 2
