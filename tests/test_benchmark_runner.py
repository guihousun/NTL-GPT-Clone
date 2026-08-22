from __future__ import annotations

from argparse import Namespace
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from threading import Lock
import time
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.tools import tool
import pytest

from benchmark_runtime import CASE_SCHEMA, RUN_SCHEMA
from benchmark_runtime.cli import build_parser, main as cli_main
from benchmark_runtime import contracts as contracts_module
from benchmark_runtime.contracts import path_is_linklike, validate_run_record
from benchmark_runtime.runner import (
    MAX_BATCH_WORKERS,
    abnormal_run_record,
    artifact_records,
    bind_thread_context,
    execute_worker_payload,
    human_message_state,
    _invoke_ntl_graph,
    _launch_worker,
    _declared_scientific_block_reason,
    _scientific_execution_block_reason,
    run_batch,
    sha256_file,
    stage_case_inputs,
)
from benchmark_runtime.telemetry import (
    BenchmarkTelemetryCallback,
    ProviderUsageCallback,
    ToolTraceCallback,
)


def _llm_result(
    *,
    content: str = "done",
    usage: dict[str, int] | None = None,
    response_metadata: dict[str, object] | None = None,
) -> LLMResult:
    return LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content=content,
                        usage_metadata=usage,
                        response_metadata=response_metadata or {},
                    )
                )
            ]
        ]
    )


def _case(case_id: str = "case-001", *, inputs: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": CASE_SCHEMA,
        "case_id": case_id,
        "prompt": f"raw prompt for {case_id}",
        "inputs": inputs or [],
        "metadata": {},
    }


def _payload(tmp_path: Path, *, case_id: str = "case-001") -> dict[str, object]:
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir(exist_ok=True)
    return {
        "case": _case(case_id),
        "cases_base_dir": str(tmp_path),
        "workspace_root": str(workspace_root),
        "result_path": str(tmp_path / "record.json"),
        "telemetry_path": str(tmp_path / "record.json.telemetry.json"),
        "batch_run_id": "batch-001",
        "task_run_id": str(uuid4()),
        "thread_id": f"thread-{case_id}",
        "model": "fake-model",
        "architecture_mode": "full",
        "request_timeout_seconds": 30,
        "task_timeout_seconds": 60,
        "recursion_limit": 20,
        "system_git_sha": "abc123",
        "submitted_at": "2026-08-09T00:00:00+00:00",
    }


def test_usage_callback_records_provider_usage_and_atomic_journal(tmp_path: Path) -> None:
    journal = tmp_path / "usage.json"
    callback = ProviderUsageCallback(journal, tested_model_ids={"deepseek-v4-flash"})
    run_id = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={"langgraph_node": "NTL_Engineer", "ls_model_name": "deepseek-v4-flash"},
    )
    in_flight = json.loads(journal.read_text(encoding="utf-8"))
    assert in_flight["usage_complete"] is False
    assert in_flight["calls"][0]["status"] == "in_flight"
    assert "in_flight_llm_call" in in_flight["incomplete_reasons"]

    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            response_metadata={"model_name": "deepseek-v4-flash-202608", "request_id": "req-1"},
        ),
        run_id=run_id,
    )
    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["input_tokens"] == 10
    assert snapshot["output_tokens"] == 4
    assert snapshot["total_tokens"] == 14
    assert snapshot["usage_complete"] is True
    assert snapshot["calls"][0]["provider_reported_model_id"] == "deepseek-v4-flash-202608"
    assert json.loads(journal.read_text(encoding="utf-8")) == snapshot


def test_usage_callback_marks_missing_provider_tokens_incomplete() -> None:
    callback = ProviderUsageCallback()
    run_id = uuid4()
    callback.on_chat_model_start({"name": "ChatOpenAI"}, [[]], run_id=run_id)
    callback.on_llm_end(_llm_result(), run_id=run_id)
    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["usage_complete"] is False
    assert snapshot["calls"][0]["input_tokens"] is None
    assert "provider_token_usage_missing_or_inconsistent" in snapshot["incomplete_reasons"]


def test_usage_callback_prefers_real_subagent_metadata_name() -> None:
    callback = ProviderUsageCallback()
    run_id = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={
            "langgraph_node": "model",
            "lc_agent_name": "Data_Searcher",
            "ls_model_name": "tested-model",
        },
    )
    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            response_metadata={"model_name": "tested-model", "request_id": "req-subagent"},
        ),
        run_id=run_id,
    )
    assert callback.snapshot()["calls"][0]["agent_name"] == "Data_Searcher"


def test_usage_callback_rejects_total_that_differs_from_input_plus_output() -> None:
    callback = ProviderUsageCallback()
    run_id = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={"ls_model_name": "tested-model"},
    )
    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 12},
            response_metadata={"model_name": "tested-model", "request_id": "req-mismatch"},
        ),
        run_id=run_id,
    )
    snapshot = callback.snapshot()
    assert snapshot["usage_complete"] is False
    assert snapshot["input_tokens"] == 10
    assert snapshot["output_tokens"] == 4
    assert snapshot["total_tokens"] == 12
    assert "provider_token_usage_missing_or_inconsistent" in snapshot["incomplete_reasons"]


