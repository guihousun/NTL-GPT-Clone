from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from deepagents.backends import CompositeBackend, FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field
from rasterio.transform import from_origin

import graph_factory
import orchestration.contract_tools as contract_tools
import orchestration.contracts_io as contracts_io
import orchestration.observation_runtime as observation_runtime
from benchmark_runtime.telemetry import BenchmarkTelemetryCallback
from contracts.agent_packages import (
    AgentRole,
    AssignmentEnvelope,
    ContractStatus,
    HandoffEnvelope,
    ObservationPackage,
    PackageRef,
    TaskPlan,
    contract_sha256,
)
from storage_manager import StorageManager, current_thread_id


UTC = timezone.utc


class ScriptedChat(BaseChatModel):
    """Provider-free chat model that emits deterministic tool calls."""

    responses: list[AIMessage]
    cursor: int = 0
    model_name: str = "deepseek-v4-flash"
    bound_tool_sets: list[list[str]] = Field(default_factory=list)
    task_tool_descriptions: list[str] = Field(default_factory=list)
    seen_message_texts: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "provider-free-scripted-hierarchical"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name}

    def _get_ls_params(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Match the production ChatOpenAI provider for exact HarnessProfile tests."""

        del args, kwargs
        return {"ls_provider": "openai", "ls_model_name": self.model_name}

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChat":
        del kwargs
        names: list[str] = []
        for candidate in tools:
            name = (
                candidate.get("name", "")
                if isinstance(candidate, dict)
                else str(getattr(candidate, "name", ""))
            )
            names.append(name)
            if name == "task" and not isinstance(candidate, dict):
                self.task_tool_descriptions.append(str(getattr(candidate, "description", "")))
        self.bound_tool_sets.append(names)
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_message_texts.append(
            "\n".join(str(getattr(message, "content", "")) for message in messages)
        )
        del stop, run_manager, kwargs
        if self.cursor >= len(self.responses):
            raise AssertionError("scripted chat model received an unexpected extra invocation")
        message = self.responses[self.cursor]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def _response(
    content: str = "", *, tool_calls: list[dict[str, Any]] | None = None
) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        response_metadata={"model_name": "deepseek-v4-flash", "request_id": "fake"},
    )


def _write_test_skill(source_root: Path, namespace: str) -> None:
    skill_name = f"provider-free-{namespace.replace('_', '-')}"
    directory = source_root / namespace / skill_name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: deterministic {namespace} integration skill\n---\n"
        f"skill-marker-{namespace}-only\n",
        encoding="utf-8",
    )


def _stage_test_raster(manager: StorageManager, thread_id: str) -> str:
    filename = "provider_free_ntl.tif"
    path = manager.get_workspace(thread_id) / "inputs" / filename
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.array([[1.0, 2.0], [3.0, -9999.0]], dtype="float32"), 1)
    return filename


@pytest.fixture
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in (
        "LANGCHAIN_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_TRACING",
        "NTL_USER_DATA_DIR",
        "NTL_SHARED_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    for name in ("LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        monkeypatch.setenv(name, "false")

    manager = StorageManager(
        base_dir=str(tmp_path / "user_data"),
        shared_dir=str(tmp_path / "shared"),
    )
    monkeypatch.setattr(graph_factory, "storage_manager", manager)
    monkeypatch.setattr(contract_tools, "storage_manager", manager)
    monkeypatch.setattr(contracts_io, "storage_manager", manager)
    monkeypatch.setattr(observation_runtime, "storage_manager", manager)
    inspector_module = __import__("tools.geodata_inspector_tool", fromlist=["sm"])
    monkeypatch.setattr(inspector_module, "sm", manager)

    skills_root = tmp_path / "skills"
    for namespace in ("common", "engineer", "data_searcher", "analyst", "event_tracker"):
        _write_test_skill(skills_root, namespace)
    monkeypatch.setattr(graph_factory, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(graph_factory, "RUNTIME_BACKEND", graph_factory._build_runtime_backend())

    @tool
    def deterministic_knowledge_probe(query: str) -> str:
        """Return a deterministic local knowledge marker."""

        return f"knowledge:{query}"

    monkeypatch.setattr(graph_factory, "_knowledge_base_tool", lambda: deterministic_knowledge_probe)
    thread_id = "pf-" + hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    token = current_thread_id.set(thread_id)
    try:
        yield manager, thread_id
    finally:
        current_thread_id.reset(token)


def _observation_contract(run_id: str, task_id: str) -> ObservationPackage:
    timestamp = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)
    return ObservationPackage(
        artifact_id="observation-provider-free",
        run_id=run_id,
        task_id=task_id,
        producer=AgentRole.DATA_SEARCHER,
        created_at_utc=timestamp,
        as_of_utc=timestamp,
        status=ContractStatus.READY,
        query_executed_at_utc=timestamp,
        product={"dataset_id": "provider/free"},
        availability={"latest_valid_observation": "2026-08-11"},
        validation={"status": "passed"},
    )


def test_real_full_graph_executes_engineer_specialist_engineer_chain(
    isolated_runtime: tuple[StorageManager, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, thread_id = isolated_runtime
    run_id = "full-provider-free"
    task_id = "case-full"
    observation = _observation_contract(run_id, task_id)
    raster_name = _stage_test_raster(manager, thread_id)
    monkeypatch.setattr(
        observation_runtime,
        "_utc_now",
        lambda: observation.query_executed_at_utc,
    )
    actual_observation_ref = PackageRef(
        artifact_id=observation.artifact_id,
        artifact_type="ObservationPackage",
        path=(
            f"/data/processed/runs/{run_id}/contracts/"
            f"observation_package__{observation.artifact_id}.json"
        ),
        sha256=contract_sha256(observation),
    )
    observation_ref = contract_tools._register_package_handle(
        actual_observation_ref,
        thread_id=thread_id,
    )
    assignment = AssignmentEnvelope(
        assignment_id="assignment-provider-free",
        run_id=run_id,
        task_id=task_id,
        target_agent=AgentRole.DATA_SEARCHER,
        objective="Persist the scripted observation package.",
        required_output_type="ObservationPackage",
        acceptance_criteria=["The package validates and is persisted."],
    )
    handoff = HandoffEnvelope(
        handoff_id="handoff-provider-free",
        assignment_id=assignment.assignment_id,
        run_id=run_id,
        task_id=task_id,
        producer=AgentRole.DATA_SEARCHER,
        status=ContractStatus.READY,
        package=observation_ref,
        summary=["Product fixed.", "Temporal record fixed.", "Validation passed."],
        validation_verdict="passed",
    )
    model = ScriptedChat(
        responses=[
            _response(
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": assignment.model_dump_json(
                                exclude={"run_id", "task_id"}
                            ),
                            "subagent_type": "NTL_Data_Searcher",
                        },
                        "id": "delegate-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response(
                tool_calls=[
                    {
                        "name": "geodata_inspector_tool",
                        "args": {"mode": "full", "raster_paths": [raster_name]},
                        "id": "inspect-observation-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response(
                tool_calls=[
                    {
                        "name": "save_observation_package",
                        "args": {
                            "contract": observation.model_dump(
                                mode="json",
                                exclude={
                                    "run_id",
                                    "task_id",
                                    "created_at_utc",
                                    "query_executed_at_utc",
                                },
                            )
                        },
                        "id": "save-observation-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response(handoff.model_dump_json()),
            _response(
                tool_calls=[
                    {
                        "name": "record_handoff_decision",
                        "args": {
                            "handoff": handoff.model_dump(
                                mode="json", exclude={"run_id", "task_id"}
                            ),
                            "decision": {
                                "decision": "accepted",
                                "validation": {
                                    "schema_valid": True,
                                    "artifact_exists": True,
                                    "checksum_valid": True,
                                    "assignment_scope_valid": True,
                                    "semantic_consistency_valid": True,
                                    "producer_validation_passed": True,
                                },
                                "reason": "All deterministic checks passed.",
                            },
                        },
                        "id": "accept-handoff-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response("Engineer accepted the persisted ObservationPackage."),
        ]
    )
    monkeypatch.setattr(graph_factory, "_build_llm", lambda **_kwargs: model)
    telemetry = BenchmarkTelemetryCallback(tested_model_ids=())

    graph = graph_factory.build_ntl_graph(
        "deepseek-v4-flash", "unused", architecture_mode="full"
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Run the provider-free delegation test.")]},
        config={
            "callbacks": [telemetry],
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "benchmark_usage_scope": "tested_agent",
                "batch_run_id": run_id,
                "task_run_id": run_id,
                "case_id": task_id,
                "task_submitted_at": "2026-08-12T00:00:00Z",
                "agent_name": "NTL_Engineer",
            },
            "recursion_limit": 80,
        },
    )

    assert result["messages"][-1].content == "Engineer accepted the persisted ObservationPackage."
    assert model.cursor == 6
    assert any("task" in names for names in model.bound_tool_sets)
    assert model.task_tool_descriptions
    task_description = "\n".join(model.task_tool_descriptions)
    assert "NTL_Data_Searcher" in task_description
    assert "NTL_Analyst" in task_description
    assert "NTL_Event_Tracker" in task_description
    assert "general-purpose" not in task_description

    workspace = manager.get_workspace(thread_id)
    assert (
        workspace
        / "outputs"
        / "runs"
        / run_id
        / "contracts"
        / f"observation_package__{observation.artifact_id}.json"
    ).is_file()
    assert list((workspace / "outputs" / "runs" / run_id / "handoffs").glob("*.json"))
    assert list((workspace / "outputs" / "runs" / run_id / "decisions").glob("*.json"))

    snapshot = telemetry.snapshot()
    assert snapshot["model_usage"]["llm_call_count"] == 6
    assert [call["agent_name"] for call in snapshot["model_usage"]["calls"]] == [
        "NTL_Engineer",
        "NTL_Data_Searcher",
        "NTL_Data_Searcher",
        "NTL_Data_Searcher",
        "NTL_Engineer",
        "NTL_Engineer",
    ]
    assert [row["tool_name"] for row in snapshot["tool_trace"]] == [
        "task",
        "geodata_inspector_tool",
        "save_observation_package",
        "record_handoff_decision",
    ]
    seen_prompts = "\n".join(model.seen_message_texts)
    for namespace in ("common", "engineer", "data_searcher"):
        assert f"provider-free-{namespace.replace('_', '-')}" in seen_prompts
    assert "provider-free-analyst" not in seen_prompts
    assert "provider-free-event-tracker" not in seen_prompts


def test_real_single_agent_has_no_delegation_and_persists_task_plan(
    isolated_runtime: tuple[StorageManager, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, thread_id = isolated_runtime
    run_id = "single-provider-free"
    task_id = "case-single"
    plan = TaskPlan(
        artifact_id="plan-provider-free",
        run_id=run_id,
        task_id=task_id,
        producer=AgentRole.ENGINEER,
        created_at_utc=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
        status=ContractStatus.READY,
        original_request="Run a provider-free single-agent test.",
        normalized_objective="Persist one valid TaskPlan without delegation.",
        observation_required=False,
        analysis_required=False,
        skip_reasons={
            "NTL_Data_Searcher": "No observation is needed.",
            "NTL_Analyst": "No analysis is needed.",
            "NTL_Event_Tracker": "No event context is needed.",
        },
    )
    model = ScriptedChat(
        responses=[
            _response(
                tool_calls=[
                    {
                        "name": "save_task_plan",
                        "args": {
                            "contract": plan.model_dump(
                                mode="json",
                                exclude={"run_id", "task_id", "created_at_utc"},
                            )
                        },
                        "id": "save-plan-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response("Single-Agent persisted its TaskPlan."),
        ]
    )
    monkeypatch.setattr(graph_factory, "_build_llm", lambda **_kwargs: model)

    graph = graph_factory.build_ntl_graph(
        "deepseek-v4-flash", "unused", architecture_mode="single_agent"
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Run the provider-free single-agent test.")]},
        config={
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "agent_name": "NTL_Engineer",
                "task_run_id": run_id,
                "case_id": task_id,
                "task_submitted_at": "2026-08-12T00:00:00Z",
            },
            "recursion_limit": 50,
        },
    )

    assert result["messages"][-1].content == "Single-Agent persisted its TaskPlan."
    assert model.cursor == 2
    assert model.bound_tool_sets
    assert all("task" not in names for names in model.bound_tool_sets)
    assert not model.task_tool_descriptions
    seen_prompts = "\n".join(model.seen_message_texts)
    for namespace in ("common", "engineer", "data_searcher", "analyst", "event_tracker"):
        assert f"provider-free-{namespace.replace('_', '-')}" in seen_prompts
    assert (
        manager.get_workspace(thread_id)
        / "outputs"
        / "runs"
        / run_id
        / "contracts"
        / f"task_plan__{plan.artifact_id}.json"
    ).is_file()


def test_real_single_agent_inspects_then_persists_system_timed_observation(
    isolated_runtime: tuple[StorageManager, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, thread_id = isolated_runtime
    run_id = "single-observation-provider-free"
    task_id = "case-single-observation"
    observation = _observation_contract(run_id, task_id).model_copy(
        update={"artifact_id": "observation-single-provider-free"}
    )
    raster_name = _stage_test_raster(manager, thread_id)
    monkeypatch.setattr(
        observation_runtime,
        "_utc_now",
        lambda: observation.query_executed_at_utc,
    )
    draft = observation.model_dump(
        mode="json",
        exclude={
            "run_id",
            "task_id",
            "created_at_utc",
            "query_executed_at_utc",
        },
    )
    model = ScriptedChat(
        responses=[
            _response(
                tool_calls=[
                    {
                        "name": "geodata_inspector_tool",
                        "args": {"mode": "full", "raster_paths": [raster_name]},
                        "id": "single-inspect-observation",
                        "type": "tool_call",
                    }
                ]
            ),
            _response(
                tool_calls=[
                    {
                        "name": "save_observation_package",
                        "args": {"contract": draft},
                        "id": "single-save-observation",
                        "type": "tool_call",
                    }
                ]
            ),
            _response("Single agent persisted the inspected ObservationPackage."),
        ]
    )
    monkeypatch.setattr(graph_factory, "_build_llm", lambda **_kwargs: model)
    telemetry = BenchmarkTelemetryCallback(tested_model_ids=())
    graph = graph_factory.build_ntl_graph(
        "deepseek-v4-flash", "unused", architecture_mode="single_agent"
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Inspect and save the staged observation.")]},
        config={
            "callbacks": [telemetry],
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "benchmark_usage_scope": "tested_agent",
                "batch_run_id": run_id,
                "task_run_id": run_id,
                "case_id": task_id,
                "task_submitted_at": "2026-08-12T00:00:00Z",
                "agent_name": "NTL_Engineer",
            },
            "recursion_limit": 40,
        },
    )

    assert result["messages"][-1].content == (
        "Single agent persisted the inspected ObservationPackage."
    )
    assert model.cursor == 3
    assert all("task" not in names for names in model.bound_tool_sets)
    assert [row["tool_name"] for row in telemetry.snapshot()["tool_trace"]] == [
        "geodata_inspector_tool",
        "save_observation_package",
    ]
    persisted_path = (
        manager.get_workspace(thread_id)
        / "outputs"
        / "runs"
        / run_id
        / "contracts"
        / f"observation_package__{observation.artifact_id}.json"
    )
    persisted = ObservationPackage.model_validate_json(
        persisted_path.read_text(encoding="utf-8")
    )
    assert persisted.query_executed_at_utc == observation.query_executed_at_utc


def test_pro_model_uses_the_exact_ntl_harness_without_general_purpose(
    isolated_runtime: tuple[StorageManager, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _manager, thread_id = isolated_runtime
    model = ScriptedChat(
        model_name="deepseek-v4-pro",
        responses=[_response("Pro harness is exact and provider-free.")],
    )
    monkeypatch.setattr(graph_factory, "_build_llm", lambda **_kwargs: model)

    graph = graph_factory.build_ntl_graph(
        "deepseek-v4-pro", "unused", architecture_mode="full"
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Inspect the pro harness.")]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": 30},
    )

    assert result["messages"][-1].content == "Pro harness is exact and provider-free."
    assert model.task_tool_descriptions
    task_description = model.task_tool_descriptions[-1]
    assert "Delegate one complete model-facing `ntl.assignment.v1` draft" in task_description
    assert "NTL_Data_Searcher" in task_description
    assert "NTL_Analyst" in task_description
    assert "NTL_Event_Tracker" in task_description
    assert "general-purpose" not in task_description


def test_large_tool_result_offloads_to_state_backend_not_thread_workspace(
    isolated_runtime: tuple[StorageManager, str],
) -> None:
    manager, thread_id = isolated_runtime

    @tool
    def huge_provider_free_result() -> str:
        """Return enough deterministic text to trigger Deep Agents offloading."""

        return ("state-backend-marker-" + "x" * 980 + "\n") * 100

    model = ScriptedChat(
        responses=[
            _response(
                tool_calls=[
                    {
                        "name": "huge_provider_free_result",
                        "args": {},
                        "id": "huge-result-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response(
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {
                            "file_path": "/large_tool_results/huge-result-1",
                            "offset": 0,
                            "limit": 2,
                        },
                        "id": "recover-huge-result-1",
                        "type": "tool_call",
                    }
                ]
            ),
            _response("Large result was offloaded."),
        ]
    )
    graph = graph_factory.create_deep_agent(
        model,
        tools=[huge_provider_free_result],
        system_prompt="Exercise the official large-result offload path.",
        backend=graph_factory.RUNTIME_BACKEND,
        permissions=graph_factory.filesystem_permissions(
            graph_factory.ROLE_SPECS["NTL_Engineer"].skill_sources,
            memory_access=True,
        ),
        checkpointer=False,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content="Call the deterministic large-result tool.")]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": 30},
    )

    assert result["messages"][-1].content == "Large result was offloaded."
    pointer_messages = [
        str(message.content)
        for message in result["messages"]
        if getattr(message, "type", "") == "tool"
    ]
    assert any("/large_tool_results/huge-result-1" in text for text in pointer_messages)
    assert "/large_tool_results/huge-result-1" in result["files"]
    assert "state-backend-marker" in result["files"]["/large_tool_results/huge-result-1"]["content"]
    assert any("state-backend-marker" in text for text in model.seen_message_texts)
    assert not (manager.get_workspace(thread_id) / "large_tool_results").exists()
