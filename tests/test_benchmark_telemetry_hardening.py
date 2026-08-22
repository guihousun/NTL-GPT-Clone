from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
import pytest

from benchmark_runtime.telemetry import BenchmarkTelemetryCallback, ProviderUsageCallback


@pytest.fixture(autouse=True)
def _disable_remote_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


def _result(
    *,
    model_name: str | None,
    request_id: str | None,
    input_tokens: int = 3,
    output_tokens: int = 2,
) -> LLMResult:
    response_metadata: dict[str, object] = {}
    if model_name is not None:
        response_metadata["model_name"] = model_name
    if request_id is not None:
        response_metadata["request_id"] = request_id
    return LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="done",
                        usage_metadata={
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        },
                        response_metadata=response_metadata,
                    )
                )
            ]
        ]
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "lc_agent_name": "Data_Searcher",
            "agent_name": "NTL_Engineer",
            "langgraph_node": "tools",
            "ls_model_name": "tested-model",
        },
        {
            "lc_agent_name": "Data_Searcher",
            "graph_name": "benchmark_evaluator",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
        },
        {
            "lc_agent_name": "Data_Searcher",
            "custom_scope": "judge",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
        },
        {
            "lc_agent_name": "Data_Searcher",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
            "nested": {"pipeline_name": "embedding-worker"},
        },
        {
            "lc_agent_name": "Data_Searcher",
            "langgraph_node": "ToolNode",
            "ls_model_name": "tested-model",
        },
        {
            "lc_agent_name": "Data_Searcher",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
            "nested": {"pipeline_name": "VLMJudge"},
        },
    ],
)
def test_every_metadata_scope_and_name_field_can_exclude_call(
    metadata: dict[str, object],
) -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    run_id = uuid4()

    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata=metadata,
    )
    callback.on_llm_end(
        _result(model_name="tested-model", request_id="excluded-request"),
        run_id=run_id,
    )

    assert callback.snapshot()["llm_call_count"] == 0


def test_missing_requested_model_is_not_counted_until_matching_provider_end() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    run_id = uuid4()

    callback.on_chat_model_start(
        {"name": "CustomChat"},
        [[]],
        run_id=run_id,
        metadata={"lc_agent_name": "Data_Searcher", "langgraph_node": "model"},
    )

    pending = callback.snapshot()
    assert pending["llm_call_count"] == 0
    assert pending["usage_complete"] is False
    assert "unresolved_tested_model_identity" in pending["incomplete_reasons"]

    callback.on_llm_end(
        _result(model_name="tested-model-202608", request_id="matched-request"),
        run_id=run_id,
    )

    completed = callback.snapshot()
    assert completed["llm_call_count"] == 1
    assert completed["usage_complete"] is True
    assert completed["calls"][0]["agent_name"] == "Data_Searcher"
    assert completed["calls"][0]["requested_model_id"] is None


def test_missing_requested_model_never_counts_a_different_provider_model() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    run_id = uuid4()

    callback.on_chat_model_start(
        {"name": "CustomChat"},
        [[]],
        run_id=run_id,
        metadata={"lc_agent_name": "Data_Searcher", "langgraph_node": "model"},
    )
    callback.on_llm_end(
        _result(model_name="other-model", request_id="other-request"),
        run_id=run_id,
    )

    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 0
    assert snapshot["total_tokens"] == 0
    assert snapshot["usage_complete"] is False


def test_excluded_pending_identity_does_not_leave_a_public_sequence_gap() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    excluded_run = uuid4()
    included_run = uuid4()
    callback.on_chat_model_start(
        {"name": "CustomChat"},
        [[]],
        run_id=excluded_run,
        metadata={"lc_agent_name": "Data_Searcher", "langgraph_node": "model"},
    )
    callback.on_llm_end(
        _result(model_name="other-model", request_id="other-request"),
        run_id=excluded_run,
    )
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=included_run,
        metadata={
            "lc_agent_name": "NTL_Engineer",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
        },
    )
    callback.on_llm_end(
        _result(model_name="tested-model", request_id="tested-request"),
        run_id=included_run,
    )

    snapshot = callback.snapshot()
    assert snapshot["usage_complete"] is True
    assert [call["sequence"] for call in snapshot["calls"]] == [1]


def test_missing_provider_request_id_keeps_call_and_usage_incomplete() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    run_id = uuid4()

    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={
            "lc_agent_name": "NTL_Engineer",
            "langgraph_node": "model",
            "ls_model_name": "tested-model",
        },
    )
    callback.on_llm_end(
        _result(model_name="tested-model", request_id=None),
        run_id=run_id,
    )

    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["calls"][0]["provider_request_id"] is None
    assert snapshot["calls"][0]["usage_complete"] is False
    assert snapshot["usage_complete"] is False
    assert "provider_request_id_missing" in snapshot["incomplete_reasons"]
    assert "provider_token_usage_missing_or_inconsistent" not in snapshot["incomplete_reasons"]


def test_lc_agent_name_preserves_main_and_subagent_ownership() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    runs = [(uuid4(), "NTL_Engineer"), (uuid4(), "Data_Searcher")]

    for run_id, lc_agent_name in runs:
        callback.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[]],
            run_id=run_id,
            metadata={
                "lc_agent_name": lc_agent_name,
                "agent_name": "NTL_Engineer",
                "graph_name": "NTL_Engineer",
                "langgraph_node": "model",
                "ls_model_name": "tested-model",
            },
        )
        callback.on_llm_end(
            _result(model_name="tested-model", request_id=f"request-{lc_agent_name}"),
            run_id=run_id,
        )

    snapshot = callback.snapshot()
    assert snapshot["usage_complete"] is True
    assert [call["agent_name"] for call in snapshot["calls"]] == [
        "NTL_Engineer",
        "Data_Searcher",
    ]


@pytest.mark.parametrize(
    "output",
    [
        {
            "status": "failed",
            "tool": "save_analysis_package",
            "error": {"code": "CONTRACT_SCHEMA_INVALID", "message": "missing field"},
        },
        '{"status":"failed","tool":"save_analysis_package","error":{"code":"CONTRACT_SCHEMA_INVALID","message":"missing field"}}',
    ],
)
def test_structured_typed_save_failure_is_not_recorded_as_success(output: object) -> None:
    callback = BenchmarkTelemetryCallback(tested_model_ids=())
    run_id = uuid4()
    callback.on_tool_start(
        {"name": "save_analysis_package"},
        '{"contract":{}}',
        run_id=run_id,
        inputs={"contract": {}},
        metadata={"lc_agent_name": "NTL_Analyst"},
    )
    callback.on_tool_end(output, run_id=run_id)

    row = callback.tool_trace_snapshot()[0]
    assert row["status"] == "error"
    assert row["result_observed"] is True
    assert row["error"] == {
        "code": "CONTRACT_SCHEMA_INVALID",
        "message": "missing field",
    }


def test_non_save_structured_outcome_remains_domain_tool_success() -> None:
    callback = BenchmarkTelemetryCallback(tested_model_ids=())
    run_id = uuid4()
    callback.on_tool_start(
        {"name": "ntl_daily_statistics"},
        "{}",
        run_id=run_id,
        inputs={},
    )
    callback.on_tool_end({"status": "failed", "reason": "no valid observations"}, run_id=run_id)

    row = callback.tool_trace_snapshot()[0]
    assert row["status"] == "succeeded"
    assert row["error"] is None
