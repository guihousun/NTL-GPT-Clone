from __future__ import annotations

import posixpath
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import (
    BackendProtocol,
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
)
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    WriteResult,
)
from deepagents.middleware.filesystem import FilesystemPermission
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agents.NTL_Analyst import system_prompt_analyst
from agents.NTL_Data_Searcher import hierarchical_system_prompt_data_searcher
from agents.NTL_Event_Tracker import system_prompt_event_tracker
from agents.role_specs import ROLE_SPECS
from model_config import get_api_model_name, get_base_url, get_model_config
from orchestration.contract_tools import (
    record_route_transition_tool,
    save_analysis_package_tool,
    save_event_context_tool,
    save_evidence_report_tool,
    save_observation_package_tool,
    save_task_plan_tool,
    validate_contract_tool,
)
from storage_manager import current_thread_id, storage_manager
from tools import (
    analyst_tools,
    data_searcher_tools,
    engineer_tools,
    event_tracker_tools,
    single_agent_tools,
)


ArchitectureMode = Literal["full", "single_agent"]
ARCHITECTURE_MODES: tuple[ArchitectureMode, ...] = ("full", "single_agent")

checkpointer = MemorySaver()
SKILLS_ROOT = Path(__file__).resolve().parent / ".ntl-gpt" / "skills"
DEEPAGENTS_HARNESS_MODEL_SPECS = (
    "openai:deepseek-v4-flash",
    "openai:deepseek-v4-pro",
)
DEEPAGENTS_HARNESS_MODEL_SPEC = DEEPAGENTS_HARNESS_MODEL_SPECS[0]
DEEPAGENTS_HARNESS_API_MODELS = tuple(
    spec.partition(":")[2] for spec in DEEPAGENTS_HARNESS_MODEL_SPECS
)
NTL_TASK_DESCRIPTION = """Delegate one self-contained natural-language task to exactly one registered NTL specialist.

Available specialists:
{available_agents}

Set `subagent_type` to one listed specialist name only. In `description`, state the objective, scientific scope, known inputs or parent package handles, requested typed scientific package, acceptance checks, and relevant limitations in normal prose. Do not serialize an AssignmentEnvelope or HandoffEnvelope. Do not include benchmark Gold or evaluator material. Runtime identity, timestamps, and assignment/handoff records are system-managed; never try to discover or supply them.
"""

NTL_HARNESS_PROFILE = HarnessProfile(
    tool_description_overrides={"task": NTL_TASK_DESCRIPTION},
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
)
for _harness_model_spec in DEEPAGENTS_HARNESS_MODEL_SPECS:
    register_harness_profile(_harness_model_spec, NTL_HARNESS_PROFILE)

ENGINEER_CONTRACT_TOOLS = (
    save_task_plan_tool,
    save_evidence_report_tool,
    validate_contract_tool,
    record_route_transition_tool,
)
DATA_SEARCHER_CONTRACT_TOOLS = (save_observation_package_tool, validate_contract_tool)
ANALYST_CONTRACT_TOOLS = (save_analysis_package_tool, validate_contract_tool)
EVENT_TRACKER_CONTRACT_TOOLS = (save_event_context_tool, validate_contract_tool)
SINGLE_AGENT_CONTRACT_TOOLS = (
    save_task_plan_tool,
    save_event_context_tool,
    save_observation_package_tool,
    save_analysis_package_tool,
    save_evidence_report_tool,
    validate_contract_tool,
    record_route_transition_tool,
)


def _prompt_text(value: Any) -> str:
    content = getattr(value, "content", value)
    return str(content)


class _KnowledgeBaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Question plus brief NTL context.")
    response_mode: Literal["theory", "workflow"] = "theory"
    locale: str = "en"
    need_citations: bool = True
    skill_gap_confirmed: bool = False


