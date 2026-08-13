from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware

import graph_factory
from storage_manager import StorageManager, current_thread_id


class _FakeGraph:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)

    def with_config(self, config: dict[str, Any]):
        self.config = config
        return self


def _fake_create_deep_agent(model: Any, tools: list[Any] | None = None, **kwargs: Any):
    return _FakeGraph(model=model, tools=list(tools or []), **kwargs)


@pytest.fixture
def factory_without_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(graph_factory, "_build_llm", lambda **_kwargs: object())
    monkeypatch.setattr(graph_factory, "_knowledge_base_tool", lambda: object())
    monkeypatch.setattr(graph_factory, "create_deep_agent", _fake_create_deep_agent)
    monkeypatch.setattr(graph_factory, "_validate_skill_sources", lambda _sources: None)


def _permission_dicts(rules: list[Any]) -> list[dict[str, Any]]:
    return [
        {"operations": list(rule.operations), "paths": list(rule.paths), "mode": rule.mode}
        for rule in rules
    ]


def test_full_architecture_uses_three_declarative_specialists(factory_without_provider) -> None:
    graph = graph_factory.build_ntl_graph("deepseek-v4-flash", "test", architecture_mode="full")

    assert graph.name == "NTL_Engineer"
    assert graph.system_prompt == graph_factory._full_system_prompt()
    assert graph.backend is graph_factory.RUNTIME_BACKEND
    assert not hasattr(graph, "memory")
    assert [spec["name"] for spec in graph.subagents] == [
        "NTL_Data_Searcher",
        "NTL_Analyst",
        "NTL_Event_Tracker",
    ]
    assert all("runnable" not in spec for spec in graph.subagents)
    assert "general-purpose" not in {spec["name"] for spec in graph.subagents}
    engineer_tool_names = {tool.name for tool in graph.tools if hasattr(tool, "name")}
    assert engineer_tool_names >= {
        "save_task_plan",
        "save_evidence_report",
        "record_route_transition",
    }
    assert "record_handoff_decision" not in engineer_tool_names

    specialists = {spec["name"]: spec for spec in graph.subagents}
    expected_save_tool = {
        "NTL_Data_Searcher": "save_observation_package",
        "NTL_Analyst": "save_analysis_package",
        "NTL_Event_Tracker": "save_event_context",
    }
    for role_name, save_tool in expected_save_tool.items():
        spec = specialists[role_name]
        assert save_tool in {tool.name for tool in spec["tools"] if hasattr(tool, "name")}
        assert spec["skills"] == list(graph_factory.ROLE_SPECS[role_name].skill_sources)
        assert _permission_dicts(spec["permissions"]) == graph_factory.filesystem_runtime_descriptor(
            graph_factory.ROLE_SPECS[role_name].skill_sources,
            memory_access=False,
        )["permissions"]


def test_full_prompt_allows_system_bound_engineer_to_analyst_route() -> None:
    prompt = graph_factory._full_system_prompt()

    assert "Engineer→Analyst" in prompt
    assert "observation_required=false" in prompt
    assert "identity will be system-bound during save" in prompt
    assert "general-purpose" not in prompt


def test_full_prompt_uses_native_task_return_and_system_owned_handoff_records() -> None:
    prompt = graph_factory._full_system_prompt()

    assert "Engineer→Event Tracker" in prompt
    assert "native `task` result" in prompt
    assert "first transition to `handoff_validation`" in prompt
    assert "validate every ready package" in prompt
    assert "runtime, not the model" in prompt
    assert "transition to `synthesis`" in prompt
    assert "save the final EvidenceReport" in prompt
    assert "then transition to `completed`" in prompt
    assert "blocked/failed specialist may return without a package or handle" in prompt
    assert "never delegate a checksum-only retry" in prompt
    assert "One normal scientifically successful Event Tracker task" in prompt
    assert "Do not split that work across a second delegation" in prompt
    assert "record_handoff_decision" not in prompt
    assert "ntl.assignment.v1" not in prompt
    assert "ntl.handoff.v1" not in prompt


