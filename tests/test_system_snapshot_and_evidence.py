from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from langchain_core.messages import AIMessage
import pytest
import yaml
import orchestration.run_evidence as run_evidence_module
import orchestration.system_snapshot as system_snapshot_module

from benchmark_runtime import CASE_SCHEMA
from benchmark_runtime.contracts import ContractError, validate_run_batch, validate_run_record
from benchmark_runtime.runner import abnormal_run_record, execute_worker_payload, run_batch
from contracts.agent_packages import (
    ArtifactRecord,
    ContractStatus,
    EvidenceReport,
    ObservationPackage,
    TaskPlan,
    canonical_json,
)
from orchestration.run_evidence import (
    PACKAGE_ARTIFACT_INTEGRITY_MISMATCH,
    architecture_expectation_issues,
    collect_internal_evidence,
    observation_timestamp_trace_issues,
    package_artifact_integrity_issues,
    validate_architecture_expectations,
    validate_internal_evidence,
)
from orchestration.route_state import RouteState
from orchestration.system_snapshot import (
    build_system_snapshot,
    system_snapshot_sha256,
    validate_system_snapshot,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

_DEEPAGENTS_RUNTIME_PINS = {
    "deepagents": "0.7.5",
    "langchain": "1.3.15",
    "langchain-core": "1.5.4",
    "langchain-openai": "1.1.7",
    "langgraph": "1.2.11",
    "langgraph-prebuilt": "1.1.0",
    "langgraph-checkpoint": "4.2.0",
    "langgraph-sdk": "0.4.2",
    "langgraph-checkpoint-postgres": "3.1.2",
}

_GEOSPATIAL_RUNTIME_DISTRIBUTIONS = (
    "ntl-toolkit",
    "fiona",
    "geopandas",
    "rasterio",
    "pyproj",
    "shapely",
    "numpy",
    "pandas",
)

_EXPECTED_RUNTIME_DISTRIBUTIONS = (
    *_DEEPAGENTS_RUNTIME_PINS,
    *_GEOSPATIAL_RUNTIME_DISTRIBUTIONS,
)


def _caller_prompt_identity(
    value: object, *, surface: str = "system_prompt"
) -> dict[str, object]:
    text = str(getattr(value, "content", value))
    encoded = text.encode("utf-8")
    return {
        "layer": "caller_authored",
        "surface": surface,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }


def _nested_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _nested_strings(key)
            yield from _nested_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _nested_strings(child)


def test_verified_deepagents_runtime_pins_match_environment() -> None:
    environment = yaml.safe_load(
        (REPO_ROOT / "environment.yml").read_text(encoding="utf-8")
    )
    pip_entries = next(
        dependency["pip"]
        for dependency in environment["dependencies"]
        if isinstance(dependency, dict) and "pip" in dependency
    )
    assert {
        entry
        for entry in pip_entries
        if isinstance(entry, str)
        and entry.partition("==")[0] in _DEEPAGENTS_RUNTIME_PINS
    } == {
        f"{distribution}=={version}"
        for distribution, version in _DEEPAGENTS_RUNTIME_PINS.items()
    }
    assert {
        distribution: metadata.version(distribution)
        for distribution in _DEEPAGENTS_RUNTIME_PINS
    } == _DEEPAGENTS_RUNTIME_PINS


def _case(case_id: str) -> dict[str, object]:
    return {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "prompt": f"smoke prompt for {case_id}",
        "inputs": [],
        "metadata": {},
    }


def _write_cases(path: Path, *case_ids: str) -> None:
    path.write_text(
        "".join(json.dumps(_case(case_id), ensure_ascii=False) + "\n" for case_id in case_ids),
        encoding="utf-8",
    )


def _snapshot(mode: str = "full") -> dict[str, object]:
    return build_system_snapshot(
        REPO_ROOT,
        architecture_mode=mode,
        model_name="deepseek-v4-flash",
        run_limits={
            "request_timeout_seconds": 30,
            "task_timeout_seconds": 60.0,
            "recursion_limit": 20,
        },
    )


def test_system_snapshot_is_deterministic_secret_free_and_architecture_exact() -> None:
    from agents.NTL_Analyst import system_prompt_analyst
    from agents.NTL_Data_Searcher import hierarchical_system_prompt_data_searcher
    from agents.NTL_Event_Tracker import system_prompt_event_tracker
    from graph_factory import (
        DEEPAGENTS_HARNESS_MODEL_SPECS,
        NTL_TASK_DESCRIPTION,
        _full_system_prompt,
        _single_agent_prompt,
    )

    full_a = _snapshot("full")
    full_b = _snapshot("full")
    single = _snapshot("single_agent")

    assert full_a == full_b
    assert full_a["schema_version"] == "ntl.system-snapshot.v3"
    assert system_snapshot_sha256(full_a) == system_snapshot_sha256(full_b)
    validate_system_snapshot(
        full_a,
        expected_sha256=system_snapshot_sha256(full_a),
        architecture_mode="full",
    )
    assert full_a["topology"]["active_roles"] == [
        "NTL_Engineer",
        "NTL_Data_Searcher",
        "NTL_Analyst",
        "NTL_Event_Tracker",
    ]
    assert full_a["topology"]["general_purpose_subagent_enabled"] is False
    assert (
        full_a["topology"]["deepagents_harness_profile"]
        == "openai:deepseek-v4-flash"
    )
    assert full_a["topology"]["deepagents_harness_profiles_supported"] == list(
        DEEPAGENTS_HARNESS_MODEL_SPECS
    )
    native_filesystem_tools = [
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
    ]
    assert full_a["tool_allowlists"]["NTL_Engineer"]["middleware_tools"] == [
        *native_filesystem_tools,
        "task",
    ]
    assert all(
        role["middleware_tools"] == native_filesystem_tools
        for name, role in full_a["tool_allowlists"].items()
        if name != "NTL_Engineer"
    )
    assert "record_handoff_decision" not in full_a["tool_allowlists"]["NTL_Engineer"][
        "contract_tools"
    ]
    assert single["topology"]["active_roles"] == ["NTL_Engineer"]
    assert single["tool_allowlists"]["NTL_Engineer"]["middleware_tools"] == (
        native_filesystem_tools
    )
    assert "record_handoff_decision" not in single["tool_allowlists"]["NTL_Engineer"][
        "contract_tools"
    ]
    assert set(single["tool_allowlists"]["NTL_Engineer"]["domain_tools"]) == {
        tool
        for role in full_a["tool_allowlists"].values()
        for tool in role["domain_tools"]
    }
    assert full_a["limits"]["specialist_max_revisions"] == 2
    assert full_a["limits"]["model_request_max_retries"] == 3
    assert full_a["package_contracts"]["system_transfer_record_models"] == [
        "AssignmentRecordV2",
        "HandoffRecordV2",
    ]
    assert full_a["package_contracts"]["legacy_handoff_models"] == full_a[
        "package_contracts"
    ]["handoff_models"]
    assert full_a["runtime_versions"] == {
        distribution: metadata.version(distribution)
        for distribution in _EXPECTED_RUNTIME_DISTRIBUTIONS
    }
    assert full_a["prompt_hashes"] == {
        "NTL_Engineer": _caller_prompt_identity(_full_system_prompt()),
        "NTL_Data_Searcher": _caller_prompt_identity(
            hierarchical_system_prompt_data_searcher
        ),
        "NTL_Analyst": _caller_prompt_identity(system_prompt_analyst),
        "NTL_Event_Tracker": _caller_prompt_identity(system_prompt_event_tracker),
        "NTL_Engineer.task": _caller_prompt_identity(
            NTL_TASK_DESCRIPTION,
            surface="tool_description",
        ),
    }
    assert single["prompt_hashes"] == {
        "NTL_Engineer": _caller_prompt_identity(_single_agent_prompt())
    }
    assert len(full_a["skill_files"]) >= 5
    assert system_snapshot_sha256(full_a) != system_snapshot_sha256(single)
    assert full_a["startup_memory_sources"] == []
    assert single["startup_memory_sources"] == []

    serialized = json.dumps(full_a, ensure_ascii=False).casefold()
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "gold_answer" not in serialized
    assert str(REPO_ROOT).casefold() not in serialized


def test_system_snapshot_code_manifest_binds_runtime_tool_and_toolkit_sources() -> None:
    from tools import _EXPORTS

    snapshot = _snapshot("full")
    code_hashes = snapshot["code_hashes"]
    code_paths = list(code_hashes)
    expected_export_modules = {
        f"tools/{module_name.removeprefix('.')}.py"
        for module_name, _attribute_name in _EXPORTS.values()
    }
    expected_toolkit_modules = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (
            REPO_ROOT / "packages" / "ntl_toolkit" / "src" / "ntl_toolkit"
        ).rglob("*.py")
    }

    assert code_paths == sorted(code_paths)
    assert expected_export_modules <= set(code_paths)
    assert expected_toolkit_modules <= set(code_paths)
    assert {
        "environment.yml",
        "packages/ntl_toolkit/pyproject.toml",
        "benchmark_runtime/contracts.py",
        "benchmark_runtime/runner.py",
        "benchmark_runtime/telemetry.py",
        "orchestration/artifact_runtime.py",
        "orchestration/run_evidence.py",
        "orchestration/observation_runtime.py",
        "orchestration/system_snapshot.py",
        "orchestration/transfer_records.py",
        "tools/geodata_inspector_tool.py",
        "packages/ntl_toolkit/src/ntl_toolkit/adapters/langchain/local.py",
        "packages/ntl_toolkit/src/ntl_toolkit/core/raster.py",
        "packages/ntl_toolkit/src/ntl_toolkit/core/urban_structure.py",
    } <= set(code_paths)
    assert all(
        row["relative_path"] == relative_path
        and not Path(relative_path).is_absolute()
        and not Path(relative_path).drive
        and "\\" not in relative_path
        and ".." not in relative_path.split("/")
        for relative_path, row in code_hashes.items()
    )


