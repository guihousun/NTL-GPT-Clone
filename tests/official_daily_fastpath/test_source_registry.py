from experiments.official_daily_ntl_fastpath.source_registry import (
    get_default_sources,
    get_nrt_priority_sources,
    get_source_spec,
    parse_sources_arg,
)


def test_source_registry_contains_three_sources():
    sources = get_default_sources()
    assert sources == ["VJ146A2", "VJ146A1", "VJ102DNB"]
    for source in sources:
        spec = get_source_spec(source)
        assert spec.short_name == source
        assert spec.processing_mode in {"gridded_tile_clip", "feasibility_only"}
        assert isinstance(spec.variable_candidates, tuple)


def test_vj102dnb_is_feasibility_only_and_night_only():
    spec = get_source_spec("VJ102DNB")
    assert spec.processing_mode == "feasibility_only"
    assert spec.night_only is True


def test_nrt_priority_profile_contains_nrt_and_fallback_sources():
    sources = get_nrt_priority_sources()
    assert sources[0] == "VJ146A1_NRT"
    assert "VJ146A1" in sources
    assert "VJ102DNB_NRT" in sources
    assert parse_sources_arg("nrt_priority") == sources
