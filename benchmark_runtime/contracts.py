"""Schema validation and safe JSON I/O for the generic benchmark runtime.

The contracts in this module intentionally know nothing about benchmark case
numbers, categories, or domain-specific scoring.  They validate only the data
needed to hand a completed task run to an external evaluator.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import stat
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, TypeVar
from urllib.parse import urlparse

from . import (
    ARCHITECTURE_MODES,
    CASE_SCHEMA,
    EVAL_RESULT_SCHEMA,
    EVAL_SPEC_SCHEMA,
    LUNA_EVALUATOR_MODEL,
    RUN_SCHEMA,
)


JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
Record = dict[str, Any]
_T = TypeVar("_T")

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class ContractError(ValueError):
    """Raised when a benchmark record violates its declared contract."""


class DuplicateRecordError(ContractError):
    """Raised when records reuse an identifier that must be unique."""


class UnsafePathError(ContractError):
    """Raised when a record path could escape its declared root."""


def path_is_linklike(path: str | os.PathLike[str]) -> bool:
    """Return ``True`` for symlinks and Windows reparse-point links.

    ``pathlib.Path.is_junction`` is unavailable on the Python version used by
    the current NTL-GPT environment.  Inspecting the reparse-point attribute
    keeps the boundary check effective for Windows junctions as well as
    ordinary symbolic links.
    """

    candidate = Path(path)
    try:
        if candidate.is_symlink():
            return True
        attributes = int(getattr(os.lstat(candidate), "st_file_attributes", 0))
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise UnsafePathError(f"cannot inspect path metadata: {candidate}") from exc
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse_flag)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _required(record: Mapping[str, Any], fields: Sequence[str], label: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise ContractError(f"{label} is missing required fields: {', '.join(missing)}")


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    if "\x00" in value:
        raise ContractError(f"{field} must not contain a NUL byte")
    return value


def _portable_id(value: Any, field: str) -> str:
    identifier = _nonempty_string(value, field)
    if identifier != identifier.strip():
        raise ContractError(f"{field} must not have leading or trailing whitespace")
    if len(identifier) > 160:
        raise ContractError(f"{field} must be at most 160 characters")
    if identifier in {".", ".."}:
        raise ContractError(f"{field} is not a safe identifier")
    if any(ord(character) < 32 for character in identifier):
        raise ContractError(f"{field} must not contain control characters")
    if any(character in _WINDOWS_FORBIDDEN_CHARS for character in identifier):
        raise ContractError(f"{field} must be a portable single-component identifier")
    if identifier.endswith((".", " ")):
        raise ContractError(f"{field} must not end in a dot or space")
    if identifier.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise ContractError(f"{field} is a reserved Windows filename")
    return identifier


def _json_compatible(value: Any, field: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must contain only finite JSON values") from exc


def canonical_json_sha256(value: Any) -> str:
    """Hash one JSON-compatible value using a stable UTF-8 representation."""

    _json_compatible(value, "canonical JSON value")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} must be a non-negative integer")
    return value


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a non-negative finite number")
    number = float(value)
    if number < 0 or not math.isfinite(number):
        raise ContractError(f"{field} must be a non-negative finite number")
    return number


def _iso_datetime(value: Any, field: str) -> datetime:
    text = _nonempty_string(value, field)
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed


def _schema(record: Mapping[str, Any], expected: str, label: str) -> None:
    if record.get("schema_version") != expected:
        raise ContractError(
            f"{label}.schema_version must be {expected!r}, got {record.get('schema_version')!r}"
        )


def safe_relative_path(value: Any, field: str = "path") -> str:
    """Return a normalized portable relative path or raise ``UnsafePathError``."""

    raw = _nonempty_string(value, field)
    if any(ord(character) < 32 for character in raw):
        raise UnsafePathError(f"{field} contains control characters")
    windows_path = PureWindowsPath(raw)
    posix_path = PurePosixPath(raw.replace("\\", "/"))
    if windows_path.is_absolute() or windows_path.drive or posix_path.is_absolute():
        raise UnsafePathError(f"{field} must be relative")
    parts = raw.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafePathError(f"{field} must be normalized and must not traverse directories")
    if any(any(character in '<>:"|?*' for character in part) for part in parts):
        raise UnsafePathError(f"{field} contains characters unsafe on Windows")
    if any(part.endswith((".", " ")) for part in parts):
        raise UnsafePathError(f"{field} contains a component ending in a dot or space")
    if any(part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES for part in parts):
        raise UnsafePathError(f"{field} contains a reserved Windows filename")
    return "/".join(parts)


def resolve_within(root: str | os.PathLike[str], relative_path: Any, field: str = "path") -> Path:
    """Resolve a record path while proving it remains within ``root``."""

    normalized = safe_relative_path(relative_path, field)
    root_path = Path(root).expanduser().resolve(strict=False)
    candidate = root_path.joinpath(*normalized.split("/")).resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise UnsafePathError(f"{field} escapes its declared root") from exc
    return candidate


def _validate_input(record: Any, index: int) -> Record:
    label = f"case.inputs[{index}]"
    item = _mapping(record, label)
    _required(item, ("source_path", "target_path"), label)
    safe_relative_path(item["source_path"], f"{label}.source_path")
    safe_relative_path(item["target_path"], f"{label}.target_path")
    if "sha256" in item and item["sha256"] is not None:
        sha256 = _nonempty_string(item["sha256"], f"{label}.sha256")
        if not _SHA256_RE.fullmatch(sha256):
            raise ContractError(f"{label}.sha256 must be a 64-character hexadecimal digest")
    _json_compatible(item, label)
    return dict(item)


def validate_case_record(record: Any) -> Record:
    """Validate and copy one ``ntl-benchmark.case.v1`` record."""

    item = _mapping(record, "case")
    _schema(item, CASE_SCHEMA, "case")
    _required(item, ("case_id", "prompt", "inputs", "metadata"), "case")
    _portable_id(item["case_id"], "case.case_id")
    _nonempty_string(item["prompt"], "case.prompt")
    if not isinstance(item["inputs"], list):
        raise ContractError("case.inputs must be a list")
    for index, input_record in enumerate(item["inputs"]):
        _validate_input(input_record, index)
    _mapping(item["metadata"], "case.metadata")
    _json_compatible(item, "case")
    return dict(item)


def validate_eval_spec_record(record: Any) -> Record:
    """Validate and copy one case-owned external evaluation specification."""

    item = _mapping(record, "eval_spec")
    _schema(item, EVAL_SPEC_SCHEMA, "eval_spec")
    _required(
        item,
        (
            "case_id",
            "mode",
            "mandatory_criteria",
            "reference",
            "authoritative_sources",
            "notes",
        ),
        "eval_spec",
    )
    _portable_id(item["case_id"], "eval_spec.case_id")
    if item["mode"] not in {"gold_compare", "live_verify"}:
        raise ContractError("eval_spec.mode must be 'gold_compare' or 'live_verify'")
    criteria = item["mandatory_criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise ContractError("eval_spec.mandatory_criteria must be a non-empty list")
    criterion_ids: set[str] = set()
    for index, criterion in enumerate(criteria):
        label = f"eval_spec.mandatory_criteria[{index}]"
        criterion_item = _mapping(criterion, label)
        _required(criterion_item, ("criterion_id", "description"), label)
        criterion_id = _portable_id(criterion_item["criterion_id"], f"{label}.criterion_id")
        _nonempty_string(criterion_item["description"], f"{label}.description")
        if criterion_id in criterion_ids:
            raise DuplicateRecordError(f"duplicate criterion_id in eval_spec: {criterion_id}")
        criterion_ids.add(criterion_id)
    if not isinstance(item["authoritative_sources"], list):
        raise ContractError("eval_spec.authoritative_sources must be a list")
    source_ids: set[str] = set()
    for index, source in enumerate(item["authoritative_sources"]):
        source_id = _authoritative_source_id(source, f"eval_spec.authoritative_sources[{index}]")
        if source_id in source_ids:
            raise DuplicateRecordError(f"duplicate authoritative source: {source_id}")
        source_ids.add(source_id)
    if item["mode"] == "live_verify" and not source_ids:
        raise ContractError("live_verify eval_spec.authoritative_sources must not be empty")
    if not isinstance(item["notes"], str):
        raise ContractError("eval_spec.notes must be a string")
    _json_compatible(item["reference"], "eval_spec.reference")
    _json_compatible(item["authoritative_sources"], "eval_spec.authoritative_sources")
    _json_compatible(item, "eval_spec")
    return dict(item)


def _authoritative_source_id(value: Any, label: str) -> str:
    if isinstance(value, str):
        return _nonempty_string(value, label)
    item = _mapping(value, label)
    for field in ("source_id", "source", "url", "identifier", "name"):
        if field in item and item[field] is not None:
            return _nonempty_string(item[field], f"{label}.{field}")
    raise ContractError(
        f"{label} must be a string or contain source_id, source, url, identifier, or name"
    )


def _source_matches_authority(authority: Any, declared_source: str, actual_source: str) -> bool:
    allowed = [declared_source]
    if isinstance(authority, str):
        allowed.append(authority)
    elif isinstance(authority, Mapping):
        allowed.extend(
            str(authority[field])
            for field in ("source_id", "source", "url", "identifier", "name")
            if isinstance(authority.get(field), str) and str(authority[field]).strip()
        )
    if actual_source in allowed:
        return True
    actual_url = urlparse(actual_source)
    if actual_url.scheme not in {"http", "https"} or not actual_url.netloc:
        return False
    for candidate in allowed:
        authority_url = urlparse(candidate)
        if (
            authority_url.scheme in {"http", "https"}
            and authority_url.netloc
            and actual_url.netloc.casefold() == authority_url.netloc.casefold()
        ):
            authority_path = authority_url.path.rstrip("/")
            actual_path = actual_url.path.rstrip("/")
            if not authority_path or authority_path == "/":
                return True
            if actual_path == authority_path or actual_path.startswith(f"{authority_path}/"):
                return True
    return False


def _validate_artifact(record: Any, index: int) -> Record:
    label = f"run_record.artifacts[{index}]"
    item = _mapping(record, label)
    _required(item, ("relative_path", "sha256", "bytes"), label)
    relative_path = safe_relative_path(item["relative_path"], f"{label}.relative_path")
    if relative_path.split("/", 1)[0] != "outputs":
        raise UnsafePathError(f"{label}.relative_path must be under outputs/")
    sha256 = _nonempty_string(item["sha256"], f"{label}.sha256")
    if not _SHA256_RE.fullmatch(sha256):
        raise ContractError(f"{label}.sha256 must be a 64-character hexadecimal digest")
    _nonnegative_int(item["bytes"], f"{label}.bytes")
    _json_compatible(item, label)
    return dict(item)


def _validate_model_usage(value: Any) -> None:
    usage = _mapping(value, "run_record.model_usage")
    _required(
        usage,
        (
            "llm_call_count",
            "calls",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "usage_complete",
        ),
        "run_record.model_usage",
    )
    call_count = _nonnegative_int(usage["llm_call_count"], "run_record.model_usage.llm_call_count")
    calls = usage["calls"]
    if not isinstance(calls, list):
        raise ContractError("run_record.model_usage.calls must be a list")
    if call_count != len(calls):
        raise ContractError("run_record.model_usage.llm_call_count must equal len(calls)")
    input_tokens = _nonnegative_int(
        usage["input_tokens"], "run_record.model_usage.input_tokens"
    )
    output_tokens = _nonnegative_int(
        usage["output_tokens"], "run_record.model_usage.output_tokens"
    )
    total_tokens = _nonnegative_int(
        usage["total_tokens"], "run_record.model_usage.total_tokens"
    )
    if not isinstance(usage["usage_complete"], bool):
        raise ContractError("run_record.model_usage.usage_complete must be a boolean")
    observed_input = 0
    observed_output = 0
    observed_total = 0
    for index, raw_call in enumerate(calls):
        label = f"run_record.model_usage.calls[{index}]"
        call = _mapping(raw_call, label)
        for field in ("requested_model_id", "provider_reported_model_id", "provider_request_id"):
            if field in call and call[field] is not None:
                _nonempty_string(call[field], f"{label}.{field}")
        call_tokens: dict[str, int | None] = {}
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            raw_token = call.get(field)
            if raw_token is None:
                call_tokens[field] = None
            else:
                call_tokens[field] = _nonnegative_int(raw_token, f"{label}.{field}")
        observed_input += int(call_tokens["input_tokens"] or 0)
        observed_output += int(call_tokens["output_tokens"] or 0)
        observed_total += int(call_tokens["total_tokens"] or 0)
        if usage["usage_complete"]:
            _required(
                call,
                (
                    "sequence",
                    "status",
                    "provider_reported_model_id",
                    "provider_request_id",
                    "model_identity_matches_tested",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "usage_complete",
                ),
                label,
            )
            if _nonnegative_int(call["sequence"], f"{label}.sequence") != index + 1:
                raise ContractError(f"{label}.sequence must preserve one-based call order")
            if call["status"] != "completed" or call["usage_complete"] is not True:
                raise ContractError(f"{label} must be a completed provider call")
            for identity_field in (
                "provider_reported_model_id",
                "provider_request_id",
            ):
                _nonempty_string(call[identity_field], f"{label}.{identity_field}")
            if call["model_identity_matches_tested"] is not True:
                raise ContractError(f"{label}.model_identity_matches_tested must be true")
            if any(value is None for value in call_tokens.values()):
                raise ContractError(f"{label} must contain complete provider token usage")
            if call_tokens["total_tokens"] != (
                int(call_tokens["input_tokens"] or 0) + int(call_tokens["output_tokens"] or 0)
            ):
                raise ContractError(f"{label}.total_tokens must equal input_tokens + output_tokens")
    if usage["usage_complete"]:
        if (input_tokens, output_tokens, total_tokens) != (
            observed_input,
            observed_output,
            observed_total,
        ):
            raise ContractError("complete model_usage aggregates must equal the per-call sums")
        if total_tokens != input_tokens + output_tokens:
            raise ContractError(
                "complete run_record.model_usage.total_tokens must equal input_tokens + output_tokens"
            )
        if usage.get("incomplete_reasons"):
            raise ContractError("complete model_usage must not contain incomplete_reasons")
    _json_compatible(calls, "run_record.model_usage.calls")


def validate_run_record(record: Any) -> Record:
    """Validate only the case-agnostic fields emitted by the batch runner."""

    item = _mapping(record, "run_record")
    _schema(item, RUN_SCHEMA, "run_record")
    _required(
        item,
        (
            "batch_run_id",
            "task_run_id",
            "case_id",
            "thread_id",
            "started_at",
            "ended_at",
            "wall_clock_seconds",
            "terminal_state",
            "final_answer",
            "artifacts",
            "tool_trace",
            "model_usage",
            "errors",
            "environment",
        ),
        "run_record",
    )
    _portable_id(item["batch_run_id"], "run_record.batch_run_id")
    _portable_id(item["task_run_id"], "run_record.task_run_id")
    _portable_id(item["case_id"], "run_record.case_id")
    _nonempty_string(item["thread_id"], "run_record.thread_id")
    started_at = _iso_datetime(item["started_at"], "run_record.started_at")
    ended_at = _iso_datetime(item["ended_at"], "run_record.ended_at")
    if ended_at < started_at:
        raise ContractError("run_record.ended_at must not precede started_at")
    _nonnegative_number(item["wall_clock_seconds"], "run_record.wall_clock_seconds")
    if item["terminal_state"] not in {"succeeded", "no_final_answer", "failed", "timed_out"}:
        raise ContractError(
            "run_record.terminal_state must be succeeded, no_final_answer, failed, or timed_out"
        )
    if item["final_answer"] is not None and not isinstance(item["final_answer"], str):
        raise ContractError("run_record.final_answer must be a string or null")
    if not isinstance(item["artifacts"], list):
        raise ContractError("run_record.artifacts must be a list")
    artifact_paths: set[str] = set()
    for index, artifact in enumerate(item["artifacts"]):
        validated = _validate_artifact(artifact, index)
        relative_path = validated["relative_path"].replace("\\", "/")
        if relative_path in artifact_paths:
            raise DuplicateRecordError(f"duplicate artifact relative_path: {relative_path}")
        artifact_paths.add(relative_path)
    if not isinstance(item["tool_trace"], list):
        raise ContractError("run_record.tool_trace must be a list")
    if "internal_evidence" in item:
        try:
            from orchestration.run_evidence import validate_internal_evidence

            validate_internal_evidence(item["internal_evidence"])
        except ValueError as exc:
            raise ContractError(f"run_record.internal_evidence is invalid: {exc}") from exc
    _validate_model_usage(item["model_usage"])
    if not isinstance(item["errors"], list):
        raise ContractError("run_record.errors must be a list")
    environment = _mapping(item["environment"], "run_record.environment")
    _required(environment, ("workspace", "architecture_mode"), "run_record.environment")
    workspace = Path(_nonempty_string(environment["workspace"], "run_record.environment.workspace"))
    if not workspace.is_absolute():
        raise UnsafePathError("run_record.environment.workspace must be an absolute path")
    architecture_mode = _nonempty_string(
        environment["architecture_mode"], "run_record.environment.architecture_mode"
    )
    if architecture_mode not in ARCHITECTURE_MODES:
        raise ContractError(
            "run_record.environment.architecture_mode must be one of: "
            + ", ".join(ARCHITECTURE_MODES)
        )
    snapshot_present = "system_snapshot" in environment
    snapshot_hash_present = "system_snapshot_sha256" in environment
    if snapshot_present != snapshot_hash_present:
        raise ContractError(
            "run_record.environment must contain system_snapshot and system_snapshot_sha256 together"
        )
    if snapshot_present:
        digest = _nonempty_string(
            environment["system_snapshot_sha256"],
            "run_record.environment.system_snapshot_sha256",
        )
        if not _SHA256_RE.fullmatch(digest):
            raise ContractError(
                "run_record.environment.system_snapshot_sha256 must be a SHA-256 digest"
            )
        try:
            from orchestration.system_snapshot import validate_system_snapshot

            validated_snapshot = validate_system_snapshot(
                environment["system_snapshot"],
                expected_sha256=digest,
                architecture_mode=architecture_mode,
                model_name=str(environment.get("model") or ""),
            )
            snapshot_limits = validated_snapshot.get("limits", {})
            for field in (
                "request_timeout_seconds",
                "task_timeout_seconds",
                "recursion_limit",
            ):
                if field in snapshot_limits and float(snapshot_limits[field]) != float(
                    environment.get(field, -1)
                ):
                    raise ValueError(f"snapshot limit {field} does not match run environment")
        except ValueError as exc:
            raise ContractError(f"run_record.environment.system_snapshot is invalid: {exc}") from exc
    _json_compatible(item, "run_record")
    return dict(item)


def _validate_result_criterion(record: Any, index: int) -> Record:
    label = f"eval_result.mandatory_criteria[{index}]"
    item = _mapping(record, label)
    _required(item, ("criterion_id", "passed", "reason", "evidence"), label)
    _portable_id(item["criterion_id"], f"{label}.criterion_id")
    if not isinstance(item["passed"], bool):
        raise ContractError(f"{label}.passed must be a boolean")
    _nonempty_string(item["reason"], f"{label}.reason")
    if not isinstance(item["evidence"], list) or not item["evidence"]:
        raise ContractError(f"{label}.evidence must be a non-empty list")
    for evidence_index, raw_evidence in enumerate(item["evidence"]):
        evidence_label = f"{label}.evidence[{evidence_index}]"
        evidence = _mapping(raw_evidence, evidence_label)
        _required(evidence, ("kind", "location", "observation"), evidence_label)
        if evidence["kind"] not in {"artifact", "answer", "trace", "calculation", "source"}:
            raise ContractError(
                f"{evidence_label}.kind must be artifact, answer, trace, calculation, or source"
            )
        _nonempty_string(evidence["location"], f"{evidence_label}.location")
        _nonempty_string(evidence["observation"], f"{evidence_label}.observation")
    _json_compatible(item, label)
    return dict(item)


def _validate_source_check(record: Any, index: int) -> Record:
    label = f"eval_result.source_checks[{index}]"
    item = _mapping(record, label)
    _required(item, ("declared_source", "source", "checked_at", "status", "evidence"), label)
    _nonempty_string(item["declared_source"], f"{label}.declared_source")
    _nonempty_string(item["source"], f"{label}.source")
    _iso_datetime(item["checked_at"], f"{label}.checked_at")
    if item["status"] not in {"verified", "unavailable", "not_needed"}:
        raise ContractError(
            f"{label}.status must be 'verified', 'unavailable', or 'not_needed'"
        )
    _nonempty_string(item["evidence"], f"{label}.evidence")
    _json_compatible(item, label)
    return dict(item)


def _validate_artifact_check(record: Any, index: int) -> Record:
    label = f"eval_result.artifacts_checked[{index}]"
    item = _mapping(record, label)
    _required(item, ("relative_path", "absolute_path", "status", "evidence"), label)
    safe_relative_path(item["relative_path"], f"{label}.relative_path")
    absolute_text = _nonempty_string(item["absolute_path"], f"{label}.absolute_path")
    if not (Path(absolute_text).is_absolute() or PureWindowsPath(absolute_text).is_absolute()):
        raise UnsafePathError(f"{label}.absolute_path must be absolute")
    if item["status"] not in {"checked", "missing", "unreadable", "not_relevant"}:
        raise ContractError(
            f"{label}.status must be checked, missing, unreadable, or not_relevant"
        )
    _nonempty_string(item["evidence"], f"{label}.evidence")
    _json_compatible(item, label)
    return dict(item)


def validate_eval_result(
    record: Any,
    *,
    eval_spec: Mapping[str, Any] | None = None,
    eval_packet: Mapping[str, Any] | None = None,
) -> Record:
    """Validate one external Luna result without performing any scoring."""

    item = _mapping(record, "eval_result")
    _schema(item, EVAL_RESULT_SCHEMA, "eval_result")
    _required(
        item,
        (
            "batch_run_id",
            "case_id",
            "task_run_id",
            "eval_spec_sha256",
            "status",
            "pass",
            "mandatory_criteria",
            "resolved_reference",
            "source_checks",
            "artifacts_checked",
            "summary",
            "worker",
            "timestamps",
            "errors",
        ),
        "eval_result",
    )
    allowed_fields = {
        "schema_version",
        "batch_run_id",
        "case_id",
        "task_run_id",
        "eval_spec_sha256",
        "status",
        "pass",
        "mandatory_criteria",
        "resolved_reference",
        "source_checks",
        "artifacts_checked",
        "summary",
        "worker",
        "timestamps",
        "errors",
    }
    unexpected_fields = sorted(set(item) - allowed_fields)
    if unexpected_fields:
        raise ContractError(
            "eval_result contains fields outside ntl-benchmark.eval-result.v1: "
            + ", ".join(unexpected_fields)
        )
    batch_run_id = _portable_id(item["batch_run_id"], "eval_result.batch_run_id")
    case_id = _portable_id(item["case_id"], "eval_result.case_id")
    task_run_id = _portable_id(item["task_run_id"], "eval_result.task_run_id")
    eval_spec_sha256 = _nonempty_string(
        item["eval_spec_sha256"], "eval_result.eval_spec_sha256"
    )
    if not _SHA256_RE.fullmatch(eval_spec_sha256):
        raise ContractError("eval_result.eval_spec_sha256 must be a 64-character digest")
    status = item["status"]
    if status not in {"completed", "eval_error"}:
        raise ContractError("eval_result.status must be 'completed' or 'eval_error'")
    criteria = item["mandatory_criteria"]
    if not isinstance(criteria, list):
        raise ContractError("eval_result.mandatory_criteria must be a list")
    criterion_ids: list[str] = []
    criterion_passes: list[bool] = []
    for index, criterion in enumerate(criteria):
        validated = _validate_result_criterion(criterion, index)
        criterion_id = validated["criterion_id"]
        if criterion_id in criterion_ids:
            raise DuplicateRecordError(f"duplicate criterion_id in eval_result: {criterion_id}")
        criterion_ids.append(criterion_id)
        criterion_passes.append(validated["passed"])
    if not isinstance(item["source_checks"], list):
        raise ContractError("eval_result.source_checks must be a list")
    validated_source_checks = [
        _validate_source_check(source_check, index)
        for index, source_check in enumerate(item["source_checks"])
    ]
    if not isinstance(item["artifacts_checked"], list):
        raise ContractError("eval_result.artifacts_checked must be a list")
    validated_artifact_checks = [
        _validate_artifact_check(artifact_check, index)
        for index, artifact_check in enumerate(item["artifacts_checked"])
    ]
    if not isinstance(item["summary"], str):
        raise ContractError("eval_result.summary must be a string")
    worker = _mapping(item["worker"], "eval_result.worker")
    _required(worker, ("role", "model", "attempt"), "eval_result.worker")
    if worker["role"] != "luna_worker":
        raise ContractError("eval_result.worker.role must be 'luna_worker'")
    if worker["model"] != LUNA_EVALUATOR_MODEL:
        raise ContractError(
            f"eval_result.worker.model must be {LUNA_EVALUATOR_MODEL!r}"
        )
    attempt = worker["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or not 1 <= attempt <= 3:
        raise ContractError("eval_result.worker.attempt must be an integer from 1 to 3")
    timestamps = _mapping(item["timestamps"], "eval_result.timestamps")
    _required(timestamps, ("started_at", "ended_at"), "eval_result.timestamps")
    started_at = _iso_datetime(timestamps["started_at"], "eval_result.timestamps.started_at")
    ended_at = _iso_datetime(timestamps["ended_at"], "eval_result.timestamps.ended_at")
    if ended_at < started_at:
        raise ContractError("eval_result.timestamps.ended_at must not precede started_at")
    for index, source_check in enumerate(validated_source_checks):
        checked_at = _iso_datetime(
            source_check["checked_at"], f"eval_result.source_checks[{index}].checked_at"
        )
        if checked_at < started_at or checked_at > ended_at:
            raise ContractError(
                f"eval_result.source_checks[{index}].checked_at must fall within worker timestamps"
            )
    if not isinstance(item["errors"], list):
        raise ContractError("eval_result.errors must be a list")
    for index, error in enumerate(item["errors"]):
        label = f"eval_result.errors[{index}]"
        error_item = _mapping(error, label)
        _required(error_item, ("code", "message"), label)
        _nonempty_string(error_item["code"], f"{label}.code")
        _nonempty_string(error_item["message"], f"{label}.message")
    if status == "completed":
        if not isinstance(item["pass"], bool):
            raise ContractError("completed eval_result.pass must be a boolean")
        if not criteria:
            raise ContractError("completed eval_result must contain mandatory criteria")
        if item["pass"] is not all(criterion_passes):
            raise ContractError("eval_result.pass must equal all mandatory criterion outcomes")
        if item["errors"]:
            raise ContractError("completed eval_result.errors must be empty")
    else:
        if item["pass"] is not None:
            raise ContractError("eval_error eval_result.pass must be null")
        if not item["errors"]:
            raise ContractError("eval_error eval_result.errors must describe the technical failure")

    packet: Mapping[str, Any] | None = None
    if eval_packet is not None:
        packet = _mapping(eval_packet, "eval_packet")
        if eval_spec is None and isinstance(packet.get("eval_spec"), Mapping):
            eval_spec = packet["eval_spec"]

    if eval_spec is not None:
        validated_spec = validate_eval_spec_record(eval_spec)
        if case_id != validated_spec["case_id"]:
            raise ContractError("eval_result.case_id does not match eval_spec.case_id")
        if eval_spec_sha256.lower() != canonical_json_sha256(validated_spec):
            raise ContractError("eval_result.eval_spec_sha256 does not match eval_spec")
        expected_ids = [criterion["criterion_id"] for criterion in validated_spec["mandatory_criteria"]]
        if status == "completed" and criterion_ids != expected_ids:
            raise ContractError("eval_result mandatory criteria must exactly match eval_spec order and IDs")
        if status == "completed" and validated_spec["mode"] == "live_verify":
            if item["resolved_reference"] in (None, "", [], {}):
                raise ContractError("live_verify completed results must save a non-empty resolved_reference")
            if not item["source_checks"]:
                raise ContractError("live_verify completed results must record source_checks")
            if not any(check["status"] == "verified" for check in validated_source_checks):
                raise ContractError(
                    "live_verify completed results must contain at least one verified source check"
                )
            expected_sources = {
                _authoritative_source_id(source, f"eval_spec.authoritative_sources[{index}]")
                for index, source in enumerate(validated_spec["authoritative_sources"])
            }
            checked_sources = {check["declared_source"] for check in validated_source_checks}
            if len(checked_sources) != len(validated_source_checks):
                raise DuplicateRecordError(
                    "live_verify source_checks must contain each declared authority exactly once"
                )
            if checked_sources != expected_sources:
                raise ContractError(
                    "live_verify source_checks must cover exactly the declared authoritative sources"
                )
            authority_by_id = {
                _authoritative_source_id(source, f"eval_spec.authoritative_sources[{index}]"): source
                for index, source in enumerate(validated_spec["authoritative_sources"])
            }
            for index, check in enumerate(validated_source_checks):
                if not _source_matches_authority(
                    authority_by_id[check["declared_source"]],
                    check["declared_source"],
                    check["source"],
                ):
                    raise ContractError(
                        f"eval_result.source_checks[{index}].source is not the declared authority"
                    )

    if packet is not None:
        if (
            batch_run_id != packet.get("batch_run_id")
            or case_id != packet.get("case_id")
            or task_run_id != packet.get("task_run_id")
        ):
            raise ContractError("eval_result identifiers do not match eval_packet")
        if eval_spec_sha256 != packet.get("eval_spec_sha256"):
            raise ContractError("eval_result eval_spec_sha256 does not match eval_packet")
        if status == "completed":
            packet_artifacts = packet.get("artifacts")
            if not isinstance(packet_artifacts, list):
                raise ContractError("eval_packet.artifacts must be a list")
            expected_paths = {
                safe_relative_path(artifact.get("relative_path"), "eval_packet artifact relative_path")
                for artifact in packet_artifacts
                if isinstance(artifact, Mapping)
            }
            if len(expected_paths) != len(packet_artifacts):
                raise ContractError("eval_packet artifacts must contain unique relative_path values")
            checked_paths: set[str] = set()
            packet_artifacts_by_path = {
                safe_relative_path(
                    artifact["relative_path"], "eval_packet artifact relative_path"
                ): artifact
                for artifact in packet_artifacts
                if isinstance(artifact, Mapping)
            }
            for index, checked_item in enumerate(validated_artifact_checks):
                checked_path = safe_relative_path(
                    checked_item["relative_path"],
                    f"eval_result.artifacts_checked[{index}].relative_path",
                )
                if checked_path in checked_paths:
                    raise DuplicateRecordError(
                        f"duplicate artifacts_checked relative_path: {checked_path}"
                    )
                checked_paths.add(checked_path)
                packet_artifact = packet_artifacts_by_path.get(checked_path)
                if packet_artifact is not None:
                    declared_absolute = Path(checked_item["absolute_path"]).resolve(strict=False)
                    expected_absolute = Path(packet_artifact["absolute_path"]).resolve(strict=False)
                    if declared_absolute != expected_absolute:
                        raise ContractError(
                            f"eval_result artifact absolute_path does not match packet: {checked_path}"
                        )
            if checked_paths != expected_paths:
                raise ContractError(
                    "completed eval_result.artifacts_checked must account for every packet artifact exactly once"
                )

    _json_compatible(item, "eval_result")
    return dict(item)


def _load_jsonl(
    path: str | os.PathLike[str],
    validator: Callable[[Any], Record],
    *,
    unique_fields: Sequence[str],
) -> list[Record]:
    source = Path(path)
    records: list[Record] = []
    seen: dict[str, set[Any]] = {field: set() for field in unique_fields}
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                try:
                    parsed = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise ContractError(f"{source}:{line_number}: invalid JSON: {exc.msg}") from exc
                try:
                    record = validator(parsed)
                except ContractError as exc:
                    raise ContractError(f"{source}:{line_number}: {exc}") from exc
                for field in unique_fields:
                    value = record[field]
                    identity = value.casefold() if field == "case_id" and isinstance(value, str) else value
                    if identity in seen[field]:
                        raise DuplicateRecordError(f"{source}:{line_number}: duplicate {field}: {value}")
                    seen[field].add(identity)
                records.append(record)
    except UnicodeDecodeError as exc:
        raise ContractError(f"{source} is not valid UTF-8") from exc
    return records


def load_case_records(path: str | os.PathLike[str]) -> list[Record]:
    return _load_jsonl(path, validate_case_record, unique_fields=("case_id",))


def load_eval_spec_records(path: str | os.PathLike[str]) -> list[Record]:
    return _load_jsonl(path, validate_eval_spec_record, unique_fields=("case_id",))


def load_run_records(path: str | os.PathLike[str]) -> list[Record]:
    return _load_jsonl(path, validate_run_record, unique_fields=("case_id", "task_run_id"))


def load_eval_result_records(path: str | os.PathLike[str]) -> list[Record]:
    return _load_jsonl(path, validate_eval_result, unique_fields=("case_id", "task_run_id"))


# Short aliases are retained for callers that treat the record type as implicit.
load_cases = load_case_records
load_eval_specs = load_eval_spec_records
load_eval_results = load_eval_result_records


def unique_index(records: Iterable[Mapping[str, Any]], field: str, label: str) -> dict[Any, Mapping[str, Any]]:
    """Index records by one required field while rejecting duplicates."""

    indexed: dict[Any, Mapping[str, Any]] = {}
    normalized_seen: set[Any] = set()
    for record in records:
        if field not in record:
            raise ContractError(f"{label} record is missing {field}")
        value = record[field]
        identity = value.casefold() if field == "case_id" and isinstance(value, str) else value
        if identity in normalized_seen:
            raise DuplicateRecordError(f"duplicate {field} in {label}: {value}")
        normalized_seen.add(identity)
        indexed[value] = record
    return indexed


def validate_run_batch(
    records: Sequence[Mapping[str, Any]],
    *,
    require_clean_git: bool = False,
) -> dict[str, Any]:
    """Prove that run records came from one batch and one runtime context."""

    if not records:
        raise ContractError("run record set must not be empty")
    batch_ids = {record["batch_run_id"] for record in records}
    if len(batch_ids) != 1:
        raise ContractError("run records must all have the same batch_run_id")
    context_fields = (
        "model",
        "architecture_mode",
        "request_timeout_seconds",
        "task_timeout_seconds",
        "recursion_limit",
        "system_git_sha",
        "system_git_dirty",
        "system_git_status_sha256",
        "cases_sha256",
        "python_version",
        "platform",
        "wall_clock_scope",
    )
    snapshot_presence = [
        (
            "system_snapshot" in _mapping(record["environment"], "run_record.environment"),
            "system_snapshot_sha256" in _mapping(
                record["environment"], "run_record.environment"
            ),
        )
        for record in records
    ]
    if any(present or digest_present for present, digest_present in snapshot_presence):
        if not all(present and digest_present for present, digest_present in snapshot_presence):
            raise ContractError(
                "run records in one batch must all carry the same system snapshot contract"
            )
        context_fields = (*context_fields, "system_snapshot", "system_snapshot_sha256")
    contexts: list[dict[str, Any]] = []
    for record in records:
        environment = _mapping(record["environment"], "run_record.environment")
        missing = [field for field in context_fields if field not in environment]
        if missing:
            raise ContractError(
                "formal run context is missing required fields: " + ", ".join(missing)
            )
        _nonempty_string(environment["model"], "run_record.environment.model")
        architecture_mode = _nonempty_string(
            environment["architecture_mode"], "run_record.environment.architecture_mode"
        )
        if architecture_mode not in ARCHITECTURE_MODES:
            raise ContractError(
                "run_record.environment.architecture_mode must be one of: "
                + ", ".join(ARCHITECTURE_MODES)
            )
        if "system_snapshot" in context_fields:
            snapshot_digest = _nonempty_string(
                environment["system_snapshot_sha256"],
                "run_record.environment.system_snapshot_sha256",
            )
            if not _SHA256_RE.fullmatch(snapshot_digest):
                raise ContractError(
                    "run_record.environment.system_snapshot_sha256 must be a SHA-256 digest"
                )
            try:
                from orchestration.system_snapshot import validate_system_snapshot

                validated_snapshot = validate_system_snapshot(
                    environment["system_snapshot"],
                    expected_sha256=snapshot_digest,
                    architecture_mode=architecture_mode,
                    model_name=str(environment.get("model") or ""),
                )
                snapshot_limits = validated_snapshot.get("limits", {})
                for field in (
                    "request_timeout_seconds",
                    "task_timeout_seconds",
                    "recursion_limit",
                ):
                    if field in snapshot_limits and float(snapshot_limits[field]) != float(
                        environment.get(field, -1)
                    ):
                        raise ValueError(
                            f"snapshot limit {field} does not match run environment"
                        )
            except ValueError as exc:
                raise ContractError(
                    f"run_record.environment.system_snapshot is invalid: {exc}"
                ) from exc
        for field in ("request_timeout_seconds", "recursion_limit"):
            if _nonnegative_int(environment[field], f"run_record.environment.{field}") <= 0:
                raise ContractError(f"run_record.environment.{field} must be positive")
        if _nonnegative_number(
            environment["task_timeout_seconds"], "run_record.environment.task_timeout_seconds"
        ) <= 0:
            raise ContractError("run_record.environment.task_timeout_seconds must be positive")
        git_sha = _nonempty_string(
            environment["system_git_sha"], "run_record.environment.system_git_sha"
        )
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", git_sha):
            raise ContractError("run_record.environment.system_git_sha must be a full Git object ID")
        if not isinstance(environment["system_git_dirty"], bool):
            raise ContractError("run_record.environment.system_git_dirty must be a boolean")
        if require_clean_git and environment["system_git_dirty"]:
            raise ContractError("formal benchmark aggregation requires a clean Git worktree")
        for field in ("system_git_status_sha256", "cases_sha256"):
            digest = _nonempty_string(environment[field], f"run_record.environment.{field}")
            if not _SHA256_RE.fullmatch(digest):
                raise ContractError(f"run_record.environment.{field} must be a SHA-256 digest")
        case_digest = _nonempty_string(
            environment.get("case_sha256"), "run_record.environment.case_sha256"
        )
        if not _SHA256_RE.fullmatch(case_digest):
            raise ContractError("run_record.environment.case_sha256 must be a SHA-256 digest")
        _nonempty_string(environment["python_version"], "run_record.environment.python_version")
        _nonempty_string(environment["platform"], "run_record.environment.platform")
        if environment["wall_clock_scope"] != "parent_process_start_to_worker_exit":
            raise ContractError(
                "run_record.environment.wall_clock_scope must be parent_process_start_to_worker_exit"
            )
        contexts.append({field: environment[field] for field in context_fields})
    architecture_modes = {context["architecture_mode"] for context in contexts}
    if len(architecture_modes) != 1:
        raise ContractError("run records in one batch must share the same architecture_mode")
    canonical = json.dumps(contexts[0], ensure_ascii=False, sort_keys=True, allow_nan=False)
    if any(
        json.dumps(context, ensure_ascii=False, sort_keys=True, allow_nan=False) != canonical
        for context in contexts[1:]
    ):
        raise ContractError("run records must share the same model, code, and runtime context")
    for record in records:
        environment = _mapping(record["environment"], "run_record.environment")
        usage = _mapping(record["model_usage"], "run_record.model_usage")
        if usage.get("usage_complete") is not True:
            continue
        expected_model = str(environment["model"]).strip().casefold()
        for index, raw_call in enumerate(usage.get("calls") or []):
            call = _mapping(raw_call, f"run_record.model_usage.calls[{index}]")
            for field in ("requested_model_id", "provider_reported_model_id"):
                if field == "requested_model_id" and not call.get(field):
                    continue
                actual_model = str(call.get(field) or "").strip().casefold()
                if not (
                    actual_model == expected_model
                    or actual_model.startswith(f"{expected_model}-")
                    or actual_model.startswith(f"{expected_model}:")
                ):
                    raise ContractError(
                        f"run_record.model_usage.calls[{index}].{field} "
                        "does not match run_record.environment.model"
                    )
    return {"batch_run_id": next(iter(batch_ids)), "environment": contexts[0]}


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> Path:
    """Write one UTF-8 JSON document using same-directory atomic replacement."""

    _json_compatible(value, "JSON output")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        return destination
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def atomic_write_jsonl(path: str | os.PathLike[str], records: Iterable[Any]) -> Path:
    """Atomically replace a JSONL file with validated UTF-8 JSON values."""

    materialized = list(records)
    for index, record in enumerate(materialized):
        _json_compatible(record, f"JSONL record {index}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            for record in materialized:
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
        return destination
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass
