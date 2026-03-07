# CHANGELOG

All notable engineering changes for this repository are documented here.

This changelog is intentionally lightweight:
- Record high-impact changes only (behavior, routing, contracts, safety, compatibility, major UX).
- Batch minor refactors/style-only tweaks.
- Sync release summaries to GitHub Releases when tagging a version.

## [Unreleased]

### Added
- Added reusable spatial-join utility module `tools/spatial_join_utils.py` for:
  - overlap-safe unique point-to-polygon assignment,
  - country-level (ADM0) point assignment,
  - per-country geoBoundaries ADM1/ADM2/ADM3 enrichment,
  - reusable impact summaries with strike-type and source-service breakdowns.
- Added generalized tests `tests/test_spatial_join_utils.py` to validate:
  - deterministic overlap disambiguation,
  - multi-country summary behavior with a non-default strike-type column.
- Added `experiments/official_daily_ntl_fastpath/convert_vnp46a1_to_tif.py` for local VNP46A1 batch conversion (`.h5 -> GeoTIFF`), including auto variable-path compatibility, tile mosaic, EPSG:4326 output, and optional bbox clipping.
- Added `experiments/official_daily_ntl_fastpath/convert_vj102dnb_to_tif.py` for VJ102DNB batch conversion (`.nc -> GeoTIFF`), with date filtering, optional DNB quality-flag masking, mosaic, and optional bbox clipping.
- Added `experiments/official_daily_ntl_fastpath/convert_vj102_vj103_precise_to_tif.py` for paired precise preprocessing (`VJ102DNB + VJ103DNB`) using per-pixel geolocation and daily composites.
- Added `experiments/official_daily_ntl_fastpath/redownload_vj103_from_query.py` to safely re-download VJ103DNB files from LAADS query JSON with token-based auth validation.
- Added `tools/query_vj_dnb_laads_json.py` to generate LAADS-style download JSON lists for `VJ102DNB`/`VJ103DNB` by bbox and date range.
- Added a clean UTF-8 `tools/download_vj_dnb_README.md` with validated Windows/Conda usage examples for tokenized LAADS downloads.
- Added `tools/official_vj_dnb_pipeline_tool.py` with LangChain `StructuredTool` registration (`official_vj_dnb_fullchain_tool`) to orchestrate official-source VJ102/VJ103 query + download + preprocessing in one callable tool.
- Added explicit preprocessing alias tool `convert_vj102_vj103_precise_to_tif_tool` (registered from `tools/official_vj_dnb_preprocess_tool.py`) so the precise converter workflow can be invoked directly by tool name.
- Added workflow/code references under `.ntl-gpt/skills/NTL-workflow-guidance` for the new official VJ full-chain path:
  - workflow task `Q25` in `references/workflows/data_retrieval_preprocessing.json`
  - code index entry in `references/code/code_index.json`
  - executable reference script `references/code/data_retrieval_preprocessing/Q25_official_vj_dnb_fullchain_iran.py`
- Added workflow/code references for preprocess-only and conflict assessment scenarios:
  - workflow task `Q26` in `references/workflows/data_retrieval_preprocessing.json` (preprocess-only, storage-manager paths)
  - workflow task `Q21` in `references/workflows/event_impact_assessment.json` (official VJ conflict assessment chain)
  - code examples:
    - `references/code/data_retrieval_preprocessing/Q26_vj102_vj103_preprocess_storage_paths.py`
    - `references/code/event_impact_assessment/Q21_iran_conflict_official_vj_workflow.py`
- Added workflow/code references for QA-controlled local-topic conflict mapping:
  - workflow task `Q22` in `references/workflows/event_impact_assessment.json`
  - code example `references/code/event_impact_assessment/Q22_iran_vj146a1_tehran_hormuz_workflow.py`
  - documents the boundary between generic tools and case-specific regional workflows.
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
- Extended `tools/GEE_download.py` `NTL_download_tool` to support direct AOI download by `bbox/box` (`minx,miny,maxx,maxy`) in addition to administrative region matching, with centralized bbox parsing/validation and backward-compatible aliases.
- Refactored `tools/fetch_inss_arcgis_strikes.py` into a thin fetch-orchestrator and moved spatial hierarchy logic to reusable helpers.
- Extended strike fetch pipeline outputs with impacted-area products:
  - `inss_arcgis_strikes_spatial_enriched.{geojson,csv}`
  - `inss_arcgis_strikes_country_summary.csv`
  - `inss_arcgis_strikes_country_type_summary.csv`
  - `inss_arcgis_strikes_admin_summary.csv`
  - `inss_arcgis_strikes_admin_type_summary.csv`
  - `inss_arcgis_strikes_spatial_catalog.json`
- Added CLI controls for reusable spatial packaging:
  - `--skip-spatial-summary`
  - `--spatial-levels`
  - `--spatial-cache-dir`
  - `--country-boundary-url`
- Refactored event-report rebuild flow under `base_data/Iran_War/analysis/scripts/` into modular layers:
  - added `iran_event_report_config.py` for event/city/time/scale runtime configuration,
  - added `iran_event_report_pipeline.py` for step-based data prep/render/report orchestration,
  - converted `rebuild_iran_event_report.py` to a thin CLI entrypoint (supports cross-event/cross-country overrides, e.g. Israel),
  - updated shared helpers to support injected city alias mappings and configurable local-map sizing.
- Generalized admin/strike schema handling in pipeline:
  - admin name-field auto-detection for ADM1/ADM2/ADM3,
  - strike date-field auto-detection (`Date/date/event_date/strike_date`),
  - preserved unique point-to-unit assignment for province/city/county accuracy.