def test_usage_callback_journals_llm_error_as_an_incomplete_call(tmp_path: Path) -> None:
    journal = tmp_path / "usage.json"
    callback = ProviderUsageCallback(journal)
    run_id = uuid4()
    callback.on_chat_model_start({"name": "ChatOpenAI"}, [[]], run_id=run_id)
    callback.on_llm_error(RuntimeError("authorization=Bearer private-value"), run_id=run_id)
    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["usage_complete"] is False
    assert snapshot["calls"][0]["status"] == "error"
    assert "private-value" not in json.dumps(snapshot)
    assert "llm_error" in snapshot["incomplete_reasons"]
    assert json.loads(journal.read_text(encoding="utf-8")) == snapshot


def test_usage_callback_excludes_vlm_embedding_tool_and_eval_scopes() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    excluded = ["vlm", "embedding", "tool", "evaluator"]
    for component in excluded:
        run_id = uuid4()
        callback.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[]],
            run_id=run_id,
            metadata={"component": component, "ls_model_name": "tested-model"},
        )
        callback.on_llm_end(
            _llm_result(usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
            run_id=run_id,
        )
    tested_run = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=tested_run,
        metadata={"benchmark_usage_scope": "tested_agent", "ls_model_name": "tested-model"},
    )
    callback.on_llm_end(
        _llm_result(usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}),
        run_id=tested_run,
    )
    snapshot = callback.snapshot()
    assert snapshot["llm_call_count"] == 1
    assert snapshot["total_tokens"] == 5


def test_usage_callback_fails_closed_for_missing_request_and_wrong_provider() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"deepseek-v4-flash"})
    run_id = uuid4()
    callback.on_chat_model_start({"name": "CustomChat"}, [[]], run_id=run_id)
    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            response_metadata={"model_name": "qwen-plus", "request_id": "wrong-provider"},
        ),
        run_id=run_id,
    )
    assert callback.snapshot()["llm_call_count"] == 0


def test_usage_callback_excludes_explicit_evaluator_despite_model_node_name() -> None:
    callback = ProviderUsageCallback(tested_model_ids={"tested-model"})
    run_id = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={
            "langgraph_node": "model",
            "agent_name": "evaluator",
            "ls_model_name": "tested-model",
        },
    )
    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            response_metadata={"model_name": "tested-model", "request_id": "eval-call"},
        ),
        run_id=run_id,
    )
    assert callback.snapshot()["llm_call_count"] == 0


def test_nested_tool_trace_uses_callbacks_and_redacts_credentials(tmp_path: Path) -> None:
    journal = tmp_path / "tools.json"
    callback = ToolTraceCallback(journal)
    outer = uuid4()
    inner = uuid4()
    callback.on_tool_start(
        {"name": "delegate_to_data_searcher"},
        "",
        run_id=outer,
        inputs={
            "query": "latest NTL",
            "api_key": "outer-secret",
            "nested": {"authorization": "Bearer outer-token", "safe": 7},
        },
    )
    callback.on_tool_start(
        {"name": "dataset_latest_availability_tool"},
        "",
        run_id=inner,
        parent_run_id=outer,
        inputs={"dataset": "VNP46A2", "access_key": "inner-secret"},
    )
    callback.on_tool_end({"status": "success", "value": 1}, run_id=inner, parent_run_id=outer)
    callback.on_tool_end("complete", run_id=outer)

    trace = callback.snapshot()
    assert [row["tool_name"] for row in trace] == [
        "delegate_to_data_searcher",
        "dataset_latest_availability_tool",
    ]
    assert trace[1]["parent_run_id"] == str(outer)
    assert trace[1]["parent_tool_call_id"] == str(outer)
    assert trace[0]["arguments"]["api_key"] == "<redacted>"
    assert trace[0]["arguments"]["nested"]["authorization"] == "<redacted>"
    assert trace[1]["arguments"]["access_key"] == "<redacted>"
    assert trace[1]["result_observed"] is True
    assert len(trace[1]["result_sha256"]) == 64
    serialized = journal.read_text(encoding="utf-8")
    assert "outer-secret" not in serialized
    assert "inner-secret" not in serialized


