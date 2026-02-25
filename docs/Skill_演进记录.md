# Skill 演进记录

> 用于记录项目内 Skills 的持续优化与范式演进（append-only）。
> 版本格式：`vYYYY.MM.DD.N`

## [2026-02-17] v2026.02.17.1 新增 self-evolution 流程

### 版本
- `v2026.02.17.1`

### 目标Skill
- `.agents/skills/skill-self-evolution/SKILL.md`

### 触发证据
- 用户明确要求：当出现更好/更正确/更符合用户习惯的流程范式时，需可持续更新项目 skills，并保留版本记录。

### 变更内容
- 新增项目 skill：`skill-self-evolution`。
- 固化“证据驱动 -> 最小改动 -> 验证 -> 双记录（Skill演进 + Codex变更）”流程。
- 明确 `docs/Skill_演进记录.md` 为技能演进专用记录文件。

### 验证
- 命令：`Get-Content .agents/skills/skill-self-evolution/SKILL.md`
- 结果：文件存在且包含完整 frontmatter + workflow + quality gate。

### 回滚点
- 删除 `.agents/skills/skill-self-evolution/SKILL.md`。
- 从 `docs/Skill_演进记录.md` 和 `docs/Codex_变更记录.md` 追加一条回滚记录（不删除历史条目）。

## [2026-02-17] v2026.02.17.2 self-evolution新增反硬编码与泛化验收门槛

### 版本
- `v2026.02.17.2`

### 目标Skill
- `.agents/skills/skill-self-evolution/SKILL.md`

### 触发证据
- 用户反馈：当前修复存在 case-specific hardcoding 倾向，要求提升 agent 判断能力、准确率与泛化能力，并防止后续回退到同类做法。

### 变更内容
- 在 skill 中新增“能力级改造优先于个案硬编码”规则。
- 增加验收门槛：行为/路由改动必须包含至少 1 个非目标场景变体测试。
- 在 Quality Gate 中新增：
  - 禁止脆弱单案例硬编码（除非明确临时 hotfix）；
  - 必须提供泛化证据。

### 验证
- 命令：`Get-Content .agents/skills/skill-self-evolution/SKILL.md`
- 结果：新增规则与质量门槛字段存在。

### 回滚点
- 回退 `.agents/skills/skill-self-evolution/SKILL.md` 到上一版本内容。
- 在 `docs/Skill_演进记录.md` 与 `docs/Codex_变更记录.md` 追加回滚记录。

## [2026-02-17] v2026.02.17.3 codex-change-log-maintenance新增编码防呆门

### 版本
- `v2026.02.17.3`

### 目标Skill
- `.agents/skills/codex-change-log-maintenance/SKILL.md`

### 触发证据
- 用户反馈 `docs/Codex_变更记录.md` 出现中文乱码，要求修复并防止再次发生。

### 变更内容
- 重写 `codex-change-log-maintenance` 规则，统一路径为 `docs/Codex_变更记录.md`。
- 新增 `Encoding Safety Gate`：
  - UTF-8/BOM 检查命令；
  - mojibake 关键字扫描命令；
  - 命中乱码时的阻断与修复流程。
- 在 `Quality Gate` 中加入编码校验通过作为完成条件。

### 验证
- 命令：`Get-Content .agents/skills/codex-change-log-maintenance/SKILL.md`
- 结果：文件可读，包含 Encoding Safety Gate 与质量门禁条款。

### 回滚点
- 回退 `.agents/skills/codex-change-log-maintenance/SKILL.md` 到上一个版本。
- 在 `docs/Skill_演进记录.md` 与 `docs/Codex_变更记录.md` 追加回滚记录（不删除历史）。

## [2026-02-18] v2026.02.18.1 乱码判定规则补强（UTF-8 parse first）

### 版本
- `v2026.02.18.1`

### 目标Skill
- `.agents/skills/codex-change-log-maintenance/SKILL.md`
- `.agents/skills/skill-self-evolution/SKILL.md`

### 触发证据
- 终端显示与文件真实编码可能不一致，出现“显示乱码但文件本体正常”的误判风险。

### 变更内容
- 新增统一判定原则：
  - 先用 Python UTF-8 解析与结构化解析（JSON/AST）判定文件是否损坏；
  - 不以终端显示异常作为唯一证据；
  - 若终端与 Python 解析冲突，按 Python 解析结果判定。

### 验证
- 命令：`python -c "from pathlib import Path; b=next(Path('docs').glob('Codex_*.md')).read_bytes(); print('bom', b.startswith(b'\\xef\\xbb\\xbf')); b.decode('utf-8'); print('utf8_ok', True)"`
- 结果：`bom False`, `utf8_ok True`

### 回滚点
- 回退上述两个 SKILL 文件新增条款。
- 在 `docs/Skill_演进记录.md` 与 `docs/Codex_变更记录.md` 追加回滚记录（不删除历史）。

## [2026-02-18] v2026.02.18.2 新增 git-result-bus-sync（跨设备结果通知隔离流程）

### 版本
- `v2026.02.18.2`

### 目标Skill
- `.agents/skills/git-result-bus-sync/SKILL.md`

### 触发证据
- 用户希望不打开主电脑也能收到 Codex 答复，并明确要求不影响主电脑上的 Codex 运行进程。

### 变更内容
- 新增 `git-result-bus-sync` skill：
  - 主机端将会话摘要写入独立结果仓库并提交；
  - OpenClaw 侧只拉取并通知，不回写；
  - 远程不可用时先保证本地快照持久化并返回缺失动作。
- 配套脚本：`scripts/publish_session_snapshot_to_result_bus.ps1`。
- 在 `AGENTS.md` 增加 `Result Bus Isolation Policy`，将“隔离仓库、只读消费端”设为项目规则。

### 验证
- 命令：`powershell -ExecutionPolicy Bypass -File scripts/publish_session_snapshot_to_result_bus.ps1 -ResultRepo E:\codex-result-bus -SourceWorkspace E:\NTL-GPT-Clone -SummaryTitle "Smoke Test" -SummaryBody "Skill and script smoke test." -NoPush`
- 结果：返回 `record_path`、`commit`、`push_status=push_skipped`
- 命令：`git -C E:\codex-result-bus log --oneline -n 2`
- 结果：可见新提交记录。

### 回滚点
- 删除 `.agents/skills/git-result-bus-sync/SKILL.md`。
- 删除 `scripts/publish_session_snapshot_to_result_bus.ps1`。
- 从 `AGENTS.md` 移除 `Result Bus Isolation Policy` 段落。
- 在 `docs/Skill_演进记录.md` 与 `docs/Codex_变更记录.md` 追加回滚记录（不删除历史）。


## [2026-02-18] Streamlit ????????????
### ????
- ?????????????????????
  1. ??? `is_running/run_heartbeat_ts/run_started_ts` ?? stale?
  2. ??? UI ?????????????????
  3. ???? `conversation` ????????????
- ???????+?????????????????????????

### ??????
- ?????????? + ?? 1 ???????generalization-first??
- ???? `tests/test_app_runtime_resilience.py` ???????


## [2026-02-18] ???????????
### ????
- ??????????????????????????????????
- ?????????max-duration ????????????????????
- stall-timeout ????? max-duration ???


## [2026-02-18] ?????????Max = ???
### ????
- `Max run(s)` ?????????????????????????
- ??????? `Stall(s)` ??????????
- ?????????? `Interrupt Current Run`?


## [2026-02-18] ???????????
### ????
- ????????????? runtime recovery??????????`getattr + callable`?
- ????? warning ????????? UI ?????


## [2026-02-18] Agent ?????????/?????
### ????
- Supervisor/Engineer ??????????????
- Code_Assistant ???????????????????
- ????? 1 ???????????? Engineer ???

### ????
- ????????????????????
- ??????????????error_type/error_message/failed_script/options??


## [2026-02-19] ????????????? + ?????
### ???
- ????????????????????? Max/Stall ???
- Code_Assistant ??? UI ??????Draft/Validate-Execute/Escalate/Success????????

### ????
- ??????????????????
- ?? Engineer ? Code_Assistant ????????????


## [2026-02-19] Streamlit ??????????????
### ???
- ?? `developing-with-streamlit`?chat-ui + layouts??????????????????
- ??? chat input ???? CSS ? JS ?? bottom ????? rerun ????
- ?????????????????????

