from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.skills import _list_skills
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langgraph.store.memory import InMemoryStore
from pathlib import Path
from pydantic import SecretStr

from agents.NTL_Code_Assistant import Code_Assistant_system_prompt_text
from agents.NTL_Data_Searcher import system_prompt_data_searcher
from agents.NTL_Engineer import system_prompt_text
from agents.NTL_Knowledge_Subagent import system_prompt_kb_searcher
from storage_manager import current_thread_id, storage_manager
from tools import Code_tools, Engineer_tools, data_searcher_tools
from tools.NTL_Knowledge_Base_Searcher import NTL_Knowledge_Base

from langgraph.checkpoint.memory import MemorySaver  # For testing
# Or: from langgraph.checkpoint.postgres import PostgresSaver  # For production

checkpointer = MemorySaver()

SKILLS_ROOT = Path(__file__).resolve().parent / ".ntl-gpt" / "skills"
SKILLS_SOURCE = "/skills/"


def _build_llm(model_name: str, api_key: str, request_timeout_s: int):
    if "qwen" in model_name.lower():
        return ChatOpenAI(
            api_key=SecretStr(api_key),
            base_url=os.getenv("DASHSCOPE_Coding_URL"),
            model=model_name,
            timeout=request_timeout_s,
        )
    return init_chat_model(
        model_name,
        model_provider="openai",
        api_key=api_key,
        temperature=0,
        timeout=request_timeout_s,
        max_retries=3,
    )


def _validate_skill_sources(skill_sources: list[str]) -> None:
    missing: list[str] = []
    for src in sorted(set(skill_sources)):
        if not src.startswith("/skills/"):
            continue
        rel = src[len("/skills/") :].strip("/")
        source_dir = SKILLS_ROOT / rel if rel else SKILLS_ROOT
        if not source_dir.exists() or not source_dir.is_dir():
            missing.append(f"{src} -> missing directory: {source_dir}")
            continue
        has_skill = any((p / "SKILL.md").exists() for p in source_dir.iterdir() if p.is_dir())
        if not has_skill:
            missing.append(f"{src} -> no child skill directories with SKILL.md under {source_dir}")
    if missing:
        missing_text = "\n".join(missing)
        raise ValueError(f"Invalid Deep Agents skill sources (missing SKILL.md):\n{missing_text}")


def _validate_skill_runtime_discovery() -> None:
    """Fail fast if Deep Agents cannot discover skills from configured source."""
    probe_backend = CompositeBackend(
        default=FilesystemBackend(root_dir=SKILLS_ROOT, virtual_mode=True),
        routes={
            "/skills/": FilesystemBackend(root_dir=SKILLS_ROOT, virtual_mode=True),
        },
    )
    discovered = _list_skills(probe_backend, SKILLS_SOURCE)
    if not discovered:
        raise ValueError(
            f"Deep Agents skill discovery returned empty from {SKILLS_SOURCE}. "
            f"Check SKILL.md frontmatter and backend routing under {SKILLS_ROOT}."
        )




def use_env_key_for_qwen = "qwen" in selected_model.lower()
env_qwen_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()  # 从 .env 读取

if use_env_key_for_qwen:
    effective_api_key = env_qwen_key  # 使用 .env 中的 key
