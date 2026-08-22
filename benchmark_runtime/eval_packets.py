"""Build read-only, case-agnostic packets for external Luna evaluation."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import EVAL_PACKET_SCHEMA, LUNA_EVALUATOR_MODEL
from .contracts import (
    ContractError,
    UnsafePathError,
    atomic_write_json,
    canonical_json_sha256,
    load_case_records,
    load_eval_spec_records,
    load_run_records,
    path_is_linklike,
    resolve_within,
    unique_index,
    validate_case_record,
    validate_eval_spec_record,
    validate_run_record,
    validate_run_batch,
)


RecordSource = str | os.PathLike[str] | Sequence[Mapping[str, Any]]
PACKET_MANIFEST_SCHEMA = "ntl-benchmark.eval-packet-manifest.v1"
PACKET_MANIFEST_NAME = "packet-manifest.json"


def _records(
    source: RecordSource,
    *,
    loader: Any,
    validator: Any,
) -> list[dict[str, Any]]:
    if isinstance(source, (str, os.PathLike)):
        return loader(source)
    if not isinstance(source, Sequence):
        raise ContractError("record source must be a JSONL path or a sequence of records")
    return [validator(record) for record in source]


def _select_case_records(
    records: list[dict[str, Any]], requested: Sequence[str] | None, label: str
) -> list[dict[str, Any]]:
    requested_ids = [str(value) for value in (requested or [])]
    if not requested_ids:
        return records
    if len({value.casefold() for value in requested_ids}) != len(requested_ids):
        raise ContractError("selected case IDs must be unique ignoring case")
    indexed = unique_index(records, "case_id", label)
    missing = [case_id for case_id in requested_ids if case_id not in indexed]
    if missing:
        raise ContractError(f"selected case IDs are absent from {label}: {missing}")
    return [dict(indexed[case_id]) for case_id in requested_ids]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _workspace_snapshot(workspace: Path) -> dict[str, Any]:
    """Hash every tested-workspace file and record every directory."""

    if path_is_linklike(workspace):
        raise UnsafePathError(f"tested workspace root must not be a link or junction: {workspace}")
    if not workspace.is_dir():
        raise ContractError(f"tested workspace does not exist or is not a directory: {workspace}")
    files: list[dict[str, Any]] = []
    directories: list[str] = []
    for candidate in sorted(workspace.rglob("*"), key=lambda path: path.as_posix().casefold()):
        if path_is_linklike(candidate):
            raise UnsafePathError(f"tested workspace contains a link or junction: {candidate}")
        resolved = candidate.resolve(strict=True)
        if not _inside(resolved, workspace):
            raise UnsafePathError(f"tested workspace entry resolves outside workspace: {candidate}")
        relative_path = candidate.relative_to(workspace).as_posix()
        if candidate.is_dir():
            directories.append(relative_path)
        elif candidate.is_file():
            if candidate.stat().st_nlink > 1:
                raise UnsafePathError(f"tested workspace contains a hard-linked file: {candidate}")
            files.append(
                {
                    "relative_path": relative_path,
                    "sha256": _sha256(candidate),
                    "bytes": candidate.stat().st_size,
                }
            )
        else:
            raise UnsafePathError(f"tested workspace contains an unsupported entry: {candidate}")
    return {"directories": directories, "files": files}


def _packet_manifest_path(packet_root: Path) -> Path:
    return packet_root / PACKET_MANIFEST_NAME


def verified_packet_paths(packet_dir: str | os.PathLike[str]) -> list[Path]:
    """Verify packet manifest, exact packet set, and each packet checksum."""

    declared_packet_root = Path(packet_dir).expanduser()
    if path_is_linklike(declared_packet_root):
        raise UnsafePathError("evaluation packet directory must not be a link or junction")
    packet_root = declared_packet_root.resolve()
    if not packet_root.is_dir():
        raise ContractError(f"evaluation packet directory is missing: {packet_root}")
    manifest_path = _packet_manifest_path(packet_root)
    if not manifest_path.is_file():
        raise ContractError(f"evaluation packet manifest is missing: {manifest_path}")
    if (
        path_is_linklike(manifest_path)
        or manifest_path.stat().st_nlink > 1
    ):
        raise UnsafePathError("evaluation packet manifest must be an ordinary standalone file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"evaluation packet manifest is invalid: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != PACKET_MANIFEST_SCHEMA:
        raise ContractError("evaluation packet manifest has the wrong schema")
    rows = manifest.get("packets")
    if not isinstance(rows, list) or not rows:
        raise ContractError("evaluation packet manifest must contain packets")
    if manifest.get("packet_count") != len(rows):
        raise ContractError("evaluation packet manifest packet_count is inconsistent")
    manifest_batch_id = manifest.get("batch_run_id")
    if not isinstance(manifest_batch_id, str) or not manifest_batch_id:
        raise ContractError("evaluation packet manifest batch_run_id is required")
    protected_values = manifest.get("protected_workspace_paths")
    if not isinstance(protected_values, list) or not protected_values:
        raise ContractError(
            "evaluation packet manifest protected_workspace_paths must be a non-empty list"
        )
    protected_workspaces: list[Path] = []
    protected_keys: set[str] = set()
    for index, value in enumerate(protected_values):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(
                f"packet manifest protected_workspace_paths[{index}] must be an absolute path"
            )
        declared_workspace = Path(value).expanduser()
        if not declared_workspace.is_absolute():
            raise UnsafePathError(
                f"packet manifest protected_workspace_paths[{index}] must be absolute"
            )
        if path_is_linklike(declared_workspace):
            raise UnsafePathError("protected workspace must not be a link or junction")
        resolved_workspace = declared_workspace.resolve(strict=False)
        key = str(resolved_workspace).casefold()
        if key in protected_keys:
            raise ContractError("packet manifest protected workspace paths must be unique")
        protected_keys.add(key)
        protected_workspaces.append(resolved_workspace)
    normalized_protected_values = [str(path) for path in protected_workspaces]
    expected: list[Path] = []
    seen_names: set[str] = set()
    seen_cases: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ContractError(f"packet manifest packets[{index}] must be an object")
        for field in ("case_id", "task_run_id", "relative_path", "sha256"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ContractError(f"packet manifest packets[{index}].{field} is required")
        relative_path = row["relative_path"]
        if Path(relative_path).name != relative_path or not relative_path.endswith(".eval-packet.json"):
            raise UnsafePathError(f"unsafe packet manifest relative_path: {relative_path}")
        name_key = relative_path.casefold()
        case_key = row["case_id"].casefold()
        if name_key in seen_names or case_key in seen_cases:
            raise ContractError("packet manifest contains duplicate packet names or case IDs")
        seen_names.add(name_key)
        seen_cases.add(case_key)
        packet_path = (packet_root / relative_path).absolute()
        if not _inside(packet_path, packet_root) or not packet_path.is_file():
            raise ContractError(f"manifest packet is missing or unsafe: {packet_path}")
        if (
            path_is_linklike(packet_path)
            or packet_path.stat().st_nlink > 1
        ):
            raise UnsafePathError(f"evaluation packet must be an ordinary standalone file: {packet_path}")
        if _sha256(packet_path).lower() != row["sha256"].lower():
            raise ContractError(f"evaluation packet checksum changed: {relative_path}")
        try:
            packet_identity = json.loads(packet_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"evaluation packet is invalid JSON: {relative_path}") from exc
        if not isinstance(packet_identity, dict) or any(
            packet_identity.get(field) != expected_value
            for field, expected_value in (
                ("batch_run_id", manifest_batch_id),
                ("case_id", row["case_id"]),
                ("task_run_id", row["task_run_id"]),
                ("eval_spec_sha256", row.get("eval_spec_sha256")),
                ("protected_workspace_paths", normalized_protected_values),
            )
        ):
            raise ContractError(f"packet identity does not match manifest: {relative_path}")
        expected.append(packet_path)
    expected_inventory = {
        manifest_path.absolute(),
        *(packet_path.absolute() for packet_path in expected),
    }
    actual_entries = list(packet_root.iterdir())
    if any(
        not entry.is_file()
        or path_is_linklike(entry)
        or entry.stat().st_nlink > 1
        for entry in actual_entries
    ):
        raise ContractError("packet directory must contain only ordinary manifest and packet files")
    actual_inventory = {entry.absolute() for entry in actual_entries}
    if actual_inventory != expected_inventory:
        raise ContractError("packet directory contents do not exactly match packet manifest")
    return expected


def _declared_workspace(run_record: Mapping[str, Any]) -> Path:
    declared_path = Path(run_record["environment"]["workspace"]).expanduser()
    if path_is_linklike(declared_path):
        raise UnsafePathError("run_record.environment.workspace must not be a link or junction")
    declared = declared_path.resolve(strict=False)
    if not declared.is_dir():
        raise ContractError(f"run workspace does not exist or is not a directory: {declared}")
    return declared


def _workspace_for(
    run_record: Mapping[str, Any],
    workspace_paths: Mapping[str, str | os.PathLike[str]] | None,
) -> Path:
    declared = _declared_workspace(run_record)
    if workspace_paths is None:
        selected = declared
    else:
        override = workspace_paths.get(run_record["task_run_id"])
        if override is None:
            override = workspace_paths.get(run_record["case_id"])
        if override is None:
            raise ContractError(
                "workspace_paths has no entry for task_run_id "
                f"{run_record['task_run_id']!r} or case_id {run_record['case_id']!r}"
            )
        selected_path = Path(override).expanduser()
        if path_is_linklike(selected_path):
            raise UnsafePathError("workspace override must not be a link or junction")
        selected = selected_path.resolve(strict=False)
        if selected != declared:
            raise ContractError(
                f"workspace override for {run_record['case_id']} does not match run_record.environment.workspace"
            )
    return selected


def _actual_artifacts(run_record: Mapping[str, Any], workspace: Path) -> tuple[Path, list[dict[str, Any]]]:
    declared_artifact_root = workspace / "outputs"
    if path_is_linklike(declared_artifact_root):
        raise UnsafePathError("workspace outputs directory must not be a link or junction")
    artifact_root = resolve_within(workspace, "outputs", "artifact_root")
    if artifact_root.exists() and not artifact_root.is_dir():
        raise ContractError(f"workspace artifact root is not a directory: {artifact_root}")
    recorded_paths = {
        artifact["relative_path"].replace("\\", "/") for artifact in run_record["artifacts"]
    }
    actual_paths: set[str] = set()
    if artifact_root.is_dir():
        for candidate in artifact_root.rglob("*"):
            if path_is_linklike(candidate):
                raise UnsafePathError(f"artifact tree contains a link or junction: {candidate}")
            if not candidate.is_file():
                continue
            resolved = candidate.resolve(strict=True)
            if not _inside(resolved, artifact_root):
                raise UnsafePathError(f"artifact file resolves outside workspace outputs: {candidate}")
            if candidate.stat().st_nlink > 1:
                raise UnsafePathError(f"artifact file must not be a hard link: {candidate}")
            actual_paths.add(candidate.relative_to(workspace).as_posix())
    if recorded_paths != actual_paths:
        missing_from_record = sorted(actual_paths - recorded_paths)
        missing_from_disk = sorted(recorded_paths - actual_paths)
        raise ContractError(
            "run_record.artifacts does not exactly match actual output files; "
            f"unrecorded={missing_from_record}, missing={missing_from_disk}"
        )
    artifacts: list[dict[str, Any]] = []
    for artifact in run_record["artifacts"]:
        relative_path = artifact["relative_path"].replace("\\", "/")
        absolute_path = resolve_within(workspace, relative_path, "artifact.relative_path")
        if not _inside(absolute_path, artifact_root):
            raise UnsafePathError(f"artifact is outside workspace outputs: {relative_path}")
        if not absolute_path.is_file():
            raise ContractError(f"recorded artifact is missing or is not a file: {absolute_path}")
        actual_bytes = absolute_path.stat().st_size
        if actual_bytes != artifact["bytes"]:
            raise ContractError(
                f"artifact size changed for {relative_path}: recorded {artifact['bytes']}, actual {actual_bytes}"
            )
        actual_sha256 = _sha256(absolute_path)
        if actual_sha256.lower() != artifact["sha256"].lower():
            raise ContractError(f"artifact sha256 changed for {relative_path}")
        artifacts.append(
            {
                **dict(artifact),
                "relative_path": relative_path,
                "absolute_path": str(absolute_path),
                "verified_at_packet_build": True,
            }
        )
    return artifact_root, artifacts


def build_eval_packets(
    cases: RecordSource,
    eval_specs: RecordSource,
    run_records: RecordSource,
    *,
    packet_dir: str | os.PathLike[str],
    result_dir: str | os.PathLike[str],
    workspace_paths: Mapping[str, str | os.PathLike[str]] | None = None,
    created_at: str | None = None,
    case_ids: Sequence[str] | None = None,
) -> list[Path]:
    """Create one external-evaluation packet per case.

    This function verifies joins and artifact integrity, then writes packet JSON
    files.  It does not judge a response, resolve live references, or write an
    evaluation result.
    """

    case_rows = _records(cases, loader=load_case_records, validator=validate_case_record)
    spec_rows = _records(eval_specs, loader=load_eval_spec_records, validator=validate_eval_spec_record)
    all_run_rows = _records(run_records, loader=load_run_records, validator=validate_run_record)
    batch_context = validate_run_batch(all_run_rows)
    protected_workspaces = sorted(
        {_declared_workspace(run_record) for run_record in all_run_rows},
        key=lambda path: str(path).casefold(),
    )
    protected_workspace_paths = [str(path) for path in protected_workspaces]
    run_rows = list(all_run_rows)
    case_rows = _select_case_records(case_rows, case_ids, "cases")
    spec_rows = _select_case_records(spec_rows, case_ids, "eval_specs")
    run_rows = _select_case_records(run_rows, case_ids, "run_records")
    if not case_rows:
        raise ContractError("cannot build evaluation packets for an empty case set")
    cases_file_sha256 = _sha256(Path(cases).resolve()) if isinstance(cases, (str, os.PathLike)) else None

    cases_by_id = unique_index(case_rows, "case_id", "cases")
    specs_by_id = unique_index(spec_rows, "case_id", "eval_specs")
    runs_by_id = unique_index(run_rows, "case_id", "run_records")
    case_ids = set(cases_by_id)
    for label, indexed in (("eval_specs", specs_by_id), ("run_records", runs_by_id)):
        missing = sorted(case_ids - set(indexed))
        extra = sorted(set(indexed) - case_ids)
        if missing or extra:
            raise ContractError(f"{label} case IDs do not match cases; missing={missing}, extra={extra}")

    declared_packet_root = Path(packet_dir).expanduser()
    declared_result_root = Path(result_dir).expanduser()
    for label, declared_root in (
        ("packet_dir", declared_packet_root),
        ("result_dir", declared_result_root),
    ):
        if path_is_linklike(declared_root):
            raise UnsafePathError(f"{label} must not be a link or junction")
    packet_root = declared_packet_root.resolve(strict=False)
    result_root = declared_result_root.resolve(strict=False)
    for label, output_root in (("packet_dir", packet_root), ("result_dir", result_root)):
        conflicting_workspace = next(
            (workspace for workspace in protected_workspaces if _inside(output_root, workspace)),
            None,
        )
        if conflicting_workspace is not None:
            raise UnsafePathError(
                f"{label} must be outside every batch workspace: {conflicting_workspace}"
            )
    if (
        packet_root == result_root
        or _inside(packet_root, result_root)
        or _inside(result_root, packet_root)
    ):
        raise UnsafePathError("packet_dir and result_dir must be separate, non-nested directories")
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    # Validate caller-provided timestamp without making it part of scoring.
    normalized_timestamp = f"{timestamp[:-1]}+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed_timestamp = datetime.fromisoformat(normalized_timestamp)
    except ValueError as exc:
        raise ContractError("created_at must be an ISO-8601 timestamp") from exc
    if parsed_timestamp.tzinfo is None:
        raise ContractError("created_at must include a timezone")

    prepared_packets: list[tuple[Path, dict[str, Any]]] = []
    for case in case_rows:
        case_id = case["case_id"]
        eval_spec = specs_by_id[case_id]
        run_record = runs_by_id[case_id]
        recorded_case_hash = run_record["environment"].get("case_sha256")
        if recorded_case_hash != canonical_json_sha256(case):
            raise ContractError(f"case content changed after task run: {case_id}")
        if cases_file_sha256 is not None and run_record["environment"].get("cases_sha256") != cases_file_sha256:
            raise ContractError("case JSONL file changed after the batch run")
        workspace = _workspace_for(run_record, workspace_paths)
        artifact_root, artifacts = _actual_artifacts(run_record, workspace)

        packet_path = (packet_root / f"{case_id}.eval-packet.json").resolve(strict=False)
        result_path = (result_root / f"{case_id}.eval-result.json").resolve(strict=False)
        for label, output_path in (("packet_path", packet_path), ("result_path", result_path)):
            if _inside(output_path, workspace):
                raise UnsafePathError(f"{label} must be outside the tested workspace: {output_path}")

        packet = {
            "schema_version": EVAL_PACKET_SCHEMA,
            "batch_run_id": batch_context["batch_run_id"],
            "case_id": case_id,
            "task_run_id": run_record["task_run_id"],
            "eval_spec_sha256": canonical_json_sha256(eval_spec),
            "created_at": timestamp,
            "read_only_rules": {
                "tested_workspace": "read_only",
                "benchmark_case_and_eval_spec": "read_only",
                "authoritative_sources": "read_only",
                "allowed_write_paths": [str(result_path)],
                "must_not_modify_tested_files": True,
                "evaluation_runs_outside_tested_agent_graph": True,
            },
            "evaluator_contract": {
                "role": "luna_worker",
                "model": LUNA_EVALUATOR_MODEL,
                "maximum_attempt": 3,
            },
            "workspace_path": str(workspace),
            "protected_workspace_paths": protected_workspace_paths,
            "workspace_snapshot": _workspace_snapshot(workspace),
            "artifact_root": str(artifact_root),
            "artifacts": artifacts,
            "case": dict(case),
            "eval_spec": dict(eval_spec),
            "run_record": dict(run_record),
            "final_answer": run_record["final_answer"],
            "tool_trace": list(run_record["tool_trace"]),
            "result_path": str(result_path),
        }
        prepared_packets.append((packet_path, packet))

    for label, root in (("packet_dir", packet_root), ("result_dir", result_root)):
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise FileExistsError(f"{label} must not exist or must be completely empty: {root}")
    packet_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)
    packet_paths: list[Path] = []
    manifest_rows: list[dict[str, str]] = []
    for packet_path, packet in prepared_packets:
        atomic_write_json(packet_path, packet)
        packet_paths.append(packet_path)
        manifest_rows.append(
            {
                "case_id": packet["case_id"],
                "task_run_id": packet["task_run_id"],
                "eval_spec_sha256": packet["eval_spec_sha256"],
                "relative_path": packet_path.name,
                "sha256": _sha256(packet_path),
            }
        )
    atomic_write_json(
        _packet_manifest_path(packet_root),
        {
            "schema_version": PACKET_MANIFEST_SCHEMA,
            "batch_run_id": batch_context["batch_run_id"],
            "created_at": timestamp,
            "protected_workspace_paths": protected_workspace_paths,
            "packet_count": len(manifest_rows),
            "packets": manifest_rows,
        },
    )
    return packet_paths


def load_eval_packet(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a packet as UTF-8 JSON and validate its generic identity fields."""

    source = Path(path)
    if path_is_linklike(source):
        raise UnsafePathError("eval packet must not be a link or junction")
    if source.is_file() and source.stat().st_nlink > 1:
        raise UnsafePathError("eval packet must be an ordinary standalone file")
    try:
        packet = json.loads(source.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ContractError(f"{source} is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"{source} is not valid JSON: {exc.msg}") from exc
    if not isinstance(packet, dict):
        raise ContractError("eval packet must be a JSON object")
    if packet.get("schema_version") != EVAL_PACKET_SCHEMA:
        raise ContractError(f"eval packet schema_version must be {EVAL_PACKET_SCHEMA!r}")
    for field in (
        "batch_run_id",
        "case_id",
        "task_run_id",
        "eval_spec_sha256",
        "read_only_rules",
        "evaluator_contract",
        "workspace_path",
        "protected_workspace_paths",
        "workspace_snapshot",
        "artifact_root",
        "artifacts",
        "case",
        "eval_spec",
        "run_record",
        "final_answer",
        "tool_trace",
        "result_path",
    ):
        if field not in packet:
            raise ContractError(f"eval packet is missing {field}")
    validate_case_record(packet["case"])
    validate_eval_spec_record(packet["eval_spec"])
    validate_run_record(packet["run_record"])
    if (
        packet["case_id"] != packet["case"]["case_id"]
        or packet["case_id"] != packet["eval_spec"]["case_id"]
        or packet["case_id"] != packet["run_record"]["case_id"]
    ):
        raise ContractError("eval packet case identifiers are inconsistent")
    if packet["task_run_id"] != packet["run_record"]["task_run_id"]:
        raise ContractError("eval packet task_run_id is inconsistent")
    if packet["batch_run_id"] != packet["run_record"]["batch_run_id"]:
        raise ContractError("eval packet batch_run_id is inconsistent")
    if packet["eval_spec_sha256"] != canonical_json_sha256(packet["eval_spec"]):
        raise ContractError("eval packet eval_spec_sha256 is inconsistent")
    if packet["final_answer"] != packet["run_record"]["final_answer"]:
        raise ContractError("eval packet final_answer does not match run_record")
    if packet["tool_trace"] != packet["run_record"]["tool_trace"]:
        raise ContractError("eval packet tool_trace does not match run_record")
    workspace = Path(packet["workspace_path"]).expanduser()
    result_path = Path(packet["result_path"]).expanduser()
    artifact_root = Path(packet["artifact_root"]).expanduser()
    if not workspace.is_absolute() or not result_path.is_absolute() or not artifact_root.is_absolute():
        raise UnsafePathError("eval packet workspace_path, artifact_root, and result_path must be absolute")
    protected_values = packet["protected_workspace_paths"]
    if not isinstance(protected_values, list) or not protected_values:
        raise ContractError("eval packet protected_workspace_paths must be a non-empty list")
    protected_workspaces: list[Path] = []
    protected_keys: set[str] = set()
    for index, value in enumerate(protected_values):
        if not isinstance(value, str) or not value.strip():
            raise ContractError(
                f"eval packet protected_workspace_paths[{index}] must be an absolute path"
            )
        declared_protected = Path(value).expanduser()
        if not declared_protected.is_absolute():
            raise UnsafePathError(
                f"eval packet protected_workspace_paths[{index}] must be absolute"
            )
        if path_is_linklike(declared_protected):
            raise UnsafePathError("eval packet protected workspace must not be a link or junction")
        resolved_protected = declared_protected.resolve(strict=False)
        key = str(resolved_protected).casefold()
        if key in protected_keys:
            raise ContractError("eval packet protected workspace paths must be unique")
        protected_keys.add(key)
        protected_workspaces.append(resolved_protected)
    if path_is_linklike(workspace):
        raise UnsafePathError("eval packet workspace_path must not be a link or junction")
    declared_artifact_root = workspace / "outputs"
    if path_is_linklike(declared_artifact_root):
        raise UnsafePathError("eval packet artifact_root must not be a link or junction")
    workspace = workspace.resolve(strict=False)
    result_path = result_path.resolve(strict=False)
    artifact_root = artifact_root.resolve(strict=False)
    source_path = source.resolve(strict=False)
    if workspace not in protected_workspaces:
        raise ContractError("eval packet workspace_path must be included in protected_workspace_paths")
    if any(_inside(result_path, protected) for protected in protected_workspaces):
        raise UnsafePathError("eval packet result_path must be outside every batch workspace")
    if any(_inside(source_path, protected) for protected in protected_workspaces):
        raise UnsafePathError("eval packet file must be outside every batch workspace")
    expected_artifact_root = resolve_within(workspace, "outputs", "artifact_root")
    if artifact_root != expected_artifact_root:
        raise UnsafePathError("eval packet artifact_root must be the tested workspace outputs directory")
    declared_workspace = Path(packet["run_record"]["environment"]["workspace"]).resolve(strict=False)
    if declared_workspace != workspace:
        raise ContractError("eval packet workspace_path does not match run_record.environment.workspace")
    if packet["workspace_snapshot"] != _workspace_snapshot(workspace):
        raise ContractError("tested workspace changed after evaluation packet creation")
    rules = packet["read_only_rules"]
    if not isinstance(rules, dict) or rules.get("must_not_modify_tested_files") is not True:
        raise ContractError("eval packet must preserve the tested-workspace read-only rule")
    if rules.get("allowed_write_paths") != [str(result_path)]:
        raise ContractError("eval packet allowed_write_paths must contain only result_path")
    if packet["evaluator_contract"] != {
        "role": "luna_worker",
        "model": LUNA_EVALUATOR_MODEL,
        "maximum_attempt": 3,
    }:
        raise ContractError("eval packet evaluator_contract is invalid")
    run_artifacts_by_path = {
        artifact["relative_path"].replace("\\", "/"): artifact
        for artifact in packet["run_record"]["artifacts"]
    }
    packet_artifact_paths: set[str] = set()
    for index, artifact in enumerate(packet["artifacts"]):
        if not isinstance(artifact, dict):
            raise ContractError(f"eval packet artifacts[{index}] must be an object")
        if "relative_path" not in artifact or "absolute_path" not in artifact:
            raise ContractError(
                f"eval packet artifacts[{index}] must contain relative_path and absolute_path"
            )
        expected_path = resolve_within(
            workspace, artifact["relative_path"], f"eval packet artifacts[{index}].relative_path"
        )
        absolute_path = Path(artifact["absolute_path"]).resolve(strict=False)
        if absolute_path != expected_path or not _inside(absolute_path, artifact_root):
            raise UnsafePathError(f"eval packet artifacts[{index}] path is inconsistent or unsafe")
        relative_path = artifact["relative_path"].replace("\\", "/")
        if relative_path in packet_artifact_paths:
            raise ContractError(f"duplicate eval packet artifact: {relative_path}")
        packet_artifact_paths.add(relative_path)
        run_artifact = run_artifacts_by_path.get(relative_path)
        if run_artifact is None:
            raise ContractError(f"eval packet artifact is absent from run_record: {relative_path}")
        if artifact.get("sha256") != run_artifact.get("sha256") or artifact.get("bytes") != run_artifact.get("bytes"):
            raise ContractError(f"eval packet artifact metadata differs from run_record: {relative_path}")
        if not absolute_path.is_file():
            raise ContractError(f"eval packet artifact is missing: {absolute_path}")
        if absolute_path.stat().st_size != artifact["bytes"] or _sha256(absolute_path).lower() != artifact["sha256"].lower():
            raise ContractError(f"eval packet artifact changed after packet creation: {relative_path}")
    if packet_artifact_paths != set(run_artifacts_by_path):
        raise ContractError("eval packet artifacts do not exactly match run_record artifacts")
    return packet