## [2026-02-19] LangSmith Trace Diagnosis Workflow Hardening
### Scope
- Improved operational workflow for analyzing latest LangSmith traces and turning findings into generalized runtime safeguards.

### What Was Added
- A repeatable diagnosis pattern was applied:
  1. Pull latest trace summary and ordered tool runs.
  2. Detect repeated same-branch tool loops (save/execute/validation/handoff).
  3. Distinguish design issues vs. non-design runtime failures.
  4. Convert repeated-failure patterns into deterministic escalation policies.
- Added convergence-oriented safeguards in runtime tools and prompts to reduce token/runtime waste:
  - dedupe-save
  - dedupe-execute-after-success
  - repeated-identical-failure escalation
  - single transfer_back rule once completion gate is satisfied

### Outcome
- The workflow now emphasizes capability-level fixes, not case-only patches.
- Added automated tests to prevent regression of convergence behavior.

### Additional Rule (Engineer Routing)
- Added a strict engineer-side redispatch rule:
  - If required input files are missing/unreadable (from quick-check or execution logs), route back to Data_Searcher before Code_Assistant execution.
- This reduces avoidable code-execution retries and improves task success stability.

## [2026-02-19] GEE Routing Policy Update: Small Zonal Stats Fast Path
### Scope
- Updated cross-agent routing policy for `zonal_stats` workloads to improve latency on small jobs.

### Policy Change
- New generalized rule:
  - If `analysis_intent == zonal_stats` and `estimated_image_count <= 6`,
    route to `direct_download` across `daily/monthly/annual`.
- Boundary retained:
  - For `zonal_stats` with `estimated_image_count > 6`, keep `gee_server_side`.

### Coordination Alignment
- Router decision logic and Data_Searcher prompt constraints are now aligned to avoid contradictory behavior.
- Added regression tests including non-target variation (`flood` scenario) to enforce generalization-first behavior.

## [2026-02-19] Runtime Code Curation + Code_RAG Manual Ingestion Workflow
### Scope
- Added a reusable, manual-review-first pipeline for curating runtime scripts before Code_RAG ingestion.

### Workflow
1. Scan `RAG/code_guide/tools_latest_runtime` and pair `.py` with `.meta.json`.
2. Score candidates by execution evidence + code completeness + domain relevance.
3. Group by task category and keep top examples (default: top 1 per category).
4. Sync curated folder `RAG/code_guide/tools_latest_runtime_curated` (remove stale files).
5. Ingest curated scripts into `Code_RAG` as `runtime_template` with hash dedup.

### Why
- Reduces retrieval noise from repeated/debug/test runtime scripts.
- Preserves high-signal exemplars for reusable coding patterns.
- Keeps ingestion manual and auditable, aligned with generalization-first policy.

## [2026-02-19] GeoCode Recipe Retrieval: Static+Runtime Hybrid (Lean Mode)
### Scope
- Upgraded `GeoCode_Knowledge_Recipes_tool` from static-only recipes to a lean hybrid retrieval model.

### What Changed
- Added `include_runtime` switch (default true) in tool input.
- Added curated runtime template loading from `RAG/code_guide/tools_latest_runtime_curated`.
- Kept static recipes as stable baseline; introduced runtime templates as optional high-confidence complements.

### Anti-Bloat Controls
- Runtime code is compacted with max length threshold and truncation notice.
- Full script path is returned for deep inspection (`full_code_path`) instead of dumping very large code blocks.
- Ranking uses only a small runtime bonus to avoid overwhelming strong static matches.

### Outcome
- Better alignment with latest successful project scripts.
- Maintains concise payloads and avoids prompt/tool output inflation.

## [2026-02-19] Engineer-First Retrieval Suppression in Code Assistant
### Scope
- Added a strict Engineer-first control-flow rule in Code Assistant to reduce unnecessary recipe retrieval.

### Policy
- First file-based execution must run on Engineer draft before any recipe lookup.
- Recipe lookup is allowed only for missing-method-details scenarios.
- Limit recipe retrieval to once per task branch unless Engineer explicitly requests another pass.

### Outcome
- Reduces avoidable tool hops and token usage while preserving fallback capability for incomplete drafts.

## [2026-02-19] Handoff Back Control-Flow Noise Handling
### Scope
- Evolved runtime/process handling for supervisor handoff-back control flow.

