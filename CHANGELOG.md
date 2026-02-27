# CHANGELOG

All notable engineering changes for this repository are documented here.

This changelog is intentionally lightweight:
- Record high-impact changes only (behavior, routing, contracts, safety, compatibility, major UX).
- Batch minor refactors/style-only tweaks.
- Sync release summaries to GitHub Releases when tagging a version.

## [Unreleased]

### Added
- Added `agents/NTL_Knowledge_Subagent.py` as a dedicated Deep Agents subagent prompt for KB routing, with strict JSON response contract (`ntl.kb.subagent.response.v1`).
- Added `docs/NTL-GPT版本介绍.md` as the consolidated product/version overview document.
- Added explicit policy in `AGENTS.md`: complex tasks should prioritize `using-superpowers`.
- Added 4 project skills under `.ntl-gpt/skills/` to extract reusable protocol/process logic
  without removing runtime tools:
  - `gee-routing-blueprint-strategy`
  - `code-generation-execution-loop`
  - `geocode-knowledge-recipe`
  - `ntl-kb-task-level-protocol`
- Added a standalone minimal subproject `subprojects/ntl-trio-basic` with:
  - three-agent topology (`NTL_Engineer`, `Data_Searcher`, `Code_Assistant`),
  - isolated `basic_graph_factory.py` using `create_supervisor` + `MemorySaver`,
  - minimal Streamlit entry (`app.py`) and a focused baseline test suite.
  - initial Engineer-side RAG hook (`NTL_Knowledge_Base`) and event-shape-agnostic
    streaming output in the subproject UI.
- Added NTL-VLM benchmark tool suite in `tools/NTL_VLM_benchmark_tools.py`:
  - `ntl_vlm_fetch_event_registry_tool`
  - `ntl_vlm_build_scene_manifest_tool`
  - `ntl_vlm_generate_tasks_tool`
  - `ntl_vlm_generate_jobs_tool`
  - `ntl_vlm_qc_tool`
  - `ntl_vlm_evaluate_tool`
- Registered the new benchmark tools in `Engineer_tools` via `tools/__init__.py` without changing prompt/graph architecture.

### Changed
- Updated `graph_factory.py` to register `Knowledge_Base_Searcher` as a third subagent, wired to the `NTL_Knowledge_Base` tool for supervisor-level delegated KB planning.
- Streamed run UX improvements in `app_ui.py`:
  - running-state hint moved below chat input,
  - reduced analysis panel flicker during active runs.
- Stop behavior in `app_logic.py`:
  - supports immediate frontend unlock while backend stop request continues.
- Deep Agents skill wiring in `graph_factory.py`:
  - added `/skills/` backend route mapped to project `.ntl-gpt/skills`,
  - attached `skills=[...]` for supervisor and per-subagent skill sets (`Data_Searcher`, `Code_Assistant`),
  - kept runtime tools unchanged (skills as protocol/process layer).
- Deep Agents filesystem backend in `graph_factory.py`:
  - switched from implicit default (`StateBackend` virtual files) to explicit per-thread `FilesystemBackend(root_dir=user_data/<thread_id>, virtual_mode=True)`,
  - aligned built-in file tools (`ls/read_file/write_file`) with actual workspace folders (`/inputs`, `/outputs`).
- Deep Agents memory bridge in `graph_factory.py`:
  - added `memory=["/memories/AGENTS.md"]`,
  - routed `/memories/` to per-thread physical directory `user_data/<thread_id>/memory/` via `CompositeBackend`,
  - seeded per-thread memory file from project-root `AGENTS.md` for isolated long-term instruction memory.
  - decoupled from Codex policy file by introducing dedicated `NTL_AGENT_MEMORY.md`,
  - now loads `memory=["/memories/NTL_AGENT_MEMORY.md"]` and seeds from `.ntl-gpt/NTL_AGENT_MEMORY.md`.
- Code execution stack cleanup:
  - removed legacy compatibility path `final_geospatial_code_execution_tool`,
  - standardized execution path to `save_geospatial_script_tool` + `execute_geospatial_script_tool` with `GeoCode_COT_Validation_tool` as failure chain,
  - updated helper scripts/UI stage mapping/runtime assertions to stop referencing the removed tool.

### Fixed
- Reasoning Graph tool-node compaction in `app_ui.py`:
  - consecutive repeated tool calls from the same AI anchor are now merged into one graph node (e.g., `#17-18 ls*2`),
  - prevents noisy duplicate `ls` / `edit_file` nodes when Code_Assistant performs iterative file checks,
  - preserves separation across agent-anchor changes (no cross-agent over-merge).
- Map initialization guardrail in `app_ui.py` to prevent accidental near-global fit bounds from invalid layer extents.
- Data_Searcher direct-download redundancy:
  - for successful lightweight `direct_download` + readable local files, enforce short-circuit and stop extra retrieval calls,
  - explicitly avoid `GEE_dataset_metadata_tool` / `GEE_catalog_discovery_tool` in that success path,
  - allow `GEE_execution_plan.metadata_validation = not_required_local_analysis`.
- Additional redundancy trims in agent prompts:
  - Data_Searcher may skip `geodata_quick_check_tool` after unambiguous successful `NTL_download_tool` and defer read validation to execution stage,
  - allow compact `GEE_execution_plan` for pure local-analysis handoff (minimal required fields only),
  - Code_Assistant path/preflight fix retry now prefers same script overwrite (`overwrite=true`) instead of creating unnecessary v2/v3 files.
- Subagent handoff guard robustness:
  - hardened repair-instruction injection for both string and block-style system messages,
  - exhausted-path response now carries explicit observability metadata
    (`handoff_guard_status`, `handoff_guard_repair_attempts`, `suppressed_invalid_handoff_tool_calls`).
- Subagent handoff guard now suppresses unavailable `transfer_*` / `handoff_*` tool names
  (not only engineer/supervisor-targeted names), preventing recurrent invalid transfer loops
  like `transfer_to_data_searcher` when emitted inside sub-agents.
- Subagent handoff guard repair path now injects explicit available-tool whitelist hints and
  forces `tool_choice=required` during repair retries (when tools exist), reducing repeated
  handoff hallucinations and improving chance of valid tool continuation.
- Exhausted handoff-guard payload now returns `status=needs_engineer_decision`
  (`failure_level=runtime_handoff_guard`) instead of generic auto-return wording, so
  downstream UI/engineer handling is clearer.
- Data_Searcher reasoning rendering fallback:
  - non-contract JSON payloads are now shown as status/reason cards instead of blank
    “Geospatial Data Acquisition” cards with empty fields.

## [2026-02-25]

### Added
- Background run isolation/event consumption path for Streamlit chat workflow.
- Engineer-first script handoff and read-before-execute protocol enhancements.

### Changed
- Sidebar/session controls: queued apply policy for model/activate during running tasks.
- Output/thread isolation and UI path redaction robustness.

### Fixed
- Multiple Chinese text/encoding cleanup rounds in UI and docs.
- Reasoning graph and runtime panel stability regressions.