def test_single_agent_has_union_skills_and_no_delegation(factory_without_provider) -> None:
    graph = graph_factory.build_ntl_graph(
        "deepseek-v4-flash", "test", architecture_mode="single_agent"
    )
    union = list(
        dict.fromkeys(
            source
            for role in graph_factory.ROLE_SPECS.values()
            for source in role.skill_sources
        )
    )

    assert graph.name == "NTL_Engineer"
    assert graph.system_prompt == graph_factory._single_agent_prompt()
    assert getattr(graph, "subagents", None) is None
    assert graph.skills == union
    assert not hasattr(graph, "memory")
    assert _permission_dicts(graph.permissions) == graph_factory.filesystem_runtime_descriptor(
        union, memory_access=True
    )["permissions"]
    tool_names = {tool.name for tool in graph.tools if hasattr(tool, "name")}
    assert {
        "save_task_plan",
        "save_event_context",
        "save_observation_package",
        "save_analysis_package",
        "save_evidence_report",
        "record_route_transition",
    } <= tool_names
    assert "record_handoff_decision" not in tool_names
    assert "an analysis task must save a ready AnalysisPackage" in graph.system_prompt
    assert "event task must save a ready EventContext" in graph.system_prompt
    assert "EvidenceReport alone never substitutes" in graph.system_prompt
    assert "Saving a package makes all referenced files immutable" in graph.system_prompt
    assert "non-delegating event-context task" in graph.system_prompt
    assert "save and validate EventContext" in graph.system_prompt
    assert "future-tense process narration" in graph.system_prompt
    assert "typed save binds its SHA-256 and byte count" in graph.system_prompt
    assert "Never compute, guess, copy, null-fill, or placeholder-fill" in graph.system_prompt
    assert "blocked/failed task may finish without an intermediate package or handle" in graph.system_prompt


def test_exact_harness_profile_disables_general_purpose_and_overrides_task() -> None:
    assert graph_factory.DEEPAGENTS_HARNESS_MODEL_SPEC == "openai:deepseek-v4-flash"
    assert graph_factory.DEEPAGENTS_HARNESS_MODEL_SPECS == (
        "openai:deepseek-v4-flash",
        "openai:deepseek-v4-pro",
    )
    assert graph_factory.DEEPAGENTS_HARNESS_API_MODELS == (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    )
    profile = graph_factory.NTL_HARNESS_PROFILE
    assert profile.general_purpose_subagent is not None
    assert profile.general_purpose_subagent.enabled is False
    assert profile.tool_description_overrides["task"] == graph_factory.NTL_TASK_DESCRIPTION
    assert "{available_agents}" in graph_factory.NTL_TASK_DESCRIPTION
    assert "self-contained natural-language task" in graph_factory.NTL_TASK_DESCRIPTION
    assert "workspace-relative path and semantic role/media type only" in graph_factory.NTL_TASK_DESCRIPTION
    assert "never include or request its SHA-256 or byte count" in graph_factory.NTL_TASK_DESCRIPTION
    assert "local artifact identity" in graph_factory.NTL_TASK_DESCRIPTION
    assert "AssignmentEnvelope or HandoffEnvelope" in graph_factory.NTL_TASK_DESCRIPTION
    assert "ntl.assignment.v1" not in graph_factory.NTL_TASK_DESCRIPTION


def test_all_supported_models_build_with_an_exact_harness_profile(
    factory_without_provider,
) -> None:
    for model_name in graph_factory.DEEPAGENTS_HARNESS_API_MODELS:
        graph = graph_factory.build_ntl_graph(model_name, "test", architecture_mode="full")
        assert graph.name == "NTL_Engineer"


def test_graph_build_rejects_unmanaged_postgres_store_lifetime(
    factory_without_provider,
) -> None:
    with pytest.raises(NotImplementedError, match="connection lifetime"):
        graph_factory.build_ntl_graph(
            "deepseek-v4-flash",
            "test",
            postgres_url="postgresql://unused",
            architecture_mode="full",
        )


def test_architecture_descriptor_and_mode_validation() -> None:
    assert graph_factory.architecture_descriptor("full")["role_names"] == [
        "NTL_Engineer",
        "NTL_Data_Searcher",
        "NTL_Analyst",
        "NTL_Event_Tracker",
    ]
    assert graph_factory.architecture_descriptor("single_agent")["delegation_enabled"] is False
    with pytest.raises(ValueError):
        graph_factory.architecture_descriptor("legacy")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    [
        "/outputs/runs/run-1/contracts/task_plan.json",
        "/outputs/runs/run-1/handoffs/handoff.json",
        "/outputs/runs/run-1/decisions/decision.json",
        "/outputs/runs/run-1/assignment_records/assignment.json",
        "/outputs/runs/run-1/handoff_records/handoff.json",
        "/outputs/runs/run-1/route/route_state.json",
        "/outputs/runs/run-1/ROUTE/Route_State__checkpoint.json",
        "/data/processed/runs/run-1/contracts/task_plan.json",
    ],
)
def test_internal_evidence_path_classifier_fails_closed(path: str) -> None:
    assert graph_factory._is_protected_evidence_path(path) is True


