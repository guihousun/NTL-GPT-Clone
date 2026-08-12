from __future__ import annotations

import importlib
import json
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
from agents.NTL_Analyst import system_prompt_analyst
from agents.NTL_Event_Tracker import system_prompt_event_tracker
from agents.role_specs import ROLE_SKILL_SOURCES, ROLE_SPECS, get_role_spec
from tools import (
    Code_tools,
    Engineer_tools,
    analyst_tools,
    data_searcher_tools,
    engineer_tools,
    event_tracker_tools,
    single_agent_tools,
)
from tools import _EXPORTS, _GROUPS, _ROLE_GROUPS


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".ntl-gpt" / "skills"


def _names(group: str) -> set[str]:
    return set(_GROUPS[group])


def test_role_specs_are_exactly_the_four_contract_roles() -> None:
    assert set(ROLE_SPECS) == {
        "NTL_Engineer",
        "NTL_Data_Searcher",
        "NTL_Analyst",
        "NTL_Event_Tracker",
    }
    assert get_role_spec("analyst") is ROLE_SPECS["NTL_Analyst"]
    assert ROLE_SPECS["NTL_Engineer"].can_delegate is True
    assert all(not ROLE_SPECS[name].can_delegate for name in ROLE_SPECS if name != "NTL_Engineer")


def test_each_role_loads_common_then_only_its_role_namespace() -> None:
    expected = {
        "NTL_Engineer": ("/skills/common/", "/skills/engineer/"),
        "NTL_Data_Searcher": ("/skills/common/", "/skills/data_searcher/"),
        "NTL_Analyst": ("/skills/common/", "/skills/analyst/"),
        "NTL_Event_Tracker": ("/skills/common/", "/skills/event_tracker/"),
    }
    assert ROLE_SKILL_SOURCES == expected

    for sources in expected.values():
        for source in sources:
            relative = source.removeprefix("/skills/").strip("/")
            namespace = SKILLS_ROOT / relative
            assert namespace.is_dir(), source
            assert any((child / "SKILL.md").is_file() for child in namespace.iterdir() if child.is_dir()), source


def test_engineer_allowlist_is_narrow_fast_path_surface() -> None:
    names = _names("engineer_tools")
    assert {"geodata_inspector_tool", "geodata_quick_check_tool"} <= names
    assert {
        "execute_geospatial_script_tool",
        "GeoCode_COT_Validation_tool",
        "NTL_download_tool",
        "GEE_request_plan_tool",
        "NTL_Trend_Analysis",
        "DEI_estimate_city_tool",
        "conflict_city_event_ranking_tool",
    }.isdisjoint(names)
    assert Engineer_tools is engineer_tools


def test_data_searcher_owns_observations_not_analysis_or_events() -> None:
    names = _names("data_searcher_tools")
    assert {
        "GEE_request_plan_tool",
        "NTL_download_tool",
        "dataset_latest_availability_tool",
        "VNP46A2_angular_correction_tool",
    } <= names
    assert {
        "execute_geospatial_script_tool",
        "GeoCode_COT_Validation_tool",
        "NTL_Trend_Analysis",
        "DEI_estimate_city_tool",
        "VNP46A2_seasonal_adjustment_tool",
        "conflict_ntl_fetch_isw_events_tool",
        "conflict_city_event_ranking_tool",
    }.isdisjoint(names)


def test_analyst_owns_scientific_methods_not_acquisition() -> None:
    names = _names("analyst_tools")
    assert {
        "execute_geospatial_script_tool",
        "NTL_Trend_Analysis",
        "detect_ntl_anomaly_tool",
        "DEI_estimate_city_tool",
        "VNP46A2_seasonal_adjustment_tool",
        "VNP46A2_persistence_classification_tool",
        "dmsp_viirs_harmonization_tool",
        "electrified_detection_tool",
    } <= names
    assert {
        "GeoCode_COT_Validation_tool",
        "NTL_download_tool",
        "GEE_batch_export_tool",
        "dataset_latest_availability_tool",
        "conflict_ntl_fetch_isw_events_tool",
    }.isdisjoint(names)