else:
    effective_api_key = (user_api_key or "").strip()  # 使用用户输入的 key(
    model_name: str,
    api_key: str,
    request_timeout_s: int = 120,
    graph_name: str = "NTL_Engineer",
    postgres_url: str | None = None,
):
    if postgres_url:
        from langgraph.store.postgres import PostgresStore

        store = PostgresStore.from_conn_string(postgres_url)
    else:
        store = InMemoryStore()

    llm = _build_llm(model_name=model_name, api_key=api_key, request_timeout_s=request_timeout_s)
    # code_assistant_llm = _build_ark_llm(
    #     model_name="doubao-seed-2.0-code",
    #     default_api_key=api_key,
    #     request_timeout_s=request_timeout_s,
    # )
    knowledge_base_llm = ChatOpenAI(
        model_name="qwen-plus",
        api_key=os.getenv("DASHSCOPE_Qwen_plus_KEY"),
        base_url=os.getenv("DASHSCOPE_Qwen_plus_URL"),
    )

    project_memory_path = Path(__file__).resolve().parent / ".ntl-gpt" / "NTL_AGENT_MEMORY.md"

    def _backend_factory(runtime):
        config = getattr(runtime, "config", {}) or {}
        thread_id = storage_manager.get_thread_id_from_config(config) or current_thread_id.get()
        workspace = storage_manager.get_workspace(str(thread_id).strip() or "debug")
        thread_memory_dir = workspace / "memory"
        thread_memory_dir.mkdir(parents=True, exist_ok=True)

        # Seed per-thread runtime memory only on first use (preserve per-thread persistence).
        thread_memory_file = thread_memory_dir / "NTL_AGENT_MEMORY.md"
        if project_memory_path.exists() and not thread_memory_file.exists():
            thread_memory_file.write_text(project_memory_path.read_text(encoding="utf-8"), encoding="utf-8")

        default_backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
        memories_backend = FilesystemBackend(root_dir=thread_memory_dir, virtual_mode=True)
        shared_backend = FilesystemBackend(root_dir=storage_manager.shared_dir, virtual_mode=True)
        skills_backend = FilesystemBackend(root_dir=SKILLS_ROOT, virtual_mode=True)
        return CompositeBackend(
            default=default_backend,
            routes={
                "/memories/": memories_backend,
                "/shared/": shared_backend,
                "/skills/": skills_backend,
            },
        )


    data_searcher_subagent = {
        "name": "Data_Searcher",
        "description": "NTL data retrieval specialist: datasets, AOI, temporal coverage, and source validation.",
        "system_prompt": system_prompt_data_searcher,
        "tools": data_searcher_tools,
        "skills": [SKILLS_SOURCE],
    }

    code_assistant_subagent = {
        "name": "Code_Assistant",
        "description": "NTL code execution specialist: geospatial processing, statistics, and script runtime.",
        "system_prompt": Code_Assistant_system_prompt_text,
        "tools": Code_tools,
        "skills": [SKILLS_SOURCE],
    }

    knowledge_base_subagent = {
        "name": "Knowledge_Base_Searcher",
        "description": "NTL domain knowledge specialist: grounded methods, workflow planning, and task-level JSON intent.",
        "system_prompt": system_prompt_kb_searcher,
        "model": knowledge_base_llm,
        "tools": [NTL_Knowledge_Base],
        "skills": [SKILLS_SOURCE],
    }

    configured_skill_sources = [
        *data_searcher_subagent.get("skills", []),
        *code_assistant_subagent.get("skills", []),
        *knowledge_base_subagent.get("skills", []),
        SKILLS_SOURCE,
    ]
    _validate_skill_sources(configured_skill_sources)
    _validate_skill_runtime_discovery()

    engineer_prompt = getattr(system_prompt_text, "content", str(system_prompt_text))

    NTL_SYSTEM_PROMPT = f"""NTL Engineer: nighttime light analysis supervisor.

Workspace protocol (canonical):
- Read input data from `/inputs/` in the current thread workspace.
- Write generated artifacts to `/outputs/` in the current thread workspace.
- Always resolve paths via `storage_manager.resolve_input_path(...)` and `storage_manager.resolve_output_path(...)`.
- Never use absolute local paths.
- Treat `/shared/...` as read-only source data: read is allowed, write/overwrite is forbidden.
- Runtime note: `/shared/...` is a virtual Deep Agents path and is runtime-mapped to local `base_data/...` during script execution.
- For data discovery, prefer file tools first (for example `glob`) on virtual paths such as `/inputs/*` and `/shared/*` before asking for re-upload or re-download.

Deep Agents virtual-path compatibility (alias mapping):
- `/data/raw/<file>` -> `inputs/<file>`
- `/data/processed/<file>` -> `outputs/<file>`
- `/memories/<file>` -> `memory/<file>`
- `/shared/<file>` -> `base_data/<file>`

Delegation policy:
- Use `Knowledge_Base_Searcher` for methodology/workflow grounding and task-level JSON framing.
- Use `Data_Searcher` for retrieval and metadata validation.
- Use `Code_Assistant` for code validation and execution.
- Keep delegation sequential (one subagent at a time).

{engineer_prompt}
"""

    ntl_agent = create_deep_agent(
        model=llm,
        tools=Engineer_tools,
        subagents=[data_searcher_subagent, code_assistant_subagent, knowledge_base_subagent],
        system_prompt=NTL_SYSTEM_PROMPT,
        skills=[SKILLS_SOURCE],
        memory=["/memories/NTL_AGENT_MEMORY.md"],
        store=store,
        backend=_backend_factory,
        name=graph_name,
        checkpointer=checkpointer, 
    )

    return ntl_agent