### Process Update
- Treat `response_metadata.__is_handoff_back` messages as control-flow artifacts, not business events.
- Exclude these synthetic messages from:
  - reasoning graph node construction
  - tool-call frequency metrics
  - transfer-back overcount diagnostics
- Keep explicit agent-issued transfer tools visible.

### Outcome
- Cleaner reasoning graphs.
- Better alignment between LangSmith traces and actual agent behavior.
- Lower false alarms for `transfer_back_to_ntl_engineer` loops.


## [2026-02-21] Process Update: Tavily Domain Filter Robustness
### Process Change
- Added a reusable input-normalization process for Tavily domain filters to avoid tool-schema hard failures.
- Adopted fallback-first behavior for malformed domain filters: continue search without domain restriction and report reason.

### Prompt/Agent Guidance
- Data_Searcher prompt now explicitly enforces:
  - do not pass `include_domains` unless required
  - when needed, use native list format (not stringified list)

### Outcome
- Reduced recurring `include_domains: Input should be a valid list` failures.
- Preserved official-source routing capability while improving runtime stability.

## [2026-02-21] Process Update: KB Progress Streaming Contract
### Process Change
- Added a reusable runtime process for long-latency tools to emit structured custom progress events.
- First adoption target: `NTL_Knowledge_Base` with 4-phase progress model.

### Event Contract
- `event_type`: `kb_progress`
- `phase`: `query_received | knowledge_retrieval | workflow_assembly | structured_output`
- `status`: `running | done | error`
- Additional fields: `tool`, `run_id`, `label`, `meta`

### UI/Runtime Behavior
- `app_logic` now consumes `custom` stream events and updates analysis logs in real time.
- `app_ui` projects these events to both `Reasoning` and `Reasoning Graph` during tool execution.
- Temporary graph progress nodes are hidden after final KB tool output to keep the graph concise.

### Reuse Guidance
- Future slow tools should follow the same custom-event contract pattern rather than ad-hoc hardcoded UI timers.


## [2026-02-21] Process Update: Engineer Pre-Handoff Validation Capability
### Process Change
- Engineer now includes lightweight `geodata_quick_check_tool` for early file/boundary readiness checks before Code_Assistant handoff.
- Deep metadata diagnostics remain Code_Assistant-owned via `geodata_inspector_tool`.

### Outcome
- Reduced protocol mismatch between Engineer prompt constraints and actual available tools.
- Improved handoff quality while keeping tool responsibilities non-bloated.


## [2026-02-21] Process Update: Supervisor Auto-Return + Handoff Packet Guard
### Process Change
- Sub-agents no longer rely on explicit `transfer_back_to_ntl_engineer` tool calls.
- Completion and escalation now use structured return payloads; supervisor regains control automatically.
- Engineer must construct a complete handoff packet before transferring to Code_Assistant.

### Outcome
- Removes invalid transfer-back tool call errors under current graph tool contract.
- Reduces empty/idle Code_Assistant handoffs caused by incomplete Engineer transfer context.


## [2026-02-21] Process Update: Streamlit AI Readability Token Contract
### Process Change
- Added a dedicated readability token contract for AI replies and output preview surfaces in `app_ui.py`.
- Scoped readability CSS to:
  - `.chat-message.bot .message` (AI bubble markdown/code/table/link/text)
  - main content output blocks (`stCodeBlock`, `stDataFrame`, `stTable`)
- Kept style changes localized to avoid sidebar bleed-through.

### Verification Process
- Added a lightweight CSS contract test:
  - `tests/test_ui_ai_readability_css_contract.py`
- Contract test asserts presence of key AI tokens and scoped selectors to prevent accidental future deletion.

### Outcome
- Preserves NTL green visual identity while improving readability and consistency.
- Reduces style regression risk for AI and Outputs rendering without changing business logic.


## [2026-02-21] Process Update: Reasoning CodeBlock Contrast Guard
### Process Change
- Added a separate token set for main-panel code blocks (`--ntl-output-code-*`) rather than reusing AI bubble code colors.
- Applied explicit `pre` surface styling to avoid theme-default gray backgrounds with low-contrast text.

### Outcome
- Prevents "code output looks empty/faded" regressions in Reasoning tab.
- Keeps chat-bubble styling and reasoning-code styling decoupled for safer UI iteration.


