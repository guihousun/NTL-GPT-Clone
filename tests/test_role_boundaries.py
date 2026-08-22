from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
from agents.NTL_Analyst import system_prompt_analyst
from agents.NTL_Data_Searcher import hierarchical_system_prompt_data_searcher
from agents.NTL_Event_Tracker import system_prompt_event_tracker
from agents.role_specs import ROLE_SKILL_SOURCES, ROLE_SPECS, get_role_spec
from graph_factory import NTL_TASK_DESCRIPTION, _full_system_prompt, _single_agent_prompt
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


def test_each_role_loads_common_role_namespace_and_declared_shared_procedures() -> None:
    expected = {
        "NTL_Engineer": (
            "/skills/common/",
            "/skills/engineer/",
            "/skills/gee-ntl-date-boundary-handling/",
        ),
        "NTL_Data_Searcher": (
            "/skills/common/",
            "/skills/data_searcher/",
            "/skills/gee-ntl-date-boundary-handling/",
        ),
        "NTL_Analyst": ("/skills/common/", "/skills/analyst/"),
        "NTL_Event_Tracker": ("/skills/common/", "/skills/event_tracker/"),
    }
    assert ROLE_SKILL_SOURCES == expected

    for sources in expected.values():
        for source in sources:
            relative = source.removeprefix("/skills/").strip("/")
            namespace = SKILLS_ROOT / relative
            assert namespace.is_dir(), source
            assert (namespace / "SKILL.md").is_file() or any(
                (child / "SKILL.md").is_file() for child in namespace.iterdir() if child.is_dir()
            ), source


def test_active_skill_names_match_their_directories() -> None:
    """Keep active role skills compatible with Deep Agents' skill loader."""
    active_sources = {
        source
        for sources in ROLE_SKILL_SOURCES.values()
        for source in sources
    }
    for source in sorted(active_sources):
        relative = source.removeprefix("/skills/").strip("/")
        source_root = SKILLS_ROOT / relative
        files = [source_root / "SKILL.md"] if (source_root / "SKILL.md").is_file() else sorted(source_root.glob("*/SKILL.md"))
        for path in files:
            head = path.read_text(encoding="utf-8").split("---", 2)[1]
            match = re.search(r"^name:\s*([^\s]+)\s*$", head, flags=re.MULTILINE)
            assert match, f"missing name frontmatter: {path}"
            assert match.group(1) == path.parent.name


