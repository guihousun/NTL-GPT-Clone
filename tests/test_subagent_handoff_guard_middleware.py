import json
from types import SimpleNamespace

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage

from middlewares.subagent_handoff_guard import (
    SubagentHandoffGuardMiddleware,
    _process_response,
)


def _build_response(tool_names: list[str], content: str = "agent output") -> ModelResponse:
    tool_calls = [{"name": n, "args": {}, "id": f"tc_{idx}"} for idx, n in enumerate(tool_names, start=1)]
    return ModelResponse(result=[AIMessage(content=content, name="Code_Assistant", tool_calls=tool_calls)])


def test_mixed_tool_calls_keep_valid_calls_and_drop_invalid_transfer():
    response = _build_response(["transfer_to_ntl_engineer", "execute_geospatial_script_tool"])
    processed, needs_repair, suppressed, _ = _process_response(response)
    assert not needs_repair
    assert suppressed == ["transfer_to_ntl_engineer"]
    message = processed.result[0]  # type: ignore[union-attr]
    assert isinstance(message, AIMessage)
    assert [c["name"] for c in message.tool_calls] == ["execute_geospatial_script_tool"]


def test_only_invalid_transfer_requires_repair_not_immediate_termination():
    response = _build_response(["transfer_to_ntl_engineer"])
    processed, needs_repair, suppressed, _ = _process_response(response)
    assert processed is None
    assert needs_repair is True
    assert suppressed == ["transfer_to_ntl_engineer"]


def test_handoff_to_supervisor_variant_is_detected_for_repair():
    response = _build_response(["handoff_to_supervisor"])
    processed, needs_repair, suppressed, _ = _process_response(response)
    assert processed is None
    assert needs_repair is True
    assert suppressed == ["handoff_to_supervisor"]


def test_unavailable_transfer_like_tool_is_suppressed_for_repair():
    response = _build_response(["transfer_to_data_searcher"])
    processed, needs_repair, suppressed, _ = _process_response(
        response,
        available_tool_names={"execute_geospatial_script_tool"},
    )
    assert processed is None
    assert needs_repair is True
    assert suppressed == ["transfer_to_data_searcher"]


def test_available_transfer_like_tool_is_not_forced_suppressed():
    response = _build_response(["transfer_to_data_searcher"])
    processed, needs_repair, suppressed, _ = _process_response(
        response,
        available_tool_names={"transfer_to_data_searcher"},
    )
    assert not needs_repair
    assert suppressed == []
    message = processed.result[0]  # type: ignore[union-attr]
    assert isinstance(message, AIMessage)
    assert [c["name"] for c in message.tool_calls] == ["transfer_to_data_searcher"]


def test_normal_tool_call_is_unchanged():
    response = _build_response(["execute_geospatial_script_tool"])
    processed, needs_repair, suppressed, _ = _process_response(response)
    assert not needs_repair
    assert suppressed == []
    message = processed.result[0]  # type: ignore[union-attr]
    assert isinstance(message, AIMessage)
    assert [c["name"] for c in message.tool_calls] == ["execute_geospatial_script_tool"]


def test_middleware_retry_then_success_path():
    middleware = SubagentHandoffGuardMiddleware(max_repair_attempts=3)
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            return _build_response(["transfer_to_ntl_engineer"], content="bad handoff")
        return _build_response(["execute_geospatial_script_tool"], content="repaired")

    output = middleware.wrap_model_call(
        request=SimpleNamespace(system_message=None, override=lambda **kwargs: SimpleNamespace(system_message=kwargs.get("system_message"), override=lambda **kw: SimpleNamespace(system_message=kw.get("system_message"), override=lambda **k: None))),
        handler=handler,
    )
    assert isinstance(output, ModelResponse)
    message = output.result[0]
    assert isinstance(message, AIMessage)
    assert [c["name"] for c in message.tool_calls] == ["execute_geospatial_script_tool"]
    assert message.response_metadata.get("handoff_guard_repair_attempts") == 1


def test_middleware_exhaustion_returns_readable_non_tool_payload():
    middleware = SubagentHandoffGuardMiddleware(max_repair_attempts=2)

    def handler(_req):
        return _build_response(["transfer_back_to_ntl_engineer"], content="still trying transfer")

    output = middleware.wrap_model_call(
        request=SimpleNamespace(system_message=None, override=lambda **kwargs: SimpleNamespace(system_message=kwargs.get("system_message"), override=lambda **kw: SimpleNamespace(system_message=kw.get("system_message"), override=lambda **k: None))),
        handler=handler,
    )
    assert isinstance(output, AIMessage)
    assert output.tool_calls == []
    assert output.response_metadata.get("handoff_guard_status") == "exhausted"
    assert output.response_metadata.get("handoff_guard_repair_attempts") == 2
    assert output.response_metadata.get("suppressed_invalid_handoff_tool_calls") == [
        "transfer_back_to_ntl_engineer"
    ]
    payload = json.loads(output.content)
    assert payload["status"] == "needs_engineer_decision"
    assert payload["failure_level"] == "runtime_handoff_guard"
    assert payload["repair_attempts"] == 2
    assert payload["suppressed_tool_calls"] == ["transfer_back_to_ntl_engineer"]


def test_repair_retry_sets_tool_choice_required_when_tools_exist():
    middleware = SubagentHandoffGuardMiddleware(max_repair_attempts=2)
    seen_tool_choices = []

    def make_request(system_message=None, tool_choice=None):
        def _override(**kwargs):
            return make_request(
                system_message=kwargs.get("system_message", system_message),
                tool_choice=kwargs.get("tool_choice", tool_choice),
            )

        return SimpleNamespace(
            system_message=system_message,
            tool_choice=tool_choice,
            tools=[{"name": "execute_geospatial_script_tool"}],
            override=_override,
        )

    def handler(req):
        seen_tool_choices.append(getattr(req, "tool_choice", None))
        return _build_response(["transfer_to_ntl_engineer"], content="bad handoff")

    output = middleware.wrap_model_call(
        request=make_request(),
        handler=handler,
    )
    assert isinstance(output, AIMessage)
    # First call keeps original tool_choice (None), retry enforces required.
    assert seen_tool_choices == [None, "required"]