def _invoke_knowledge_base(
    query: str,
    response_mode: str = "theory",
    locale: str = "en",
    need_citations: bool = True,
    skill_gap_confirmed: bool = False,
    config: RunnableConfig | None = None,
):
    # Chroma opens its persistent stores during module import. Keep that side
    # effect out of graph construction and provider-free tests; import only if
    # the tested agent actually requests supplemental knowledge.
    from tools.NTL_Knowledge_Base_Searcher import NTL_Knowledge_Base

    return NTL_Knowledge_Base.invoke(
        {
            "query": query,
            "response_mode": response_mode,
            "locale": locale,
            "need_citations": need_citations,
            "skill_gap_confirmed": skill_gap_confirmed,
        },
        config=config,
    )


def _knowledge_base_tool():
    return StructuredTool.from_function(
        func=_invoke_knowledge_base,
        name="NTL_Knowledge_Base",
        description=(
            "Supplement local NTL skills with grounded theory or literature context. "
            "Use workflow mode only after relevant role skills lack coverage."
        ),
        args_schema=_KnowledgeBaseInput,
    )


def _build_llm(model_name: str, api_key: str, request_timeout_s: int):
    model_config = get_model_config(model_name)
    api_model = get_api_model_name(model_name)
    if model_config.provider != "deepseek":
        raise ValueError(f"Unsupported frontend model provider: {model_config.provider}")
    base_url = get_base_url(model_name)
    if not api_key or not base_url:
        raise RuntimeError(
            f"{model_config.api_key_env} and {model_config.base_url_env} are required for {api_model}."
        )
    return ChatOpenAI(
        api_key=SecretStr(api_key),
        base_url=base_url,
        model=api_model,
        temperature=0,
        timeout=request_timeout_s,
        max_retries=3,
    )


def _validate_skill_sources(skill_sources: Sequence[str]) -> None:
    missing: list[str] = []
    for src in sorted(set(skill_sources)):
        if not src.startswith("/skills/"):
            missing.append(f"{src} -> role skill sources must be mounted below /skills/")
            continue
        rel = src[len("/skills/") :].strip("/")
        source_dir = SKILLS_ROOT / rel
        if not source_dir.exists() or not source_dir.is_dir():
            missing.append(f"{src} -> missing directory: {source_dir}")
            continue
        if not any((p / "SKILL.md").exists() for p in source_dir.iterdir() if p.is_dir()):
            missing.append(f"{src} -> no child skill directories with SKILL.md under {source_dir}")
    if missing:
        raise ValueError("Invalid Deep Agents skill sources:\n" + "\n".join(missing))


def _is_protected_evidence_path(file_path: str) -> bool:
    """Return whether a virtual path belongs to the internal run-evidence tree.

    Deep Agents' generic filesystem middleware and the typed contract tools use
    different persistence paths: the former goes through this backend, while
    the latter writes via ``storage_manager`` after schema validation.  Protect
    both the canonical ``/outputs`` tree and its documented
    ``/data/processed`` alias so an agent cannot overwrite or spoof contracts,
    handoffs, decisions, system-authored transfer records, or route checkpoints
    with ``write_file``/``edit_file``. The model-facing filesystem cannot read
    this identity-bearing audit tree; typed tools and the runner own access.
    """

    raw = str(file_path or "").replace("\\", "/")
    normalized = posixpath.normpath("/" + raw.lstrip("/"))
    parts = tuple(part.casefold() for part in normalized.split("/") if part)
    if parts[:2] == ("outputs", "runs"):
        evidence_parts = parts[2:]
    elif parts[:3] == ("data", "processed", "runs"):
        evidence_parts = parts[3:]
    else:
        return False
    return any(
        part
        in {
            "contracts",
            "handoffs",
            "decisions",
            "assignment_records",
            "handoff_records",
        }
        or part.startswith("route_state")
        for part in evidence_parts
    )


def _normalize_virtual_path(path: str) -> str:
    raw = str(path or "").replace("\\", "/")
    return posixpath.normpath("/" + raw.lstrip("/"))