## [2026-02-21] Process Update: Mixed-Payload Tail Noise Filter + Field Chip Rendering
### Process Change
- Standardized lightweight field rendering for Data_Searcher key-value chips (`Product Identifier`, `Storage Location`) to avoid visual clash with white cards.
- Introduced reusable tail-noise filtering (`undefined/null/none/nan`) for mixed text+JSON tool outputs.
- Added isolated-scope fallback behavior so rendering functions remain testable when extracted independently.

### Outcome
- Cleaner reasoning output panels with fewer confusing artifacts.
- Better readability without changing backend tool payload contracts.


## [2026-02-21] Process Update: Reasoning AI Empty-Message Skip + CodeAssistant Render Unification
### Process Change
- In Reasoning AI rendering, empty message payloads are filtered before display (`strip()`-empty skip).
- `Code_Assistant` no longer uses forced `st.code(...)` for normal assistant text in reasoning stream.
- Rendering path is unified with general AI text rendering (while keeping `Data_Searcher` structured rendering path).

### Outcome
- Eliminates blank `Code_Assistant` cards in Reasoning view.
- Improves visual consistency across agents without changing tool outputs or routing behavior.


## [2026-02-21] Process Update: Minimal Reasoning Patch After UI Rollback
### Process Change
- For rollback safety, keep sidebar/theme changes out of scope and patch only reasoning runtime behavior.
- Preserve first AI heading even when first payload is empty, while skipping empty body rendering.
- Remove stage micro-caption (`Code_Assistant Stage: ...`) from reasoning tool stream to reduce noise.

### Outcome
- Matches operator expectation: cleaner reasoning panel with stable headings and fewer redundant labels.
- Reduces risk of collateral UI regressions when only behavior-level fixes are requested.

## [2026-02-23] Process Update: Thread-Bound Output Recovery + UI Path Redaction
### Process Change
- Execution runtime now enforces thread-bound storage path resolution to reduce implicit fallback writes into `user_data/debug/outputs`.
- For `execute_geospatial_script_tool`, cross-thread output artifacts are auto-copied back to current thread `outputs` (outputs-only, source preserved).
- UI now renders path information in relative form (workspace-relative / repo-relative) and avoids exposing machine absolute paths.

### Outcome
- Reduced manual recovery operations after cross-thread writes.
- Preserved strict auditability while improving end-user safety/privacy in UI display.
- Keeps backend audit values available while sanitizing frontend rendering.

## [2026-02-23] Process Update: Conditional Boundary Strategy for Lightweight Downloads
### Process Change
- Data_Searcher no longer treats boundary retrieval + quick check as a global pre-step.
- New default strategy for lightweight download intent:
  - call `GEE_dataset_router_tool` then `NTL_download_tool` first
  - use boundary tools and `geodata_quick_check_tool` only when explicitly required, ambiguity/failure fallback is triggered, or execution/statistics path needs confirmed boundary.
- Engineer boundary gate is now execution-path mandatory only; download-only completion can bypass confirmed-boundary requirement when coverage is complete.

### Outcome
- Fewer redundant calls (`get_administrative_division_data` / `geodata_quick_check_tool`) in simple annual/monthly/daily lightweight retrieval requests.
- Maintains strict boundary confirmation where it materially affects execution quality (analysis/statistics/Code_Assistant handoff).
- Improves latency and token efficiency without changing tool interfaces.

## [2026-02-23] Process Update: Three-Agent Threshold Unification + Conditional Router Policy
### Process Change
- Unified lightweight orchestration thresholds across the three-agent stack:
  - daily `<=14`
  - monthly `<=12`
  - annual `<=12`
- Kept `GEE_dataset_router_tool` but switched policy to **conditional required**:
  - required for GEE retrieval/planning tasks
  - not required for pure local-file processing/inspection with explicit existing filenames and no GEE retrieval.
- Removed router-only `zonal_stats <= 6` exception to eliminate dual-threshold behavior and reduce routing ambiguity.

### Outcome
- Reduced policy drift between prompts and runtime router behavior.
- Improved predictability of route selection and lowered unnecessary routing complexity.
- Preserved generalization through non-target regression coverage (earthquake / wildfire / conflict / flood).