def test_event_tracker_owns_sources_not_ntl_observations_or_analysis() -> None:
    names = _names("event_tracker_tools")
    assert {
        "conflict_ntl_fetch_isw_events_tool",
        "conflict_ntl_source_freshness_tool",
        "conflict_ntl_screen_events_tool",
        "conflict_city_event_ranking_tool",
    } <= names
    assert {
        "execute_geospatial_script_tool",
        "GeoCode_COT_Validation_tool",
        "NTL_download_tool",
        "VNP46A2_angular_correction_tool",
        "NTL_Trend_Analysis",
        "electrified_detection_tool",
    }.isdisjoint(names)


def test_matched_single_agent_is_the_strict_ordered_role_union() -> None:
    expected = list(
        dict.fromkeys(
            name
            for group_name in (
                "engineer_tools",
                "data_searcher_tools",
                "analyst_tools",
                "event_tracker_tools",
            )
            for name in _ROLE_GROUPS[group_name]
        )
    )
    assert _GROUPS["single_agent_tools"] == expected
    assert single_agent_tools.export_names == tuple(expected)
    assert len(expected) == len(set(expected))
    assert "execute_geospatial_script_tool" in expected
    assert "GeoCode_COT_Validation_tool" not in expected


def test_formal_four_role_surface_confines_custom_code_execution_to_analyst() -> None:
    formal = {name: set(tools) for name, tools in _ROLE_GROUPS.items()}
    execute_owners = {
        role for role, tools in formal.items() if "execute_geospatial_script_tool" in tools
    }
    assert execute_owners == {"analyst_tools"}
    assert all("GeoCode_COT_Validation_tool" not in tools for tools in formal.values())


def test_legacy_code_assistant_surface_is_preserved_but_separate() -> None:
    assert set(Code_tools.export_names) == {
        "GeoCode_Knowledge_Recipes_tool",
        "execute_geospatial_script_tool",
        "GeoCode_COT_Validation_tool",
    }
    assert "Code_Assistant" not in ROLE_SPECS


def test_migrated_benchmark_tool_exports_point_to_real_symbols() -> None:
    expected = {
        "VNP46A2_seasonal_adjustment_tool": ".NTL_seasonal_adjustment",
        "VNP46A2_persistence_classification_tool": ".VNP46A2_persistence",
        "dmsp_viirs_harmonization_tool": ".NTL_cross_sensor_harmonization",
        "electrified_detection_tool": ".electrified_detection",
        "conflict_city_event_ranking_tool": ".conflict_city_events",
        "VNP46A2_angular_correction_tool": ".VNP46A2_angular_correction",
    }
    for export_name, expected_module in expected.items():
        module_name, attr_name = _EXPORTS[export_name]
        assert module_name == expected_module
        module = importlib.import_module(module_name, "tools")
        tool = getattr(module, attr_name)
        assert tool is not None


def test_specialist_prompts_enforce_typed_return_and_no_direct_dispatch() -> None:
    analyst = str(system_prompt_analyst.content)
    tracker = str(system_prompt_event_tracker.content)
    assert "HandoffEnvelope" in analyst and '"NTL_Analyst"' in analyst
    assert "HandoffEnvelope" in tracker and '"NTL_Event_Tracker"' in tracker
    assert "never contact the user" in analyst
    assert "never contact the user" in tracker
    assert "directly dispatch" in analyst
    assert "directly dispatch" in tracker
    assert "observation_required=false" in analyst
    assert "checksum-bound" in analyst
    assert "/inputs/" in analyst
    assert '"schema"' in analyst
    assert "schema_version" in analyst
    assert "never overwrite, edit, or version-replace them" in analyst
    assert "workspace-relative" in tracker
    assert "without a leading slash" in tracker


def test_all_formal_tool_schemas_hide_system_managed_identity_fields() -> None:
    forbidden = {
        "run_id",
        "task_id",
        "case_id",
        "created_at_utc",
        "query_executed_at_utc",
        "thread_id",
    }
    groups = (engineer_tools, data_searcher_tools, analyst_tools, event_tracker_tools)
    for collection in groups:
        for candidate in collection:
            schema = convert_to_openai_tool(candidate)["function"]["parameters"]
            encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True)
            leaked = {field for field in forbidden if f'"{field}"' in encoded}
            assert not leaked, f"{candidate.name} exposes system identity fields: {sorted(leaked)}"