class ContextFilesystemBackend(BackendProtocol):
    """Deep Agents 0.7.5 backend whose filesystem root follows ContextVar state."""

    def __init__(self, root_resolver: Callable[[], Path]) -> None:
        self._root_resolver = root_resolver

    def _backend(self) -> FilesystemBackend:
        root = Path(self._root_resolver()).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return FilesystemBackend(root_dir=root, virtual_mode=True)

    def ls(self, path: str):
        return self._backend().ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return self._backend().read(file_path, offset=offset, limit=limit)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None, *, max_count: int | None = None):
        return self._backend().grep(pattern, path=path, glob=glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None):
        return self._backend().glob(pattern, path=path)

    def write(self, file_path: str, content: str) -> WriteResult:
        return self._backend().write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return self._backend().edit(file_path, old_string, new_string, replace_all=replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        return self._backend().delete(file_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return self._backend().upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._backend().download_files(paths)


def _workspace_subdir(name: str) -> Path:
    workspace = storage_manager.get_workspace(str(current_thread_id.get() or "debug").strip() or "debug")
    return workspace / name


def _build_skills_backend() -> CompositeBackend:
    return CompositeBackend(
        # The project tree is the catch-all skill mount so listing /skills works
        # outside graph execution too. Explicit role routes keep source paths
        # stable; native permissions still hide every namespace except common
        # plus the active role (or the Single-Agent union).
        default=FilesystemBackend(root_dir=SKILLS_ROOT, virtual_mode=True),
        routes={
            f"/{namespace}/": FilesystemBackend(root_dir=SKILLS_ROOT / namespace, virtual_mode=True)
            for namespace in ("common", "engineer", "data_searcher", "analyst", "event_tracker")
        },
    )


def _build_runtime_backend() -> CompositeBackend:
    inputs = ContextFilesystemBackend(lambda: _workspace_subdir("inputs"))
    outputs = ContextFilesystemBackend(lambda: _workspace_subdir("outputs"))
    # Thread memory remains an ordinary runtime-state route for export
    # manifests and failed-run records. It is deliberately not registered as
    # Deep Agents startup memory: scientific routing and role policy live in
    # versioned system prompts and role skills, not mutable thread Markdown.
    memories = ContextFilesystemBackend(lambda: _workspace_subdir("memory"))
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/inputs/": inputs,
            "/outputs/": outputs,
            "/data/raw/": inputs,
            "/data/processed/": outputs,
            "/memories/": memories,
            "/shared/": FilesystemBackend(root_dir=storage_manager.shared_dir, virtual_mode=True),
            "/skills/": _build_skills_backend(),
        },
    )


RUNTIME_BACKEND = _build_runtime_backend()


def filesystem_permissions(
    skill_sources: Sequence[str], *, memory_access: bool
) -> list[FilesystemPermission]:
    sources = tuple(dict.fromkeys(_normalize_virtual_path(source) for source in skill_sources))
    # The whole internal audit tree is owned exclusively by typed contract
    # tools. Denying reads as well as writes prevents runtime identity from
    # leaking through directory names or persisted envelope fields.
    protected = [
        "/outputs/runs{,/**}",
        "/data/processed/runs{,/**}",
    ]
    readable = [
        "/",
        "/skills",
        "/inputs{,/**}",
        "/outputs{,/**}",
        "/data/raw{,/**}",
        "/data/processed{,/**}",
        "/shared{,/**}",
        "/large_tool_results{,/**}",
        "/conversation_history{,/**}",
    ]
    readable.extend(f"{source.rstrip('/')}{'{,/**}'}" for source in sources)
    writable = ["/outputs{,/**}", "/data/processed{,/**}"]
    if memory_access:
        readable.append("/memories{,/**}")
        writable.append("/memories{,/**}")
    return [
        FilesystemPermission(operations=["read", "write"], paths=protected, mode="deny"),
        FilesystemPermission(
            operations=["read", "write"], paths=["/**/.*{,/**}"], mode="deny"
        ),
        FilesystemPermission(operations=["read"], paths=readable, mode="allow"),
        FilesystemPermission(operations=["write"], paths=writable, mode="allow"),
        FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
    ]