## [2026-02-23] Process Update: Manual File Understanding + Per-User Thread History
### Process Change
- Added a manual-only file understanding entry point in sidebar to avoid automatic token spend after upload.
- Standardized supported understanding file set for manual parsing: `pdf`, common images (`png/jpg/jpeg/webp/bmp`), and `tif/tiff`.
- Added user-scoped thread switching strategy:
  - `User` identity controls active history namespace.
  - `History Threads` selector switches thread context and reloads persisted chat records.
- Kept upload behavior passive (upload-only), with explicit operator action required for context injection.

### Outcome
- Multi-user usage on a shared deployment is more stable and auditable.
- Context injection is now intentional and query-relevant (Top-N retrieval at runtime), reducing unnecessary token overhead.
- Preserves existing QA flow while enabling document/image/tif grounding when needed.

## [2026-02-23] Process Update: Image Understanding Uses VLM End-to-End (No Statistical Fallback)
### Process Change
- Manual file understanding pipeline now routes image files (`png/jpg/jpeg/webp/bmp`) to VLM end-to-end analysis using LangChain multimodal message format.
- Removed image-statistics fallback path from image understanding stage to keep semantics model-driven.
- Kept retrieval injection strategy unchanged: understanding text is indexed and only Top-N relevant chunks are injected at question time.

### Outcome
- Better alignment with user requirement for true visual-language understanding.
- Reduced mismatch risk between low-level image stats and task-level semantic interpretation.
- Preserved token-efficiency guardrail via manual trigger + Top-N retrieval injection.

## [2026-02-24] Process Update: Manual File Understanding Defaults Locked + Image Query Retrieval Robustness
### Process Change
- Manual file-understanding control parameters are now fixed by policy (`120/4/6000`) and no longer user-adjustable in UI.
- Retrieval now applies a staged strategy for file-grounded QA:
  - exact filename mention priority,
  - source/stem score boost,
  - image-question fallback to recent injected image context.

### Outcome
- Better response reliability for direct image questions without relaxing manual-trigger constraints.
- Cleaner sidebar UX and lower operator confusion from unnecessary parameter tuning.

## [2026-02-24] Process Update: Auto Image Understanding (Intent-Gated) + Fixed Manual Defaults
### Process Change
- Introduced capability-level runtime gate for image understanding:
  - explicit filename mentions and image-intent language can auto-trigger image context injection.
  - avoids requiring manual button click for obvious image QA.
- Kept resource safety controls:
  - signature-based de-dup to prevent repeated VLM calls for unchanged images.
  - non-blocking fallback if auto-injection fails.
- Simplified manual operator UX by fixing context parameters (`120/4/6000`) and removing tuning sliders.

### Outcome
- Higher success rate for direct image questions (`xxx.png写了什么`) with no extra operator steps.
- Lower accidental overhead versus fully automatic always-on image parsing.
- Cleaner sidebar and more predictable behavior in production usage.

## [2026-02-24] Process Update: Reasoning Visibility for Auto Image Understanding
### Process Change
- Standardized runtime observability for auto image-understanding gate by emitting a custom reasoning event with file and trigger metadata.
- Reasoning panel now surfaces a concise human-readable notice line when auto image understanding is triggered.

### Outcome
- Operators can verify whether image understanding was auto-triggered in the current turn without inspecting raw logs.
- Improves debugging of image QA behavior with negligible UI noise.

## [2026-02-24] Process Update: Reasoning Graph UI Simplified (No Sub-step Toggle)
### Process Change
- Removed optional sub-step visibility control in Reasoning Graph tab to reduce UI clutter and operator confusion.
- Graph remains stable with default high-level node flow rendering.

### Outcome
- Cleaner Reasoning Graph interaction surface.
- Reduced accidental state variance from toggle persistence.

## [2026-02-24] Process Update: Uploaded PDF/Image Understanding via Explicit Engineer Tools
### Process Change
- Replaced implicit runtime intent-gated auto parsing with explicit tool-driven invocation under Engineer orchestration.
- Introduced dedicated modality tools (PDF/Image) plus a combined fallback tool.
- Tool descriptions now encode usage intent, reducing hidden runtime behavior and improving controllability.

### Outcome
- Better predictability and auditability in multi-agent flows.
- Engineer can explicitly decide when to consume uploaded PDF/image context.
- Avoids accidental token spend from hidden auto-injection logic.