def test_code_manifest_hash_changes_when_temporary_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_repo = tmp_path / "repo"
    copied_source = temp_repo / "orchestration" / "system_snapshot.py"
    copied_source.parent.mkdir(parents=True)
    copied_source.write_bytes((REPO_ROOT / "orchestration/system_snapshot.py").read_bytes())
    monkeypatch.setattr(
        system_snapshot_module,
        "_snapshot_code_relative_paths",
        lambda _repo_root: ("orchestration/system_snapshot.py",),
    )

    before = system_snapshot_module._code_manifest(temp_repo)
    copied_source.write_bytes(copied_source.read_bytes() + b"\n# temporary drift\n")
    after = system_snapshot_module._code_manifest(temp_repo)

    assert before["orchestration/system_snapshot.py"]["sha256"] != after[
        "orchestration/system_snapshot.py"
    ]["sha256"]


def test_system_snapshot_records_native_permissions_and_backend_design() -> None:
    from agents.role_specs import ROLE_SPECS
    from graph_factory import filesystem_runtime_descriptor

    full = _snapshot("full")
    single = _snapshot("single_agent")
    expected_full = {
        role_name: filesystem_runtime_descriptor(
            spec.skill_sources,
            memory_access=(role_name == "NTL_Engineer"),
        )
        for role_name, spec in ROLE_SPECS.items()
    }
    single_sources = tuple(
        dict.fromkeys(
            source for spec in ROLE_SPECS.values() for source in spec.skill_sources
        )
    )
    assert full["filesystem_runtime"] == expected_full
    assert single["filesystem_runtime"] == {
        "NTL_Engineer": filesystem_runtime_descriptor(
            single_sources,
            memory_access=True,
        )
    }

    for descriptor in full["filesystem_runtime"].values():
        rules = descriptor["permissions"]
        assert rules[-1] == {
            "operations": ["read", "write"],
            "paths": ["/**"],
            "mode": "deny",
        }
        assert descriptor["backend_type"] == "CompositeBackend(default=StateBackend)"
        assert all(not Path(path).drive for rule in rules for path in rule["paths"])
        assert not any(
            re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\")
            for value in _nested_strings(descriptor)
        )


def test_system_snapshot_hash_and_runtime_limit_binding_fail_closed(tmp_path: Path) -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="sha256"):
        validate_system_snapshot(snapshot, expected_sha256="0" * 64)

    payload = _worker_payload(tmp_path, snapshot=snapshot)
    record = _minimal_run_record(payload)
    record["environment"]["recursion_limit"] = 21
    with pytest.raises(ContractError, match="snapshot limit recursion_limit"):
        validate_run_record(record)