def filesystem_runtime_descriptor(
    skill_sources: Sequence[str], *, memory_access: bool
) -> dict[str, Any]:
    rules = filesystem_permissions(skill_sources, memory_access=memory_access)
    return {
        "backend_type": "CompositeBackend(default=StateBackend)",
        "routes": {
            "/inputs/": "ContextFilesystemBackend(thread.inputs)",
            "/outputs/": "ContextFilesystemBackend(thread.outputs)",
            "/data/raw/": "ContextFilesystemBackend(thread.inputs)",
            "/data/processed/": "ContextFilesystemBackend(thread.outputs)",
            "/memories/": "ContextFilesystemBackend(thread.memory)",
            "/shared/": "FilesystemBackend(read-only by permissions)",
            "/skills/": "CompositeBackend(project skill tree plus explicit role namespaces)",
        },
        "internal_state_paths": ["/large_tool_results/", "/conversation_history/"],
        "permissions": [
            {"operations": list(rule.operations), "paths": list(rule.paths), "mode": rule.mode}
            for rule in rules
        ],
    }


def _full_system_prompt() -> str:
    return f"""NTL Engineer: supervisor of the four-agent NTL-GPT system.

System boundary and delegation contract:
- You are the only internal supervisor and the owner of task truth, routing, handoff acceptance, and final EvidenceReport.
- The only specialists are NTL_Data_Searcher, NTL_Analyst, and NTL_Event_Tracker.
- Specialists never call one another. Delegate sequentially through the `task` tool and validate every returned typed package before continuing.
- NTL_Data_Searcher owns products, observations, AOI, temporal validity, QA/scaling, acquisition, standard preprocessing, provenance, and ObservationPackage.
- ObservationPackage query time is system-managed: after a successful full geodata inspection, the runtime injects its completion time. Never ask a model to supply or guess it.
- NTL_Analyst owns task-specific NTL methods, code execution, statistics, models, figures, internal validation, and AnalysisPackage.
- NTL_Event_Tracker owns authorized event sources, source-bounded timelines, conflicts, as-of semantics, and EventContext.
- Use the six-gate direct-execution fast path only for simple tasks with existing verified inputs, settled scientific semantics, a mature single-stage operation, and an immediate deterministic check.
- A ready specialist package is not accepted until you check schema, path/checksum, assignment scope, scientific semantics, validation, and limitations.
- Never read benchmark Gold or evaluator material. Do not accept post-run repair suggestions during the tested run.
- Produce an EvidenceReport for completed, limited, blocked, or failed tasks. The runtime owns contract storage paths and audit identity.
- At task start save a TaskPlan and checkpoint legal route transitions. Runtime IDs, case identity, and system timestamps are injected by the system and are intentionally absent from model-facing tool inputs; producer is schema-fixed to the active role. Never discover, request, guess, echo, or override system identity; refer to saved packages only through the opaque references returned by typed contract tools.
- Never use generic filesystem mutation (`write_file` or `edit_file`) on the internal contracts or route-state tree. Never create or modify system-owned assignment/handoff records. Use only typed `save_*`, `validate_contract`, and `record_route_transition` tools for model-owned contract work.
- Every `task` delegation description must be a self-contained natural-language request: give the selected specialist the objective, scientific scope, known inputs or parent package handles, requested typed package, acceptance checks, and limitations. Do not ask for or emit an AssignmentEnvelope or HandoffEnvelope. The runtime records the native task call and return automatically.
- Route only as needed: direct fast path; Engineer→Data Searcher; Engineer→Analyst when checksum-bound analysis-ready inputs are already staged and `observation_required=false`; Engineer→Event Tracker for a source-bounded event-context-only task; Engineer→Data Searcher→Analyst; or Engineer→Event Tracker→Data Searcher→Analyst. Record why unused specialists were skipped.
- A specialist returns normally through the native `task` result with status, the exact opaque package handle when one was saved, an evidence-based summary, validation verdict, and limitations or error. After a specialist returns, first transition to `handoff_validation`, then inspect that result and validate every ready package before using it. Request a bounded revision or route another needed specialist when appropriate; otherwise transition to `synthesis` and continue from the validated package. The runtime, not the model, standardizes assignment/handoff process records.
- Before completion, transition to `synthesis`, save the final EvidenceReport, and then transition to `completed`. Do not leave a run in `handoff_validation` or `synthesis` when the remaining required model action is available.
- Do not emit a final answer before `save_evidence_report` succeeds. Afterwards output only the saved `EvidenceReport.direct_answer`, without process narration.

Workspace protocol:
- Read user or staged data only from `/inputs/`; write task artifacts only to `/outputs/`.
- `/shared/` is read-only; `/memories/` stores thread memory. Never inspect environment variables, runner telemetry, hidden control files, or host paths. Never expose credentials or absolute local paths.
"""