def test_non_evidence_outputs_are_not_protected() -> None:
    assert graph_factory._is_protected_evidence_path("/outputs/artifacts/result.csv") is False
    assert graph_factory._is_protected_evidence_path("/outputs/runs/run-1/artifacts/result.csv") is False
    assert graph_factory._is_protected_evidence_path("/inputs/contracts/user_fixture.json") is False


def _write_skill(skills_root: Path, namespace: str, marker: str) -> None:
    directory = skills_root / namespace / "scope-test"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        "---\nname: scope-test\ndescription: scope test\n---\n" + marker + "\n",
        encoding="utf-8",
    )


def _actual_filesystem_tools(
    *, tmp_path: Path, skill_sources: tuple[str, ...], memory_access: bool = False
) -> tuple[dict[str, Any], SimpleNamespace]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    skills_root = tmp_path / "skills"
    skills_backend = CompositeBackend(
        default=FilesystemBackend(root_dir=skills_root, virtual_mode=True),
        routes={
            f"/{namespace}/": FilesystemBackend(
                root_dir=skills_root / namespace, virtual_mode=True
            )
            for namespace in ("common", "engineer", "data_searcher", "analyst", "event_tracker", "legacy")
        },
    )
    backend = CompositeBackend(
        default=FilesystemBackend(root_dir=workspace, virtual_mode=True),
        routes={"/skills/": skills_backend},
    )
    middleware = FilesystemMiddleware(
        backend=backend,
        _permissions=graph_factory.filesystem_permissions(
            skill_sources, memory_access=memory_access
        ),
    )
    return {tool.name: tool for tool in middleware.tools}, SimpleNamespace(tool_call_id="scope-test")


def _content(value: Any) -> str:
    return str(getattr(value, "content", value))


@pytest.mark.parametrize(
    ("role_name", "role_namespace"),
    [
        ("NTL_Engineer", "engineer"),
        ("NTL_Data_Searcher", "data_searcher"),
        ("NTL_Analyst", "analyst"),
        ("NTL_Event_Tracker", "event_tracker"),
    ],
)
def test_native_permissions_enforce_each_role_skill_scope(
    tmp_path: Path, role_name: str, role_namespace: str
) -> None:
    namespaces = ("common", "engineer", "data_searcher", "analyst", "event_tracker", "legacy")
    for namespace in namespaces:
        _write_skill(tmp_path / "skills", namespace, f"marker-{namespace}")

    tools, runtime = _actual_filesystem_tools(
        tmp_path=tmp_path,
        skill_sources=graph_factory.ROLE_SPECS[role_name].skill_sources,
    )
    listing = _content(tools["ls"].func(runtime=runtime, path="/skills/"))
    discovered = _content(
        tools["glob"].func(runtime=runtime, pattern="**/SKILL.md", path="/skills/")
    )
    grep_result = _content(
        tools["grep"].func(
            runtime=runtime,
            pattern="marker-",
            path="/skills/",
            glob="**/SKILL.md",
        )
    )

    assert f"/skills/{role_namespace}/" in listing
    assert "/skills/common/" in listing
    assert "/skills/legacy/" not in listing
    assert f"/skills/{role_namespace}/scope-test/SKILL.md" in discovered
    assert "/skills/common/scope-test/SKILL.md" in discovered
    assert "/skills/legacy/" not in discovered
    assert f"/skills/{role_namespace}/scope-test/SKILL.md" in grep_result
    assert "/skills/legacy/" not in grep_result

    blocked_read = _content(
        tools["read_file"].func(
            file_path="/skills/legacy/scope-test/SKILL.md", runtime=runtime
        )
    )
    blocked_write = _content(
        tools["write_file"].func(
            file_path=f"/skills/{role_namespace}/injected/SKILL.md",
            content="untrusted",
            runtime=runtime,
        )
    )
    normal_write = _content(
        tools["write_file"].func(
            file_path="/outputs/artifacts/result.txt",
            content="normal artifact",
            runtime=runtime,
        )
    )

    assert "permission denied" in blocked_read
    assert "permission denied" in blocked_write
    assert "Updated file /outputs/artifacts/result.txt" == normal_write
    assert (tmp_path / "workspace" / "outputs" / "artifacts" / "result.txt").is_file()