def test_real_deepagents_chain_propagates_usage_and_nested_tool_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the installed DeepAgents main-agent/subagent/tool callback path."""

    create_deep_agent = pytest.importorskip("deepagents").create_deep_agent

    for name in ("LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        monkeypatch.setenv(name, "false")

    class ScriptedChat(BaseChatModel):
        responses: list[AIMessage]
        cursor: int = 0
        model_name: str = "deepseek-v4-flash"

        @property
        def _llm_type(self) -> str:
            return "provider-free-scripted"

        @property
        def _identifying_params(self) -> dict[str, Any]:
            return {"model_name": self.model_name}

        def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChat":
            del tools, kwargs
            return self

        def _generate(
            self,
            messages: Any,
            stop: Any = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            del messages, stop, run_manager, kwargs
            message = self.responses[self.cursor]
            self.cursor += 1
            return ChatResult(generations=[ChatGeneration(message=message)])

    def response(content: str = "", *, tool_calls: list[dict[str, Any]] | None = None) -> AIMessage:
        return AIMessage(
            content=content,
            tool_calls=tool_calls or [],
            usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            response_metadata={"model_name": "deepseek-v4-flash", "request_id": "fake"},
        )

    @tool
    def inner_probe(value: str) -> str:
        """Return a deterministic marker."""

        return f"inner:{value}"

    model = ScriptedChat(
        responses=[
            response(
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "call inner_probe with value x",
                            "subagent_type": "Data_Searcher",
                        },
                        "id": "task-1",
                        "type": "tool_call",
                    }
                ]
            ),
            response(
                tool_calls=[
                    {
                        "name": "inner_probe",
                        "args": {"value": "x"},
                        "id": "inner-1",
                        "type": "tool_call",
                    }
                ]
            ),
            response("subagent done"),
            response("main done"),
        ]
    )
    telemetry = BenchmarkTelemetryCallback(tested_model_ids=())
    graph = create_deep_agent(
        model=model,
        tools=[],
        subagents=[
            {
                "name": "Data_Searcher",
                "description": "test subagent",
                "system_prompt": "Use inner_probe.",
                "tools": [inner_probe],
            }
        ],
        system_prompt="Delegate.",
        name="NTL_Engineer",
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="go")]},
        config={
            "callbacks": [telemetry],
            "metadata": {
                "benchmark_usage_scope": "tested_agent",
                "batch_run_id": "batch",
                "case_id": "case",
                "agent_name": "NTL_Engineer",
            },
            "recursion_limit": 50,
        },
    )
    snapshot = telemetry.snapshot()
    assert result["messages"][-1].content == "main done"
    assert snapshot["model_usage"]["usage_complete"] is True
    assert snapshot["model_usage"]["llm_call_count"] == 4
    assert snapshot["model_usage"]["total_tokens"] == 8
    assert [call["agent_name"] for call in snapshot["model_usage"]["calls"]] == [
        "NTL_Engineer",
        "Data_Searcher",
        "Data_Searcher",
        "NTL_Engineer",
    ]
    assert [row["tool_name"] for row in snapshot["tool_trace"]] == ["task", "inner_probe"]
    assert snapshot["tool_trace"][1]["parent_tool_call_id"] == snapshot["tool_trace"][0][
        "tool_call_id"
    ]


def test_stage_inputs_checks_checksum_and_preserves_nested_target(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    source_dir = cases_root / "assets"
    source_dir.mkdir(parents=True)
    source = source_dir / "fixture.csv"
    source.write_text("id,value\n1,2\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    case = _case(
        inputs=[
            {
                "source_path": "assets/fixture.csv",
                "target_path": "nested/fixture.csv",
                "sha256": sha256_file(source),
            }
        ]
    )
    records = stage_case_inputs(case, workspace=workspace, cases_base_dir=cases_root)
    assert records[0]["relative_path"] == "inputs/nested/fixture.csv"
    assert (workspace / "inputs" / "nested" / "fixture.csv").read_bytes() == source.read_bytes()


def test_stage_inputs_rejects_checksum_mismatch(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    (cases_root / "fixture.txt").write_text("fixture", encoding="utf-8")
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    case = _case(
        inputs=[
            {
                "source_path": "fixture.txt",
                "target_path": "fixture.txt",
                "sha256": hashlib.sha256(b"different").hexdigest(),
            }
        ]
    )
    with pytest.raises(ValueError, match="sha256 mismatch"):
        stage_case_inputs(case, workspace=workspace, cases_base_dir=cases_root)


def test_artifact_inventory_rejects_linklike_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    linked = outputs / "linked.txt"
    linked.write_text("content", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == linked or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(ValueError, match="symbolic links or junctions"):
        artifact_records(outputs)


def test_artifact_inventory_rejects_hardlinked_outputs(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    original = outputs / "original.txt"
    linked = outputs / "hardlink.txt"
    original.write_text("same inode", encoding="utf-8")
    os.link(original, linked)
    with pytest.raises(ValueError, match="hard links"):
        artifact_records(outputs)


def test_windows_reparse_attribute_is_detected_without_path_is_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "junction-like"
    candidate.mkdir()

    def fake_lstat(_path: object) -> SimpleNamespace:
        return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)

    monkeypatch.setattr(contracts_module.os, "lstat", fake_lstat)
    assert path_is_linklike(candidate) is True


def test_artifact_inventory_rejects_linklike_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setattr(
        "benchmark_runtime.runner.path_is_linklike",
        lambda path: Path(path) == outputs,
    )
    with pytest.raises(ValueError, match="output root"):
        artifact_records(outputs)


def test_stage_inputs_rejects_hardlinked_fixture(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("shared inode", encoding="utf-8")
    fixture = cases_root / "fixture.txt"
    os.link(external, fixture)
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    case = _case(inputs=[{"source_path": "fixture.txt", "target_path": "fixture.txt"}])
    with pytest.raises(ValueError, match="hard-linked"):
        stage_case_inputs(case, workspace=workspace, cases_base_dir=cases_root)


@pytest.mark.parametrize(
    ("source_path", "target_path"),
    [
        ("../outside.txt", "inside.txt"),
        ("C:/outside.txt", "inside.txt"),
        ("assets/fixture.txt", "../escape.txt"),
        ("assets/fixture.txt", "C:/escape.txt"),
        ("assets/fixture.txt", "outputs/not-an-input.txt"),
    ],
)
def test_stage_inputs_rejects_path_traversal(
    tmp_path: Path, source_path: str, target_path: str
) -> None:
    cases_root = tmp_path / "cases"
    assets = cases_root / "assets"
    assets.mkdir(parents=True)
    (assets / "fixture.txt").write_text("fixture", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    case = _case(inputs=[{"source_path": source_path, "target_path": target_path}])
    with pytest.raises((ValueError, FileNotFoundError)):
        stage_case_inputs(case, workspace=workspace, cases_base_dir=cases_root)


def test_failed_worker_record_redacts_error_and_marks_usage_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NTL_USER_DATA_DIR", str(tmp_path / "original-user-data"))
    payload = _payload(tmp_path)

    def fail_graph(*_args: object) -> object:
        raise RuntimeError("api_key=should-not-leak")

    record = execute_worker_payload(payload, graph_invoker=fail_graph)
    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert record["model_usage"]["usage_complete"] is False
    assert "should-not-leak" not in json.dumps(record)


def test_worker_failure_after_complete_model_call_preserves_usage(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="failure-after-model")

    def fail_after_model(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        run_id = uuid4()
        telemetry.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[]],
            run_id=run_id,
            metadata={"ls_model_name": "fake-model", "agent_name": "NTL_Engineer"},
        )
        telemetry.on_llm_end(
            _llm_result(
                usage={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                response_metadata={"model_name": "fake-model", "request_id": "req-before-error"},
            ),
            run_id=run_id,
        )
        raise RuntimeError("tool failed after the completed model response")

    record = execute_worker_payload(payload, graph_invoker=fail_after_model)
    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert record["model_usage"]["usage_complete"] is True
    assert record["model_usage"]["llm_call_count"] == 1
    assert record["model_usage"]["total_tokens"] == 6


def test_worker_rejects_planning_only_final_answer(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="planning-only")

    def planning_only(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        tool_run_id = uuid4()
        telemetry.on_tool_start(
            {"name": "read_file"},
            '{"file_path":"/skills/engineer/task-planning-and-routing/SKILL.md"}',
            run_id=tool_run_id,
        )
        telemetry.on_tool_end("instructions", run_id=tool_run_id)
        return {"messages": [AIMessage(content="I will now execute the task.", name="NTL_Engineer")]}

    record = execute_worker_payload(payload, graph_invoker=planning_only)

    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert {item["code"] for item in record["errors"]} >= {"NO_SUBSTANTIVE_EXECUTION"}


def test_worker_accepts_registered_task_execution_before_final_answer(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="registered-execution")

    def executed(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        tool_run_id = uuid4()
        telemetry.on_tool_start({"name": "NTL_download_tool"}, "{}", run_id=tool_run_id)
        telemetry.on_tool_end({"status": "completed"}, run_id=tool_run_id)
        return {"messages": [AIMessage(content="Retrieved the requested data.", name="NTL_Engineer")]}

    record = execute_worker_payload(payload, graph_invoker=executed)

    validate_run_record(record)
    assert record["terminal_state"] == "succeeded"
    assert not {item["code"] for item in record["errors"]} & {"NO_SUBSTANTIVE_EXECUTION"}


def test_worker_inventories_runtime_generated_input_without_requiring_a_package(tmp_path: Path) -> None:
    """Retrieval-only tools may write verified results under inputs/.

    The runner records only files created after case staging, so a model does
    not need to copy a successful download into outputs/ just to make it
    auditable.
    """

    payload = _payload(tmp_path, case_id="generated-input")

    def retrieved(
        _case_record: dict[str, object],
        payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        generated = (
            Path(str(payload_record["workspace_root"]))
            / str(payload_record["thread_id"])
            / "inputs"
            / "retrieved.tif"
        )
        generated.write_bytes(b"verified live retrieval")
        tool_run_id = uuid4()
        telemetry.on_tool_start({"name": "NTL_download_tool"}, "{}", run_id=tool_run_id)
        telemetry.on_tool_end({"status": "completed"}, run_id=tool_run_id)
        return {"messages": [AIMessage(content="Retrieved the requested layer.", name="NTL_Engineer")]}

    record = execute_worker_payload(payload, graph_invoker=retrieved)

    validate_run_record(record)
    assert record["terminal_state"] == "succeeded"
    assert [artifact["relative_path"] for artifact in record["artifacts"]] == [
        "inputs/retrieved.tif"
    ]


def test_worker_marks_blocked_evidence_report_as_scientific_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typed blocked result is useful evidence, but not a successful task."""

    payload = _payload(tmp_path, case_id="blocked-evidence-report")

    def blocked_evidence(*_args: object, **_kwargs: object) -> tuple[dict[str, object], list[str], list[str], str]:
        return (
            {
                "schema_version": "ntl-benchmark.internal-evidence.v1",
                "content_policy": "identity_metadata_and_hashes_only",
                "valid": True,
                "package_counts": {
                    "TaskPlan": 0,
                    "EventContext": 0,
                    "ObservationPackage": 0,
                    "AnalysisPackage": 0,
                    "EvidenceReport": 1,
                },
                "packages": [
                    {
                        "relative_path": "outputs/runs/run-blocked/contracts/evidence_report.json",
                        "sha256": "a" * 64,
                        "bytes": 1,
                        "artifact_type": "EvidenceReport",
                        "status": "blocked",
                    },
                ]
                ,
                "handoffs": [],
                "decisions": [],
                "route_states": [],
                "invalid_records": [],
                "issue_count": 0,
                "discovered_run_ids": ["run-blocked"],
            },
            [],
            [],
            "Earth Engine could not provide the requested qualified observation.",
        )

    monkeypatch.setattr("benchmark_runtime.runner._collect_architecture_evidence", blocked_evidence)

    def executed_but_blocked(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        tool_run_id = uuid4()
        telemetry.on_tool_start({"name": "NTL_download_tool"}, "{}", run_id=tool_run_id)
        telemetry.on_tool_end({"status": "blocked"}, run_id=tool_run_id)
        return {"messages": [AIMessage(content="No qualified observation was available.", name="NTL_Engineer")]}

    record = execute_worker_payload(payload, graph_invoker=executed_but_blocked)

    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert {item["code"] for item in record["errors"]} >= {"SCIENTIFIC_EXECUTION_BLOCKED"}
    assert _scientific_execution_block_reason({"packages": []}) is None


def test_worker_marks_explicit_blocked_result_without_package_as_failure(tmp_path: Path) -> None:
    """A natural-language blocked closeout is not counted as a successful answer."""

    payload = _payload(tmp_path, case_id="blocked-natural-language")

    def executed_but_explicitly_blocked(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        tool_run_id = uuid4()
        telemetry.on_tool_start({"name": "NTL_download_tool"}, "{}", run_id=tool_run_id)
        telemetry.on_tool_end({"status": "error"}, run_id=tool_run_id)
        return {
            "messages": [
                AIMessage(
                    content=(
                        "## Result: requested daily layers — BLOCKED\\n\\n"
                        "The layers could not be materialized and no data was acquired."
                    ),
                    name="NTL_Engineer",
                )
            ]
        }

    record = execute_worker_payload(payload, graph_invoker=executed_but_explicitly_blocked)

    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert {item["code"] for item in record["errors"]} >= {"SCIENTIFIC_EXECUTION_BLOCKED"}
    assert _declared_scientific_block_reason({"packages": []}, "Retrieved an output.") is None


def test_worker_rejects_process_only_answer_after_execution(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="unfinished-closeout")

    def executed_but_unfinished(
        _case_record: dict[str, object],
        _payload_record: dict[str, object],
        telemetry: BenchmarkTelemetryCallback,
    ) -> object:
        tool_run_id = uuid4()
        telemetry.on_tool_start({"name": "NTL_download_tool"}, "{}", run_id=tool_run_id)
        telemetry.on_tool_end({"status": "completed"}, run_id=tool_run_id)
        return {
            "messages": [
                AIMessage(
                    content="Saving the final EvidenceReport, then delivering the direct answer.",
                    name="NTL_Engineer",
                )
            ]
        }

    record = execute_worker_payload(payload, graph_invoker=executed_but_unfinished)

    validate_run_record(record)
    assert record["terminal_state"] == "no_final_answer"
    assert {item["code"] for item in record["errors"]} >= {"PREMATURE_PROCESS_NARRATION"}


def test_internal_worker_subprocess_emits_failed_record_without_provider_call(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="subprocess-case")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "LANGCHAIN_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_API_KEY": "",
            "LANGSMITH_API_KEY": "",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "benchmark_runtime.cli", "_worker", str(payload_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    record = json.loads(Path(str(payload["result_path"])).read_text(encoding="utf-8"))
    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert record["model_usage"]["usage_complete"] is False
    assert Path(record["environment"]["workspace"]) == (
        Path(str(payload["workspace_root"])) / str(payload["thread_id"])
    ).resolve()


def test_parent_launcher_records_full_subprocess_wall_clock_scope(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="parent-clock-case")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    record = _launch_worker(payload_path, payload, Path(__file__).resolve().parents[1])

    validate_run_record(record)
    assert record["terminal_state"] == "failed"
    assert record["wall_clock_seconds"] > 0
    assert record["environment"]["wall_clock_scope"] == "parent_process_start_to_worker_exit"


def test_timeout_record_recovers_inflight_usage_and_forces_incomplete(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    workspace = Path(payload["workspace_root"]) / str(payload["thread_id"])
    for name in ("inputs", "outputs", "memory"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    callback = ProviderUsageCallback(Path(str(payload["telemetry_path"])))
    run_id = uuid4()
    callback.on_chat_model_start({"name": "ChatOpenAI"}, [[]], run_id=run_id)
    # ProviderUsageCallback journals usage-only; the parent reader intentionally
    # supports this shape as well as the combined worker telemetry journal.
    record = abnormal_run_record(
        payload,
        terminal_state="timed_out",
        elapsed=60.1,
        error_code="TASK_TIMEOUT",
        error_message="task exceeded 60 seconds",
    )
    validate_run_record(record)
    assert record["terminal_state"] == "timed_out"
    assert record["model_usage"]["llm_call_count"] == 1
    assert record["model_usage"]["calls"][0]["status"] == "in_flight"
    assert record["model_usage"]["usage_complete"] is False


def test_timeout_record_preserves_fully_journaled_provider_usage(tmp_path: Path) -> None:
    payload = _payload(tmp_path, case_id="timeout-after-model")
    workspace = Path(payload["workspace_root"]) / str(payload["thread_id"])
    for name in ("inputs", "outputs", "memory"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    callback = ProviderUsageCallback(Path(str(payload["telemetry_path"])))
    run_id = uuid4()
    callback.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[]],
        run_id=run_id,
        metadata={"ls_model_name": "fake-model"},
    )
    callback.on_llm_end(
        _llm_result(
            usage={"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
            response_metadata={"model_name": "fake-model", "request_id": "req-complete"},
        ),
        run_id=run_id,
    )

    record = abnormal_run_record(
        payload,
        terminal_state="timed_out",
        elapsed=60.1,
        error_code="TASK_TIMEOUT",
        error_message="task exceeded 60 seconds during a later tool call",
    )

    validate_run_record(record)
    assert record["terminal_state"] == "timed_out"
    assert record["model_usage"]["usage_complete"] is True
    assert record["model_usage"]["llm_call_count"] == 1
    assert record["model_usage"]["total_tokens"] == 17


def test_worker_launcher_converts_subprocess_timeout_to_run_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover the parent-side timeout branch without importing the agent graph."""

    class TimedOutProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode: int | None = None
            self.stdout = io.StringIO()
            self.stderr = io.StringIO()
            self.killed = False

        def communicate(self, *, timeout: float) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(cmd="benchmark worker", timeout=timeout)

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, *, timeout: float) -> int:
            assert timeout > 0
            if self.returncode is None:
                raise subprocess.TimeoutExpired(cmd="benchmark worker", timeout=timeout)
            return self.returncode

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

    process = TimedOutProcess()
    monkeypatch.setattr(
        "benchmark_runtime.runner.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )

    def terminate(timed_out_process: TimedOutProcess) -> None:
        assert timed_out_process is process
        timed_out_process.kill()

    monkeypatch.setattr("benchmark_runtime.runner._terminate_process_tree", terminate)
    payload = _payload(tmp_path, case_id="timeout-case")
    payload["task_timeout_seconds"] = 0.01
    record = _launch_worker(tmp_path / "payload.json", payload, Path(__file__).parents[1])

    validate_run_record(record)
    assert process.killed is True
    assert record["terminal_state"] == "timed_out"
    assert record["errors"][0]["code"] == "TASK_TIMEOUT"
    assert record["model_usage"]["usage_complete"] is False


def test_thread_context_binding_resets_even_after_exception() -> None:
    from storage_manager import current_thread_id

    original = current_thread_id.get()
    with pytest.raises(RuntimeError):
        with bind_thread_context("benchmark-thread"):
            assert current_thread_id.get() == "benchmark-thread"
            raise RuntimeError("stop")
    assert current_thread_id.get() == original


def test_human_message_state_contains_only_the_raw_prompt() -> None:
    prompt = "请分析这个夜间灯光文件，不要添加 benchmark gold。"
    state = human_message_state(prompt)
    assert len(state["messages"]) == 1
    assert state["messages"][0].content == prompt


def test_graph_invocation_receives_architecture_mode_and_resource_profile_in_builder_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class FakeGraph:
        def invoke(self, state: object, *, config: dict[str, object]) -> dict[str, object]:
            observed["state"] = state
            observed["config"] = config
            return {"messages": [AIMessage(content="done", name="NTL_Engineer")]}

    def fake_builder(**kwargs: object) -> FakeGraph:
        observed["builder"] = kwargs
        return FakeGraph()

    monkeypatch.setitem(
        sys.modules,
        "graph_factory",
        SimpleNamespace(build_ntl_graph=fake_builder),
    )
    monkeypatch.setitem(
        sys.modules,
        "model_config",
        SimpleNamespace(
            missing_env_for_model=lambda _model: [],
            get_api_model_name=lambda model: model,
            get_env_api_key=lambda _model: "fake-key",
        ),
    )
    payload = {
        "model": "fake-model",
        "architecture_mode": "single_agent",
        "resource_profile": "tools_prompt_only",
        "request_timeout_seconds": 30,
        "thread_id": "thread-mode-test",
        "task_run_id": "task-run-mode-test",
        "recursion_limit": 20,
        "batch_run_id": "batch-mode-test",
    }

    _invoke_ntl_graph(_case("mode-test"), payload, BenchmarkTelemetryCallback())

    assert observed["builder"]["architecture_mode"] == "single_agent"
    assert observed["builder"]["resource_profile"] == "tools_prompt_only"
    assert observed["config"]["metadata"]["architecture_mode"] == "single_agent"
    assert observed["config"]["metadata"]["resource_profile"] == "tools_prompt_only"


def _write_cases(path: Path, count: int) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(count):
            handle.write(json.dumps(_case(f"case-{index:03d}"), ensure_ascii=False) + "\n")


def _fake_success_record(payload: dict[str, object]) -> dict[str, object]:
    workspace = Path(str(payload["workspace_root"])) / str(payload["thread_id"])
    for name in ("inputs", "outputs", "memory"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": RUN_SCHEMA,
        "batch_run_id": payload["batch_run_id"],
        "task_run_id": payload["task_run_id"],
        "case_id": payload["case"]["case_id"],
        "thread_id": payload["thread_id"],
        "started_at": "2026-08-09T00:00:00+00:00",
        "ended_at": "2026-08-09T00:00:01+00:00",
        "wall_clock_seconds": 1.0,
        "terminal_state": "succeeded",
        "final_answer": "done",
        "artifacts": [],
        "tool_trace": [],
        "model_usage": {
            "llm_call_count": 1,
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 3,
            "usage_complete": True,
            "incomplete_reasons": [],
            "calls": [
                {
                    "sequence": 1,
                    "status": "completed",
                    "requested_model_id": "fake-model",
                    "provider_reported_model_id": "fake-model",
                    "provider_request_id": "fake-request",
                    "model_identity_matches_tested": True,
                    "input_tokens": 2,
                    "output_tokens": 1,
                    "total_tokens": 3,
                    "usage_complete": True,
                }
            ],
        },
        "errors": [],
        "environment": {
            "workspace": str(workspace.resolve()),
            "architecture_mode": payload["architecture_mode"],
            "resource_profile": payload.get("resource_profile", "standard"),
        },
    }


def test_batch_runner_never_exceeds_four_concurrent_launches(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, 4)
    output_dir = tmp_path / "batch"
    guard = Lock()
    active = 0
    peak = 0

    def fake_launcher(_payload_path: Path, payload: dict[str, object], _repo_root: Path) -> dict[str, object]:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        try:
            return _fake_success_record(payload)
        finally:
            with guard:
                active -= 1

    args = Namespace(
        cases=str(cases_path),
        output_dir=str(output_dir),
        model="deepseek-v4-flash",
        architecture_mode="full",
        max_workers=4,
        task_timeout_seconds=60,
        request_timeout_seconds=30,
        recursion_limit=20,
        case_id=[],
    )
    assert run_batch(args, launcher=fake_launcher) == 0
    assert peak == MAX_BATCH_WORKERS
    manifest = json.loads((output_dir / "batch-manifest.json").read_text(encoding="utf-8"))
    assert manifest["configured_concurrency"] == 4
    assert manifest["architecture_mode"] == "full"
    assert manifest["resource_profile"] == "standard"
    assert manifest["task_count"] == 4
    assert manifest["system_finalizer_excluded_from_task_model_usage"] is True
    # This intentionally minimal fake record has no internal-evidence block;
    # the collector therefore records it without claiming scientific closeout.
    assert manifest["system_finalization_counts"] == {"completed_with_audit_warnings": 4}
    system_evidence_dir = Path(manifest["system_evidence_dir"])
    assert system_evidence_dir.is_dir()
    system_evidence = list(system_evidence_dir.glob("*.json"))
    assert len(system_evidence) == 4
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["excluded_from_task_model_usage"] is True
        for path in system_evidence
    )
    assert isinstance(manifest["environment"]["system_git_dirty"], bool)
    assert len(manifest["environment"]["system_git_status_sha256"]) == 64
    records = [json.loads(line) for line in (output_dir / "task-runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4
    assert all(record["environment"]["architecture_mode"] == "full" for record in records)
    assert all(record["environment"]["resource_profile"] == "standard" for record in records)
    assert all(validate_run_record(record) for record in records)
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output_dir / "control").glob("*.json"))
    ]
    assert len(payloads) == 4
    for payload in payloads:
        opaque = str(payload["thread_id"])
        assert re.fullmatch(r"ws-[0-9a-f]{32}", opaque)
        assert str(payload["case"]["case_id"]) not in opaque
        assert str(payload["task_run_id"]) not in opaque
        assert str(payload["task_run_id"])[:8] not in opaque
        assert str(payload["batch_run_id"]) not in opaque


def test_parent_launcher_failure_still_emits_comparable_wall_clock_contract(
    tmp_path: Path,
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, 1)
    output_dir = tmp_path / "batch"

    def failing_launcher(*_args: object) -> dict[str, object]:
        raise OSError("subprocess launch failed")

    args = Namespace(
        cases=str(cases_path),
        output_dir=str(output_dir),
        model="deepseek-v4-flash",
        architecture_mode="single_agent",
        max_workers=1,
        task_timeout_seconds=60,
        request_timeout_seconds=30,
        recursion_limit=20,
        case_id=[],
    )
    assert run_batch(args, launcher=failing_launcher) == 0
    record = json.loads((output_dir / "task-runs.jsonl").read_text(encoding="utf-8"))
    assert record["terminal_state"] == "failed"
    assert record["errors"][0]["code"] == "PARENT_LAUNCHER_FAILED"
    assert record["environment"]["wall_clock_scope"] == "parent_process_start_to_worker_exit"
    assert record["wall_clock_seconds"] >= 0
    assert record["environment"]["architecture_mode"] == "single_agent"
    validate_run_record(record)


def test_batch_runner_rejects_more_than_eight_workers_without_creating_output(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, 1)
    output_dir = tmp_path / "batch"
    args = Namespace(
        cases=str(cases_path),
        output_dir=str(output_dir),
        model="fake-model",
        architecture_mode="full",
        max_workers=9,
        task_timeout_seconds=60,
        request_timeout_seconds=30,
        recursion_limit=20,
        case_id=[],
    )
    with pytest.raises(ValueError, match="cannot exceed 4"):
        run_batch(args, launcher=lambda *_args: {})
    assert not output_dir.exists()


def test_batch_runner_refuses_existing_output_directory(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, 1)
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    args = Namespace(
        cases=str(cases_path),
        output_dir=str(output_dir),
        model="fake-model",
        architecture_mode="full",
        max_workers=1,
        task_timeout_seconds=60,
        request_timeout_seconds=30,
        recursion_limit=20,
        case_id=[],
    )
    with pytest.raises(FileExistsError, match="resume/overwrite is disabled"):
        run_batch(args, launcher=lambda *_args: {})


def test_cli_defaults_to_four_workers_and_supports_case_filters() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--cases",
            "cases.jsonl",
            "--output-dir",
            "out",
            "--model",
            "deepseek-v4-flash",
            "--architecture-mode",
            "full",
            "--case-id",
            "case-a",
            "--case-id",
            "case-b",
        ]
    )
    assert args.max_workers == 4
    assert args.architecture_mode == "full"
    assert args.resource_profile == "standard"
    assert args.case_id == ["case-a", "case-b"]
    assert args.task_timeout_seconds == 1800.0

    prepare = build_parser().parse_args(
        [
            "prepare-eval",
            "--cases",
            "cases.jsonl",
            "--eval-specs",
            "specs.jsonl",
            "--run-records",
            "runs.jsonl",
            "--packet-dir",
            "packets",
            "--result-dir",
            "results",
            "--case-id",
            "case-a",
        ]
    )
    assert prepare.command == "prepare-eval"
    assert prepare.case_id == ["case-a"]
    collect = build_parser().parse_args(
        [
            "collect-eval",
            "--packet-dir",
            "packets",
            "--result-dir",
            "results",
            "--output",
            "eval-results.jsonl",
        ]
    )
    assert collect.command == "collect-eval"
    summary = build_parser().parse_args(
        [
            "summarize",
            "--run-records",
            "runs.jsonl",
            "--eval-results",
            "eval-results.jsonl",
            "--eval-specs",
            "specs.jsonl",
            "--packet-dir",
            "packets",
            "--output",
            "summary.json",
            "--case-id",
            "case-a",
        ]
    )
    assert summary.command == "summarize"
    assert summary.case_id == ["case-a"]


def test_run_subcommand_dispatches_through_public_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(args: Namespace) -> int:
        observed["cases"] = args.cases
        observed["max_workers"] = args.max_workers
        return 0

    monkeypatch.setattr("benchmark_runtime.cli.run_batch", fake_run)
    assert (
        cli_main(
            [
                "run",
                "--cases",
                "cases.jsonl",
                "--output-dir",
                "new-output",
                    "--model",
                    "deepseek-v4-flash",
                    "--architecture-mode",
                    "full",
                    "--max-workers",
                "4",
            ]
        )
        == 0
    )
    assert observed == {"cases": "cases.jsonl", "max_workers": 4}
