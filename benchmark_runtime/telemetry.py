from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any, Iterable
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler


TELEMETRY_SCHEMA = "ntl-benchmark.telemetry.v1"

_SENSITIVE_FIELD_PARTS = (
    "token",
    "apikey",
    "accesskey",
    "privatekey",
    "secret",
    "password",
    "passwd",
    "authorization",
    "credential",
    "cookie",
)
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|private[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|token|password|passwd|secret|authorization|credential|cookie)"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)
_AUTH_BEARER_RE = re.compile(
    r"(?i)\b(authorization)(\s*[:=]\s*)Bearer\s+[^\s,;}\]]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_EXCLUDED_USAGE_SCOPES = {
    "critic",
    "tool",
    "tools",
    "vlm",
    "vision",
    "embedding",
    "embeddings",
    "eval",
    "evaluation",
    "evaluator",
    "judge",
    "grader",
    "grading",
    "rerank",
    "reranker",
}

_SCOPE_OR_NAME_METADATA_FIELDS = {
    "agentrole",
    "benchmarkusagescope",
    "calltype",
    "component",
    "componenttype",
    "langgraphnode",
    "node",
    "usagescope",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return dict(value or {})
    except (TypeError, ValueError):
        return {}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _jsonable(model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    return str(value)


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = _AUTH_BEARER_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text
    )
    text = _SENSITIVE_TEXT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    return _BEARER_RE.sub("Bearer <redacted>", text)


def _sensitive_field(key: Any) -> bool:
    raw = str(key or "").casefold()
    collapsed = re.sub(r"[^a-z0-9]", "", raw)
    tokens = {part for part in re.split(r"[^a-z0-9]+", raw) if part}
    if "key" in tokens or collapsed.endswith("key"):
        return True
    return any(part in collapsed for part in _SENSITIVE_FIELD_PARTS)


def redact_sensitive(value: Any) -> Any:
    """Return a JSON-safe copy with credential-like fields redacted."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            result[str(key)] = "<redacted>" if _sensitive_field(key) else redact_sensitive(item)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return redact_sensitive(model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    return _jsonable(value)


def _stable_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return text.encode("utf-8", errors="replace")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _first_int(payloads: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> int | None:
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                normalized = int(value)
                if normalized >= 0:
                    return normalized
    return None


def _first_text(payloads: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _message_from_result(response: Any) -> Any | None:
    for group in getattr(response, "generations", []) or []:
        for generation in group or []:
            message = getattr(generation, "message", None)
            if message is not None:
                return message
    return None


def _normalized_words(value: Any) -> set[str]:
    text = str(value or "")
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return {part for part in re.split(r"[^a-z0-9]+", text.casefold()) if part}


def _metadata_scope_and_name_values(metadata: dict[str, Any]) -> list[Any]:
    """Collect every metadata value that can identify a call's scope or owner.

    LangGraph and Deep Agents may add multiple ownership fields to the same
    callback.  They are intentionally all inspected: choosing the first
    non-empty name can otherwise let ``lc_agent_name=Data_Searcher`` conceal
    ``langgraph_node=tools`` on a non-tested model call.
    """

    values: list[Any] = []
    stack: list[dict[str, Any]] = [metadata]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        for key, value in current.items():
            raw_key = str(key or "").casefold()
            collapsed_key = re.sub(r"[^a-z0-9]", "", raw_key)
            key_words = _normalized_words(raw_key)
            if (
                "scope" in key_words
                or "name" in key_words
                or collapsed_key.endswith("scope")
                or collapsed_key.endswith("name")
                or collapsed_key in _SCOPE_OR_NAME_METADATA_FIELDS
            ):
                values.append(value)
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, (list, tuple)):
                stack.extend(item for item in value if isinstance(item, dict))
    return values


def _provider_tokens_complete(call: dict[str, Any]) -> bool:
    values = (
        call.get("input_tokens"),
        call.get("output_tokens"),
        call.get("total_tokens"),
    )
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values):
        return False
    return int(call["total_tokens"]) == int(call["input_tokens"]) + int(call["output_tokens"])


class BenchmarkTelemetryCallback(BaseCallbackHandler):
    """Thread-safe provider usage and nested tool telemetry.

    The callback is attached only to the tested graph.  It counts chat-model
    calls whose requested model matches ``tested_model_ids`` and ignores calls
    explicitly marked as tool/VLM/embedding/evaluation work.  Tool callbacks
    retain the parent run id, so calls made by nested subagents are not lost
    when their messages are absent from the supervisor's final state.
    """

    run_inline = True

    def __init__(
        self,
        journal_path: str | Path | None = None,
        *,
        tested_model_ids: Iterable[str] | None = None,
        capture_usage: bool = True,
        capture_tools: bool = True,
    ) -> None:
        self._lock = RLock()
        self._journal_path = Path(journal_path) if journal_path else None
        self._tested_model_ids = {
            str(value).strip().casefold() for value in (tested_model_ids or []) if str(value).strip()
        }
        self._capture_usage = capture_usage
        self._capture_tools = capture_tools
        self._model_calls: dict[str, dict[str, Any]] = {}
        self._pending_model_calls: dict[str, dict[str, Any]] = {}
        self._model_call_sequence = 0
        self._ignored_model_runs: set[str] = set()
        self._tool_calls: dict[str, dict[str, Any]] = {}
        self._run_parents: dict[str, str | None] = {}
        self._usage_incomplete_reasons: list[str] = []

    def _requested_model_id(
        self,
        serialized: dict[str, Any],
        metadata: dict[str, Any],
        invocation_params: dict[str, Any],
    ) -> str | None:
        return _first_text(
            (metadata, invocation_params, serialized),
            ("ls_model_name", "model_name", "model", "model_id", "model_version"),
        )

    def _matches_tested_model(self, value: Any) -> bool:
        candidate = str(value or "").strip().casefold()
        if not candidate:
            return False
        if not self._tested_model_ids:
            return True
        return any(
            candidate == allowed
            or candidate.startswith(f"{allowed}-")
            or candidate.startswith(f"{allowed}:")
            for allowed in self._tested_model_ids
        )

    def _model_call_decision(
        self,
        serialized: dict[str, Any],
        metadata: dict[str, Any],
        tags: list[str],
        invocation_params: dict[str, Any],
    ) -> str:
        if metadata.get("benchmark_count_usage") is False:
            return "ignore"
        scope_values = [
            *_metadata_scope_and_name_values(metadata),
            *tags,
        ]
        for value in scope_values:
            if _normalized_words(value).intersection(_EXCLUDED_USAGE_SCOPES):
                return "ignore"
        requested = self._requested_model_id(serialized, metadata, invocation_params)
        if self._tested_model_ids:
            if not requested:
                # Keep the callback internally until the provider response can
                # establish identity, but do not count it as a tested call yet.
                return "pending_identity"
            if not self._matches_tested_model(requested):
                return "ignore"
        return "include"

    def _include_model_call(
        self,
        serialized: dict[str, Any],
        metadata: dict[str, Any],
        tags: list[str],
        invocation_params: dict[str, Any],
    ) -> bool:
        return (
            self._model_call_decision(serialized, metadata, tags, invocation_params)
            == "include"
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del messages
        if not self._capture_usage:
            return
        serialized_map = _mapping(serialized)
        metadata_map = _mapping(metadata)
        invocation = _mapping(kwargs.get("invocation_params"))
        tag_values = list(tags or [])
        run_key = str(run_id)
        with self._lock:
            self._run_parents[run_key] = str(parent_run_id) if parent_run_id else None
            decision = self._model_call_decision(
                serialized_map, metadata_map, tag_values, invocation
            )
            if decision == "ignore":
                self._ignored_model_runs.add(run_key)
                return
            self._model_call_sequence += 1
            call = {
                "sequence": self._model_call_sequence,
                "agent_name": _first_text(
                    (metadata_map,),
                    ("lc_agent_name", "agent_name", "graph_name", "langgraph_node"),
                ) or "unknown",
                "provider_request_id": None,
                "provider_reported_model_id": None,
                "model_identity_matches_tested": None,
                "requested_model_id": self._requested_model_id(serialized_map, metadata_map, invocation),
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "usage_complete": False,
                "status": "in_flight",
                "started_at": _utc_now(),
                "ended_at": None,
                "run_id": run_key,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "error": None,
            }
            if decision == "pending_identity":
                self._pending_model_calls[run_key] = call
            else:
                self._model_calls[run_key] = call
            self._write_journal_locked()

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if not self._capture_usage:
            return
        run_key = str(run_id)
        message = _message_from_result(response)
        response_metadata = _mapping(getattr(message, "response_metadata", None))
        usage_metadata = _mapping(getattr(message, "usage_metadata", None))
        llm_output = _mapping(getattr(response, "llm_output", None))
        usage_payloads = (
            usage_metadata,
            _mapping(response_metadata.get("token_usage")),
            _mapping(response_metadata.get("usage")),
            _mapping(llm_output.get("token_usage")),
            _mapping(llm_output.get("usage")),
            llm_output,
        )
        input_tokens = _first_int(usage_payloads, ("input_tokens", "prompt_tokens"))
        output_tokens = _first_int(usage_payloads, ("output_tokens", "completion_tokens"))
        total_tokens = _first_int(usage_payloads, ("total_tokens",))
        model_id = _first_text(
            (response_metadata, llm_output),
            ("model_name", "model", "model_id", "model_version", "ls_model_name"),
        )
        request_id = _first_text(
            (response_metadata, llm_output),
            ("request_id", "id", "response_id"),
        )
        with self._lock:
            if run_key in self._ignored_model_runs:
                self._ignored_model_runs.discard(run_key)
                return
            call = self._model_calls.get(run_key)
            if call is None:
                call = self._pending_model_calls.pop(run_key, None)
                if call is None:
                    return
                if not model_id:
                    reason = "provider_model_identity_missing_for_unresolved_call"
                    if reason not in self._usage_incomplete_reasons:
                        self._usage_incomplete_reasons.append(reason)
                    self._write_journal_locked()
                    return
                if not self._matches_tested_model(model_id):
                    self._write_journal_locked()
                    return
                self._model_calls[run_key] = call
            identity_matches = bool(model_id and self._matches_tested_model(model_id))
            tokens_complete = all(
                value is not None and value >= 0
                for value in (input_tokens, output_tokens, total_tokens)
            )
            complete = bool(
                tokens_complete
                and total_tokens == int(input_tokens or 0) + int(output_tokens or 0)
                and identity_matches
                and bool(request_id)
            )
            call.update(
                {
                    "provider_request_id": request_id,
                    "provider_reported_model_id": model_id,
                    "model_identity_matches_tested": identity_matches,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "usage_complete": complete,
                    "status": "completed",
                    "ended_at": _utc_now(),
                    "parent_run_id": str(parent_run_id) if parent_run_id else call.get("parent_run_id"),
                }
            )
            self._write_journal_locked()

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if not self._capture_usage:
            return
        run_key = str(run_id)
        with self._lock:
            if run_key in self._ignored_model_runs:
                self._ignored_model_runs.discard(run_key)
                return
            call = self._model_calls.get(run_key)
            if call is None:
                pending = self._pending_model_calls.pop(run_key, None)
                if pending is not None:
                    reason = "unresolved_tested_model_identity_on_llm_error"
                    if reason not in self._usage_incomplete_reasons:
                        self._usage_incomplete_reasons.append(reason)
                    self._write_journal_locked()
                return
            call.update(
                {
                    "usage_complete": False,
                    "status": "error",
                    "ended_at": _utc_now(),
                    "parent_run_id": str(parent_run_id) if parent_run_id else call.get("parent_run_id"),
                    "error": {"code": type(error).__name__, "message": redact_text(error)},
                }
            )
            self._write_journal_locked()

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if not self._capture_tools:
            return
        serialized_map = _mapping(serialized)
        raw_arguments: Any = inputs
        if raw_arguments is None:
            try:
                raw_arguments = json.loads(input_str)
            except (TypeError, json.JSONDecodeError):
                raw_arguments = input_str
        arguments = redact_sensitive(raw_arguments)
        arguments_bytes = _stable_bytes(arguments)
        run_key = str(run_id)
        with self._lock:
            self._run_parents[run_key] = str(parent_run_id) if parent_run_id else None
            self._tool_calls[run_key] = {
                "sequence": len(self._tool_calls) + 1,
                "tool_call_id": run_key,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "tool_name": _first_text((serialized_map,), ("name", "id")) or "unknown",
                "status": "in_flight",
                "started_at": _utc_now(),
                "ended_at": None,
                "arguments": arguments,
                "arguments_sha256": hashlib.sha256(arguments_bytes).hexdigest(),
                "result_observed": False,
                "result_sha256": None,
                "result_bytes": None,
                "error": None,
                "tags": [str(tag) for tag in (tags or [])],
                "metadata": redact_sensitive(_mapping(metadata)),
            }
            self._write_journal_locked()

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del serialized, inputs, kwargs
        with self._lock:
            self._run_parents[str(run_id)] = str(parent_run_id) if parent_run_id else None

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if not self._capture_tools:
            return
        run_key = str(run_id)
        result_bytes = _stable_bytes(output)
        with self._lock:
            call = self._tool_calls.get(run_key)
            if call is None:
                call = self._unmatched_tool_call_locked(run_key, parent_run_id)
            call.update(
                {
                    "status": "succeeded",
                    "ended_at": _utc_now(),
                    "result_observed": True,
                    "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                    "result_bytes": len(result_bytes),
                }
            )
            self._write_journal_locked()

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if not self._capture_tools:
            return
        run_key = str(run_id)
        with self._lock:
            call = self._tool_calls.get(run_key)
            if call is None:
                call = self._unmatched_tool_call_locked(run_key, parent_run_id)
            call.update(
                {
                    "status": "error",
                    "ended_at": _utc_now(),
                    "error": {"code": type(error).__name__, "message": redact_text(error)},
                }
            )
            self._write_journal_locked()

    def _unmatched_tool_call_locked(
        self, run_key: str, parent_run_id: UUID | None
    ) -> dict[str, Any]:
        call = {
            "sequence": len(self._tool_calls) + 1,
            "tool_call_id": run_key,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tool_name": "unknown",
            "status": "in_flight",
            "started_at": None,
            "ended_at": None,
            "arguments": None,
            "arguments_sha256": None,
            "result_observed": False,
            "result_sha256": None,
            "result_bytes": None,
            "error": None,
            "tags": [],
            "metadata": {},
        }
        self._tool_calls[run_key] = call
        return call

    def mark_incomplete(self, reason: Any) -> None:
        with self._lock:
            message = redact_text(reason).strip() or "telemetry incomplete"
            if message not in self._usage_incomplete_reasons:
                self._usage_incomplete_reasons.append(message)
            self._write_journal_locked()

    def allow_tested_models(self, model_ids: Iterable[str]) -> None:
        """Add accepted requested model ids before the first model callback."""

        with self._lock:
            self._tested_model_ids.update(
                str(value).strip().casefold() for value in model_ids if str(value).strip()
            )

    def _model_usage_locked(self) -> dict[str, Any]:
        calls = sorted((deepcopy(call) for call in self._model_calls.values()), key=lambda row: row["sequence"])
        # Calls whose start metadata lacked a model identity reserve an internal
        # order slot while awaiting the provider response.  If that response is
        # later proven to be a different model, omit it and compact the public
        # tested-call sequence so the persisted audit record stays one-based and
        # gap-free.
        for sequence, call in enumerate(calls, start=1):
            call["sequence"] = sequence
        reasons = list(self._usage_incomplete_reasons)
        if not calls:
            reasons.append("no_tested_model_calls")
        if self._pending_model_calls:
            reasons.append("unresolved_tested_model_identity")
        if any(call.get("status") == "in_flight" for call in calls):
            reasons.append("in_flight_llm_call")
        if any(call.get("status") == "error" for call in calls):
            reasons.append("llm_error")
        if any(
            call.get("status") == "completed" and not _provider_tokens_complete(call)
            for call in calls
        ):
            reasons.append("provider_token_usage_missing_or_inconsistent")
        if any(
            call.get("status") == "completed" and not call.get("provider_request_id")
            for call in calls
        ):
            reasons.append("provider_request_id_missing")
        if any(
            call.get("status") == "completed"
            and not call.get("provider_reported_model_id")
            for call in calls
        ):
            reasons.append("provider_model_identity_missing")
        if any(
            call.get("status") == "completed"
            and call.get("model_identity_matches_tested") is False
            for call in calls
        ):
            reasons.append("provider_model_identity_mismatch")
        reasons = list(dict.fromkeys(reasons))
        complete = bool(calls) and not reasons and all(
            call.get("usage_complete") is True for call in calls
        )
        return {
            "llm_call_count": len(calls),
            "input_tokens": sum(int(call.get("input_tokens") or 0) for call in calls),
            "output_tokens": sum(int(call.get("output_tokens") or 0) for call in calls),
            "total_tokens": sum(int(call.get("total_tokens") or 0) for call in calls),
            "usage_complete": complete,
            "incomplete_reasons": reasons,
            "calls": calls,
        }

    def _tool_trace_locked(self) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for call in self._tool_calls.values():
            row = deepcopy(call)
            ancestors: list[str] = []
            seen: set[str] = set()
            parent = row.get("parent_run_id")
            while parent and parent not in seen:
                seen.add(parent)
                if parent in self._tool_calls:
                    ancestors.append(parent)
                parent = self._run_parents.get(parent)
            ancestors.reverse()
            row["ancestor_tool_call_ids"] = ancestors
            row["parent_tool_call_id"] = ancestors[-1] if ancestors else None
            trace.append(row)
        return sorted(trace, key=lambda row: row["sequence"])

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "schema_version": TELEMETRY_SCHEMA,
            "model_usage": self._model_usage_locked(),
            "tool_trace": self._tool_trace_locked(),
        }

    def _journal_payload_locked(self) -> Any:
        return self._snapshot_locked()

    def _write_journal_locked(self) -> None:
        if self._journal_path is not None:
            _atomic_write_json(self._journal_path, self._journal_payload_locked())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def model_usage_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._model_usage_locked()

    def tool_trace_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._tool_trace_locked()


class ProviderUsageCallback(BenchmarkTelemetryCallback):
    """Usage-only compatibility callback."""

    def __init__(
        self,
        journal_path: str | Path | None = None,
        *,
        tested_model_ids: Iterable[str] | None = None,
    ) -> None:
        super().__init__(
            journal_path,
            tested_model_ids=tested_model_ids,
            capture_usage=True,
            capture_tools=False,
        )

    def _journal_payload_locked(self) -> Any:
        return self._model_usage_locked()

    def snapshot(self) -> dict[str, Any]:
        return self.model_usage_snapshot()


class ToolTraceCallback(BenchmarkTelemetryCallback):
    """Tool-only compatibility callback."""

    def __init__(self, journal_path: str | Path | None = None) -> None:
        super().__init__(journal_path, capture_usage=False, capture_tools=True)

    def _journal_payload_locked(self) -> Any:
        return {"tool_trace": self._tool_trace_locked()}

    def snapshot(self) -> list[dict[str, Any]]:
        return self.tool_trace_snapshot()


def incomplete_model_usage(reason: str) -> dict[str, Any]:
    return {
        "llm_call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_complete": False,
        "incomplete_reasons": [redact_text(reason)],
        "calls": [],
    }
