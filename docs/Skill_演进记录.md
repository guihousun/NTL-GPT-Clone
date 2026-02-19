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
