from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, cast

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage

_HANDOFF_PREFIXES = ("transfer", "handoff")
_HANDOFF_TARGET_MARKERS = ("ntl_engineer", "ntlengineer", "supervisor")

_DEFAULT_REPAIR_INSTRUCTION = (
    "Handoff tool names to engineer/supervisor are not available in this runtime. "
    "Do NOT call any transfer/handoff tool to engineer/supervisor. "
    "You must either: (1) call only valid available tools, or "
    "(2) return a final structured JSON result directly."
)


def _normalize_tool_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", (name or "").lower())


def _is_handoff_like_tool_name(name: str) -> bool:
    normalized = _normalize_tool_name(name)
    return bool(normalized and normalized.startswith(_HANDOFF_PREFIXES))


def _is_invalid_handoff_target(name: str) -> bool:
    normalized = _normalize_tool_name(name)
    if not normalized:
        return False
    if not normalized.startswith(_HANDOFF_PREFIXES):
        return False
    return any(marker in normalized for marker in _HANDOFF_TARGET_MARKERS)


def _extract_available_tool_names(tools: list[Any]) -> set[str]:
    """Normalize available tool names from ModelRequest.tools."""
    names: set[str] = set()
    for tool in tools or []:
        raw_name: str = ""
        # BaseTool
        if hasattr(tool, "name"):
            raw_name = str(getattr(tool, "name", "") or "")
        # Dict-style schema
        elif isinstance(tool, dict):
            raw_name = str(tool.get("name") or "")
            if not raw_name and isinstance(tool.get("function"), dict):
                raw_name = str((tool.get("function") or {}).get("name") or "")
        normalized = _normalize_tool_name(raw_name)
        if normalized:
            names.add(normalized)
    return names


def _build_available_tools_hint(available_tool_names: set[str]) -> str:
    if not available_tool_names:
        return ""
    ordered = ", ".join(sorted(available_tool_names))
    return (
        "Available tool names in this sub-agent are strictly: "
        f"{ordered}. "
        "If you need a handoff, do NOT call transfer/handoff tools. "
        "Instead, return final structured JSON for supervisor continuation."
    )


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _analyze_ai_message(
    message: AIMessage,
    *,
    available_tool_names: set[str] | None = None,
) -> tuple[str, AIMessage | None, list[str]]:
    tool_calls = list(message.tool_calls or [])
    if not tool_calls:
        return "unchanged", message, []

    invalid: list[str] = []
    valid_calls: list[dict[str, Any]] = []
    normalized_available = available_tool_names or set()
    for call in tool_calls:
        name = str(call.get("name", ""))
        normalized_name = _normalize_tool_name(name)
        is_handoff_like = _is_handoff_like_tool_name(name)
        is_unavailable_handoff = (
            is_handoff_like and normalized_name and normalized_name not in normalized_available
        )
        if _is_invalid_handoff_target(name) or is_unavailable_handoff:
            invalid.append(name)
            continue
        valid_calls.append(call)

    if not invalid:
        return "unchanged", message, []

    if valid_calls:
        response_metadata = dict(message.response_metadata or {})
        response_metadata["suppressed_invalid_handoff_tool_calls"] = invalid
        response_metadata["handoff_guard_status"] = "filtered"
        return (
            "filtered",
            AIMessage(
                content=message.content,
                name=message.name,
                id=message.id,
                additional_kwargs=dict(message.additional_kwargs or {}),
                response_metadata=response_metadata,
                usage_metadata=message.usage_metadata,
                tool_calls=valid_calls,
                invalid_tool_calls=list(message.invalid_tool_calls or []),
            ),
            invalid,
        )

    return "needs_repair", None, invalid


def _process_response(
    response: ModelResponse | AIMessage,
    *,
    available_tool_names: set[str] | None = None,
) -> tuple[ModelResponse | AIMessage | None, bool, list[str], str]:
    if isinstance(response, AIMessage):
        status, updated, suppressed = _analyze_ai_message(
            response, available_tool_names=available_tool_names
        )
        if status == "needs_repair":
            note = response.content if isinstance(response.content, str) else ""
            return None, True, suppressed, note.strip()
        return (updated if updated is not None else response), False, suppressed, ""

    changed = False
    needs_repair = False
    suppressed_total: list[str] = []
    fallback_note = ""
    updated_messages = []

    for msg in response.result:
        if not isinstance(msg, AIMessage):
            updated_messages.append(msg)
            continue
        status, updated, suppressed = _analyze_ai_message(
            msg, available_tool_names=available_tool_names
        )
        if status == "needs_repair":
            needs_repair = True
            suppressed_total.extend(suppressed)
            if not fallback_note and isinstance(msg.content, str):
                fallback_note = msg.content.strip()
            updated_messages.append(msg)
            continue
        if status == "filtered":
            changed = True
            suppressed_total.extend(suppressed)
        updated_messages.append(updated if updated is not None else msg)

    if needs_repair:
        return None, True, suppressed_total, fallback_note

    if changed:
        return ModelResponse(result=updated_messages, structured_response=response.structured_response), False, suppressed_total, ""

    return response, False, [], ""