- Reworked `tools/download_vj_dnb.py` for robust production download behavior:
  - auto-loads `.env` (including repo-root `.env`) for `EARTHDATA_TOKEN`,
  - applies Windows Schannel workaround (`curl --ssl-no-revoke`) for revocation/TLS failures,
  - hardens file validation (HDF5/netCDF signature + HTML error-page rejection),
  - removes non-ASCII/emoji console output to avoid GBK terminal crashes,
  - preserves resumable behavior by skipping existing valid files.
- Updated `experiments/official_daily_ntl_fastpath/convert_vj102_vj103_precise_to_tif.py`:
  - default radiance scaling is now `1e9` (W to nW) for DNB value magnitude consistency with existing NOAA preprocess pipeline,
  - default output grid now targets `500m` via new `--resolution-m` (with optional `--resolution-deg` override),
  - summary metadata now records raw units, scale attributes, applied radiance scale, and resolved output resolution.
- Registered `official_vj_dnb_fullchain_tool` in `tools/__init__.py` and exposed it to both `data_searcher_tools` and `Engineer_tools`.
- Registered `convert_vj102_vj103_precise_to_tif_tool` in `tools/__init__.py` and exposed it to both `data_searcher_tools` and `Engineer_tools`.
- Extended `tools/official_vj_dnb_pipeline_tool.py` to support:
  - gridded `VJ146A1/VJ146A2` runs in addition to swath `VJ102DNB/VJ103DNB`,
  - explicit `qa_mode` passthrough for gridded runs,
  - formal pipeline-mode routing with mixed-source rejection,
  - gridded manifest/path reporting aligned with the formal tool contract.
- Improved storage-manager path compatibility for official VJ tools:
  - `official_vj_dnb_preprocess_tool` now supports virtual paths (`/data/raw`, `/data/processed`, `/memories`, `/shared`) and workspace-relative reads/writes with output-root safety checks.
  - `official_vj_dnb_fullchain_tool` output root resolution now handles `outputs/...` prefixes without duplication and enforces `outputs`-only write boundaries.
- Disabled legacy `Noaa20_VIIRS_Preprocess` routing for agent tool selection and migrated default preprocessing path to official VJ workflow:
  - removed `noaa20_sdr_preprocess_tool` from active `Engineer_tools` registry in `tools/__init__.py`,
  - retained a deprecated compatibility stub in `tools/NTL_preprocess.py` that returns a migration message,
  - remapped KB aliases and workflow/tool metadata to `convert_vj102_vj103_precise_to_tif_tool`.
- Enhanced NTL workflow router keywords in `.ntl-gpt/skills/NTL-workflow-guidance/references/router_index.json` to include official-source terms (`laads`, `VJ102DNB`, `VJ103DNB`).
- Updated `experiments/official_daily_ntl_fastpath/convert_vnp46a1_to_tif.py` to support date filtering via `--date` and `--start-date/--end-date`, with file-date parsing from `Ayyyyddd` granule names and filter metadata in summary output.
- Documented VJ102DNB geolocation handling in conversion summaries as `approx_granule_bbox_from_global_attrs` and explicit recommendation to pair with VJ103DNB for precise per-pixel geolocation.
- Enhanced `experiments/official_daily_ntl_fastpath/convert_vj102_vj103_precise_to_tif.py` with NOAA20-style QC controls: edge-of-swath mask, solar zenith mask, lunar zenith mask, observation/geolocation quality-flag masks, and per-mask ratio diagnostics in summary metadata.
- Path protocol policy in `tools/NTL_Code_generation.py` switched to sandbox-first:
  - added `NTL_PATH_PROTOCOL_MODE` (`sandbox` default; optional `hybrid`/`resolver`),
  - removed resolver-only preflight pressure in sandbox mode for both `execute_geospatial_script_tool` and `GeoCode_COT_Validation_tool`,
  - kept hard safety boundaries (absolute-path risk, repo source/config writes, forbidden commands, cross-workspace audit),
  - changed `strict_mode` defaults to `False` for `ExecuteScriptInput` and `GeoCodeCOTBlockInput`,
  - added response metadata fields: `path_protocol_mode`, `path_protocol_enforcement`.
- Hardened shared-path runtime behavior for script execution:
  - added runtime virtual-path rewrite in `tools/NTL_Code_generation.py` so string literals like `/shared/...` and `/data/raw/...` are resolved to thread-bound local filesystem paths before execution,
  - added structured execution metadata `runtime_path_rewrite` to report mapping details,
  - added preflight blocking for any detected write target under `/shared/...` (read-only boundary),
  - updated `storage_manager.resolve_deepagents_path` to avoid creating parent directories for `/shared/...` resolution.
- Prompt alignment for path policy:
  - `agents/NTL_Code_Assistant.py` now allows sandbox-relative `inputs/...` and `outputs/...` (resolver remains compatible option),
  - `agents/NTL_Engineer.py` now explicitly states sandbox-first mapping with resolver as optional compatibility path.
- Unified workflow evolution authority model:
  - `NTL_Engineer` is now the single decision + landing role for formal workflow mutations.
  - `Code_Assistant` is restricted to proposal-only outputs via `ntl.workflow.evolution.proposal.v1`.
- Updated prompt/skill contracts to align authority split:
  - `agents/NTL_Engineer.py` now enforces proposal review + completion-gate checks before formal writeback.
  - `agents/NTL_Code_Assistant.py` now explicitly forbids direct workflow/log file edits.
  - `.ntl-gpt/skills/NTL-workflow-guidance/SKILL.md` now documents mandatory role split (Engineer write, Code proposal).
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

### Removed
- Removed legacy runtime auto-learning module `utils/workflow_intent_learning.py`.
- Removed obsolete test file tied to deleted auto-learning module: `tests/test_ntl_workflow_guidance_learning.py`.

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

