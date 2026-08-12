"""Compact post-run inventory of persisted internal NTL-GPT evidence.

The inventory deliberately contains identity metadata and checksums only.  It
does not copy package bodies into the run record, so benchmark Gold/evaluator
material cannot be introduced through this post-run evidence surface.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from typing import Any, Mapping

from contracts.agent_packages import (
    AnalysisPackage,
    EngineerDecision,
    EventContext,
    EvidenceReport,
    HandoffEnvelope,
    ObservationPackage,
    TaskPlan,
    canonical_json,
)
from orchestration.route_state import RouteState


INTERNAL_EVIDENCE_SCHEMA = "ntl-benchmark.internal-evidence.v1"
_PACKAGE_TYPES = (
    "TaskPlan",
    "EventContext",
    "ObservationPackage",
    "AnalysisPackage",
    "EvidenceReport",
)
_SHA256_HEX = frozenset("0123456789abcdef")
_MAX_INTERNAL_JSON_BYTES = 10 * 1024 * 1024
_CONTRACT_MODELS = {
    "TaskPlan": TaskPlan,
    "EventContext": EventContext,
    "ObservationPackage": ObservationPackage,
    "AnalysisPackage": AnalysisPackage,
    "EvidenceReport": EvidenceReport,
}
_ARCHITECTURE_MODES = frozenset({"full", "single_agent"})
_ARCHITECTURE_EXPECTATION_FIELDS = frozenset(
    {
        "required_package_types",
        "require_completed_route",
        "required_specialist",
        "require_accepted_handoff_decision",
        "forbid_delegation",
    }
)
_SPECIALIST_TYPES = frozenset(
    {"NTL_Data_Searcher", "NTL_Analyst", "NTL_Event_Tracker"}
)
_PACKAGE_ISSUE_NAMES = {
    "TaskPlan": "TASK_PLAN",
    "EventContext": "EVENT_CONTEXT",
    "ObservationPackage": "OBSERVATION_PACKAGE",
    "AnalysisPackage": "ANALYSIS_PACKAGE",
    "EvidenceReport": "EVIDENCE_REPORT",
}
PACKAGE_ARTIFACT_INTEGRITY_MISMATCH = "PACKAGE_ARTIFACT_INTEGRITY_MISMATCH"
_EVALUATOR_ONLY_KEYS = frozenset(
    {
        "gold",
        "gold_answer",
        "gold_answers",
        "gold_contract",
        "judge_packet",
        "judge_prompt",
        "evaluator_prompt",
        "reference_answer",
        "expected_score",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _linklike(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = int(getattr(os.lstat(path), "st_file_attributes", 0))
    except (FileNotFoundError, OSError):
        return False
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _declared_local_artifact_records(value: Any):
    """Yield typed-package mappings that declare a complete local artifact.

    Artifact-bearing fields are intentionally discovered by their complete
    ``path``/``sha256``/``bytes`` identity rather than by a fixed field name.
    This covers strict ``ArtifactRecord`` fields as well as extensible records
    such as ``EvidenceReport.source_and_artifact_links``.  A path-only field
    (for example ``artifact_manifest_path``) is not an integrity declaration.
    """

    if isinstance(value, Mapping):
        if {"path", "sha256", "bytes"}.issubset(value):
            yield value
        for nested in value.values():
            yield from _declared_local_artifact_records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _declared_local_artifact_records(nested)


def _resolve_declared_workspace_artifact(path_value: Any, *, outputs_root: Path) -> Path:
    """Resolve one declared artifact without leaving the tested workspace."""

    if not isinstance(path_value, str):
        raise ValueError("artifact path is not text")
    raw = path_value.strip().replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    if not raw or "\x00" in raw or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("unsafe artifact path")
    workspace_root = outputs_root.parent
    if raw.startswith("/data/processed/"):
        raw = raw[len("/data/processed/") :]
        declared_root = outputs_root
    elif raw.startswith("/data/raw/"):
        raw = raw[len("/data/raw/") :]
        declared_root = workspace_root / "inputs"
    elif raw.startswith("outputs/"):
        raw = raw[len("outputs/") :]
        declared_root = outputs_root
    elif raw.startswith("inputs/"):
        raw = raw[len("inputs/") :]
        declared_root = workspace_root / "inputs"
    elif raw.startswith("/"):
        raise ValueError("unsafe artifact root")
    else:
        # Strict ArtifactRecord fields historically allow an output-relative
        # path without the explicit ``outputs/`` prefix.
        declared_root = outputs_root
    relative = PurePosixPath(raw)
    if (
        not raw
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("unsafe artifact path")

    if _linklike(workspace_root) or _linklike(declared_root):
        raise ValueError("unsafe workspace artifact root")
    resolved_workspace = workspace_root.resolve(strict=True)
    resolved_declared_root = declared_root.resolve(strict=True)
    if not _inside(resolved_declared_root, resolved_workspace):
        raise ValueError("declared root escaped workspace")
    lexical = declared_root.joinpath(*relative.parts)
    cursor = declared_root
    for part in relative.parts:
        cursor = cursor / part
        if _linklike(cursor):
            raise ValueError("artifact path traverses a link")
    resolved = lexical.resolve(strict=True)
    if not _inside(resolved, resolved_declared_root) or not _inside(
        resolved, resolved_workspace
    ):
        raise ValueError("artifact escaped tested workspace")
    if not lexical.is_file() or lexical.stat().st_nlink > 1:
        raise ValueError("artifact is not an independent regular file")
    return lexical


def _opaque_package_record_matches(
    record: Mapping[str, Any],
    *,
    package_inventory: list[dict[str, Any]],
    opaque_package_bindings: Mapping[str, Mapping[str, Any]] | None,
) -> bool:
    """Bind an opaque model-facing handle to one persisted current-run package."""

    path = record.get("path")
    if not isinstance(path, str) or not path.startswith("package/"):
        return False
    token = path[len("package/") :]
    if (
        len(token) != 32
        or token != token.casefold()
        or not set(token).issubset(_SHA256_HEX)
    ):
        return False
    digest = str(record.get("sha256") or "").casefold()
    byte_count = record.get("bytes")

    def metadata_matches(candidate: Mapping[str, Any]) -> bool:
        if candidate.get("sha256") != digest or candidate.get("bytes") != byte_count:
            return False
        for field in ("artifact_id", "artifact_type"):
            declared = record.get(field)
            if declared is not None and candidate.get(field) != declared:
                return False
        return True

    if opaque_package_bindings is not None:
        binding = opaque_package_bindings.get(path)
        if not isinstance(binding, Mapping):
            return False
        expected_relative = binding.get("relative_path")
        matches = [
            candidate
            for candidate in package_inventory
            if metadata_matches(candidate)
            and candidate.get("artifact_id") == binding.get("artifact_id")
            and candidate.get("artifact_type") == binding.get("artifact_type")
            and candidate.get("sha256") == binding.get("sha256")
            and (
                expected_relative is None
                or candidate.get("relative_path") == expected_relative
            )
        ]
        return len(matches) == 1

    # An abnormal/parent-process collector cannot recover the worker's
    # in-memory token registry. Fail closed unless digest+bytes (and any
    # declared type/id) select exactly one persisted package in this run.
    return sum(1 for candidate in package_inventory if metadata_matches(candidate)) == 1


def _record_identity(path: Path, *, outputs_root: Path) -> dict[str, Any]:
    return {
        "relative_path": "outputs/" + path.relative_to(outputs_root).as_posix(),
        "sha256": _sha256(path),
        "bytes": int(path.stat().st_size),
    }


def _validate_contract_payload(raw: dict[str, Any]):
    """Validate a package without importing storage_manager-bound runtime I/O."""

    stack: list[Any] = [raw]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().casefold().replace("-", "_").replace(" ", "_")
                if normalized in _EVALUATOR_ONLY_KEYS:
                    raise ValueError("evaluator-only field in runtime contract")
                stack.append(nested)
        elif isinstance(value, list):
            stack.extend(value)
    artifact_type = str(raw.get("artifact_type") or "").strip()
    model = _CONTRACT_MODELS.get(artifact_type)
    if model is None:
        raise ValueError("unsupported package type")
    return model.model_validate(raw)


def _invalid_identity(
    path: Path,
    *,
    outputs_root: Path,
    category: str,
    issue_code: str,
) -> dict[str, Any]:
    try:
        identity = _record_identity(path, outputs_root=outputs_root)
    except (OSError, ValueError):
        identity = {
            "relative_path": "outputs/" + path.relative_to(outputs_root).as_posix(),
            "sha256": "0" * 64,
            "bytes": 0,
        }
    return {**identity, "category": category, "issue_code": issue_code}


def _candidate_files(runs_root: Path) -> list[tuple[str, Path, str]]:
    candidates: list[tuple[str, Path, str]] = []
    for run_dir in sorted(runs_root.iterdir(), key=lambda item: item.name.casefold()):
        if not run_dir.is_dir() or _linklike(run_dir):
            candidates.append(("run_tree", run_dir, run_dir.name))
            continue
        for category, relative in (
            ("package", "contracts"),
            ("handoff", "handoffs"),
            ("decision", "decisions"),
            ("route_state", "route"),
        ):
            directory = run_dir / relative
            if not directory.exists():
                continue
            if not directory.is_dir() or _linklike(directory):
                candidates.append((category, directory, run_dir.name))
                continue
            for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix().casefold()):
                if path.is_file() or _linklike(path):
                    candidates.append((category, path, run_dir.name))
    return candidates


def collect_internal_evidence(outputs_dir: str | Path) -> dict[str, Any]:
    """Validate and inventory internal packages beneath ``outputs/runs``.

    Invalid records are represented by a path/hash plus a stable issue code;
    exception text and raw JSON are intentionally omitted.
    """

    outputs_root = Path(outputs_dir).resolve(strict=False)
    packages: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    route_states: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    runs_root = outputs_root / "runs"

    if runs_root.exists() and (not runs_root.is_dir() or _linklike(runs_root)):
        invalid.append(
            {
                "relative_path": "outputs/runs",
                "sha256": "0" * 64,
                "bytes": 0,
                "category": "run_tree",
                "issue_code": "UNSAFE_RUN_TREE",
            }
        )
    elif runs_root.is_dir():
        for category, path, expected_run_id in _candidate_files(runs_root):
            if category == "run_tree" or not path.is_file():
                invalid.append(
                    _invalid_identity(
                        path,
                        outputs_root=outputs_root,
                        category=category,
                        issue_code="UNSAFE_INTERNAL_PATH",
                    )
                )
                continue
            try:
                resolved = path.resolve(strict=True)
                if _linklike(path) or not _inside(resolved, outputs_root):
                    raise ValueError("unsafe path")
                if path.stat().st_nlink > 1:
                    raise ValueError("hard link")
                if path.suffix.casefold() != ".json":
                    raise TypeError("not JSON")
                if path.stat().st_size > _MAX_INTERNAL_JSON_BYTES:
                    raise OverflowError("too large")
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise TypeError("not object")
                identity = _record_identity(path, outputs_root=outputs_root)

                if category == "package":
                    value = _validate_contract_payload(raw)
                    if value.run_id != expected_run_id:
                        raise ValueError("run mismatch")
                    if hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest() != identity["sha256"]:
                        raise ValueError("noncanonical")
                    packages.append(
                        {
                            **identity,
                            "artifact_type": value.artifact_type,
                            "artifact_id": value.artifact_id,
                            "run_id": value.run_id,
                            "task_id": value.task_id,
                            "producer": str(value.producer),
                            "status": str(value.status),
                        }
                    )
                elif category == "handoff":
                    value = HandoffEnvelope.model_validate(raw)
                    if value.run_id != expected_run_id:
                        raise ValueError("run mismatch")
                    if hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest() != identity["sha256"]:
                        raise ValueError("noncanonical")
                    handoffs.append(
                        {
                            **identity,
                            "handoff_id": value.handoff_id,
                            "assignment_id": value.assignment_id,
                            "run_id": value.run_id,
                            "task_id": value.task_id,
                            "producer": str(value.producer),
                            "status": str(value.status),
                            "package_type": value.package.artifact_type if value.package else None,
                            "validation_verdict": value.validation_verdict,
                        }
                    )
                elif category == "decision":
                    value = EngineerDecision.model_validate(raw)
                    if value.run_id != expected_run_id:
                        raise ValueError("run mismatch")
                    if hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest() != identity["sha256"]:
                        raise ValueError("noncanonical")
                    decisions.append(
                        {
                            **identity,
                            "decision_id": value.decision_id,
                            "handoff_id": value.handoff_id,
                            "assignment_id": value.assignment_id,
                            "run_id": value.run_id,
                            "task_id": value.task_id,
                            "decision": str(value.decision),
                            "package_type": value.package.artifact_type if value.package else None,
                        }
                    )
                elif category == "route_state":
                    if path.name != "route_state.json":
                        raise ValueError("unexpected route file")
                    value = RouteState.model_validate(raw)
                    if value.run_id != expected_run_id:
                        raise ValueError("run mismatch")
                    if hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest() != identity["sha256"]:
                        raise ValueError("noncanonical")
                    route_states.append(
                        {
                            **identity,
                            "run_id": value.run_id,
                            "task_id": value.task_id,
                            "status": str(value.status),
                            "revision_count": value.revision_count,
                            "max_revisions": value.max_revisions,
                            "event_count": len(value.events),
                            "accepted_package_types": sorted(value.accepted_packages),
                            "skipped_specialists": sorted(value.skipped_specialists),
                            "terminal": value.terminal,
                        }
                    )
            except json.JSONDecodeError:
                issue_code = "INVALID_INTERNAL_JSON"
                invalid.append(
                    _invalid_identity(
                        path,
                        outputs_root=outputs_root,
                        category=category,
                        issue_code=issue_code,
                    )
                )
            except (OSError, UnicodeError, TypeError, ValueError, OverflowError):
                issue_code = "INVALID_INTERNAL_RECORD"
                invalid.append(
                    _invalid_identity(
                        path,
                        outputs_root=outputs_root,
                        category=category,
                        issue_code=issue_code,
                    )
                )

    packages.sort(key=lambda row: row["relative_path"].casefold())
    handoffs.sort(key=lambda row: row["relative_path"].casefold())
    decisions.sort(key=lambda row: row["relative_path"].casefold())
    route_states.sort(key=lambda row: row["relative_path"].casefold())
    invalid.sort(key=lambda row: row["relative_path"].casefold())
    package_counts = {
        package_type: sum(1 for row in packages if row["artifact_type"] == package_type)
        for package_type in _PACKAGE_TYPES
    }
    run_ids = sorted(
        {
            str(row["run_id"])
            for group in (packages, handoffs, decisions, route_states)
            for row in group
        }
    )
    return {
        "schema_version": INTERNAL_EVIDENCE_SCHEMA,
        "content_policy": "identity_metadata_and_hashes_only",
        "valid": not invalid,
        "package_counts": package_counts,
        "packages": packages,
        "handoffs": handoffs,
        "decisions": decisions,
        "route_states": route_states,
        "invalid_records": invalid,
        "issue_count": len(invalid),
        "discovered_run_ids": run_ids,
    }


def package_artifact_integrity_issues(
    outputs_dir: str | Path,
    value: Any,
    *,
    expected_run_id: str,
    expected_task_id: str,
    opaque_package_bindings: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Recheck every local artifact identity declared by current-run packages.

    This is deliberately a post-run, workspace-bound check.  Package bodies
    are reopened only from identities already collected beneath
    ``outputs/runs``; no case reference, evaluator packet, or benchmark Gold is
    consulted.  Any missing file, unsafe/link-like path, or digest/byte drift
    collapses to one stable non-sensitive issue code.
    """

    try:
        evidence = validate_internal_evidence(value)
        outputs_root = Path(outputs_dir)
        resolved_outputs = outputs_root.resolve(strict=True)
        if not resolved_outputs.is_dir() or _linklike(outputs_root):
            raise ValueError("unsafe output root")
        candidates = [
            row
            for row in evidence["packages"]
            if row.get("run_id") == expected_run_id
        ]
        for identity in candidates:
            relative = str(identity.get("relative_path") or "")
            logical = PurePosixPath(relative)
            if (
                not relative.startswith("outputs/runs/")
                or logical.is_absolute()
                or any(part in {"", ".", ".."} for part in logical.parts)
            ):
                raise ValueError("unsafe package identity")
            package_path = outputs_root.joinpath(*logical.parts[1:])
            cursor = outputs_root
            for part in logical.parts[1:]:
                cursor = cursor / part
                if _linklike(cursor):
                    raise ValueError("package path traverses a link")
            resolved_package = package_path.resolve(strict=True)
            if (
                not _inside(resolved_package, resolved_outputs)
                or not package_path.is_file()
                or package_path.stat().st_nlink > 1
                or _sha256(package_path) != identity.get("sha256")
                or package_path.stat().st_size != identity.get("bytes")
            ):
                raise ValueError("package identity drift")
            raw = json.loads(package_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("package is not an object")
            package = _validate_contract_payload(raw)
            if package.run_id != expected_run_id or package.task_id != expected_task_id:
                raise ValueError("package runtime identity mismatch")
            if canonical_json(package).encode("utf-8") != package_path.read_bytes():
                raise ValueError("package is not canonical")

            for record in _declared_local_artifact_records(raw):
                digest = record.get("sha256")
                byte_count = record.get("bytes")
                if (
                    not _valid_digest(digest)
                    or isinstance(byte_count, bool)
                    or not isinstance(byte_count, int)
                    or byte_count < 0
                ):
                    raise ValueError("invalid declared artifact identity")
                path_value = record.get("path")
                if isinstance(path_value, str) and path_value.startswith("package/"):
                    if not _opaque_package_record_matches(
                        record,
                        package_inventory=candidates,
                        opaque_package_bindings=opaque_package_bindings,
                    ):
                        raise ValueError("opaque package artifact mismatch")
                    continue
                artifact_path = _resolve_declared_workspace_artifact(
                    path_value, outputs_root=outputs_root
                )
                if (
                    artifact_path.stat().st_size != byte_count
                    or _sha256(artifact_path) != str(digest).casefold()
                ):
                    raise ValueError("declared artifact identity drift")
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return [PACKAGE_ARTIFACT_INTEGRITY_MISMATCH]
    return []


def minimum_architecture_evidence_issues(
    value: Any,
    *,
    architecture_mode: str,
    expected_run_id: str,
    expected_task_id: str,
) -> list[str]:
    """Return stable issue codes for the minimum auditable architecture trace.

    Both Full and matched Single-Agent must persist exactly one TaskPlan and one
    final EvidenceReport for the tested task, plus at least one route-state
    checkpoint.  This is a system-compliance gate, not a scientific score.
    """

    if architecture_mode not in {"full", "single_agent"}:
        return ["UNSUPPORTED_ARCHITECTURE_MODE"]
    try:
        evidence = validate_internal_evidence(value)
    except ValueError:
        return ["INVALID_INTERNAL_EVIDENCE"]
    issues: list[str] = []
    if evidence["valid"] is not True:
        issues.append("INVALID_INTERNAL_EVIDENCE")

    expected_packages = [
        row
        for row in evidence["packages"]
        if row.get("run_id") == expected_run_id and row.get("task_id") == expected_task_id
    ]
    package_codes = {
        "TaskPlan": "TASK_PLAN",
        "EvidenceReport": "EVIDENCE_REPORT",
    }
    for package_type, code_name in package_codes.items():
        matching = [
            row for row in expected_packages if row.get("artifact_type") == package_type
        ]
        total = int(evidence["package_counts"].get(package_type, 0))
        if len(matching) == 0:
            issues.append(f"MISSING_{code_name}")
        elif len(matching) > 1 or total != 1:
            issues.append(f"NON_UNIQUE_{code_name}")

    matching_routes = [
        row
        for row in evidence["route_states"]
        if row.get("run_id") == expected_run_id and row.get("task_id") == expected_task_id
    ]
    if not matching_routes:
        issues.append("MISSING_ROUTE_STATE")
    unexpected_run_ids = [
        run_id for run_id in evidence["discovered_run_ids"] if run_id != expected_run_id
    ]
    if unexpected_run_ids:
        issues.append("UNEXPECTED_INTERNAL_RUN_ID")
    return list(dict.fromkeys(issues))


def validate_architecture_expectations(value: Any) -> dict[str, dict[str, Any]]:
    """Validate and normalize optional per-mode architecture expectations.

    The contract is deliberately small and JSON-shaped. Unknown mode or field
    names are rejected so a typo cannot silently disable a benchmark gate.
    Missing expectations are valid and preserve the existing minimum evidence
    gate.
    """

    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("architecture_expectations must be an object")
    unknown_modes = sorted(set(value) - _ARCHITECTURE_MODES)
    if unknown_modes:
        raise ValueError(
            "architecture_expectations has unsupported mode keys: "
            + ", ".join(str(mode) for mode in unknown_modes)
        )

    normalized: dict[str, dict[str, Any]] = {}
    for mode in sorted(value):
        raw = value[mode]
        if not isinstance(raw, Mapping):
            raise ValueError(f"architecture_expectations.{mode} must be an object")
        unknown_fields = sorted(set(raw) - _ARCHITECTURE_EXPECTATION_FIELDS)
        if unknown_fields:
            raise ValueError(
                f"architecture_expectations.{mode} has unsupported fields: "
                + ", ".join(str(field) for field in unknown_fields)
            )
        entry: dict[str, Any] = {}
        if "required_package_types" in raw:
            packages = raw["required_package_types"]
            if (
                not isinstance(packages, list)
                or not packages
                or any(not isinstance(package, str) for package in packages)
            ):
                raise ValueError(
                    f"architecture_expectations.{mode}.required_package_types "
                    "must be a non-empty list of strings"
                )
            unknown_packages = sorted(set(packages) - set(_PACKAGE_TYPES))
            if unknown_packages:
                raise ValueError(
                    f"architecture_expectations.{mode}.required_package_types "
                    "contains unsupported package types: "
                    + ", ".join(unknown_packages)
                )
            if len(packages) != len(set(packages)):
                raise ValueError(
                    f"architecture_expectations.{mode}.required_package_types "
                    "must not contain duplicates"
                )
            entry["required_package_types"] = [
                package for package in _PACKAGE_TYPES if package in packages
            ]

        for field in (
            "require_completed_route",
            "require_accepted_handoff_decision",
            "forbid_delegation",
        ):
            if field in raw:
                if not isinstance(raw[field], bool):
                    raise ValueError(
                        f"architecture_expectations.{mode}.{field} must be boolean"
                    )
                entry[field] = raw[field]

        if "required_specialist" in raw:
            specialist = raw["required_specialist"]
            if not isinstance(specialist, str) or specialist not in _SPECIALIST_TYPES:
                raise ValueError(
                    f"architecture_expectations.{mode}.required_specialist must be one of: "
                    + ", ".join(sorted(_SPECIALIST_TYPES))
                )
            entry["required_specialist"] = specialist

        if mode == "single_agent" and "required_specialist" in entry:
            raise ValueError(
                "architecture_expectations.single_agent cannot require a specialist"
            )
        if mode == "single_agent" and entry.get(
            "require_accepted_handoff_decision"
        ):
            raise ValueError(
                "architecture_expectations.single_agent cannot require an accepted handoff"
            )
        if entry.get("required_specialist") and entry.get("forbid_delegation"):
            raise ValueError(
                f"architecture_expectations.{mode} cannot both require a specialist "
                "and forbid delegation"
            )
        normalized[str(mode)] = entry
    return normalized


def architecture_expectation_issues(
    value: Any,
    *,
    tool_trace: Any,
    expectations: Any,
    architecture_mode: str,
    expected_run_id: str,
    expected_task_id: str,
) -> list[str]:
    """Return stable issue codes for optional case-level architecture gates."""

    try:
        configured = validate_architecture_expectations(expectations)
    except ValueError:
        return ["INVALID_ARCHITECTURE_EXPECTATIONS"]
    expected = configured.get(architecture_mode)
    if expected is None:
        return []
    try:
        evidence = validate_internal_evidence(value)
    except ValueError:
        return ["INVALID_INTERNAL_EVIDENCE"]

    issues: list[str] = []
    expected_packages = [
        row
        for row in evidence["packages"]
        if row.get("run_id") == expected_run_id
        and row.get("task_id") == expected_task_id
    ]
    for package_type in expected.get("required_package_types", []):
        if not any(
            row.get("artifact_type") == package_type and row.get("status") == "ready"
            for row in expected_packages
        ):
            issues.append(f"MISSING_READY_{_PACKAGE_ISSUE_NAMES[package_type]}")

    matching_routes = [
        row
        for row in evidence["route_states"]
        if row.get("run_id") == expected_run_id
        and row.get("task_id") == expected_task_id
    ]
    if expected.get("require_completed_route") and not any(
        row.get("status") == "completed" and row.get("terminal") is True
        for row in matching_routes
    ):
        issues.append("MISSING_COMPLETED_ROUTE")

    if expected.get("require_accepted_handoff_decision"):
        matching_handoffs = {
            str(row.get("handoff_id")): row
            for row in evidence["handoffs"]
            if row.get("run_id") == expected_run_id
            and row.get("task_id") == expected_task_id
            and row.get("status") == "ready"
            and row.get("validation_verdict") == "passed"
        }
        accepted_pair = any(
            row.get("run_id") == expected_run_id
            and row.get("task_id") == expected_task_id
            and row.get("decision") == "accepted"
            and str(row.get("handoff_id")) in matching_handoffs
            and matching_handoffs[str(row.get("handoff_id"))].get("package_type")
            == row.get("package_type")
            for row in evidence["decisions"]
        )
        if not accepted_pair:
            issues.append("MISSING_ACCEPTED_HANDOFF_DECISION")

    trace = (
        [row for row in tool_trace if isinstance(row, Mapping)]
        if isinstance(tool_trace, list)
        else []
    )
    task_rows = [row for row in trace if row.get("tool_name") == "task"]
    specialist = expected.get("required_specialist")
    if specialist:
        specialist_tasks = [
            row
            for row in task_rows
            if row.get("status") == "succeeded"
            and isinstance(row.get("arguments"), Mapping)
            and row["arguments"].get("subagent_type") == specialist
        ]
        if not specialist_tasks:
            issues.append("MISSING_REQUIRED_SPECIALIST_TASK")
        task_ids = {
            str(row.get("tool_call_id"))
            for row in specialist_tasks
            if str(row.get("tool_call_id") or "").strip()
        }
        descendant_observed = any(
            row.get("tool_name") != "task"
            and isinstance(row.get("metadata"), Mapping)
            and row["metadata"].get("lc_agent_name") == specialist
            and bool(
                task_ids.intersection(
                    str(item)
                    for item in (row.get("ancestor_tool_call_ids") or [])
                )
            )
            for row in trace
        )
        if not descendant_observed:
            issues.append("MISSING_REQUIRED_SPECIALIST_DESCENDANT_TRACE")

    if expected.get("forbid_delegation") and task_rows:
        issues.append("FORBIDDEN_DELEGATION_OBSERVED")
    return list(dict.fromkeys(issues))


def canonical_evidence_report_answer(
    outputs_dir: str | Path,
    value: Any,
    *,
    expected_run_id: str,
    expected_task_id: str,
) -> str | None:
    """Return ``EvidenceReport.direct_answer`` only after full local validation.

    The compact evidence record continues to omit contract bodies.  This helper
    reopens the one expected report, rechecks its path, hash, canonical bytes,
    schema, and runtime identity, then exposes only its canonical answer to the
    runner.
    """

    try:
        evidence = validate_internal_evidence(value)
    except ValueError:
        return None
    candidates = [
        row
        for row in evidence["packages"]
        if row.get("artifact_type") == "EvidenceReport"
        and row.get("run_id") == expected_run_id
        and row.get("task_id") == expected_task_id
    ]
    if len(candidates) != 1 or int(evidence["package_counts"].get("EvidenceReport", 0)) != 1:
        return None
    outputs_root = Path(outputs_dir).resolve(strict=False)
    relative = str(candidates[0]["relative_path"])
    if not relative.startswith("outputs/"):
        return None
    path = (outputs_root / PurePosixPath(relative).relative_to("outputs")).resolve(strict=False)
    try:
        if not path.is_file() or _linklike(path) or path.stat().st_nlink > 1:
            return None
        if not _inside(path.resolve(strict=True), outputs_root):
            return None
        if _sha256(path) != candidates[0]["sha256"]:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        report = _validate_contract_payload(raw)
        if not isinstance(report, EvidenceReport):
            return None
        if report.run_id != expected_run_id or report.task_id != expected_task_id:
            return None
        canonical_sha = hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()
        if canonical_sha != candidates[0]["sha256"]:
            return None
        return report.direct_answer
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value.casefold()).issubset(_SHA256_HEX)
    )