def _single_agent_prompt() -> str:
    return f"""NTL Engineer: matched Single-Agent baseline for NTL-GPT.

Complete the task in one context with the same data, tools, procedural knowledge, output contracts, and scientific guardrails as the Full system. You perform planning, event-context work, observation preparation, task-specific analysis, validation, and evidence synthesis yourself.

Critical comparison rules:
- No delegation or inter-agent handoff is available. Do not claim that another role performed work.
- Produce the same TaskPlan, optional EventContext/ObservationPackage/AnalysisPackage, artifact manifest, and final EvidenceReport required of the Full system.
- Treat every package type explicitly required by the task as mandatory, not optional: persist it with the matching typed `save_*` tool before EvidenceReport synthesis. In particular, an analysis task must save a ready AnalysisPackage and a source-reconciliation event task must save a ready EventContext even though one context performs all work. An EvidenceReport alone never substitutes for the required intermediate package.
- Finalize, re-open, and checksum every artifact before saving its typed package. Saving a package makes all referenced files immutable: never overwrite or edit them afterward. Complete every bounded repair before package persistence.
- For a non-delegating event-context task, complete this sequence in the same run: save TaskPlan with `event_context_required=true`; checkpoint event-context work; write and verify the requested source-bounded artifact; save and validate EventContext; checkpoint `handoff_validation` then `synthesis`; save EvidenceReport; checkpoint `completed`. Never end a model turn with future-tense process narration such as "now persist" or "next save" while a required tool call remains—call that tool in the same turn.
- At task start persist the TaskPlan and checkpoint the non-delegating route. Runtime IDs, case identity, and system timestamps are injected by the system and are intentionally absent from model-facing tool inputs; producer is schema-fixed to the active role. Never discover, request, guess, echo, or override system identity; use only opaque package references returned by typed contract tools. Persist every package you actually need and finish with an EvidenceReport.
- ObservationPackage query time is system-managed: after a successful full geodata inspection, the runtime injects its completion time. Never supply or guess it.
- Never use generic filesystem mutation (`write_file` or `edit_file`) on the internal contracts or route-state tree; use only typed `save_*`, `validate_contract`, and `record_route_transition` tools there. No assignment or handoff envelope is part of this non-delegating baseline.
- Respect the same AOI/time/product/QA/provenance/non-attribution boundaries and bounded repair policy.
- Never read benchmark Gold or evaluator material.
- Do not emit a final answer before `save_evidence_report` succeeds. Afterwards output only the saved `EvidenceReport.direct_answer`, without process narration.
- Read `/inputs/`, write `/outputs/`, keep `/shared/` read-only, and never inspect environment variables, runner telemetry, hidden control files, or host paths. Never expose credentials or absolute local paths.
"""


def architecture_descriptor(architecture_mode: ArchitectureMode) -> dict[str, Any]:
    if architecture_mode not in ARCHITECTURE_MODES:
        raise ValueError(f"unsupported architecture_mode: {architecture_mode}")
    role_names = ["NTL_Engineer"]
    if architecture_mode == "full":
        role_names.extend(["NTL_Data_Searcher", "NTL_Analyst", "NTL_Event_Tracker"])
    return {
        "architecture_mode": architecture_mode,
        "role_names": role_names,
        "delegation_enabled": architecture_mode == "full",
        "general_purpose_subagent_enabled": False,
        "contract_schema_version": "ntl.contract.v1",
    }