def test_single_agent_skill_scope_is_four_role_union_without_legacy(tmp_path: Path) -> None:
    namespaces = ("common", "engineer", "data_searcher", "analyst", "event_tracker", "legacy")
    for namespace in namespaces:
        _write_skill(tmp_path / "skills", namespace, f"marker-{namespace}")
    sources = tuple(
        dict.fromkeys(
            source for role in graph_factory.ROLE_SPECS.values() for source in role.skill_sources
        )
    )
    tools, runtime = _actual_filesystem_tools(tmp_path=tmp_path, skill_sources=sources)
    discovered = _content(
        tools["glob"].func(runtime=runtime, pattern="**/SKILL.md", path="/skills/")
    )

    for namespace in ("common", "engineer", "data_searcher", "analyst", "event_tracker"):
        assert f"/skills/{namespace}/scope-test/SKILL.md" in discovered
    assert "/skills/legacy/" not in discovered


def test_native_permissions_protect_evidence_and_read_only_routes(tmp_path: Path) -> None:
    tools, runtime = _actual_filesystem_tools(
        tmp_path=tmp_path,
        skill_sources=graph_factory.ROLE_SPECS["NTL_Engineer"].skill_sources,
        memory_access=True,
    )
    protected = tmp_path / "workspace" / "outputs" / "runs" / "run-1" / "contracts" / "plan.json"
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text('{"canonical":true}', encoding="utf-8")
    (tmp_path / "workspace" / "shared").mkdir(parents=True, exist_ok=True)

    blocked_write = _content(
        tools["write_file"].func(
            file_path="/outputs/runs/run-1/contracts/plan.json",
            content='{"canonical":false}',
            runtime=runtime,
        )
    )
    blocked_edit = _content(
        tools["edit_file"].func(
            file_path="/outputs/runs/run-1/contracts/plan.json",
            old_string="true",
            new_string="false",
            runtime=runtime,
        )
    )
    blocked_delete = _content(
        tools["delete"].func(
            file_path="/outputs/runs/run-1/contracts/plan.json", runtime=runtime
        )
    )
    blocked_shared = _content(
        tools["write_file"].func(
            file_path="/shared/tampered.txt", content="tampered", runtime=runtime
        )
    )
    blocked_route_state = _content(
        tools["write_file"].func(
            file_path="/outputs/runs/run-1/route/route_state__checkpoint/payload.json",
            content="tampered",
            runtime=runtime,
        )
    )
    blocked_read = _content(
        tools["read_file"].func(
            file_path="/outputs/runs/run-1/contracts/plan.json", runtime=runtime
        )
    )
    blocked_run_listing = _content(tools["ls"].func(path="/outputs/runs", runtime=runtime))

    assert all(
        "permission denied" in value
        for value in (
            blocked_write,
            blocked_edit,
            blocked_delete,
            blocked_shared,
            blocked_route_state,
            blocked_read,
            blocked_run_listing,
        )
    )
    assert protected.read_text(encoding="utf-8") == '{"canonical":true}'


def test_permissions_hide_runner_instrumentation_and_root_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    for directory in ("inputs", "outputs"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    telemetry = workspace / ".benchmark-telemetry.json"
    telemetry.write_text('{"secret":"runner-journal-marker"}', encoding="utf-8")
    (workspace / "unassigned-root.txt").write_text("root-marker", encoding="utf-8")
    (workspace / "inputs" / "fixture.txt").write_text("input-marker", encoding="utf-8")
    (workspace / "outputs" / "artifact.txt").write_text("output-marker", encoding="utf-8")

    tools, runtime = _actual_filesystem_tools(
        tmp_path=tmp_path,
        skill_sources=graph_factory.ROLE_SPECS["NTL_Engineer"].skill_sources,
    )
    listing = _content(tools["ls"].func(runtime=runtime, path="/"))
    grep_result = _content(
        tools["grep"].func(
            runtime=runtime, pattern="marker", path="/", glob="**/*", output_mode="content"
        )
    )
    blocked_read = _content(
        tools["read_file"].func(file_path="/.benchmark-telemetry.json", runtime=runtime)
    )

    assert "/inputs/" in listing and "/outputs/" in listing
    assert ".benchmark-telemetry" not in listing
    assert "unassigned-root" not in listing
    assert "runner-journal-marker" not in grep_result
    assert "root-marker" not in grep_result
    assert "input-marker" in grep_result and "output-marker" in grep_result
    assert "permission denied" in blocked_read


@pytest.mark.parametrize(
    "file_path",
    [
        "/inputs/.env",
        "/shared/.credentials",
        "/skills/analyst/.x",
        "/outputs/nested/.secrets/token.txt",
    ],
)
def test_permissions_deny_nested_hidden_paths(tmp_path: Path, file_path: str) -> None:
    disk_path = (
        tmp_path / "skills" / file_path.removeprefix("/skills/")
        if file_path.startswith("/skills/")
        else tmp_path / "workspace" / file_path.lstrip("/")
    )
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_text("hidden-marker", encoding="utf-8")
    tools, runtime = _actual_filesystem_tools(
        tmp_path=tmp_path,
        skill_sources=graph_factory.ROLE_SPECS["NTL_Analyst"].skill_sources,
    )

    blocked_read = _content(
        tools["read_file"].func(file_path=file_path, runtime=runtime)
    )
    blocked_write = _content(
        tools["write_file"].func(
            file_path=file_path,
            content="tampered",
            runtime=runtime,
        )
    )

    assert "permission denied" in blocked_read
    assert "permission denied" in blocked_write
    assert disk_path.read_text(encoding="utf-8") == "hidden-marker"


def test_internal_state_paths_are_read_only_to_filesystem_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    for relative in (
        "large_tool_results/call-1",
        "conversation_history/turn-1",
    ):
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"state-marker:{relative}", encoding="utf-8")
    tools, runtime = _actual_filesystem_tools(
        tmp_path=tmp_path,
        skill_sources=graph_factory.ROLE_SPECS["NTL_Engineer"].skill_sources,
    )

    for file_path in (
        "/large_tool_results/call-1",
        "/conversation_history/turn-1",
    ):
        recovered = _content(
            tools["read_file"].func(file_path=file_path, runtime=runtime)
        )
        blocked_write = _content(
            tools["write_file"].func(
                file_path=file_path,
                content="tampered",
                runtime=runtime,
            )
        )
        assert f"state-marker:{file_path.lstrip('/')}" in recovered
        assert "permission denied" in blocked_write


