"""Deterministic integrity checks for the hierarchical engineering smoke assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmark_runtime.contracts import (
    validate_case_record,
    validate_eval_spec_record,
)


ROOT = Path(__file__).resolve().parent
EXPECTED_EVENT_SNAPSHOT_HASHES = {
    "fixtures/event_sources/usgs_official_domain_search.json":
        "e70612add1a878b8b7cf0e2975aef309f023465849defa83b73ba8e16f843dcb",
    "fixtures/event_sources/reliefweb_official_domain_search.json":
        "7c087f14aedae780740f9c0faaee57aab12154296e5e987e7c2753d0ae830980",
}


def _jsonl(name: str) -> list[dict[str, object]]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_by_case_id(name: str, case_id: str) -> dict[str, object]:
    return next(row for row in _jsonl(name) if row["case_id"] == case_id)


def test_case_and_eval_contracts_have_the_same_unique_ids() -> None:
    cases = [validate_case_record(row) for row in _jsonl("cases.jsonl")]
    specs = [validate_eval_spec_record(row) for row in _jsonl("eval-specs.jsonl")]
    case_ids = [row["case_id"] for row in cases]
    spec_ids = [row["case_id"] for row in specs]
    assert len(case_ids) == len(set(case_ids))
    assert len(spec_ids) == len(set(spec_ids))
    assert set(case_ids) == set(spec_ids) == {
        "SMOKE-FAST-001",
        "SMOKE-ANALYSIS-001",
        "SMOKE-EVENT-001",
        "SMOKE-OBSERVATION-001",
    }


def test_every_declared_input_exists_and_matches_its_hash() -> None:
    for case in _jsonl("cases.jsonl"):
        for input_record in case["inputs"]:
            source = ROOT / input_record["source_path"]
            assert source.is_file(), source
            assert _sha256(source) == input_record["sha256"]


def test_event_snapshots_are_exact_raw_copies_without_resolved_gold_assets() -> None:
    for relative_path, expected_hash in EXPECTED_EVENT_SNAPSHOT_HASHES.items():
        assert _sha256(ROOT / relative_path) == expected_hash

    event_fixture_root = ROOT / "fixtures" / "event_sources"
    assert {path.name for path in event_fixture_root.iterdir()} == {
        "usgs_official_domain_search.json",
        "reliefweb_official_domain_search.json",
    }
    assert not (event_fixture_root / "resolved_event.json").exists()
    assert not (event_fixture_root / "manifest.json").exists()


def test_event_snapshots_contain_the_required_fact_and_conflict_evidence() -> None:
    usgs_text = (ROOT / "fixtures/event_sources/usgs_official_domain_search.json").read_text(
        encoding="utf-8"
    )
    reliefweb_text = (
        ROOT / "fixtures/event_sources/reliefweb_official_domain_search.json"
    ).read_text(encoding="utf-8")

    for expected in (
        "us7000pn9s",
        "2025-03-28 06:20:52 (UTC)",
        "22.011",
        "95.936",
        "10.0 km depth",
    ):
        assert expected in usgs_text
    assert "aftershock of 6.4 M" in reliefweb_text
    assert "second earthquake of 6.7 magnitude" in reliefweb_text


def test_conditional_architecture_route_criteria_are_explicit() -> None:
    specs = {row["case_id"]: row for row in _jsonl("eval-specs.jsonl")}
    for case_id, specialist, package in (
        ("SMOKE-ANALYSIS-001", "NTL_Analyst", "AnalysisPackage"),
        ("SMOKE-EVENT-001", "NTL_Event_Tracker", "EventContext"),
        ("SMOKE-OBSERVATION-001", "NTL_Data_Searcher", "ObservationPackage"),
    ):
        criteria = {
            criterion["criterion_id"]: criterion["description"]
            for criterion in specs[case_id]["mandatory_criteria"]
        }
        route_text = criteria["architecture-route"]
        assert "architecture_mode" in route_text
        assert specialist in route_text
        assert package in route_text
        assert "ntl.assignment-record.v2" in route_text
        assert "ntl.handoff-record.v2" in route_text
        assert "natural-language output" in route_text
        assert "single_agent" in route_text
        assert "no `task`" in route_text
        assert "completed route" in route_text


def test_full_smoke_prompts_use_native_task_and_system_owned_records() -> None:
    cases = {row["case_id"]: row for row in _jsonl("cases.jsonl")}
    specs = {row["case_id"]: row for row in _jsonl("eval-specs.jsonl")}
    for case_id in (
        "SMOKE-ANALYSIS-001",
        "SMOKE-EVENT-001",
        "SMOKE-OBSERVATION-001",
    ):
        prompt = str(cases[case_id]["prompt"])
        assert "native `task` call" in prompt
        assert "ntl.assignment-record.v2" in prompt
        assert "ntl.handoff-record.v2" in prompt
        assert "model-authored HandoffEnvelope or EngineerDecision" in prompt
        assert "then validate and accept" not in prompt
        assert "persisted handoff acceptance" not in prompt
        assert "require_accepted_handoff_decision" not in cases[case_id]["metadata"][
            "architecture_expectations"
        ]["full"]

        route = specs[case_id]["reference"]["architecture_route"]["full"]
        assert route["assignment_record_schema"] == "ntl.assignment-record.v2"
        assert route["handoff_record_schema"] == "ntl.handoff-record.v2"
        assert route["system_recorded"] is True
        assert route["specialist_natural_language_json_required"] is False
        assert "persisted_handoff" not in route
        assert "accepted_engineer_decision" not in route
        assert not any("record_path" in str(key) for key in route)


def test_observation_case_requires_specialist_owned_inspection_and_system_query_time() -> None:
    case = _record_by_case_id("cases.jsonl", "SMOKE-OBSERVATION-001")
    prompt = str(case["prompt"])

    for required in (
        "`geodata_inspector_tool` is the only permitted domain tool",
        "any live, network, retrieval, catalog, or download tool",
        "Do not supply or guess `query_executed_at_utc`",
        "the runtime records its actual offset-aware UTC completion time",
        "NTL_Engineer must not call `geodata_inspector_tool` directly",
        "make exactly one successful native `task` call to NTL_Data_Searcher",
        "require that single descendant to call `geodata_inspector_tool` in `full` mode",
        "runtime automatically records `ntl.assignment-record.v2` and `ntl.handoff-record.v2`",
        "In matched Single-Agent mode, make no `task` call",
        "NTL_Engineer may call `geodata_inspector_tool` directly in `full` mode",
    ):
        assert required in prompt

    expectations = case["metadata"]["architecture_expectations"]
    assert expectations["full"] == {
        "required_package_types": ["ObservationPackage"],
        "required_specialist": "NTL_Data_Searcher",
        "require_completed_route": True,
    }
    assert expectations["single_agent"] == {
        "required_package_types": ["ObservationPackage"],
        "forbid_delegation": True,
        "require_completed_route": True,
    }


def test_observation_eval_contract_has_strict_trace_tool_and_timestamp_gates() -> None:
    spec = _record_by_case_id("eval-specs.jsonl", "SMOKE-OBSERVATION-001")
    criteria = {
        criterion["criterion_id"]: criterion["description"]
        for criterion in spec["mandatory_criteria"]
    }
    assert set(criteria) == {
        "fixture-identity",
        "raster-metadata",
        "raster-statistics",
        "observation-scope",
        "observation-timestamp",
        "architecture-route",
    }

    scope_text = criteria["observation-scope"]
    assert "only domain tool" in scope_text
    for forbidden_class in (
        "live",
        "network",
        "retrieval",
        "catalog",
        "download",
        "GEE",
        "Tavily",
        "BigQuery",
        "browser",
    ):
        assert forbidden_class in scope_text

    timestamp_text = criteria["observation-timestamp"]
    for required in (
        "system-injected, non-placeholder `query_executed_at_utc`",
        "valid offset-aware UTC",
        "greater than or equal to",
        "`created_at_utc`",
        "must not expose that field",
        "`save_observation_package` call",
        "successful full `geodata_inspector_tool` completion",
    ):
        assert required in timestamp_text

    route_text = criteria["architecture-route"]
    for required in (
        "exactly one successful native `task` call total",
        "`subagent_type=NTL_Data_Searcher`",
        "`lc_agent_name=NTL_Data_Searcher`",
        "zero Engineer `geodata_inspector_tool` calls",
        "`ntl.assignment-record.v2`",
        "`ntl.handoff-record.v2`",
        "natural-language output",
        "In `single_agent`, require no `task` call",
        "`lc_agent_name=NTL_Engineer`",
    ):
        assert required in route_text

    reference = spec["reference"]
    assert reference["tool_policy"]["allowed_domain_tools"] == ["geodata_inspector_tool"]
    assert reference["tool_policy"]["live_retrieval_allowed"] is False
    timestamp = reference["query_timestamp"]
    assert timestamp["authorship"] == "system"
    assert timestamp["model_input_exposed"] is False
    assert timestamp["source"] == "successful full geodata_inspector_tool completion"
    assert timestamp["placeholder_allowed"] is False
    assert timestamp["relation_to_package_created_at_utc"] == ">="
    assert "save_observation_package" in timestamp["preferred_trace_check"]

    routes = reference["architecture_route"]
    full = routes["full"]
    assert full["task_call_count"] == full["successful_task_call_count"] == 1
    assert full["task_subagent_type"] == "NTL_Data_Searcher"
    assert full["descendant_inspector"] == {
        "tool_name": "geodata_inspector_tool",
        "mode": "full",
        "lc_agent_name": "NTL_Data_Searcher",
        "must_descend_from_task": True,
    }
    assert full["engineer_inspector_call_count"] == 0
    assert full["assignment_record_schema"] == "ntl.assignment-record.v2"
    assert full["handoff_record_schema"] == "ntl.handoff-record.v2"
    assert full["system_recorded"] is True
    assert full["specialist_natural_language_json_required"] is False
    assert full["terminal_route"] == "completed"

    single = routes["single_agent"]
    assert single["task_call_count"] == 0
    assert single["task_delegation"] is False
    assert single["direct_inspector"] == {
        "tool_name": "geodata_inspector_tool",
        "mode": "full",
        "lc_agent_name": "NTL_Engineer",
    }
    assert single["ready_package"] == "ObservationPackage"
    assert single["terminal_route"] == "completed"


def test_observation_fixture_is_the_declared_synthetic_raster() -> None:
    import rasterio

    path = ROOT / "fixtures" / "observation" / "synthetic_ntl_2020.tif"
    assert path.stat().st_size == 400
    assert _sha256(path) == "995c2fe5fa8cc1bffc157bebb8f44b9b23b8ca4a43422fc4a22323a2806c8158"
    with rasterio.open(path) as dataset:
        values = dataset.read(1, masked=True).compressed().tolist()
        assert str(dataset.crs) == "EPSG:4326"
        assert (dataset.height, dataset.width, dataset.count) == (2, 2, 1)
        assert list(dataset.bounds) == [0.0, 0.0, 2.0, 2.0]
        assert dataset.dtypes == ("float32",)
        assert dataset.nodata == -9999.0
        assert values == [1.0, 2.0, 3.0]


def test_readme_pins_the_compatibility_preflight_and_gis_data_sources() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for expected in (
        "Python 3.11.15",
        "Deep Agents 0.7.5",
        "LangChain 1.3.15",
        "langchain-core 1.5.4",
        "LangGraph 1.2.11",
        "langchain-openai 1.1.7",
        "Rasterio 1.4.4",
        "pyproj 3.7.2",
        "Fiona 1.10.1",
        "pip install --no-deps -e",
        "ntl_toolkit.__file__",
        "$env:PROJ_DATA",
        "$env:GDAL_DATA",
        "sys.base_prefix",
        "No `.env`",
    ):
        assert expected in readme