def test_internal_evidence_inventory_validates_packages_and_route_without_copying_bodies(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    contract_dir = outputs / "runs" / "run-1" / "contracts"
    route_dir = outputs / "runs" / "run-1" / "route"
    contract_dir.mkdir(parents=True)
    route_dir.mkdir(parents=True)
    now = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)
    plan = TaskPlan(
        artifact_id="plan-1",
        run_id="run-1",
        task_id="case-1",
        created_at_utc=now,
        status=ContractStatus.READY,
        original_request="Inspect the supplied raster.",
        normalized_objective="Inspect the supplied raster.",
    )
    (contract_dir / "task_plan__plan-1.json").write_text(
        canonical_json(plan), encoding="utf-8"
    )
    state = RouteState(run_id="run-1", task_id="case-1")
    (route_dir / "route_state.json").write_text(canonical_json(state), encoding="utf-8")

    evidence = collect_internal_evidence(outputs)
    validate_internal_evidence(evidence)
    assert evidence["valid"] is True
    assert evidence["package_counts"]["TaskPlan"] == 1
    assert evidence["route_states"][0]["status"] == "received"
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "Inspect the supplied raster" not in serialized


def test_invalid_internal_contract_is_reported_without_leaking_gold(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    contract_dir = outputs / "runs" / "run-1" / "contracts"
    contract_dir.mkdir(parents=True)
    (contract_dir / "bad.json").write_text(
        json.dumps({"gold_answer": "must-not-leak", "artifact_type": "TaskPlan"}),
        encoding="utf-8",
    )
    evidence = collect_internal_evidence(outputs)
    validate_internal_evidence(evidence)
    assert evidence["valid"] is False
    assert evidence["issue_count"] == 1
    assert "must-not-leak" not in json.dumps(evidence)
    assert evidence["invalid_records"][0]["issue_code"] == "INVALID_INTERNAL_RECORD"


def _write_evidence_report_with_artifact_links(
    outputs: Path,
    *,
    representative_path: str | None = None,
    source_links: list[dict[str, object]] | None = None,
) -> None:
    contract_dir = outputs / "runs" / "run-artifacts" / "contracts"
    contract_dir.mkdir(parents=True, exist_ok=True)
    representatives = []
    if representative_path is not None:
        artifact = outputs / "products" / "result.bin"
        payload = artifact.read_bytes()
        representatives.append(
            ArtifactRecord(
                path=representative_path,
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )
    report = EvidenceReport(
        artifact_id="report-artifacts",
        run_id="run-artifacts",
        task_id="case-artifacts",
        created_at_utc=datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc),
        status=ContractStatus.READY,
        final_status="completed",
        direct_answer="Artifact-backed answer.",
        # A path without digest/bytes is not a local ArtifactRecord declaration.
        artifact_manifest_path="outputs/not-created-manifest.json",
        representative_artifacts=representatives,
        source_and_artifact_links=source_links or [],
    )
    (contract_dir / "evidence_report__report-artifacts.json").write_text(
        canonical_json(report), encoding="utf-8"
    )


def test_package_artifact_integrity_accepts_current_workspace_artifacts_and_ignores_path_only_fields(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    artifact = outputs / "products" / "result.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"verified-result")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    staged_input = tmp_path / "inputs" / "source.json"
    staged_input.parent.mkdir()
    staged_input.write_bytes(b'{"source":"staged"}')
    _write_evidence_report_with_artifact_links(
        outputs,
        representative_path="/data/processed/products/result.bin",
        source_links=[
            {
                "kind": "local_artifact",
                "path": "outputs/products/result.bin",
                "sha256": digest,
                "bytes": artifact.stat().st_size,
            },
            {
                "kind": "local_source",
                "path": "inputs/source.json",
                "sha256": hashlib.sha256(staged_input.read_bytes()).hexdigest(),
                "bytes": staged_input.stat().st_size,
            },
        ],
    )
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == []


def test_package_artifact_integrity_detects_post_collection_hash_or_byte_drift(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    artifact = outputs / "products" / "result.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"original")
    _write_evidence_report_with_artifact_links(
        outputs,
        representative_path="outputs/products/result.bin",
    )
    evidence = collect_internal_evidence(outputs)
    artifact.write_bytes(b"tampered-and-longer")
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


@pytest.mark.parametrize("declared_path", ["../outside.bin", "outputs/missing.bin"])
def test_package_artifact_integrity_rejects_escape_and_missing_paths(
    tmp_path: Path,
    declared_path: str,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    _write_evidence_report_with_artifact_links(
        outputs,
        source_links=[
            {
                "path": declared_path,
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "bytes": outside.stat().st_size,
            }
        ],
    )
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


def test_package_artifact_integrity_rejects_linklike_artifacts(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    target = outputs / "products" / "target.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"linked")
    alias = outputs / "products" / "alias.bin"
    try:
        alias.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    _write_evidence_report_with_artifact_links(
        outputs,
        source_links=[
            {
                "path": "outputs/products/alias.bin",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "bytes": target.stat().st_size,
            }
        ],
    )
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


def test_package_artifact_integrity_fail_closes_on_detected_reparse_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    artifact = outputs / "products" / "alias.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"reparse-target-bytes")
    _write_evidence_report_with_artifact_links(
        outputs,
        source_links=[
            {
                "path": "outputs/products/alias.bin",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "bytes": artifact.stat().st_size,
            }
        ],
    )
    real_linklike = run_evidence_module._linklike
    monkeypatch.setattr(
        run_evidence_module,
        "_linklike",
        lambda path: path.name == "alias.bin" or real_linklike(path),
    )
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


def _write_opaque_package_reference(outputs: Path, *, token: str) -> tuple[str, int]:
    contract_dir = outputs / "runs" / "run-artifacts" / "contracts"
    contract_dir.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)
    target = TaskPlan(
        artifact_id="opaque-target",
        run_id="run-artifacts",
        task_id="case-artifacts",
        created_at_utc=now,
        status=ContractStatus.READY,
        original_request="Bind this opaque package.",
        normalized_objective="Bind this opaque package.",
    )
    target_path = contract_dir / "task_plan__opaque-target.json"
    target_path.write_text(canonical_json(target), encoding="utf-8")
    digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
    report = EvidenceReport(
        artifact_id="report-opaque",
        run_id="run-artifacts",
        task_id="case-artifacts",
        created_at_utc=now,
        status=ContractStatus.READY,
        final_status="completed",
        direct_answer="Opaque package is bound.",
        representative_artifacts=[
            ArtifactRecord(
                path=f"package/{token}",
                sha256=digest,
                bytes=target_path.stat().st_size,
                role="task_plan_package",
            )
        ],
    )
    (contract_dir / "evidence_report__report-opaque.json").write_text(
        canonical_json(report), encoding="utf-8"
    )
    return digest, target_path.stat().st_size


def test_package_artifact_integrity_binds_opaque_handle_to_unique_persisted_package(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    token = "a" * 32
    digest, byte_count = _write_opaque_package_reference(outputs, token=token)
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
        opaque_package_bindings={
            f"package/{token}": {
                "artifact_id": "opaque-target",
                "artifact_type": "TaskPlan",
                "sha256": digest,
                "relative_path": (
                    "outputs/runs/run-artifacts/contracts/"
                    "task_plan__opaque-target.json"
                ),
            }
        },
    ) == []
    # Parent-process/abnormal collection has no token registry. The same
    # reference remains auditable because digest+bytes select one package.
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == []
    assert byte_count > 0


def test_package_artifact_integrity_rejects_unknown_opaque_handle_even_with_real_digest(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    digest, _byte_count = _write_opaque_package_reference(outputs, token="b" * 32)
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
        opaque_package_bindings={
            "package/" + "a" * 32: {
                "artifact_id": "opaque-target",
                "artifact_type": "TaskPlan",
                "sha256": digest,
                "relative_path": (
                    "outputs/runs/run-artifacts/contracts/"
                    "task_plan__opaque-target.json"
                ),
            }
        },
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


def test_package_artifact_integrity_rejects_opaque_handle_digest_forgery(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _digest, _byte_count = _write_opaque_package_reference(outputs, token="c" * 32)
    report_path = (
        outputs
        / "runs"
        / "run-artifacts"
        / "contracts"
        / "evidence_report__report-opaque.json"
    )
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    raw["representative_artifacts"][0]["sha256"] = "f" * 64
    forged = EvidenceReport.model_validate(raw)
    report_path.write_text(canonical_json(forged), encoding="utf-8")
    evidence = collect_internal_evidence(outputs)
    assert package_artifact_integrity_issues(
        outputs,
        evidence,
        expected_run_id="run-artifacts",
        expected_task_id="case-artifacts",
    ) == [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]


def _architecture_evidence_fixture() -> dict[str, object]:
    run_id = "run-architecture"
    task_id = "case-architecture"

    def identity(relative: str, index: int) -> dict[str, object]:
        return {
            "relative_path": f"outputs/runs/{run_id}/{relative}",
            "sha256": f"{index:064x}",
            "bytes": 100 + index,
        }

    evidence: dict[str, object] = {
        "schema_version": "ntl-benchmark.internal-evidence.v1",
        "content_policy": "identity_metadata_and_hashes_only",
        "valid": True,
        "package_counts": {
            "TaskPlan": 0,
            "EventContext": 0,
            "ObservationPackage": 0,
            "AnalysisPackage": 1,
            "EvidenceReport": 0,
        },
        "packages": [
            {
                **identity("contracts/analysis_package__analysis-1.json", 1),
                "artifact_type": "AnalysisPackage",
                "artifact_id": "analysis-1",
                "run_id": run_id,
                "task_id": task_id,
                "producer": "NTL_Analyst",
                "status": "ready",
            }
        ],
        "handoffs": [
            {
                **identity("handoffs/handoff__handoff-1.json", 2),
                "handoff_id": "handoff-1",
                "assignment_id": "assignment-1",
                "run_id": run_id,
                "task_id": task_id,
                "producer": "NTL_Analyst",
                "status": "ready",
                "package_type": "AnalysisPackage",
                "validation_verdict": "passed",
            }
        ],
        "decisions": [
            {
                **identity("decisions/engineer_decision__decision-1.json", 3),
                "decision_id": "decision-1",
                "handoff_id": "handoff-1",
                "assignment_id": "assignment-1",
                "run_id": run_id,
                "task_id": task_id,
                "decision": "accepted",
                "package_type": "AnalysisPackage",
            }
        ],
        "route_states": [
            {
                **identity("route/route_state.json", 4),
                "run_id": run_id,
                "task_id": task_id,
                "status": "completed",
                "revision_count": 0,
                "max_revisions": 2,
                "event_count": 5,
                "accepted_package_types": ["AnalysisPackage"],
                "skipped_specialists": [],
                "terminal": True,
            }
        ],
        "invalid_records": [],
        "issue_count": 0,
        "discovered_run_ids": [run_id],
    }
    validate_internal_evidence(evidence)
    return evidence


def _analyst_trace() -> list[dict[str, object]]:
    return [
        {
            "tool_call_id": "task-call-1",
            "tool_name": "task",
            "status": "succeeded",
            "result_observed": True,
            "arguments": {"subagent_type": "NTL_Analyst"},
            "metadata": {
                "lc_agent_name": "NTL_Engineer",
                "task_run_id": "run-architecture",
                "case_id": "case-architecture",
            },
            "ancestor_tool_call_ids": [],
        },
        {
            "tool_call_id": "save-call-1",
            "tool_name": "save_analysis_package",
            "status": "succeeded",
            "arguments": {},
            "metadata": {
                "lc_agent_name": "NTL_Analyst",
                "task_run_id": "run-architecture",
                "case_id": "case-architecture",
            },
            "ancestor_tool_call_ids": ["task-call-1"],
            "parent_tool_call_id": "task-call-1",
        },
    ]


def test_case_architecture_expectations_accept_full_and_single_contracts() -> None:
    configured = validate_architecture_expectations(
        {
            "full": {
                "required_package_types": ["AnalysisPackage"],
                "required_specialist": "NTL_Analyst",
                "require_accepted_handoff_decision": True,
                "require_completed_route": True,
                "task_call_count": 1,
                "successful_task_call_count": 1,
            },
            "single_agent": {
                "required_package_types": ["AnalysisPackage"],
                "forbid_delegation": True,
                "require_completed_route": True,
                "task_call_count": 0,
                "successful_task_call_count": 0,
            },
        }
    )
    evidence = _architecture_evidence_fixture()
    assert architecture_expectation_issues(
        evidence,
        tool_trace=_analyst_trace(),
        expectations=configured,
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == []
    assert architecture_expectation_issues(
        evidence,
        tool_trace=[],
        expectations=configured,
        architecture_mode="single_agent",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == []


@pytest.mark.parametrize(
    "configured",
    [
        {"ful": {"require_completed_route": True}},
        {"full": {"required_specialists": "NTL_Analyst"}},
        {"full": {"required_package_types": ["AnalysisPackge"]}},
        {"full": {"require_completed_route": 1}},
        {"full": {"task_call_count": True}},
        {"full": {"successful_task_call_count": -1}},
        {
            "full": {
                "task_call_count": 1,
                "successful_task_call_count": 2,
            }
        },
        {"single_agent": {"required_specialist": "NTL_Analyst"}},
        {"single_agent": {"task_call_count": 1}},
        {
            "full": {
                "required_specialist": "NTL_Analyst",
                "forbid_delegation": True,
            }
        },
    ],
)
def test_case_architecture_expectations_reject_shape_typos_and_conflicts(
    configured: object,
) -> None:
    with pytest.raises(ValueError, match="architecture_expectations"):
        validate_architecture_expectations(configured)


def test_architecture_expectation_issues_fail_closed_with_stable_codes() -> None:
    evidence = deepcopy(_architecture_evidence_fixture())
    evidence["packages"][0]["status"] = "failed"
    evidence["route_states"][0].update({"status": "blocked", "terminal": True})
    evidence["handoffs"][0].update(
        {"status": "failed", "validation_verdict": "failed"}
    )
    evidence["decisions"][0]["decision"] = "blocked"
    assert architecture_expectation_issues(
        evidence,
        tool_trace=[],
        expectations={
            "full": {
                "required_package_types": ["AnalysisPackage"],
                "required_specialist": "NTL_Analyst",
                "require_accepted_handoff_decision": True,
                "require_completed_route": True,
            }
        },
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == [
        "MISSING_READY_ANALYSIS_PACKAGE",
        "MISSING_COMPLETED_ROUTE",
        "MISSING_ACCEPTED_HANDOFF_DECISION",
        "MISSING_REQUIRED_SPECIALIST_TASK",
        "MISSING_REQUIRED_SPECIALIST_DESCENDANT_TRACE",
    ]
    assert architecture_expectation_issues(
        evidence,
        tool_trace=[],
        expectations={"full": {"require_completed_routes": True}},
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == ["INVALID_ARCHITECTURE_EXPECTATIONS"]


def _task_trace_row(
    call_id: str,
    *,
    status: str = "succeeded",
    run_id: str = "run-architecture",
    task_id: str = "case-architecture",
    source_role: str = "NTL_Engineer",
    target_role: str = "NTL_Analyst",
) -> dict[str, object]:
    return {
        "tool_call_id": call_id,
        "tool_name": "task",
        "status": status,
        "result_observed": status == "succeeded",
        "arguments": {"subagent_type": target_role},
        "metadata": {
            "lc_agent_name": source_role,
            "task_run_id": run_id,
            "case_id": task_id,
        },
        "ancestor_tool_call_ids": [],
    }


@pytest.mark.parametrize(
    ("tool_trace", "expected_issues"),
    [
        (
            [
                _task_trace_row("task-1"),
                _task_trace_row("task-2"),
            ],
            [
                "TASK_CALL_COUNT_MISMATCH",
                "SUCCESSFUL_TASK_CALL_COUNT_MISMATCH",
            ],
        ),
        (
            [
                _task_trace_row("task-failed", status="error"),
                _task_trace_row("task-succeeded"),
            ],
            ["TASK_CALL_COUNT_MISMATCH"],
        ),
        (
            [_task_trace_row("task-other-run", run_id="other-run")],
            [
                "TASK_CALL_COUNT_MISMATCH",
                "SUCCESSFUL_TASK_CALL_COUNT_MISMATCH",
            ],
        ),
        (
            [],
            [
                "TASK_CALL_COUNT_MISMATCH",
                "SUCCESSFUL_TASK_CALL_COUNT_MISMATCH",
            ],
        ),
    ],
    ids=("duplicate-success", "failed-plus-success", "wrong-scope", "missing"),
)
def test_exact_native_task_count_gate_rejects_non_exact_current_scope_telemetry(
    tool_trace: list[dict[str, object]],
    expected_issues: list[str],
) -> None:
    assert architecture_expectation_issues(
        _architecture_evidence_fixture(),
        tool_trace=tool_trace,
        expectations={
            "full": {
                "task_call_count": 1,
                "successful_task_call_count": 1,
            }
        },
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == expected_issues


@pytest.mark.parametrize(
    ("source_role", "target_role"),
    [
        ("NTL_Analyst", "NTL_Analyst"),
        ("NTL_Engineer", "NTL_Event_Tracker"),
    ],
)
def test_exact_native_task_gate_requires_engineer_to_declared_specialist_route(
    source_role: str,
    target_role: str,
) -> None:
    assert architecture_expectation_issues(
        _architecture_evidence_fixture(),
        tool_trace=[
            _task_trace_row(
                "task-wrong-route",
                source_role=source_role,
                target_role=target_role,
            )
        ],
        expectations={
            "full": {
                "required_specialist": "NTL_Analyst",
                "task_call_count": 1,
                "successful_task_call_count": 1,
            }
        },
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == [
        "MISSING_REQUIRED_SPECIALIST_TASK",
        "MISSING_REQUIRED_SPECIALIST_DESCENDANT_TRACE",
    ]


def test_task_count_expectations_are_opt_in_for_backward_compatibility() -> None:
    assert architecture_expectation_issues(
        _architecture_evidence_fixture(),
        tool_trace=[_task_trace_row("task-1"), _task_trace_row("task-2")],
        expectations={"full": {}},
        architecture_mode="full",
        expected_run_id="run-architecture",
        expected_task_id="case-architecture",
    ) == []


def _observation_timestamp_fixture(
    tmp_path: Path,
    *,
    query: datetime,
) -> tuple[Path, dict[str, object], list[dict[str, object]]]:
    outputs = tmp_path / "outputs"
    contract_dir = outputs / "runs" / "run-observation" / "contracts"
    contract_dir.mkdir(parents=True)
    package = ObservationPackage(
        artifact_id="observation-trace",
        run_id="run-observation",
        task_id="case-observation",
        created_at_utc=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
        query_executed_at_utc=query,
        status=ContractStatus.READY,
        product={"collection_id": "staged/synthetic"},
        validation={"status": "passed"},
    )
    (contract_dir / "observation_package__observation-trace.json").write_text(
        canonical_json(package), encoding="utf-8"
    )
    evidence = collect_internal_evidence(outputs)
    metadata = {
        "task_run_id": "run-observation",
        "case_id": "case-observation",
        "lc_agent_name": "NTL_Data_Searcher",
    }
    trace: list[dict[str, object]] = [
        {
            "tool_call_id": "task-observation",
            "tool_name": "task",
            "status": "succeeded",
            "result_observed": True,
            "arguments": {"subagent_type": "NTL_Data_Searcher"},
            "metadata": {
                "task_run_id": "run-observation",
                "case_id": "case-observation",
                "lc_agent_name": "NTL_Engineer",
            },
            "ancestor_tool_call_ids": [],
            "started_at": "2026-08-12T12:00:01+00:00",
            "ended_at": "2026-08-12T12:00:09+00:00",
        },
        {
            "tool_call_id": "inspect-observation",
            "tool_name": "geodata_inspector_tool",
            "status": "succeeded",
            "result_observed": True,
            "arguments": {"mode": "full"},
            "metadata": metadata,
            "ancestor_tool_call_ids": ["task-observation"],
            "started_at": "2026-08-12T12:00:04+00:00",
            "ended_at": "2026-08-12T12:00:05.500000+00:00",
        },
        {
            "tool_call_id": "save-observation",
            "tool_name": "save_observation_package",
            "status": "succeeded",
            "result_observed": True,
            "arguments": {"contract": {"artifact_id": "observation-trace"}},
            "metadata": metadata,
            "ancestor_tool_call_ids": ["task-observation"],
            "started_at": "2026-08-12T12:00:06+00:00",
            "ended_at": "2026-08-12T12:00:06.500000+00:00",
        },
    ]
    return outputs, evidence, trace


def test_observation_timestamp_gate_accepts_system_time_inside_full_trace(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 12, 0, 5, tzinfo=timezone.utc),
    )
    assert observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:00+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    ) == []


def test_observation_timestamp_gate_fails_closed_for_future_model_time(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc),
    )
    issues = observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:00+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    )
    assert {
        "OBSERVATION_TIMESTAMP_OUTSIDE_RUN",
        "OBSERVATION_TIMESTAMP_OUTSIDE_INSPECTOR",
        "OBSERVATION_TIMESTAMP_AFTER_SAVE",
    } <= set(issues)


def test_observation_timestamp_gate_requires_data_searcher_descendant(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 12, 0, 5, tzinfo=timezone.utc),
    )
    trace[1]["ancestor_tool_call_ids"] = []
    trace[2]["ancestor_tool_call_ids"] = []
    issues = observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:00+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    )
    assert "MISSING_OBSERVATION_INSPECTOR_DESCENDANT_TRACE" in issues
    assert "MISSING_OBSERVATION_SAVE_TRACE" in issues


def test_observation_timestamp_gate_accepts_single_direct_and_rejects_delegation(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 12, 0, 5, tzinfo=timezone.utc),
    )
    direct = deepcopy(trace[1:])
    for row in direct:
        row["metadata"] = {
            **row["metadata"],
            "lc_agent_name": "NTL_Engineer",
        }
        row["ancestor_tool_call_ids"] = []
    kwargs = {
        "architecture_mode": "single_agent",
        "expected_run_id": "run-observation",
        "expected_task_id": "case-observation",
        "run_started_at": "2026-08-12T12:00:00+00:00",
        "evidence_checked_at": "2026-08-12T12:00:10+00:00",
    }
    assert observation_timestamp_trace_issues(
        outputs, evidence, tool_trace=direct, **kwargs
    ) == []
    delegated = [trace[0], *direct]
    assert "FORBIDDEN_OBSERVATION_DELEGATION" in observation_timestamp_trace_issues(
        outputs, evidence, tool_trace=delegated, **kwargs
    )


def test_observation_timestamp_gate_uses_strict_run_bounds_and_exact_save_identity(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 12, 0, 5, tzinfo=timezone.utc),
    )
    strict_issues = observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:05.500000+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    )
    assert "OBSERVATION_TIMESTAMP_OUTSIDE_RUN" in strict_issues

    trace[2]["arguments"] = {"contract": {"artifact_id": "different-package"}}
    identity_issues = observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:00+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    )
    assert "AMBIGUOUS_OBSERVATION_SAVE_TRACE" in identity_issues


def test_observation_timestamp_gate_rejects_wrong_scope_task_and_failed_inspector(
    tmp_path: Path,
) -> None:
    outputs, evidence, trace = _observation_timestamp_fixture(
        tmp_path,
        query=datetime(2026, 8, 12, 12, 0, 5, tzinfo=timezone.utc),
    )
    trace[0]["metadata"] = {
        **trace[0]["metadata"],
        "task_run_id": "other-run",
    }
    trace[1]["status"] = "failed"
    issues = observation_timestamp_trace_issues(
        outputs,
        evidence,
        tool_trace=trace,
        architecture_mode="full",
        expected_run_id="run-observation",
        expected_task_id="case-observation",
        run_started_at="2026-08-12T12:00:00+00:00",
        evidence_checked_at="2026-08-12T12:00:10+00:00",
    )
    assert "MISSING_OBSERVATION_INSPECTOR_TRACE" in issues
    assert "MISSING_OBSERVATION_SAVE_TRACE" in issues


def _worker_payload(tmp_path: Path, *, snapshot: dict[str, object]) -> dict[str, object]:
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir(exist_ok=True)
    case = _case("case-001")
    return {
        "case": case,
        "cases_base_dir": str(tmp_path),
        "workspace_root": str(workspace_root),
        "result_path": str(tmp_path / "record.json"),
        "telemetry_path": str(tmp_path / "record.json.telemetry.json"),
        "batch_run_id": "batch-001",
        "task_run_id": "task-run-001",
        "thread_id": "thread-case-001",
        "model": "deepseek-v4-flash",
        "architecture_mode": "full",
        "system_snapshot": snapshot,
        "system_snapshot_sha256": system_snapshot_sha256(snapshot),
        "request_timeout_seconds": 30,
        "task_timeout_seconds": 60.0,
        "recursion_limit": 20,
        "system_git_sha": "a" * 40,
        "system_git_dirty": False,
        "system_git_status_sha256": "b" * 64,
        "cases_sha256": "c" * 64,
        "case_sha256": hashlib.sha256(
            json.dumps(
                case,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "submitted_at": "2026-08-12T00:00:00+00:00",
        "wall_clock_scope": "parent_process_start_to_worker_exit",
    }


def _minimal_run_record(payload: dict[str, object]) -> dict[str, object]:
    return abnormal_run_record(
        payload,
        terminal_state="failed",
        elapsed=0.1,
        error_code="TEST_FAILURE",
        error_message="controlled test failure",
    )


def test_worker_run_record_binds_snapshot_and_internal_evidence(tmp_path: Path) -> None:
    snapshot = _snapshot()
    payload = _worker_payload(tmp_path, snapshot=snapshot)
    record = execute_worker_payload(
        payload,
        graph_invoker=lambda *_args: {"messages": [AIMessage(content="done")]},
    )
    validate_run_record(record)
    assert record["environment"]["system_snapshot_sha256"] == system_snapshot_sha256(
        snapshot
    )
    assert record["internal_evidence"]["valid"] is True
    assert record["internal_evidence"]["package_counts"] == {
        "TaskPlan": 0,
        "EventContext": 0,
        "ObservationPackage": 0,
        "AnalysisPackage": 0,
        "EvidenceReport": 0,
    }
    assert record["terminal_state"] == "failed"
    assert record["errors"][-1] == {
        "code": "ARCHITECTURE_EVIDENCE_INCOMPLETE",
        "message": (
            "minimum internal architecture evidence gate failed: "
            "MISSING_TASK_PLAN, MISSING_EVIDENCE_REPORT, MISSING_ROUTE_STATE"
        ),
    }


def test_worker_runner_applies_case_architecture_expectations_to_tool_trace(
    tmp_path: Path,
) -> None:
    payload = _worker_payload(tmp_path, snapshot={})
    payload.pop("system_snapshot")
    payload.pop("system_snapshot_sha256")
    payload["architecture_mode"] = "single_agent"
    payload["case"]["metadata"] = {
        "architecture_expectations": {
            "single_agent": {
                "forbid_delegation": True,
                "task_call_count": 0,
                "successful_task_call_count": 0,
            }
        }
    }

    def graph_invoker(_case, _payload, telemetry):
        call_id = uuid4()
        telemetry.on_tool_start(
            {"name": "task"},
            "",
            run_id=call_id,
            inputs={
                "subagent_type": "NTL_Analyst",
                "description": "Analyze the staged input and save an AnalysisPackage.",
            },
            metadata={
                "lc_agent_name": "NTL_Engineer",
                "task_run_id": _payload["task_run_id"],
                "case_id": _case["case_id"],
            },
        )
        telemetry.on_tool_end("unexpected delegation", run_id=call_id)
        return {"messages": [AIMessage(content="done")]}

    record = execute_worker_payload(payload, graph_invoker=graph_invoker)
    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    architecture_error = next(
        error
        for error in record["errors"]
        if error["code"] == "ARCHITECTURE_EVIDENCE_INCOMPLETE"
    )
    for issue_code in (
        "TASK_CALL_COUNT_MISMATCH",
        "SUCCESSFUL_TASK_CALL_COUNT_MISMATCH",
        "FORBIDDEN_DELEGATION_OBSERVED",
    ):
        assert issue_code in architecture_error["message"]


def test_worker_runner_fails_terminal_on_observation_timestamp_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _worker_payload(tmp_path, snapshot={})
    payload.pop("system_snapshot")
    payload.pop("system_snapshot_sha256")
    monkeypatch.setattr(
        run_evidence_module,
        "observation_timestamp_trace_issues",
        lambda *_args, **_kwargs: ["OBSERVATION_TIMESTAMP_OUTSIDE_RUN"],
    )
    record = execute_worker_payload(
        payload,
        graph_invoker=lambda *_args: {"messages": [AIMessage(content="done")]},
    )
    assert record["terminal_state"] == "failed"
    assert any(
        error["code"] == "ARCHITECTURE_EVIDENCE_INCOMPLETE"
        and "OBSERVATION_TIMESTAMP_OUTSIDE_RUN" in error["message"]
        for error in record["errors"]
    )


def test_worker_runner_fails_closed_when_typed_package_artifact_drifts(
    tmp_path: Path,
) -> None:
    # This runner regression does not need to import/build the provider harness.
    payload = _worker_payload(tmp_path, snapshot={})
    payload.pop("system_snapshot")
    payload.pop("system_snapshot_sha256")

    def graph_invoker(_case, worker_payload, _telemetry):
        workspace = (
            Path(worker_payload["workspace_root"]) / worker_payload["thread_id"]
        )
        run_id = worker_payload["task_run_id"]
        task_id = worker_payload["case"]["case_id"]
        artifact = workspace / "outputs" / "products" / "result.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"original")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        contract_dir = workspace / "outputs" / "runs" / run_id / "contracts"
        route_dir = workspace / "outputs" / "runs" / run_id / "route"
        contract_dir.mkdir(parents=True)
        route_dir.mkdir(parents=True)
        now = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)
        plan = TaskPlan(
            artifact_id="plan-artifact-gate",
            run_id=run_id,
            task_id=task_id,
            created_at_utc=now,
            status=ContractStatus.READY,
            original_request="Return an artifact-backed answer.",
            normalized_objective="Return an artifact-backed answer.",
        )
        report = EvidenceReport(
            artifact_id="report-artifact-gate",
            run_id=run_id,
            task_id=task_id,
            created_at_utc=now,
            status=ContractStatus.READY,
            final_status="completed",
            direct_answer="The original artifact passed analysis.",
            representative_artifacts=[
                ArtifactRecord(
                    path="outputs/products/result.bin",
                    sha256=digest,
                    bytes=artifact.stat().st_size,
                )
            ],
        )
        (contract_dir / "task_plan__plan-artifact-gate.json").write_text(
            canonical_json(plan), encoding="utf-8"
        )
        (contract_dir / "evidence_report__report-artifact-gate.json").write_text(
            canonical_json(report), encoding="utf-8"
        )
        state = RouteState(run_id=run_id, task_id=task_id)
        (route_dir / "route_state.json").write_text(
            canonical_json(state), encoding="utf-8"
        )
        artifact.write_bytes(b"tampered after package persistence")
        return {"messages": [AIMessage(content="done")]}

    record = execute_worker_payload(payload, graph_invoker=graph_invoker)
    validate_run_record(record)
    assert record["internal_evidence"]["valid"] is True
    assert record["terminal_state"] == "failed"
    assert record["errors"][-1] == {
        "code": PACKAGE_ARTIFACT_INTEGRITY_MISMATCH,
        "message": (
            "post-run typed-package artifact integrity gate failed: "
            "PACKAGE_ARTIFACT_INTEGRITY_MISMATCH"
        ),
    }


def test_runner_import_before_worker_env_still_persists_contracts_in_batch_workspace(
    tmp_path: Path,
) -> None:
    """Regress the eager storage_manager import that escaped batch isolation."""

    script = r'''
import json
import os
from pathlib import Path
import sys

from benchmark_runtime.runner import execute_worker_payload

assert "storage_manager" not in sys.modules, "runner imported storage_manager before worker env setup"

test_root = Path(sys.argv[1]).resolve()
workspace_root = test_root / "workspaces"
workspace_root.mkdir()
thread_id = sys.argv[2]
task_run_id = "task-run-isolation"
case_id = "case-isolation"
payload = {
    "case": {
        "schema_version": "ntl-benchmark.case.v1",
        "case_id": case_id,
        "prompt": "Create the minimum architecture evidence.",
        "inputs": [],
        "metadata": {},
    },
    "cases_base_dir": str(test_root),
    "workspace_root": str(workspace_root),
    "result_path": str(test_root / "unused-record.json"),
    "telemetry_path": str(test_root / "unused-record.json.telemetry.json"),
    "batch_run_id": "batch-isolation",
    "task_run_id": task_run_id,
    "thread_id": thread_id,
    "model": "deepseek-v4-flash",
    "architecture_mode": "full",
    "request_timeout_seconds": 30,
    "task_timeout_seconds": 60.0,
    "recursion_limit": 20,
    "system_git_sha": "a" * 40,
    "system_git_dirty": False,
    "system_git_status_sha256": "b" * 64,
    "cases_sha256": "c" * 64,
    "case_sha256": "d" * 64,
    "submitted_at": "2026-08-12T00:00:00+00:00",
    "wall_clock_scope": "parent_process_start_to_worker_exit",
}

def graph_invoker(_case, _payload, _telemetry):
    from orchestration.contract_tools import (
        record_route_transition,
        save_evidence_report,
        save_task_plan,
    )
    from storage_manager import storage_manager

    assert storage_manager.base_dir.resolve() == workspace_root.resolve()
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"task_run_id": task_run_id, "case_id": case_id},
    }
    plan = save_task_plan(
        {
            "artifact_id": "plan-isolation",
            "created_at_utc": "2026-08-12T00:00:00Z",
            "status": "ready",
            "original_request": "Create the minimum architecture evidence.",
            "normalized_objective": "Create the minimum architecture evidence.",
        },
        config=config,
    )
    assert plan["status"] == "success", plan
    route = record_route_transition(
        run_id=task_run_id,
        task_id=case_id,
        target_status="planning",
        reason="Persist the tested route.",
        config=config,
    )
    assert route["status"] == "success", route
    report = save_evidence_report(
        {
            "artifact_id": "report-isolation",
            "created_at_utc": "2026-08-12T00:00:01Z",
            "status": "ready",
            "final_status": "completed",
            "direct_answer": "Minimum evidence persisted.",
        },
        config=config,
    )
    assert report["status"] == "success", report
    return {"messages": [{"type": "ai", "content": "done"}]}

record = execute_worker_payload(payload, graph_invoker=graph_invoker)
(test_root / "record.json").write_text(json.dumps(record), encoding="utf-8")
'''
    thread_id = f"isolation-{tmp_path.name}"
    environment = os.environ.copy()
    environment.pop("NTL_USER_DATA_DIR", None)
    environment.update(
        {
            "LANGCHAIN_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "LANGSMITH_TRACING": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(tmp_path), thread_id],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    record = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    workspace = tmp_path / "workspaces" / thread_id
    assert record["terminal_state"] == "succeeded"
    assert record["final_answer"] == "Minimum evidence persisted."
    assert record["internal_evidence"]["package_counts"]["TaskPlan"] == 1
    assert record["internal_evidence"]["package_counts"]["EvidenceReport"] == 1
    assert len(record["internal_evidence"]["route_states"]) == 1
    assert (
        workspace
        / "outputs"
        / "runs"
        / "task-run-isolation"
        / "contracts"
        / "task_plan__plan-isolation.json"
    ).is_file()
    assert not (REPO_ROOT / "user_data" / thread_id).exists()


def test_batch_manifest_payload_and_formal_context_share_one_snapshot(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, "case-a", "case-b")
    output_dir = tmp_path / "batch"

    def launcher(_payload_path: Path, payload: dict[str, object], _repo: Path):
        local = dict(payload)
        local["wall_clock_scope"] = "parent_process_start_to_worker_exit"
        return _minimal_run_record(local)

    args = Namespace(
        cases=str(cases_path),
        output_dir=str(output_dir),
        model="deepseek-v4-flash",
        architecture_mode="full",
        max_workers=2,
        task_timeout_seconds=60.0,
        request_timeout_seconds=30,
        recursion_limit=20,
        case_id=[],
    )
    assert run_batch(args, launcher=launcher) == 0
    manifest = json.loads((output_dir / "batch-manifest.json").read_text(encoding="utf-8"))
    payload = json.loads(next((output_dir / "control").glob("*.json")).read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in (output_dir / "task-runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    digest = manifest["system_snapshot_sha256"]
    assert digest == system_snapshot_sha256(manifest["system_snapshot"])
    assert payload["system_snapshot_sha256"] == digest
    telemetry_path = Path(payload["telemetry_path"])
    assert telemetry_path.parent == output_dir / "task-records"
    assert telemetry_path.parent != Path(payload["workspace_root"])
    assert ".benchmark-telemetry.json" not in str(telemetry_path)
    assert all(record["environment"]["system_snapshot_sha256"] == digest for record in records)
    validate_run_batch(records)

    changed = deepcopy(records)
    changed_snapshot = deepcopy(changed[1]["environment"]["system_snapshot"])
    first_code = next(iter(changed_snapshot["code_hashes"].values()))
    first_code["sha256"] = "f" * 64
    changed[1]["environment"]["system_snapshot"] = changed_snapshot
    changed[1]["environment"]["system_snapshot_sha256"] = system_snapshot_sha256(
        changed_snapshot
    )
    with pytest.raises(ContractError, match="same model, code, and runtime context"):
        validate_run_batch(changed)