def build_ntl_graph(
    model_name: str,
    api_key: str,
    request_timeout_s: int = 120,
    graph_name: str = "NTL_Engineer",
    postgres_url: str | None = None,
    architecture_mode: ArchitectureMode = "full",
):
    if architecture_mode not in ARCHITECTURE_MODES:
        raise ValueError(f"unsupported architecture_mode: {architecture_mode}")
    api_model = get_api_model_name(model_name)
    if api_model not in DEEPAGENTS_HARNESS_API_MODELS:
        raise ValueError(
            "Deep Agents architecture has no registered NTL harness profile for "
            f"{api_model}; supported API models: {', '.join(DEEPAGENTS_HARNESS_API_MODELS)}."
        )
    if postgres_url:
        raise NotImplementedError(
            "postgres_url is disabled until PostgresStore setup and connection lifetime "
            "are owned by the application runtime."
        )
    store = InMemoryStore()

    model = _build_llm(model_name=model_name, api_key=api_key, request_timeout_s=request_timeout_s)
    if architecture_mode == "single_agent":
        sources = tuple(ROLE_SPECS[role].skill_sources for role in ROLE_SPECS)
        skill_sources = tuple(dict.fromkeys(source for group in sources for source in group))
        _validate_skill_sources(skill_sources)
        return create_deep_agent(
            model,
            tools=[*single_agent_tools, *SINGLE_AGENT_CONTRACT_TOOLS, _knowledge_base_tool()],
            system_prompt=_single_agent_prompt(),
            skills=list(skill_sources),
            permissions=filesystem_permissions(skill_sources, memory_access=True),
            backend=RUNTIME_BACKEND,
            store=store,
            name=graph_name,
            checkpointer=checkpointer,
        ).with_config({"recursion_limit": 1000})

    role_data = ROLE_SPECS["NTL_Data_Searcher"]
    role_analyst = ROLE_SPECS["NTL_Analyst"]
    role_tracker = ROLE_SPECS["NTL_Event_Tracker"]
    all_sources = [
        *ROLE_SPECS["NTL_Engineer"].skill_sources,
        *role_data.skill_sources,
        *role_analyst.skill_sources,
        *role_tracker.skill_sources,
    ]
    _validate_skill_sources(all_sources)

    specialists = [
        {
            "name": "NTL_Data_Searcher",
            "description": role_data.description,
            "system_prompt": _prompt_text(hierarchical_system_prompt_data_searcher),
            "tools": [*data_searcher_tools, *DATA_SEARCHER_CONTRACT_TOOLS],
            "model": model,
            "skills": list(role_data.skill_sources),
            "permissions": filesystem_permissions(role_data.skill_sources, memory_access=False),
        },
        {
            "name": "NTL_Analyst",
            "description": role_analyst.description,
            "system_prompt": _prompt_text(system_prompt_analyst),
            "tools": [*analyst_tools, *ANALYST_CONTRACT_TOOLS],
            "model": model,
            "skills": list(role_analyst.skill_sources),
            "permissions": filesystem_permissions(role_analyst.skill_sources, memory_access=False),
        },
        {
            "name": "NTL_Event_Tracker",
            "description": role_tracker.description,
            "system_prompt": _prompt_text(system_prompt_event_tracker),
            "tools": [*event_tracker_tools, *EVENT_TRACKER_CONTRACT_TOOLS],
            "model": model,
            "skills": list(role_tracker.skill_sources),
            "permissions": filesystem_permissions(role_tracker.skill_sources, memory_access=False),
        },
    ]

    engineer_sources = ROLE_SPECS["NTL_Engineer"].skill_sources
    return create_deep_agent(
        model,
        tools=[*engineer_tools, *ENGINEER_CONTRACT_TOOLS, _knowledge_base_tool()],
        system_prompt=_full_system_prompt(),
        subagents=specialists,
        skills=list(engineer_sources),
        permissions=filesystem_permissions(engineer_sources, memory_access=True),
        backend=RUNTIME_BACKEND,
        store=store,
        name=graph_name,
        checkpointer=checkpointer,
    ).with_config({"recursion_limit": 1000})