def test_disaster_event_observation_workflow_is_active_and_bounded() -> None:
    """The shared disaster route must be discoverable by every active role."""
    skill = (
        SKILLS_ROOT / "common" / "disaster-event-observation-workflow" / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")

    assert "Event Tracker -> Data Searcher -> Analyst" in text
    assert "summary_only" in text
    assert "typed_package" in text
    assert "never merge their dates" in text
    assert "never encode a" in text
    assert "frozen snapshot" in text
    assert "Do not infer causality" in text
    assert "Do not invent an event" in text
    assert "only to obtain a checksum" in text
    assert all("/skills/common/" in sources for sources in ROLE_SKILL_SOURCES.values())
    for prompt in (_full_system_prompt(), _single_agent_prompt()):
        assert "/skills/common/disaster-event-observation-workflow/SKILL.md" in prompt


def test_source_backed_utc_time_route_is_active_for_engineer_and_data_searcher() -> None:
    shared_source = "/skills/gee-ntl-date-boundary-handling/"
    assert shared_source in ROLE_SKILL_SOURCES["NTL_Engineer"]
    assert shared_source in ROLE_SKILL_SOURCES["NTL_Data_Searcher"]

    skill = SKILLS_ROOT / "gee-ntl-date-boundary-handling" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    data_prompt = str(hierarchical_system_prompt_data_searcher.content)

    assert "Source-backed UTC_Time Route" in text
    assert "metadata establishes granule availability" in text
    assert "not a pixel-level observation time" in text
    assert "VNP46A1 `UTC_Time` may validate timing while VNP46A2 remains the radiance" in text
    assert "2025-03-28T06:20:52Z" in text
    assert shared_source.rstrip("/") in data_prompt


def test_active_prompts_and_skills_exclude_retired_startup_memory_policies() -> None:
    active_texts = [
        _full_system_prompt(),
        _single_agent_prompt(),
        str(hierarchical_system_prompt_data_searcher.content),
        str(system_prompt_analyst.content),
        str(system_prompt_event_tracker.content),
        NTL_TASK_DESCRIPTION,
    ]
    active_sources = {
        source
        for sources in ROLE_SKILL_SOURCES.values()
        for source in sources
    }
    for source in sorted(active_sources):
        relative = source.removeprefix("/skills/").strip("/")
        active_texts.extend(
            path.read_text(encoding="utf-8")
            for path in sorted((SKILLS_ROOT / relative).glob("*/SKILL.md"))
        )

    combined = "\n".join(active_texts)
    retired_markers = {
        "Always query router FIRST",
        "Workflow Router Protocol",
        "Router Priority",
        "Self-Evolution Policy",
        "NTL_AGENT_MEMORY.md",
        "Knowledge_Base_Searcher",
        "Code_Assistant",
    }
    leaked = sorted(marker for marker in retired_markers if marker in combined)
    assert not leaked, f"retired startup-memory policies leaked into active surfaces: {leaked}"


def test_active_contract_guidance_stops_duplicate_package_probes_and_uses_relative_script_paths() -> None:
    full_prompt = _full_system_prompt()
    single_prompt = _single_agent_prompt()
    analyst_prompt = str(system_prompt_analyst.content)
    planning_skill = (
        SKILLS_ROOT / "engineer" / "task-planning-and-routing" / "SKILL.md"
    ).read_text(encoding="utf-8")
    execution_skill = (
        SKILLS_ROOT / "analyst" / "code-execution-validation" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "do not save another TaskPlan" in full_prompt
    assert "do not save the same package again" in single_prompt
    assert "skeleton or single-field packages" in analyst_prompt
    assert "Do not save the same plan again" in planning_skill
    assert '"path": "inputs/input.ext"' in execution_skill
    assert '"path": "outputs/result.ext"' in execution_skill
    assert '"path": "/inputs/input.ext"' not in execution_skill
    assert '"path": "/outputs/result.ext"' not in execution_skill


def test_data_searcher_prompt_names_registered_location_tools() -> None:
    prompt = str(hierarchical_system_prompt_data_searcher.content)
    assert "get_administrative_division_data" in prompt
    assert "poi_search_tool" in prompt
    assert "geocode_tool" in prompt
    assert "do not claim that Amap is" in prompt
    assert "no input file is staged" in prompt
    assert "inputs/<filename>" in prompt
    assert "NTL_composite_local_tool" in prompt
    assert "NTL_daily_antl_statistics" in prompt
    assert "multiple dates do not imply that a composite" in prompt
    assert "VNP46A2_angular_correction_tool" in prompt
    assert "Do not run\n   catalog discovery" in prompt


def test_engineer_prompt_distinguishes_daily_retrieval_and_angle_correction_routes() -> None:
    prompt = _full_system_prompt()
    assert "A request for separate daily layers is not a composite request" in prompt
    assert "do not substitute the uncorrected daily-ANTL executor" in prompt
    assert "persistent Earth Engine asset only when the user explicitly asks" in prompt


def test_engineer_and_single_prompts_route_location_requests_to_registered_tools() -> None:
    full_prompt = _full_system_prompt()
    single_prompt = _single_agent_prompt()
    for prompt in (full_prompt, single_prompt):
        assert "get_administrative_division_data" in prompt
        assert "poi_search_tool" in prompt
        assert "geocode_tool" in prompt


def test_engineer_prompt_does_not_block_live_acquisition_on_empty_inputs() -> None:
    prompt = _full_system_prompt()
    assert "empty `/inputs/` directory is expected" in prompt
    assert "route the request to NTL_Data_Searcher" in prompt


def test_latest_availability_prompt_distinguishes_gee_and_nasa_channels() -> None:
    prompts = (_full_system_prompt(), str(hierarchical_system_prompt_data_searcher.content))
    for prompt in prompts:
        assert "gee_catalog" in prompt
        assert "nasa_earthdata_cmr_laads" in prompt
        assert "never merge" in prompt.lower()
        assert "query_executed_at_utc" in prompt


def test_engineer_allowlist_includes_bounded_routine_execution() -> None:
    names = _names("engineer_tools")
    assert {
        "geodata_inspector_tool",
        "geodata_quick_check_tool",
        "execute_geospatial_script_tool",
    } <= names
    assert {
        "GeoCode_Knowledge_Recipes_tool",
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
        "SDGSAT1_index_tool",
        "SDGSAT1_jia_light_classification_tool",
        "electrified_detection_tool",
    } <= names
    assert {
        "GeoCode_COT_Validation_tool",
        "NTL_download_tool",
        "GEE_batch_export_tool",
        "dataset_latest_availability_tool",
        "conflict_ntl_fetch_isw_events_tool",
    }.isdisjoint(names)


def test_analyst_prompt_prefers_named_svm_workflow_over_generic_code() -> None:
    prompt = str(system_prompt_analyst.content)
    assert "Detect_Urban_Area_by_SVM" in prompt
    assert "environment probe" in prompt
    assert "before writing code" in prompt
    assert "explicitly names a callable registered tool" in prompt
    assert "requested decision rule" in prompt
    assert "SDGSAT1_jia_light_classification" in prompt
    assert "RLED if RRLI>9" in prompt


def test_full_prompt_routes_staged_named_methods_directly_to_analyst() -> None:
    prompt = _full_system_prompt()
    assert "treat those inputs as analysis-ready" in prompt
    assert "Do not add a Data Searcher leg merely to re-inspect" in prompt
    assert "Direct Analyst capability index for staged inputs" in prompt
    assert "They are not Data Searcher jobs" in prompt
    assert "explicitly requested model-selection criterion" in prompt
    assert "stripe-noise removal request is standard preprocessing" in prompt
    assert "SDGSAT-1_strip_removal_tool" in prompt
    assert "SDGSAT1_jia_light_classification" in prompt
    assert "RLED if RRLI>9" in prompt
    data_prompt = str(hierarchical_system_prompt_data_searcher.content)
    assert "SDGSAT-1_strip_removal_tool" in data_prompt
    assert "Do not replace it with a generic script" in data_prompt


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


def test_formal_four_role_surface_shares_bounded_code_execution_only() -> None:
    formal = {name: set(tools) for name, tools in _ROLE_GROUPS.items()}
    execute_owners = {
        role for role, tools in formal.items() if "execute_geospatial_script_tool" in tools
    }
    assert execute_owners == {"engineer_tools", "analyst_tools"}
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


def test_specialist_prompts_save_typed_package_and_return_native_result() -> None:
    analyst = str(system_prompt_analyst.content)
    tracker = str(system_prompt_event_tracker.content)
    data_searcher = str(hierarchical_system_prompt_data_searcher.content)
    tracker_flat = " ".join(tracker.split())
    assert "normal task result" in analyst
    assert "normal task result" in tracker
    assert "exact opaque package handle" in analyst
    assert "exact opaque package handle" in tracker
    assert "typed_package" in analyst
    assert "summary_only" in analyst
    assert "typed_package" in tracker
    assert "summary_only" in tracker
    assert "typed_package" in data_searcher
    assert "summary_only" in data_searcher
    assert "do not require an AssignmentEnvelope" in analyst
    assert "do not require an AssignmentEnvelope" in tracker
    assert "ntl.assignment.v1" not in analyst
    assert "ntl.assignment.v1" not in tracker
    assert "ntl.handoff.v1" not in analyst
    assert "ntl.handoff.v1" not in tracker
    assert "never contact the user" in analyst
    assert "never contact the user" in tracker
    assert "directly dispatch" in analyst
    assert "directly dispatch" in tracker
    assert "observation_required=false" in analyst
    assert "checksum-bound" in analyst
    assert "/inputs/" in analyst
    assert '"schema"' in analyst
    assert "never overwrite, edit, or version-replace them" in analyst
    assert "workspace-relative" in tracker
    assert "without a leading slash" in tracker
    assert "Local `sha256` and `bytes` are system-owned" in tracker_flat
    assert "Never compute, guess, copy, or null-fill" in tracker_flat
    assert "one normal native task invocation" in tracker_flat
    assert "without persisting a package and therefore without a package handle" in tracker_flat
    assert "checksum-only follow-up delegation" in tracker_flat


def test_model_facing_skills_delegate_local_artifact_identity_to_typed_save() -> None:
    common_workspace = (
        SKILLS_ROOT / "common" / "workspace-and-artifact-contract" / "SKILL.md"
    ).read_text(encoding="utf-8")
    common_provenance = (
        SKILLS_ROOT / "common" / "provenance-and-evidence-boundary" / "SKILL.md"
    ).read_text(encoding="utf-8")
    event_skills = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((SKILLS_ROOT / "event_tracker").glob("*/SKILL.md"))
    )

    assert "workspace-relative path, its semantic `role`, and `media_type`" in common_workspace
    assert "injects its actual SHA-256 and byte count" in common_workspace
    assert "Never calculate, guess, copy, null-fill, or placeholder-fill" in common_workspace
    assert "no checksum utility is available" in common_workspace
    assert "model declares only its workspace-relative path, semantic role" in common_provenance
    assert "system-owned fields" in common_provenance
    assert "checksum tooling is not missing scientific evidence" in common_provenance
    assert "same native task" in event_skills
    assert "must not trigger a checksum-only retry" in event_skills


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