def test_runtime_backend_uses_state_for_internal_files_and_dynamic_thread_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = StorageManager(
        base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "shared")
    )
    monkeypatch.setattr(graph_factory, "storage_manager", manager)
    backend = graph_factory._build_runtime_backend()

    assert isinstance(backend.default, StateBackend)
    assert isinstance(backend._get_backend_and_key("/large_tool_results/call-1")[0], StateBackend)
    assert isinstance(backend._get_backend_and_key("/conversation_history/turn-1")[0], StateBackend)

    first = current_thread_id.set("thread-a")
    try:
        assert backend.write("/outputs/result.txt", "thread-a").error is None
        assert backend.write("/data/raw/input.txt", "input-a").error is None
    finally:
        current_thread_id.reset(first)
    second = current_thread_id.set("thread-b")
    try:
        assert backend.write("/outputs/result.txt", "thread-b").error is None
    finally:
        current_thread_id.reset(second)

    assert (manager.get_workspace("thread-a") / "outputs" / "result.txt").read_text() == "thread-a"
    assert (manager.get_workspace("thread-a") / "inputs" / "input.txt").read_text() == "input-a"
    assert (manager.get_workspace("thread-b") / "outputs" / "result.txt").read_text() == "thread-b"


def test_runtime_memory_route_does_not_seed_legacy_agent_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = StorageManager(
        base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "shared")
    )
    monkeypatch.setattr(graph_factory, "storage_manager", manager)
    backend = graph_factory._build_runtime_backend()

    token = current_thread_id.set("thread-memory")
    try:
        assert backend.write("/memories/gee_exports/run.json", '{"state":"ready"}').error is None
        loaded = backend.read("/memories/gee_exports/run.json")
    finally:
        current_thread_id.reset(token)

    workspace = manager.get_workspace("thread-memory")
    assert loaded.error is None
    assert loaded.file_data == {"content": '{"state":"ready"}', "encoding": "utf-8"}
    assert not (workspace / "memory" / "NTL_AGENT_MEMORY.md").exists()


def test_runtime_descriptor_is_path_free_and_ordered() -> None:
    descriptor = graph_factory.filesystem_runtime_descriptor(
        graph_factory.ROLE_SPECS["NTL_Engineer"].skill_sources,
        memory_access=True,
    )
    assert descriptor["backend_type"] == "CompositeBackend(default=StateBackend)"
    assert descriptor["internal_state_paths"] == [
        "/large_tool_results/",
        "/conversation_history/",
    ]
    assert descriptor["permissions"][-1] == {
        "operations": ["read", "write"],
        "paths": ["/**"],
        "mode": "deny",
    }
    rendered = repr(descriptor)
    assert str(graph_factory.SKILLS_ROOT) not in rendered
    assert str(graph_factory.storage_manager.base_dir) not in rendered