## [2026-02-24] Process Update: Uploaded-Understanding Tool Outputs Have Dedicated Reasoning Cards
### Process Change
- Added dedicated render contract for uploaded-file understanding tool outputs instead of generic JSON dump.
- Ensured PDF/Image understanding tool responses are human-readable in Reasoning panel.

### Outcome
- Better operator readability and faster debugging when Engineer invokes uploaded-file understanding tools.
- Keeps fallback raw JSON available for audit without sacrificing primary UX clarity.

## [2026-02-24] Process Update: Runtime Import Guard for Hotfixes
### Process Change
- When trimming/refactoring intent-gate code, ensure shared utility imports (e.g., `re`) used by downstream helpers are preserved.

### Outcome
- Prevents latent NameError in long-path execution functions unrelated to the edited block.


## [2026-02-24] Process Update: Uploaded Understanding Status Is Split by Capability Outcome
### Process Change
- Standardized uploaded-file-understanding status semantics to separate retrieval miss from ingestion success:
  - `success` (snippet hit),
  - `context_injected_no_match` (ingested but no hit for current phrasing),
  - `no_relevant_snippet` (no usable context hit).
- Reasoning card now explains the `context_injected_no_match` state explicitly.

### Outcome
- Reduces false-negative interpretation in UI when extraction actually succeeded.
- Improves operator trust and debugging efficiency without changing agent/tool interfaces.


## [2026-02-24] Process Update: Filename Matching Uses Normalized Query-Source Alignment
### Process Change
- For uploaded-file understanding and retrieval, filename detection now uses a normalized strategy (whitespace-insensitive) in addition to regex extraction.
- This prevents false misses for long filenames with brackets/spaces and mixed CJK/English forms.

### Outcome
- Better stability for real user phrasing variants without introducing case-specific hardcoding.
- Reduces `context_injected_no_match` false positives caused by filename formatting differences.


## [2026-02-24] Process Update: Streamlit Chat Attachments as Primary Inline Upload Path
### Process Change
- Adopted `st.chat_input` attachment mode (`accept_file`) for inline screenshot/document upload in chat workflows.
- Standardized attachment persistence to current thread workspace `inputs/` with collision-safe filenames.

### Outcome
- Closer UX to GPT-style chat upload flow (single input surface).
- Keeps existing sidebar uploader while adding a direct chat-path for screenshot-driven tasks.


## [2026-02-24] Process Update: Chat Input Uses Multimodal Component for Ctrl+V Upload UX
### Process Change
- Replaced single-mode chat input with multimodal chat component when available, enabling GPT-style paste/upload flow at input level.
- Kept graceful fallback to native Streamlit chat input to avoid hard dependency failure.

### Outcome
- Screenshot paste (`Ctrl+V`) and inline file sending are now unified with text entry.
- Files continue to land in per-thread `inputs/`, preserving existing downstream tool contracts.


## [2026-02-25] Process Update: UI Runtime Paths Hardened Against Non-Root Startup
### Process Change
- Standardized `app_ui.py` runtime resource discovery to project-root absolute paths (`APP_ROOT + _project_path`) instead of cwd-relative lookups.
- Applied to three runtime-critical resources:
  - sidebar NTL availability scan script path,
  - background image asset path,
  - sidebar test case file path list.
- Added dedicated regression tests for both target and non-target startup contexts:
  - non-repo cwd startup,
  - repo-root startup.

### Outcome
- ECS/service startup is robust even when process cwd is not repository root.
- Eliminates false "script/file not found" errors for NTL Data Availability and Test Cases modules.
- Prevents background loss due to relative asset resolution drift.


## [2026-02-25] Process Update: Code_Assistant Reasoning Render Uses Content Shape
### Process Change
- Replaced Code_Assistant message rendering from fixed Python code block to shape-based rendering:
  - JSON object/array -> structured `st.json`
  - mixed text + JSON -> text then JSON
  - non-JSON -> Python code block fallback
- Parsing relies on existing `_extract_json` and does not inspect schema-specific fields.

### Outcome
- Improves readability for successful Code_Assistant JSON outputs without coupling UI to internal keys.
- Maintains backward compatibility for non-JSON code responses.
- Preserves Data_Searcher / NTL_Engineer and tool-output rendering paths.