def _safe_evidence_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("outputs/runs/"):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def validate_internal_evidence(value: Any) -> dict[str, Any]:
    """Validate the compact run-record representation."""

    if not isinstance(value, Mapping):
        raise ValueError("internal_evidence must be a JSON object")
    record = dict(value)
    required = {
        "schema_version",
        "content_policy",
        "valid",
        "package_counts",
        "packages",
        "handoffs",
        "decisions",
        "route_states",
        "invalid_records",
        "issue_count",
        "discovered_run_ids",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError("internal_evidence is missing fields: " + ", ".join(missing))
    if record["schema_version"] != INTERNAL_EVIDENCE_SCHEMA:
        raise ValueError("internal_evidence has the wrong schema_version")
    if record["content_policy"] != "identity_metadata_and_hashes_only":
        raise ValueError("internal_evidence has an invalid content_policy")
    if not isinstance(record["valid"], bool):
        raise ValueError("internal_evidence.valid must be boolean")
    all_paths: set[str] = set()
    for group_name in ("packages", "handoffs", "decisions", "route_states", "invalid_records"):
        rows = record[group_name]
        if not isinstance(rows, list):
            raise ValueError(f"internal_evidence.{group_name} must be a list")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"internal_evidence.{group_name} contains a non-object")
            relative_path = row.get("relative_path")
            if not _safe_evidence_path(relative_path):
                raise ValueError(f"internal_evidence.{group_name} contains an unsafe path")
            if relative_path in all_paths:
                raise ValueError("internal_evidence contains a duplicate path")
            all_paths.add(str(relative_path))
            if not _valid_digest(row.get("sha256")):
                raise ValueError(f"internal_evidence.{group_name} contains an invalid sha256")
            byte_count = row.get("bytes")
            if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
                raise ValueError(f"internal_evidence.{group_name} contains invalid bytes")
    invalid_count = len(record["invalid_records"])
    if record["issue_count"] != invalid_count or record["valid"] != (invalid_count == 0):
        raise ValueError("internal_evidence validity/count fields are inconsistent")
    counts = record["package_counts"]
    if not isinstance(counts, Mapping) or set(counts) != set(_PACKAGE_TYPES):
        raise ValueError("internal_evidence.package_counts has the wrong package types")
    observed = {
        package_type: sum(
            1 for row in record["packages"] if row.get("artifact_type") == package_type
        )
        for package_type in _PACKAGE_TYPES
    }
    if dict(counts) != observed:
        raise ValueError("internal_evidence.package_counts do not match packages")
    if not isinstance(record["discovered_run_ids"], list) or not all(
        isinstance(run_id, str) and run_id for run_id in record["discovered_run_ids"]
    ):
        raise ValueError("internal_evidence.discovered_run_ids must be strings")
    json.dumps(record, ensure_ascii=False, allow_nan=False)
    return record


__all__ = [
    "INTERNAL_EVIDENCE_SCHEMA",
    "PACKAGE_ARTIFACT_INTEGRITY_MISMATCH",
    "architecture_expectation_issues",
    "canonical_evidence_report_answer",
    "collect_internal_evidence",
    "minimum_architecture_evidence_issues",
    "package_artifact_integrity_issues",
    "validate_architecture_expectations",
    "validate_internal_evidence",
]