def _attach_repair_metadata(
    response: ModelResponse | AIMessage,
    *,
    repair_attempts: int,
    suppressed_tool_calls: list[str],
) -> ModelResponse | AIMessage:
    if repair_attempts <= 0 and not suppressed_tool_calls:
        return response

    metadata_patch = {
        "handoff_guard_repair_attempts": repair_attempts,
        "handoff_guard_status": "repaired" if repair_attempts > 0 else "filtered",
    }
    if suppressed_tool_calls:
        metadata_patch["suppressed_invalid_handoff_tool_calls"] = _unique_keep_order(suppressed_tool_calls)

    def patch_msg(msg: AIMessage) -> AIMessage:
        meta = dict(msg.response_metadata or {})
        meta.update(metadata_patch)
        return AIMessage(
            content=msg.content,
            name=msg.name,
            id=msg.id,
            additional_kwargs=dict(msg.additional_kwargs or {}),
            response_metadata=meta,
            usage_metadata=msg.usage_metadata,
            tool_calls=list(msg.tool_calls or []),
            invalid_tool_calls=list(msg.invalid_tool_calls or []),
        )

    if isinstance(response, AIMessage):
        return patch_msg(response)

    updated = []
    for msg in response.result:
        if isinstance(msg, AIMessage):
            updated.append(patch_msg(msg))
        else:
            updated.append(msg)
    return ModelResponse(result=updated, structured_response=response.structured_response)


def _build_repair_request(request: ModelRequest, instruction: str) -> ModelRequest:
    available_tool_names = _extract_available_tool_names(
        list(getattr(request, "tools", None) or [])
    )
    full_instruction = "\n\n".join(
        p for p in [instruction, _build_available_tools_hint(available_tool_names)] if p
    )
    if request.system_message is not None:
        existing_content = request.system_message.content
        if isinstance(existing_content, str):
            merged_content = f"{existing_content}\n\n{full_instruction}"
        elif isinstance(existing_content, list):
            merged_content = cast(
                "list[str | dict[str, str]]",
                [*existing_content, {"type": "text", "text": f"\n\n{full_instruction}"}],
            )
        else:
            merged_content = f"{str(existing_content)}\n\n{full_instruction}"
    else:
        merged_content = full_instruction

    new_system_message = SystemMessage(content=cast("list[str | dict[str, str]] | str", merged_content))
    overrides: dict[str, Any] = {"system_message": new_system_message}
    # When tools exist, force the model to pick a valid tool instead of free-text
    # hallucinated handoff names.
    if available_tool_names:
        overrides["tool_choice"] = "required"
    return request.override(**overrides)


def _build_exhausted_response(
    *,
    suppressed_tool_calls: list[str],
    repair_attempts: int,
    assistant_note: str,
) -> AIMessage:
    payload: dict[str, Any] = {
        "status": "needs_engineer_decision",
        "failure_level": "runtime_handoff_guard",
        "reason": "invalid_handoff_tool_call_repeated",
        "suppressed_tool_calls": _unique_keep_order(suppressed_tool_calls),
        "repair_attempts": repair_attempts,
        "guidance": (
            "Sub-agent repeatedly attempted unavailable handoff tool names. "
            "Engineer should re-dispatch with tighter sub-task boundaries or "
            "request direct final structured output."
        ),
    }
    if assistant_note:
        payload["assistant_note"] = assistant_note

    return AIMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_calls=[],
        response_metadata={
            "handoff_guard_status": "exhausted",
            "handoff_guard_repair_attempts": repair_attempts,
            "suppressed_invalid_handoff_tool_calls": _unique_keep_order(suppressed_tool_calls),
        },
    )


class SubagentHandoffGuardMiddleware(AgentMiddleware):
    """Guard sub-agents against invalid handoff tool hallucinations.

    Success-first policy:
    - Keep valid tool calls.
    - Remove invalid handoff calls.
    - If only invalid handoff calls are produced, retry model call with a repair
      instruction up to `max_repair_attempts`.
    - On exhaustion, return a readable terminal message without tool calls.
    """

    def __init__(
        self,
        *,
        max_repair_attempts: int = 3,
        repair_instruction: str = _DEFAULT_REPAIR_INSTRUCTION,
    ) -> None:
        self.max_repair_attempts = max(1, int(max_repair_attempts))
        self.repair_instruction = repair_instruction

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        suppressed_all: list[str] = []
        repair_attempts = 0
        current_request = request
        last_note = ""
        available_tool_names = _extract_available_tool_names(
            list(getattr(request, "tools", None) or [])
        )

        while True:
            response = handler(current_request)
            processed, needs_repair, suppressed, note = _process_response(
                response,
                available_tool_names=available_tool_names,
            )
            if suppressed:
                suppressed_all.extend(suppressed)
            if note:
                last_note = note

            if not needs_repair and processed is not None:
                return _attach_repair_metadata(
                    processed,
                    repair_attempts=repair_attempts,
                    suppressed_tool_calls=suppressed_all,
                )

            repair_attempts += 1
            if repair_attempts >= self.max_repair_attempts:
                return _build_exhausted_response(
                    suppressed_tool_calls=suppressed_all,
                    repair_attempts=repair_attempts,
                    assistant_note=last_note,
                )

            current_request = _build_repair_request(current_request, self.repair_instruction)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        suppressed_all: list[str] = []
        repair_attempts = 0
        current_request = request
        last_note = ""
        available_tool_names = _extract_available_tool_names(
            list(getattr(request, "tools", None) or [])
        )

        while True:
            response = await handler(current_request)
            processed, needs_repair, suppressed, note = _process_response(
                response,
                available_tool_names=available_tool_names,
            )
            if suppressed:
                suppressed_all.extend(suppressed)
            if note:
                last_note = note

            if not needs_repair and processed is not None:
                return _attach_repair_metadata(
                    processed,
                    repair_attempts=repair_attempts,
                    suppressed_tool_calls=suppressed_all,
                )

            repair_attempts += 1
            if repair_attempts >= self.max_repair_attempts:
                return _build_exhausted_response(
                    suppressed_tool_calls=suppressed_all,
                    repair_attempts=repair_attempts,
                    assistant_note=last_note,
                )

            current_request = _build_repair_request(current_request, self.repair_instruction)
