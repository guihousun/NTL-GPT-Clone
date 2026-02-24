# Codex 变更记录

> 说明：记录 Codex 在本仓库的已落地改动，用于审计与回溯。  
> 日期格式：`YYYY-MM-DD`  
> 编码要求：`UTF-8`（无 BOM）。

---

## 记录规范
- 一次可独立验证的改动对应一个版本：`vYYYY.MM.DD.N`。
- 同日多次改动按 `N` 递增，append-only（只追加不覆盖）。
- 每条记录至少包含：`目标`、`修改文件`、`关键变更`、`验证结果`、`复现命令`。

---

## 快速索引

### RAG / Knowledge Base
- `v2026.02.17.1` Literature_RAG 入库能力建设
- `v2026.02.17.7` Literature 检索与复现导向优化
- `v2026.02.17.8` Knowledge Searcher 切换 `qwen3.5-plus`
- `v2026.02.17.11`（A）KB workflow 降噪与 Literature 收敛
- `v2026.02.17.11`（B）RAG 无结果兜底与 Qwen 步骤格式兼容
- `v2026.02.17.12` Workflow 去硬编码 + LandScan 对齐 + KB 回写 Skill
- `v2026.02.17.13` Solution_RAG 重建落库 + 命令参数修正
- `v2026.02.17.15` 地震场景路由修正（fallback 多步化 + GEE server-side）
- `v2026.02.17.16` 路由泛化改造（地震特判 -> 通用事件分析）
- `v2026.02.17.18` KB 意图判别升级（LLM优先）+ 统一响应合同 + UI 对齐
- `v2026.02.18.1` 优先保留 Solution_RAG 嵌套 workflow 细节（避免误回退为通用模板）
- `v2026.02.18.2` Q20 地震 workflow 扩展为 25/50/100km 多尺度并重建 Solution_RAG
- `v2026.02.18.4` 首夜过境时序规则固化（RAG + System Prompt + 泛化回归）
- `v2026.02.18.5` TGRS 引文对齐 Literature_RAG + 参考文献段降噪入库
- `v2026.02.18.6` 余柏蒗 2025 夜光文献补充（文献卡）+ Literature 文本入库能力

### Data Searcher
- `v2026.02.17.2` 路由稳定性修复（非 RAG）
- `v2026.02.17.3` 官方 GDP 数据源与多年份统计增强（非 RAG）

### UI
- `v2026.02.17.6` 超时错误显式渲染修复
- `v2026.02.17.10` 默认模型与 Key 输入策略优化

### Experiments
- `v2026.02.18.8` 官方 Daily NTL 快速实验流（CMR/边界/对照/报告）
- `v2026.02.18.9` NRT 优先链路 + 实时可用性监控网页 + GIBS 全球渲染
- `v2026.02.18.10` Web monitor layer fallback + favicon (Layer not empty when API fails)
- `v2026.02.18.11` Web monitor layer load status reminder (success/failure/partial)
- `v2026.02.18.12` Region snapshot mode (China/Shanghai/custom bbox) for image loading fallback
- `v2026.02.18.13` UX flow upgrade: explicit query/apply buttons + non-idle layer status

### Skills / 流程
- `v2026.02.17.4` LangSmith 调试 Skill 加固（仓库外）
- `v2026.02.17.9` codex-change-log-maintenance Skill 固化
- `v2026.02.17.14` 新增 skill-self-evolution 与专用演进记录
- `v2026.02.17.17` 变更记录乱码修复与编码防呆落地
- `v2026.02.18.7` Git 结果总线流程落地（独立仓库快照 + skill + 规则）

---

## [2026-02-17] v2026.02.17.1 Literature_RAG 入库能力建设
### 目标
- 新增 `literature` profile，支持文献库稳定重建与结构化 metadata。
### 修改文件
- `agents/NTL_Knowledge_Base_manager.py`
- `tests/test_literature_rag_ingestion_manager.py`
- `RAG/Literature_RAG/rebuild_report.json`
### 关键变更
- 文献入库流程、哈希去重、metadata 字段补齐。
### 验证结果
- `6 passed`；`final_collection_count=484`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile literature --literature-dir "RAG/literature base" --persist-dir RAG/Literature_RAG --collection-name Literature_RAG --reset --report-path RAG/Literature_RAG/rebuild_report.json
```

## [2026-02-17] v2026.02.17.2 Data_Searcher 路由稳定性修复（非 RAG）
### 目标
- 修复重复下载、越权分析、错误 handoff。
### 修改文件
- `tools/GEE_download.py`
- `agents/NTL_Data_Searcher.py`
- `agents/NTL_Engineer.py`
### 关键变更
- 下载输出名补 `.tif`；明确 Data_Searcher 仅做数据准备。
### 验证结果
- `9 passed`。
### 复现命令
```bash
conda run -n NTL-GPT python -m pytest -q tests/test_ntl_download_filename_suffix.py tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py
```

## [2026-02-17] v2026.02.17.3 官方 GDP 数据源与多年份统计增强（非 RAG）
### 目标
- 官方源优先，提升 GDP 与多年份统计能力。
### 修改文件
- `tools/China_official_stats.py`
- `tools/NTL_raster_stats.py`
- `agents/NTL_Data_Searcher.py`
### 关键变更
- 新增 `China_Official_GDP_tool`；统计工具支持多文件批处理。
### 验证结果
- `10 passed`。
### 复现命令
```bash
conda run -n NTL-GPT python -m pytest -q tests/test_china_official_stats_tool.py tests/test_ntl_raster_stats_batch_input.py
```

## [2026-02-17] v2026.02.17.4 LangSmith 调试 Skill 加固（仓库外）
### 目标
- 降低调试配置错误和 API 参数错误。
### 修改文件
- `C:\Users\HONOR\.codex\skills\langsmith-fetch\SKILL.md`（仓库外）
### 关键变更
- 增加前置校验、`limit<=100` 约束、固定排查顺序。
### 验证结果
- 技能文件可读，规则完整。
### 复现命令
```bash
Get-Content C:\Users\HONOR\.codex\skills\langsmith-fetch\SKILL.md
```

## [2026-02-17] v2026.02.17.5 变更记录索引增强
### 目标
- 支持按模块快速定位版本。
### 修改文件
- `docs/Codex_变更记录.md`
### 关键变更
- 新增“快速索引”区块。
### 验证结果
- 文档结构检查通过。
### 复现命令
```bash
rg -n "快速索引|v2026.02.17" docs/Codex_变更记录.md
```

## [2026-02-17] v2026.02.17.6 UI 超时错误显式渲染修复
### 目标
- 解决“看似成功但实际超时”的可见性问题。
### 修改文件
- `app_logic.py`
### 关键变更
- 运行时异常写入聊天区，不只显示在临时面板。
### 验证结果
- `py_compile app_logic.py` 通过。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m py_compile app_logic.py
```

## [2026-02-17] v2026.02.17.7 Literature 检索与复现导向优化
### 目标
- 提升论文方法复现场景召回质量，降低噪声。
### 修改文件
- `tools/NTL_Knowledge_Base.py`
- `tools/NTL_Knowledge_Base_Searcher.py`
- `agents/NTL_Knowledge_Base_manager.py`
### 关键变更
- Literature 检索参数调整；新增方法复现意图识别；低价值 chunk 过滤。
### 验证结果
- `10 passed`；`final_collection_count=444`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_kb_retriever_config.py tests/test_literature_query_routing_policy.py
```

## [2026-02-17] v2026.02.17.8 Knowledge Searcher 切换 `qwen3.5-plus`
### 目标
- 让 `NTL_Knowledge_Base_Searcher` 使用 `qwen3.5-plus`。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tests/test_literature_searcher_model_provider.py`
### 关键变更
- 默认 provider 切换到 DashScope 兼容端点，补充 key 校验。
### 验证结果
- `3 passed`；语法检查通过。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_searcher_model_provider.py tests/test_literature_query_routing_policy.py
```

## [2026-02-17] v2026.02.17.9 codex-change-log-maintenance Skill 固化
### 目标
- 将变更记录流程沉淀为项目 skill。
### 修改文件
- `skills/codex-change-log-maintenance/SKILL.md`（历史路径）
- `docs/Codex_变更记录.md`
### 关键变更
- 固化 append-only、字段完整性、可复现命令等规范。
### 验证结果
- skill 可读、结构完整。
### 复现命令
```bash
rg -n "codex-change-log-maintenance|v2026.02.17.9" docs/Codex_变更记录.md
```

## [2026-02-17] v2026.02.17.10 默认模型与 Key 输入策略优化
### 目标
- `qwen3.5-plus` 默认可用并自动读取 DashScope Key。
### 修改文件
- `app_ui.py`
### 关键变更
- `qwen*` 不再要求手工输入 key；缺 key 时明确报错。
### 验证结果
- `py_compile app_ui.py` 通过。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py
```

## [2026-02-17] v2026.02.17.11（A）KB workflow 降噪与 Literature 收敛
### 目标
- 减少 `workflow/auto` 模式冗余上下文，提升 JSON 稳定输出。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tools/NTL_Knowledge_Base.py`
### 关键变更
- 默认优先 `Solution+Code`；复现实验意图才优先 Literature；新增 `force_json` 兜底。
### 验证结果
- 定向测试 `4 passed`。
### 复现命令
```bash
conda run -n NTL-GPT pytest tests/test_literature_kb_retriever_config.py tests/test_literature_query_routing_policy.py tests/test_kb_workflow_force_json.py -q
```

## [2026-02-17] v2026.02.17.11（B）RAG 无结果兜底与 Qwen 步骤格式兼容修复
### 目标
- 修复 `no_valid_tool` 无结果问题并兼容 Qwen 步骤 schema。
### 修改文件
- `utils/ntl_kb_aliases.py`
- `tools/NTL_Knowledge_Base_Searcher.py`
### 关键变更
- 兼容 `tool_name/tool -> name`、`input_parameters/parameters -> input` 等别名。
### 验证结果
- 测试 `14 passed`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_validation.py tests/test_literature_query_routing_policy.py
```

## [2026-02-17] v2026.02.17.12 Workflow 去硬编码 + LandScan 对齐 + KB 回写 Skill
### 目标
- 清理不可复现的固定结论，保证 workflow 与工具语义一致。
### 修改文件
- `RAG/guidence_json/Workflow.json`
- `RAG/guidence_json/tools.json`
- `.agents/skills/kb-regression-sync/SKILL.md`
### 关键变更
- Q19/Q20 去固定结果；LandScan `out_name` 改目录语义；新增 KB 回写流程 skill。
### 验证结果
- `10 passed`；`json_ok`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_workflow_knowledge_quality.py tests/test_kb_workflow_validation.py tests/test_literature_query_routing_policy.py
```

## [2026-02-17] v2026.02.17.13 Solution_RAG 重建落库 + 命令参数修正
### 目标
- 让 Workflow/tools 更新在 `Solution_RAG` 即时生效。
### 修改文件
- `RAG/Solution_RAG/rebuild_report.json`
- `.agents/skills/kb-regression-sync/SKILL.md`
### 关键变更
- 执行 `--profile solution --reset`；参数 `--guidence-dir` 改为 `--json-dir`。
### 验证结果
- `final_collection_count=57`，`workflow_task=30`，`tool_spec=27`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile solution --json-dir RAG/guidence_json --persist-dir RAG/Solution_RAG --collection-name Solution_RAG --reset --report-path RAG/Solution_RAG/rebuild_report.json
```

## [2026-02-17] v2026.02.17.14 新增 skill-self-evolution（含专用版本记录）
### 目标
- 建立技能自我进化与可追溯记录机制。
### 修改文件
- `.agents/skills/skill-self-evolution/SKILL.md`
- `docs/Skill_演进记录.md`
### 关键变更
- 固化“证据驱动 -> 最小改动 -> 验证 -> 双记录”。
### 验证结果
- 文档存在且结构完整。
### 复现命令
```bash
Get-Content .agents/skills/skill-self-evolution/SKILL.md
Get-Content docs/Skill_演进记录.md
```

## [2026-02-17] v2026.02.17.15 地震场景路由修正（KB fallback 多步化 + GEE server-side）
### 目标
- 修复地震查询退化与错误下载链路。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tools/GEE_specialist_toolkit.py`
- `agents/NTL_Data_Searcher.py`
### 关键变更
- 新增地震 + GEE 分析识别与多步 fallback；分析型查询强制 server-side。
### 验证结果
- 测试 `22 passed`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_force_json.py tests/test_gee_router_execution_mode.py tests/test_data_searcher_prompt_constraints.py
```

## [2026-02-17] v2026.02.17.16 路由泛化改造（地震特判 -> 通用事件分析）
### 目标
- 从单场景硬编码升级为可泛化的事件分析路由。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tests/test_kb_workflow_force_json.py`
- `tests/test_literature_query_routing_policy.py`
- `.agents/skills/skill-self-evolution/SKILL.md`
- `AGENTS.md`
### 关键变更
- 通用查询信号层 + 评分式工具选择 + 通用 fallback。
### 验证结果
- 测试 `23 passed`。
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_force_json.py tests/test_literature_query_routing_policy.py tests/test_gee_router_execution_mode.py
```

## [2026-02-17] v2026.02.17.17 变更记录乱码修复与编码防呆落地
### 目标
- 修复变更记录乱码并防止复发。
### 修改文件
- `docs/Codex_变更记录.md`
- `.agents/skills/codex-change-log-maintenance/SKILL.md`
- `docs/Skill_演进记录.md`
- `AGENTS.md`
### 关键变更
- 重写本文件并统一 UTF-8（无 BOM）。
- 在 skill 与 AGENTS 中增加编码校验流程。
### 验证结果
- 文件可正常显示中文，编码检查命令可执行。
### 复现命令
```bash
python - << 'PY'
from pathlib import Path
p = next(Path('docs').glob('Codex_*.md'))
b = p.read_bytes()
print('bom', b.startswith(b'\\xef\\xbb\\xbf'))
b.decode('utf-8')
print('utf8_ok', True)
PY
```

## [2026-02-17] v2026.02.17.18 KB 意图判别升级（LLM优先）+ 统一响应合同 + UI 对齐
### 目标
- 将 `NTL_Knowledge_Base_Searcher` 从关键词硬编码主导升级为“LLM意图判别主导 + 最小安全兜底”。
- 统一 KB 最终回复 JSON 框架，并让 UI 按统一合同渲染。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `app_ui.py`
- `tests/test_kb_workflow_force_json.py`
- `tests/test_literature_query_routing_policy.py`
- `tests/test_kb_payload_normalization.py`
### 关键变更
- Searcher 侧：
  - 新增意图判别链：`_classify_query_intent_with_fallback`（LLM优先，失败回退规则）。
  - 新增意图驱动工具选择：`_infer_tool_from_intent`，并改造 `_infer_tool_from_query`。
  - 新增统一响应合同：`_build_kb_response_contract`，输出 `schema=ntl.kb.response.v2`。
  - `_validate_and_normalize_workflow_output` 改为始终返回统一合同 JSON，并保留兼容字段（`task_id/task_name/steps/...`）。
- UI 侧：
  - `_normalize_kb_payload` 增加 `ntl.kb.response.v2` 解析与扁平化兼容。
  - `render_kb_output` 统一展示 `mode/schema`，并支持 `supplementary_text`。
- 测试侧：
  - 强化 `force_json` 测试：校验 `schema`、`workflow` 与兼容字段同时存在。
  - 强化路由泛化测试：冲突/灾害官方源场景优先 `tavily_search`。
  - 新增 UI 归一化测试：验证统一合同在渲染前可正确归一化。
### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_validation.py tests/test_literature_searcher_model_provider.py tests/test_kb_payload_normalization.py tests/test_kb_render_fallback_contract.py tests/test_kb_workflow_force_json.py tests/test_literature_query_routing_policy.py`
- 结果：`16 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py app_ui.py`
- 结果：通过
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q \
  tests/test_kb_workflow_validation.py \
  tests/test_literature_searcher_model_provider.py \
  tests/test_kb_payload_normalization.py \
  tests/test_kb_render_fallback_contract.py \
  tests/test_kb_workflow_force_json.py \
  tests/test_literature_query_routing_policy.py

conda run --no-capture-output -n NTL-GPT python -m py_compile \
  tools/NTL_Knowledge_Base_Searcher.py \
  app_ui.py
```

## [2026-02-18] v2026.02.18.1 优先保留 Solution_RAG 嵌套 workflow 细节（避免误回退为通用模板）
### 目标
- 让 `NTL_Knowledge_Base_Searcher` 在命中 `NTL_Solution_Knowledge` 的嵌套 `workflow` JSON 时，尽量保留模板细节而不是回退成通用 `generated_*` 模板。
### 修改文件
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tests/test_kb_workflow_force_json.py`
- `docs/Codex_变更记录.md`
### 关键变更
- 修复 `force_json` 分支中的细节丢失：
  - 当返回为 `{"workflow": {"steps": ...}}` 且顶层无 `steps` 时，先“提升/展开”嵌套 workflow 字段，再进行归一化校验；
  - 仅在确实没有可用细节时才进入通用 fallback。
- 增加“细节保留”策略：
  - 对含 geospatial 细节步骤的 workflow，在存在部分无效 builtin 工具名时优先局部修补/剔除无效步骤，避免整段降级。
- 强化提示词约束：
  - 明确要求优先复用 `NTL_Solution_Knowledge` 检索到的详细 workflow（task_id、窗口、公式、输出路径）。
- 新增回归测试：
  - `test_workflow_validation_preserves_nested_solution_workflow_details`，验证 Q20 风格嵌套 workflow 不再被误替换为 `generated_dict_fallback_workflow`。
### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_force_json.py tests/test_literature_query_routing_policy.py tests/test_kb_payload_normalization.py tests/test_kb_render_fallback_contract.py tests/test_kb_workflow_validation.py tests/test_literature_searcher_model_provider.py`
- 结果：`17 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py app_ui.py tests/test_kb_workflow_force_json.py`
- 结果：通过
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q \
  tests/test_kb_workflow_force_json.py \
  tests/test_literature_query_routing_policy.py \
  tests/test_kb_payload_normalization.py \
  tests/test_kb_render_fallback_contract.py \
  tests/test_kb_workflow_validation.py \
  tests/test_literature_searcher_model_provider.py

conda run --no-capture-output -n NTL-GPT python -m py_compile \
  tools/NTL_Knowledge_Base_Searcher.py \
  app_ui.py \
  tests/test_kb_workflow_force_json.py
```

## [2026-02-18] v2026.02.18.2 Q20 地震 workflow 扩展为 25/50/100km 多尺度并重建 Solution_RAG
### 目标
- 将 `Q20` 从单一 `25km` 缓冲区扩展为 `25/50/100km` 多尺度分析，并让该模板在 `Solution_RAG` 检索中可直接输出更多细节。
### 修改文件
- `RAG/guidence_json/Workflow.json`
- `RAG/Solution_RAG/rebuild_report.json`
- `docs/Codex_变更记录.md`
### 关键变更
- 更新 `Q20` 的描述与步骤：
  - 事件区缓冲由 `25km` 扩展为 `25km + 50km + 100km`；
  - `geospatial_code_step_2` 改为对每个缓冲尺度分别计算三阶段 ANTL；
  - 输出 CSV 字段新增 `buffer_km`，支持多尺度分组结果；
  - `geospatial_code_step_3` 增加 per-buffer 指标与 cross-buffer 对比要求。
- 使用 `solution` profile 执行全量重建，确保新模板立即进入检索库。
### 验证结果
- 重建命令执行成功，`RAG/Solution_RAG/rebuild_report.json` 关键结果：
  - `final_collection_count=57`
  - `records_ingested=57`
  - `errors=[]`
### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile solution --json-dir RAG/guidence_json --persist-dir RAG/Solution_RAG --collection-name Solution_RAG --reset --report-path RAG/Solution_RAG/rebuild_report.json
```

## [2026-02-18] v2026.02.18.3 Encoding decision rule: Python UTF-8 parse first

### 目标
- 固化“先用 Python UTF-8 解析判断，再决定是否为乱码”的统一规则，避免终端显示误报。

### 修改文件
- `AGENTS.md`
- `.agents/skills/codex-change-log-maintenance/SKILL.md`
- `.agents/skills/skill-self-evolution/SKILL.md`

### 关键变更
- 在项目级规则中新增：
  - 乱码判定必须优先依据 Python UTF-8 解析结果；
  - 终端 code page / 字体导致的显示异常不能直接判定文件损坏；
  - 发现疑似乱码时先跑 UTF-8 解析检查命令。
- 在两个技能文档中同步加入同样判定规则，确保后续 agent 执行一致。

### 验证结果
- 命令：`python -c "from pathlib import Path; b=next(Path('docs').glob('Codex_*.md')).read_bytes(); print('bom', b.startswith(b'\\xef\\xbb\\xbf')); b.decode('utf-8'); print('utf8_ok', True)"`
- 结果：`bom False`, `utf8_ok True`
- 命令：`python -c "from pathlib import Path; bad=[0x9359,0x7481,0x951b,0x9286,0x9225,0x20ac]; t=next(Path('docs').glob('Codex_*.md')).read_text(encoding='utf-8'); print('mojibake_hits',[(hex(cp),chr(cp)) for cp in bad if chr(cp) in t])"`
- 结果：`mojibake_hits []`

### 复现命令
```bash
python -c "from pathlib import Path; b=next(Path('docs').glob('Codex_*.md')).read_bytes(); print('bom', b.startswith(b'\\xef\\xbb\\xbf')); b.decode('utf-8'); print('utf8_ok', True)"
python -c "from pathlib import Path; bad=[0x9359,0x7481,0x951b,0x9286,0x9225,0x20ac]; t=next(Path('docs').glob('Codex_*.md')).read_text(encoding='utf-8'); print('mojibake_hits',[(hex(cp),chr(cp)) for cp in bad if chr(cp) in t])"
```

## [2026-02-18] v2026.02.18.4 首夜过境时序规则固化（RAG + System Prompt + 泛化回归）
### 目标
- 将“daily VNP46A2 首夜应按本地过境时刻判定（可能是 D+1）”固化到知识库模板与系统提示词，避免把事件发生日误当作首夜灾后影像。

### 修改文件
- `RAG/guidence_json/Workflow.json`
- `tools/NTL_Knowledge_Base_Searcher.py`
- `agents/NTL_Data_Searcher.py`
- `agents/NTL_Engineer.py`
- `tests/test_kb_workflow_force_json.py`
- `tests/test_data_searcher_prompt_constraints.py`
- `tests/test_ntl_engineer_prompt_constraints.py`
- `tests/test_solution_workflow_q20_first_night_rule.py`
- `RAG/Solution_RAG/rebuild_report.json`
- `docs/Codex_变更记录.md`

### 关键变更
- RAG（Q20）新增首夜判定规则：
  - 明确 first night 是“first post-event overpass night”，不是默认事件日；
  - 引入本地时区 + 过境时刻（约 01:30 local）判定；
  - 若事件发生在 day D 该次夜间过境之后，则首夜取 D+1。
- KB Searcher system prompt 与 fallback workflow 同步规则：
  - fallback geospatial step 不再写“event-night (or event-day)”；
  - 强制写入“按本地过境时刻判定首夜，必要时 D+1”并要求输出记录该判定。
- Data_Searcher / NTL_Engineer system prompt 加入同一硬规则，确保编排和检索一致。
- 增加泛化回归：
  - 除 wildfire 外新增 conflict 场景测试，验证该规则不是地震硬编码。

### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_workflow_force_json.py tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py tests/test_solution_workflow_q20_first_night_rule.py`
- 结果：`15 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile solution --json-dir RAG/guidence_json --persist-dir RAG/Solution_RAG --collection-name Solution_RAG --reset --report-path RAG/Solution_RAG/rebuild_report.json`
- 结果：`records_ingested=57`, `final_collection_count=57`, `errors=[]`
- 抽样查询（Myanmar 地震）检查：
  - 返回文本包含 `first post-event overpass night`
  - 返回文本包含 `day D+1` 与 `not day D`

### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q \
  tests/test_kb_workflow_force_json.py \
  tests/test_data_searcher_prompt_constraints.py \
  tests/test_ntl_engineer_prompt_constraints.py \
  tests/test_solution_workflow_q20_first_night_rule.py

conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py \
  --profile solution \
  --json-dir RAG/guidence_json \
  --persist-dir RAG/Solution_RAG \
  --collection-name Solution_RAG \
  --reset \
  --report-path RAG/Solution_RAG/rebuild_report.json
```

## [2026-02-18] v2026.02.18.5 TGRS 引文对齐 Literature_RAG + 参考文献段降噪入库
### 目标
- 核对 `docs/TGRS-Manuscrip.docx` 中夜光应用文献在 `Literature_RAG` 的覆盖情况。
- 对缺失文献执行可用 DOI 自动补充。
- 在 literature 入库阶段剔除 `References/参考文献` 后续页，降低检索噪声。

### 修改文件
- `agents/NTL_Knowledge_Base_manager.py`
- `tests/test_literature_rag_ingestion_manager.py`
- `RAG/literature base/补充_TGRS_refs_2026-02-18/[21] 2024 - Increases in Night Lights Intensity Reveal Extreme Events A Case of Study on the Ongoing Conflict in Ukraine.pdf`
- `RAG/literature base/补充_TGRS_refs_2026-02-18/[3] 2021 - Nighttime light remote sensing and urban studies Data methods applications and prospects.pdf`
- `RAG/Literature_RAG/rebuild_report.json`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增 `_strip_references_tail`：
  - 识别 `References/Bibliography/参考文献/致谢` 标题；
  - 当页在标题处截断；
  - 后续页直接跳过，避免参考文献块写入向量库。
- 新增回归测试 `test_literature_ingestion_stops_after_references_heading`，验证 references 后文本不入库。
- 从 `TGRS-Manuscrip.docx` 自动抽取引用并对照 `Literature_RAG`：
  - 夜光应用焦点引用：`28`
  - 已覆盖：`18`
  - 仍缺失：`10`（多数为出版社访问限制导致无法自动获取 PDF）
- 可自动补充并已入库的新增 PDF：`2`（见上方路径）。

### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_rag_ingestion_manager.py`
- 结果：`3 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile literature --literature-dir "RAG/literature base" --persist-dir RAG/Literature_RAG --collection-name Literature_RAG --reset --report-path RAG/Literature_RAG/rebuild_report.json`
- 结果：`records_ingested=400`, `final_collection_count=400`, `errors=[]`

### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_rag_ingestion_manager.py

conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py \
  --profile literature \
  --literature-dir "RAG/literature base" \
  --persist-dir RAG/Literature_RAG \
  --collection-name Literature_RAG \
  --reset \
  --report-path RAG/Literature_RAG/rebuild_report.json
```

## [2026-02-18] v2026.02.18.7 Git 结果总线流程落地（独立仓库快照 + skill + 规则）
### 目标
- 验证并落地“把 Codex 会话结果异步同步到 Git 私有仓库”的流程，且不影响主项目运行进程。

### 修改文件
- `.agents/skills/git-result-bus-sync/SKILL.md`
- `scripts/publish_session_snapshot_to_result_bus.ps1`
- `AGENTS.md`
- `docs/Skill_演进记录.md`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增 skill：`git-result-bus-sync`，定义“独立结果仓库 + 发布机写入 + 消费机只拉取通知”的隔离范式。
- 新增脚本：`publish_session_snapshot_to_result_bus.ps1`，支持：
  - 初始化结果仓库；
  - 生成会话快照文件；
  - 本地 commit；
  - 可选 push（有远程则推送，无远程给出失败原因）。
- 新增项目规则（`AGENTS.md`）：
  - 结果同步必须在独立仓库执行；
  - 禁止在主工程目录做同步 push/pull；
  - OpenClaw 侧只 pull + notify，不回写。
- 实测：
  - 在 `E:\codex-result-bus` 成功创建并提交会话记录；
  - `push origin main` 因未配置远程 `origin` 失败（流程已验证到远程前一步）。

### 验证结果
- 命令：
  `git -C E:\codex-result-bus log --oneline -n 2`
- 结果：
  - `55298c5`（脚本 smoke test 提交）
  - `776570d`（本次会话快照提交）
- 命令：
  `powershell -ExecutionPolicy Bypass -File scripts/publish_session_snapshot_to_result_bus.ps1 -ResultRepo E:\codex-result-bus -SourceWorkspace E:\NTL-GPT-Clone -SummaryTitle "Smoke Test" -SummaryBody "Skill and script smoke test." -NoPush`
- 结果：返回 `record_path`、`commit`、`push_status=push_skipped`
- 命令：
  `git -C E:\codex-result-bus push origin main`
- 结果：失败，原因 `remote origin not configured`

### 复现命令
```bash
# 1) 本地快照发布（不推送）
powershell -ExecutionPolicy Bypass -File scripts/publish_session_snapshot_to_result_bus.ps1 `
  -ResultRepo E:\codex-result-bus `
  -SourceWorkspace E:\NTL-GPT-Clone `
  -SummaryTitle "Session Snapshot" `
  -SummaryBody "Manual publish test." `
  -NoPush

# 2) 配置远程后再推送
git -C E:\codex-result-bus remote add origin <YOUR_PRIVATE_REPO_URL>
git -C E:\codex-result-bus push -u origin main
```

## [2026-02-18] v2026.02.18.6 余柏蒗 2025 夜光文献补充（文献卡）+ Literature 文本入库能力
### 目标
- 补充余柏蒗老师 2025–2026 最新夜光相关论文到 `Literature_RAG`。
- 在全文 PDF 暂不可自动下载时，仍可通过结构化文献卡（含 DOI/摘要/链接）纳入检索。

### 修改文件
- `agents/NTL_Knowledge_Base_manager.py`
- `tests/test_literature_rag_ingestion_manager.py`
- `RAG/literature base/补充_余柏蒗_2025_2026/*.md`（8 篇文献卡）
- `outputs/yu_2025_2026_ntl_openalex.json`
- `outputs/yu_2025_2026_download_result.json`
- `outputs/yu_2025_2026_retry_result.json`
- `outputs/yu_2025_2026_cards.json`
- `RAG/Literature_RAG/rebuild_report.json`
- `docs/Codex_变更记录.md`

### 关键变更
- Literature 入库能力升级：
  - 在原 `pdf` 基础上新增支持 `md/txt` 文献源；
  - 统一走 literature profile 的分块、去重、metadata 标注流程；
  - 新增 `source_bucket=literature_text`，用于区分文献卡与 PDF 原文。
- 补充了 8 篇余柏蒗 2025 夜光相关文献卡（OpenAlex 元数据）：
  - 包含标题、作者、年份、DOI、期刊、落地页、OA 链接、摘要。
- 自动全文下载结果：
  - 目标条目 9 篇；
  - 受出版社页面限制，环境内未自动抓取到新增全文 PDF；
  - 因此采用文献卡先入库，后续可被同名 PDF 无缝替换。

### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_rag_ingestion_manager.py`
- 结果：`4 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py --profile literature --literature-dir "RAG/literature base" --persist-dir RAG/Literature_RAG --collection-name Literature_RAG --reset --report-path RAG/Literature_RAG/rebuild_report.json`
- 结果：`final_collection_count=508`，其中 `literature_pdf=500`，`literature_text=8`，`errors=[]`

### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_literature_rag_ingestion_manager.py

conda run --no-capture-output -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py \
  --profile literature \
  --literature-dir "RAG/literature base" \
  --persist-dir RAG/Literature_RAG \
  --collection-name Literature_RAG \
  --reset \
  --report-path RAG/Literature_RAG/rebuild_report.json
```


## [2026-02-18] v2026.02.18.8 Official Daily NTL Fastpath Experiment (CMR + Boundary + Baseline)
### 目标
- 在不改主架构的前提下，落地独立实验工作区，验证“官方源比 GEE 更快获取日尺度 NTL”的可执行流程。

### 修改文件
- `experiments/official_daily_ntl_fastpath/cmr_client.py`
- `experiments/official_daily_ntl_fastpath/gridded_pipeline.py`
- `experiments/official_daily_ntl_fastpath/boundary_resolver.py`
- `tests/official_daily_fastpath/test_cmr_parse.py`
- `tests/official_daily_fastpath/test_boundary_naming.py`
- `docs/NTL-GPT_项目介绍_最新版.md`
- `docs/Codex_变更记录.md`

### 关键变更
- 下载与鉴权安全性修复：
  - `cmr_client.py` 下载改为 `curl --fail-with-body`。
  - 新增下载体签名校验（HDF5 / netCDF classic），阻断把 `HTTP Basic: Access denied` 错误页误当数据文件。
- token 解析修复：
  - `EARTHDATA_TOKEN` 不再回退到通用 `ACCESS_TOKEN`，避免误用非 Earthdata token。
- 处理链容错增强：
  - `gridded_pipeline.py` 对每个 tile 的下载/读取/变量匹配/写出失败进行显式状态回传，避免单点异常导致整次任务崩溃。
- 边界命名泛化：
  - 新增 `_safe_boundary_filename`，支持中文行政区名并避免 `boundary__.shp` 空名退化。
- 文档补充：
  - 在项目介绍中新增“官方 Daily NTL 快速实验流（独立工作区）”章节，明确范围、输出与限制。

### 验证结果
- 命令：
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`12 passed`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py --study-area "上海市" --workspace experiments/official_daily_ntl_fastpath/workspace_validation/shanghai`
- 结果：成功生成
  - `experiments/official_daily_ntl_fastpath/workspace_validation/shanghai/outputs/availability_report.json`
  - `experiments/official_daily_ntl_fastpath/workspace_validation/shanghai/outputs/availability_report.csv`
- 命令：
  `conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py --study-area "Yangon, Myanmar" --workspace experiments/official_daily_ntl_fastpath/workspace_validation/yangon`
- 结果：成功生成
  - `experiments/official_daily_ntl_fastpath/workspace_validation/yangon/outputs/availability_report.json`
  - `experiments/official_daily_ntl_fastpath/workspace_validation/yangon/outputs/availability_report.csv`
- 报告摘录（两地）：
  - `VJ146A1.latest_available_date=2026-02-11`
  - `gee_latest_date=2026-02-10`
  - `lead_days_vs_gee=1`

### 复现命令
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath

conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py \
  --study-area "上海市" \
  --workspace experiments/official_daily_ntl_fastpath/workspace_validation/shanghai

conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py \
  --study-area "Yangon, Myanmar" \
  --workspace experiments/official_daily_ntl_fastpath/workspace_validation/yangon
```

### 已知限制（可选）
- 当前环境无有效 `EARTHDATA_TOKEN`，A1/A2 仅完成元数据与日期领先性验证，未产出裁剪日影像。
- 若 token 无效，报告会显式返回 `download_failed` 并附 `401 + Access denied` 提示，不会静默成功。


## [2026-02-18] v2026.02.18.9 NRT Priority + Live Availability Web Monitor + GIBS Render
### ??
- ????????????????????? "NRT first, standard fallback"???????????????????????

### ????
- `experiments/official_daily_ntl_fastpath/source_registry.py`
- `experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py`
- `experiments/official_daily_ntl_fastpath/noaa20_feasibility.py`
- `experiments/official_daily_ntl_fastpath/gridded_pipeline.py`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/README.md`
- `tests/official_daily_fastpath/test_source_registry.py`
- `tests/official_daily_fastpath/test_monitor_helpers.py`
- `docs/NTL-GPT_????_???.md`
- `docs/Codex_????.md`

### ????
- Source registry now includes NRT sources: `VJ146A1_NRT`, `VJ146A1G_NRT`, `VJ102DNB_NRT`.
- Added `nrt_priority` profile and made it the default in `run_fast_daily_ntl.py`:
  - `VJ146A1_NRT -> VJ146A1 -> VJ146A2 -> VJ102DNB_NRT -> VJ102DNB`
- Feasibility-only flow is now generic and driven by source spec (not hardcoded to one source).
- Fixed mosaic temp output directory creation in `gridded_pipeline.py`.
- Added independent live monitor service and web UI:
  - API: `/api/health`, `/api/latest`
  - Live global render layers: `VIIRS_SNPP_DayNightBand`, `VIIRS_NOAA20_DayNightBand`, `VIIRS_NOAA21_DayNightBand`.

### ????
- ???
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- ???`16 passed`
- ???
  `conda run --no-capture-output -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py experiments/official_daily_ntl_fastpath/source_registry.py experiments/official_daily_ntl_fastpath/noaa20_feasibility.py experiments/official_daily_ntl_fastpath/gridded_pipeline.py`
- ?????
- ???
  `conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py --study-area "???" --workspace experiments/official_daily_ntl_fastpath/workspace_validation/shanghai_nrt_priority`
- ?????????? `VJ146A1_NRT.latest_available_date=2026-02-17`?
- ???
  `conda run --no-capture-output -n NTL-GPT python -c "import threading, urllib.request, json; from http.server import ThreadingHTTPServer; from experiments.official_daily_ntl_fastpath.monitor_server import MonitorHandler; srv=ThreadingHTTPServer(('127.0.0.1', 8877), MonitorHandler); t=threading.Thread(target=srv.serve_forever, daemon=True); t.start(); h=urllib.request.urlopen('http://127.0.0.1:8877/api/health').read().decode(); l=urllib.request.urlopen('http://127.0.0.1:8877/api/latest?sources=nrt_priority&days=3').read().decode(); obj=json.loads(l); html=urllib.request.urlopen('http://127.0.0.1:8877/').read().decode('utf-8'); print('rows', len(obj['rows']), 'html_ok', 'Official Daily NTL Fast Monitor' in html); srv.shutdown(); srv.server_close()"`
- ???`rows=5`, `html_ok=True`

### ????
```bash
conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath

conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py   --study-area "???"   --workspace experiments/official_daily_ntl_fastpath/workspace_validation/shanghai_nrt_priority

conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py   --host 127.0.0.1   --port 8765
```

### ????????
- Some NRT download links still return HTML login pages or connection-reset in this environment; these are explicitly marked as `download_failed` in reports.
- `VJ102DNB_NRT` and `VJ102DNB` remain feasibility-only in this round.


## [2026-02-18] v2026.02.18.UI-Run-Resilience Streamlit ?????????????
### ??
- ?????????????????????? thinking ??????
- ????????????????????/??????????????

### ????
- `app_logic.py`
- `app_ui.py`
- `app_state.py`
- `Streamlit.py`
- `tests/test_app_runtime_resilience.py`

### ????
- ???????????
  - `should_recover_stale_run(...)`
  - `recover_runtime_health()`
- ???? `Streamlit.py` ????????????????????????? stale running state?
- ? `handle_userinput()` ?? `run_started_ts/run_heartbeat_ts/run_ended_ts` ??????????????
- `render_content_layout()` ?????
  - Reasoning / Map / Outputs ??????? `try/except`????????????????
  - ???????? `conversation`??????????????????
  - ???????????stale run auto-recovered??
- `render_map_view()` ????????????????????/IO ?????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_app_runtime_resilience.py`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_kb_payload_normalization.py tests/test_kb_render_fallback_contract.py`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py app_logic.py app_state.py Streamlit.py`

### ??
- ??????? 4 ????????? + ???????
- ?? UI/??????????


## [2026-02-18] v2026.02.18.UI-ChatInput-Offset ???????
### ????
- `app_ui.py`

### ??
- ??????????? `max(0px, env(safe-area-inset-bottom))` ??? `calc(12px + env(safe-area-inset-bottom))`?
- ???? JS ?????? `input.style.bottom`??? rerun ??????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`



## [2026-02-18] v2026.02.18.10 Web Monitor Layer Fallback + Favicon
### ??
- ??????? Layer ??????????? `favicon.ico` 404 ???

### ????
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/favicon.svg`
- `docs/Codex_????.md`

### ????
- ?????????? `FALLBACK_GIBS_LAYERS`????????? Layer ?????? `/api/latest` ?????
- `refresh()` ???????/????????? `updateOverlayLayer()`???????
- `populateLayerSelect()` ????????????????
- ? `index.html` ?? SVG favicon ?????? `favicon.svg`?????????? favicon 404?

### ????
- ???
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- ???`16 passed`
- ???
  `http://127.0.0.1:8765`?Playwright ?????
- ???`Layer` ???? 3 ????`SNPP DayNightBand (NRT)`?`NOAA20 DayNightBand (NRT)`?`NOAA21 DayNightBand`?

### ????
```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py   --host 127.0.0.1   --port 8765

# Open in browser and verify Layer options are visible immediately:
# http://127.0.0.1:8765
```

### ????????
- ????????? GIBS????????????? Layer ???????????


## [2026-02-18] v2026.02.18.UI-ChatInput-Offset-Revert ???????
### ????
- `app_ui.py`

### ??
- ?????????????????
  - CSS: `bottom: max(0px, env(safe-area-inset-bottom))`
  - JS: `input.style.bottom = 'max(0px, env(safe-area-inset-bottom))'`

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`


## [2026-02-18] v2026.02.18.11 Web Monitor Layer Load Status Reminder
### ??
- ?????????????????????????????????

### ????
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/NTL-GPT_????_???.md`
- `docs/Codex_????.md`

### ????
- ??????? `Layer status` ????
- ?? Leaflet ??????????
  - `loading`???????
  - `success`???????
  - `partial`??????????
  - `failed`?????
- ????????????????????????????

### ????
- ???
  `http://127.0.0.1:8765`?Playwright ?????
- ??????? `Layer status: failed (0 loaded, 12 errors)`??????????Layer ??????
- ???
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- ???`16 passed`

### ????
```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py   --host 127.0.0.1   --port 8765

# Open http://127.0.0.1:8765
# Switch layer/date or disconnect network to observe status transitions.
```


## [2026-02-18] v2026.02.18.12 Region Snapshot Mode for Fallback Rendering
### ??
- ???????????????????/??/????????????

### ????
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/NTL-GPT_????_???.md`
- `docs/Codex_????.md`

### ????
- ?? `Render Mode`?
  - `Global Tiles`??? WMTS ?????
  - `Region Snapshot`?WMS ???????
- ?? `Region` ???`Global / China / Shanghai / Custom(BBox)`?
- ?? `Snapshot px` ?????????????
- ????? `Layer status` ?????? `loading/success/partial/failed`?

### ????
- ???
  `http://127.0.0.1:8765`?Playwright ?????
- ???
  - ?????????`Render Mode`?`Region`?`Snapshot px`?
  - ??? `Region Snapshot` ?????? `failed snapshot ...`?????????
- ???
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- ???`16 passed`

### ????
```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py   --host 127.0.0.1   --port 8765

# Open http://127.0.0.1:8765
# 1) Render Mode -> Region Snapshot
# 2) Region -> China or Shanghai
# 3) Observe Layer status for success/failure
```


## [2026-02-18] v2026.02.18.Run-Limit-Boundary-Fix 480s ??????
### ??
- ????? `Max run=480s` ???????????????????????????

### ????
- `app_logic.py`
- `tests/test_app_run_limits.py`

### ???
- ?????????? `evaluate_limit_interruption(...)`?
- ?????????????????????????????????????????
- ? `max_duration` ?? `1` ??????grace event??????????????
- `stall_timeout` ???????? max-duration ???

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_app_run_limits.py tests/test_app_runtime_resilience.py`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_logic.py Streamlit.py app_ui.py app_state.py`

### ??
- ???????????? Continue/Stop????????????????


## [2026-02-18] v2026.02.18.MaxRun-Soft-Continue Max????????
### ??
- ??????? `Max run(s)` ??????? Continue??????? Stop/Interrupt???????

### ????
- `app_logic.py`
- `app_ui.py`
- `tests/test_app_run_limits.py`

### ??
- `evaluate_limit_interruption(...)` ?? `auto_continue_on_max_duration` ?????? `reached_max_duration` ???
- ???? `auto_continue_on_max_duration=True`?
  - ?? `max_duration` ??????????
  - ?????? `Interrupt Current Run` ?????
- `stall_timeout` ???????? Continue/Stop??????
- ???? `Max run(s)` ???????????????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_app_run_limits.py tests/test_app_runtime_resilience.py`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_logic.py app_ui.py`


## [2026-02-18] v2026.02.18.13 UX Flow Upgrade for Monitor Page
### ??
- ????????????????`Layer status: idle` ???????????????????????

### ????
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/NTL-GPT_????_???.md`
- `docs/Codex_????.md`

### ????
- ???????????????????????
  - ?? `Query Availability`??????????
  - ?? `Load Imagery`????????????
- `Layer status` ?????? `idle`?
  - ??????? `parameters updated, click "Load Imagery"`?
  - ???/??/??/??????????????
- ????????????????????????????????????
- ?????????????????????

### ????
- ???
  `http://127.0.0.1:8765`?Playwright ?????
- ???
  - ???? `Load Imagery` ???
  - ?????? `Layer status: parameters updated, click "Load Imagery"`?
  - ????????? `failed (0 loaded, N errors)`??????????????????
- ???
  `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- ???`16 passed`

### ????
```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py   --host 127.0.0.1   --port 8765

# Open http://127.0.0.1:8765
# 1) Click Query Availability
# 2) Adjust render parameters
# 3) Click Load Imagery and observe Layer status
```


## [2026-02-18] v2026.02.18.Streamlit-Recover-SafeCall ????????
### ??
- ?????`module 'app_logic' has no attribute 'recover_runtime_health'`?
- ??????????/???????????????

### ????
- `Streamlit.py`
- `tests/test_streamlit_runtime_recovery_fallback.py`

### ??
- ?? `_safe_recover_runtime_health()`?
  - ? `app_logic.recover_runtime_health` ??????
  - ??????? warning ????????? UI?
- `main()` ????????????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_streamlit_runtime_recovery_fallback.py`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile Streamlit.py`

## [2026-02-18] v2026.02.18.14 Monitor-Bilingual-UX-Refresh3m
### 背景
- 用户需要明确区分 Source/Layer 含义，并要求页面支持中英文切换。
- 用户反馈自动刷新频率 60s 过高，改为 3 分钟更合适。
- 用户希望页面不再显示“auto 60s”文案，但保留自动刷新能力。

### 变更文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/Codex_变更记录.md`

### 主要变更
- 新增 UI 语言切换：`中文 / English`，并使用 `localStorage` 持久化语言偏好。
- 页面静态文本与状态文案统一接入 i18n 字典（含数据状态/图层状态）。
- 自动刷新周期由 `60s` 调整为 `180s`（3 分钟）。
- 隐藏页面上的自动刷新文字，仅保留复选框与悬停提示。
- 修复 Study Area 占位符乱码，改为 UTF-8 正常文本。

### 验证
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`16 passed`
- UTF-8 校验：
  - `bom False`
  - `utf8_ok True`
  - `mojibake_hits []`


## [2026-02-18] v2026.02.18.RoleSplit-EngineerDesign-CodeExec ?????
### ??
- ??????????`NTL_Engineer` ????????????`Code_Assistant` ???????????????? Engineer ???

### ????
- `agents/NTL_Engineer.py`
- `agents/NTL_Code_Assistant.py`
- `tools/NTL_Code_generation.py`
- `tests/test_code_file_protocol_prompts.py`
- `tests/test_ntl_engineer_prompt_constraints.py`
- `tests/test_code_error_handling_policy.py`

### ????
- Engineer ????????????
  - Engineer ??????? owner?
  - handoff ? Code_Assistant ????????? `.py` ???
  - hard/ambiguous ????????Engineer ???????? `v2.py/v3.py`?
- Code_Assistant ??????????
  - ??? Engineer ????????? block-by-block ???
  - `GeoCode_COT_Validation_tool` ??????????????
  - ???????????? 1 ??
- ???????
  - `tools/NTL_Code_generation.py` ? simple policy `max_self_retries` ? 2 ??? 1?

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_code_file_protocol_prompts.py tests/test_ntl_engineer_prompt_constraints.py tests/test_code_error_handling_policy.py`
- ???`10 passed`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile agents/NTL_Engineer.py agents/NTL_Code_Assistant.py tools/NTL_Code_generation.py`

## [2026-02-18] v2026.02.18.15 Monitor-Data-Download-H5-TIF
### 背景
- 用户明确要求下载数据文件（`.h5/.nc` 或 `.tif`），而不是下载渲染 PNG。
- 用户要求默认渲染图层为 `NOAA20 DayNightBand`。

### 变更文件
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/Codex_变更记录.md`

### 主要变更
- 默认图层改为 `VIIRS_NOAA20_DayNightBand`（后端图层顺序 + 前端默认选择逻辑双保险）。
- 新增后端下载接口：`GET /api/download_data`
  - `format=raw_h5`：下载最新日期 granule 原始文件；多文件自动打包 zip。
  - `format=clipped_tif`：对 `gridded_tile_clip` 源执行裁剪并返回 tif。
  - 下载依赖 `EARTHDATA_TOKEN`，缺失时明确返回错误，不报假成功。
- 前端新增下载控件：`Download Source` + `Download Format` + `Download Data`。
- 前端下载流程接入 `/api/download_data`，自动解析文件名并触发浏览器保存。

### 验证
- `conda run --no-capture-output -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`16 passed`
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`

## [2026-02-18] v2026.02.18.16 Monitor-LeftSidebar-Download-Mapping
### 背景
- 用户要求将“日期”和“下载数据”放到左侧栏。
- 用户要求下载参数与左栏空间范围、时间范围、数据源一一对应。

### 变更文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `docs/Codex_变更记录.md`

### 主要变更
- 左侧栏新增 `Data Download` 区块，包含：
  - `Date`
  - `Download Source`
  - `Download Format`
  - `Download Data` 按钮
- 右侧地图区移除下载相关控件，仅保留地图渲染参数。
- 下载请求参数与左栏直接对应：
  - 空间：`study_area` / `bbox`
  - 时间窗口：`days`
  - 数据源：`downloadSource`
  - 指定日期：`date`
- 后端 `/api/download_data` 新增 `date` 支持：
  - 传入 `date=YYYY-MM-DD` 时按指定日下载
  - 不传时保持“窗口内最新日”行为

### 验证
- `conda run --no-capture-output -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py`
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`16 passed`


## [2026-02-19] v2026.02.19.ManualInterruptOnly + CodeAssistantStageView
### ??
- ????????????????/?????????????????
- ??????? Code_Assistant ??????????????????????

### ????
- `app_state.py`
- `app_logic.py`
- `app_ui.py`
- `tests/test_code_assistant_stage_classification.py`
- `tests/test_code_error_handling_policy.py`
- `tests/test_code_file_protocol_prompts.py`
- `tests/test_ntl_engineer_prompt_constraints.py`
- ???`tests/test_app_run_limits.py`

### ????
- ?? `Max run(s)` / `Stall(s)` ?? UI???????????
  - ?? `run_max_duration_s` / `run_stall_timeout_s` / `run_decision_pending`?
  - ?? `evaluate_limit_interruption` ? Continue/Stop ???
  - ??????? `Interrupt Current Run` ??????
- ?????????stale run recovery??????????????? Max/Stall ???
- ?? Code_Assistant ?????
  - `Draft Received`?save script?
  - `Validate/Execute`?validation/execute in progress?
  - `Escalate`?fail/needs_engineer_decision/transfer_back?
  - `Success`?execution success?

### ??
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/test_code_assistant_stage_classification.py tests/test_app_runtime_resilience.py tests/test_code_file_protocol_prompts.py tests/test_ntl_engineer_prompt_constraints.py tests/test_code_error_handling_policy.py`
- ???`16 passed`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_state.py app_logic.py app_ui.py agents/NTL_Engineer.py agents/NTL_Code_Assistant.py tools/NTL_Code_generation.py`

## [2026-02-18] v2026.02.18.17 Monitor-Layout-Balance-RightPanel
### 背景
- 用户反馈页面整体不协调，尤其右侧控制区留白大、密度不均。
- 用户要求左侧在拥挤时可采用两列布局。

### 变更文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/Codex_变更记录.md`

### 主要变更
- 左侧栏：查询区与下载区改为“局部两列”，并让 `Study Area/BBox/按钮行` 跨两列，减少拥挤感。
- 右侧栏：地图控制区重排为两行结构：
  - 第一行：`Layer + Render Mode + Region + Load Imagery`
  - 第二行：`Opacity + Snapshot px`
- 调整按钮高度与最小宽度，统一控件视觉节奏。
- 移动端回退：<980px 自动回到单列布局，保证可读性。

### 验证
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`16 passed`

## [2026-02-18] v2026.02.18.18 Monitor-RightPanel-Layout-Fix
### 背景
- 用户反馈右侧布局异常，存在明显大面积留白与控件分布不协调。

### 变更文件
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `docs/Codex_变更记录.md`

### 主要变更
- 将右侧 `panel-map` 从网格布局改为纵向 `flex` 布局，避免旧网格行定义与新增控件数量不匹配导致的中间行被异常拉伸。
- 调整右侧两行控件列宽比例：
  - 第一行（图层/渲染模式/区域/按钮）更均衡；
  - 第二行（透明度/快照像素）减少横向拥挤。
- 地图容器改为 `flex: 1`，保证在可用高度内自然填充。

### 验证
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`16 passed`


## [2026-02-19] v2026.02.19.UI-InputPosition-Robust + MaxStallResidualCheck
### ????
- `app_ui.py`

### ??
- ????????????????
  - `bottom: calc(clamp(10px, 1.4vh, 18px) + env(safe-area-inset-bottom))`?CSS + JS ???
- ??????????`block-container` bottom padding ? `5.5rem` ??? `7.0rem`????????????
- ????????? `Max run(s)/Stall(s)` ????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`

## [2026-02-18] v2026.02.18.19 GEE-Baseline-Info-And-Download-Script
### 背景
- 用户要求在左侧栏接入最新 GEE 数据可获取信息。
- 用户要求将“从 GEE 下载数据”的脚本加入独立实验项目。

### 变更文件
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `tests/official_daily_fastpath/test_gee_download_script.py`
- `experiments/official_daily_ntl_fastpath/README.md`
- `docs/Codex_变更记录.md`

### 主要变更
- 左栏新增 `GEE Baseline` 信息区，展示当前查询区域对应的：
  - GEE 数据集（默认 `NASA/VIIRS/002/VNP46A2`）
  - 最新可用日期 `gee_latest_date`
  - 滞后天数 `gee_latest_lag_days`
  - 异常信息 `gee_error`（如 `bbox_missing`）
- `/api/latest` 新增 GEE 基线字段输出，并与当前 bbox 同步查询。
- 新增独立脚本：`download_gee_daily_ntl.py`
  - 输入：`study-area/bbox + date + dataset + (optional) band`
  - 输出：区域日尺度 GeoTIFF + `download_meta.json`
  - 默认支持 `VNP46A2` 与 `VNP46A1` 自动波段映射。
- 新增单测覆盖：bbox 解析、非目标变体（非法 bbox 顺序）、波段映射与异常分支。

### 验证
- `conda run --no-capture-output -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath`
- 结果：`20 passed`


## [2026-02-19] v2026.02.19.StreamlitSkillInstall + InputBarAndBorderPolish
### ??
- ???????? `streamlit/agent-skills`????????????????????

### ????
- `app_state.py`
- `app_ui.py`

### ??
- ????????`streamlit/agent-skills`??????
  - ????`developing-with-streamlit`?`template-skill`?
- ???????????? Max/Stall ?????
  - ? `app_state.init_app()` ?? `run_max_duration_s/run_stall_timeout_s/run_decision_pending`?
- ?????????????
  - `block-container` ??????? `8.0rem`?
  - ??? bottom ?? `calc(clamp(14px, 2.2vh, 24px) + env(safe-area-inset-bottom))`?CSS + JS ????
  - JS ?? `right=auto`???????????
- ????????
  - `stVerticalBlockBorderWrapper` ???? `rgba(100,116,139,0.44)`?????????????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py app_state.py`
- `npx skills list | Select-String "developing-with-streamlit"`


## [2026-02-19] v2026.02.19.UI-ChatInput-BottomAnchor + WhitePanelBorder
### ????
- `app_ui.py`

### ??
- ????????????`--ntl-panel-border: rgba(255, 255, 255, 0.62)`?
- ???????????????????????
  - JS ??? `ntl-chat-input-anchor` ????? `targetTop = anchorTop - inputHeight - 10`?
  - ????????????????????????? viewport ?????
  - ???? `input.style.top` / `bottom`?????????????

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`


## [2026-02-19] v2026.02.19.ChatInputAnchorFix + WhiteBorderStronger
### ????
- `app_ui.py`

### ??
- ??????????
  - `--ntl-panel-border` ??? `rgba(255,255,255,0.88)`?
  - ??? wrapper ????? `1.2px`?????? inset ???
- ??????????
  - ?? `getLastVisibleById`????? id ????????
  - ???????? `stVerticalBlockBorderWrapper` ?????????????
  - ???????inputAnchor -> chatColRect -> viewport bottom??

### ??
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`

## [2026-02-18] v2026.02.18.20 FastMonitor-GEE-Table-Unification-And-RangeGuard
### 目标
- 将 GEE 基线并入可用性总表，减少信息割裂。
- 删除表格“模式”列，保留核心时效对比字段。
- 修复图层状态提示不更新问题，并补齐 GEE 下载时间范围校验。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `tests/official_daily_fastpath/test_gee_download_script.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 左侧可用性表新增一行 `GEE NASA/VIIRS/002/VNP46A2`，与 5 个官方 Source 同表展示最新日期和滞后天数。
- 删除表格 `Mode` 列，降低阅读噪音。
- 修复 `layerDate` 变化事件中错误调用 `markDirty()` 导致 `Layer status` 长时间停留的问题，改为 `markLayerDirty()`。
- 修复 `/api/download_data` 中 GEE 默认数据集回退变量作用域问题，避免默认参数异常。
- `download_gee_daily_ntl.py` 新增 `validate_dataset_period(...)`：
  - 日/月 VIIRS 起始时间限制（2014-01-01 起）。
  - 年度 DMSP-OLS 限制（1992-2013）。
  - 未来日期拦截（daily/monthly/annual）。
- 单测新增时间范围校验覆盖，并修正 VNP46A1 数据集 ID 断言。

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`23 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-19] v2026.02.19.LangSmith-Run-Convergence-And-Redundancy-Guard
### Context
- Inspected latest LangSmith trace in project `NTL-GPT` (trace_id: `019c71fb-ef66-74a1-88ba-e0fd54ea023f`).
- Observed non-smooth behavior: repeated `save_geospatial_script_tool` + `execute_geospatial_script_tool` loops, with multiple identical failure patterns before final success.

### Root Findings
- Repeated failure signatures were retried multiple times (`FileNotFoundError` / missing workspace files) without early escalation.
- Code_Assistant convergence after success was weak, allowing extra save/execute cycles in the same branch.
- Data_Searcher handoff behavior lacked an explicit “single transfer_back once complete” constraint.

### Changes
- `tools/NTL_Code_generation.py`
  - Added save dedupe for identical script content per thread:
    - Reuse previously saved script metadata instead of creating redundant rewrites.
  - Added execute dedupe for already-successful identical script:
    - Skip re-execution and return `already_executed=true` with `next_action_hint=transfer_back_to_ntl_engineer`.
  - Added repeated identical failure guard:
    - Track failure signatures per thread.
    - Auto-escalate policy from simple to hard on repeated identical failures (`>=2`), forcing engineer handoff instead of endless self-debug.
- `agents/NTL_Code_Assistant.py`
  - Added mandatory convergence rule:
    - After first successful execute, transfer back immediately.
    - If `already_executed=true`, treat as terminal success and transfer back.
- `agents/NTL_Data_Searcher.py`
  - Added single handoff rule:
    - When completion gate is satisfied, call `transfer_back_to_ntl_engineer` exactly once and stop.

### Tests
- Added: `tests/test_code_execution_convergence_guard.py`
  - identical save dedupe reuse
  - redundant success execution skip
  - repeated identical fail escalates to hard handoff policy
- Updated:
  - `tests/test_code_file_protocol_prompts.py`
  - `tests/test_data_searcher_prompt_constraints.py`

### Verification
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Code_generation.py agents/NTL_Code_Assistant.py agents/NTL_Data_Searcher.py`
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_code_execution_convergence_guard.py tests/test_code_file_protocol_prompts.py tests/test_data_searcher_prompt_constraints.py`
- Result: `11 passed`

## [2026-02-19] v2026.02.19.Engineer-Missing-Input-Redispatch-Rule
### Scope
- Added a hard guard in engineer planning flow to avoid sending Code_Assistant into execution when required inputs are missing/unreadable.

### Changes
- `agents/NTL_Engineer.py`
  - Added explicit rule:
    - If `geodata_quick_check_tool` or execution logs indicate missing/unreadable required input files, re-dispatch `Data_Searcher` (or request upload) before handing back to `Code_Assistant`.
- `tests/test_ntl_engineer_prompt_constraints.py`
  - Added assertions to lock this behavior in prompt constraints.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_code_file_protocol_prompts.py tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py`
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_code_execution_convergence_guard.py`
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Code_generation.py agents/NTL_Code_Assistant.py agents/NTL_Data_Searcher.py agents/NTL_Engineer.py`

## [2026-02-19] v2026.02.19.Streamlit-PanelBorder-And-ChatInput-Reanchor
### 目标
- 修复主内容区边框样式未命中（看起来像“没有变化”）的问题。
- 修复聊天输入框定位错位（出现在错误位置/不在聊天面板内底部附近）的问题。

### 修改文件
- `app_ui.py`

### 关键变更
- 边框选择器从旧版 `stVerticalBlockBorderWrapper` 兼容扩展到当前 Streamlit 结构：
  - `div[data-testid="stVerticalBlock"][overflow="auto"][height="600px"]`
- 主内容区左右两块滚动面板统一增强边框样式（白色高对比、圆角、内描边）。
- 聊天输入框定位逻辑改为“基于实际可滚动主面板识别”：
  - 识别左侧主滚动面板作为聊天面板。
  - 输入框宽度/左偏移与聊天面板对齐。
  - 输入框垂直位置锚定到聊天面板底部可视区域。
- 修复 CSS 与 JS 定位冲突：
  - 去掉会阻止 JS 覆盖的 `bottom/left/width` 的 `!important`。
  - JS 改用 `style.setProperty(..., 'important')`，确保 `top/bottom` 不冲突。

### 验证
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
- Playwright 实测：
  - 主面板边框命中并可见（`rgba(255,255,255,0.9)`）。
  - 聊天输入框坐标与左侧聊天面板对齐，不再跑到页面顶部。

## [2026-02-19] v2026.02.19.Streamlit-PanelAlignment-And-SoftBorder
### 目标
- 修复左右主内容区不等高、起点不齐问题。
- 将主面板边框调整为更柔和半透明样式，避免过于突兀。

### 修改文件
- `app_ui.py`

### 关键变更
- 删除聊天列中用于旧定位方案的锚点 markdown，消除额外纵向偏移。
- 保持左右主面板同一高度配置下，统一起始 `y` 坐标。
- 边框改为半透明白：
  - `rgba(255,255,255,0.52)`
  - 线宽调整为 `1.2px`
  - 内阴影强度降低。
- JS 动态样式同步使用同一半透明边框参数，防止 rerun 后样式回弹。

### 验证
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
- Playwright 实测（Active 页面）：
  - 左右主面板 `y` 坐标一致（已水平对齐）。
  - 左右主面板高度一致（`600px`）。

## [2026-02-18] v2026.02.18.21 GEE-Monthly-Annual-Status-And-Band-Selector
### 目标
- 补齐 GEE 年度 `NPP-VIIRS-Like` 下载支持。
- 在状态表中展示 GEE 日/月/年产品的最新可用时间（全局 + 区域）。
- 将 GEE 波段改为下拉选项，按数据集提供可选 band。

### 修改文件
- `experiments/official_daily_ntl_fastpath/gee_baseline.py`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `tests/official_daily_fastpath/test_gee_baseline_products.py`
- `tests/official_daily_fastpath/test_gee_download_script.py`
- `docs/Codex_变更记录.md`

### 关键变更
- `GEE_SOURCE_OPTIONS.annual` 新增：
  - `projects/sat-io/open-datasets/npp-viirs-ntl`（NPP-VIIRS-Like）。
- `download_gee_daily_ntl.py`：
  - 新增 NPP-VIIRS-Like 默认波段 `b1`。
  - 新增年度范围校验 `2000-2024`。
- `gee_baseline.py`：
  - 新增 `GEE_MONITOR_PRODUCTS`（日/月/年全量监控清单）。
  - 新增 `query_gee_products_latest(...)`，返回每个 GEE 产品的：
    - `latest_global_date`
    - `latest_bbox_date`
    - `error`
- `monitor_server.py`：
  - `/api/latest` 新增 `gee_rows`，并计算 `latest_global_lag_days/latest_bbox_lag_days`。
- 前端状态表：
  - 直接把 `payload.gee_rows` 合并到同一张表，显示 GEE 各产品时效。
- GEE 波段输入：
  - 从自由文本改为下拉 `select`。
  - 按数据集动态加载 band 选项（基于 GEE 集合真实 band 列表）。

### 官方参考（用于 band 口径）
- Earth Engine Data Catalog: `NASA/VIIRS/002/VNP46A2`
- Earth Engine Data Catalog: `NOAA/VIIRS/001/VNP46A1`
- Earth Engine Data Catalog: `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`
- Earth Engine Data Catalog: `NOAA/VIIRS/DNB/ANNUAL_V22`
- Earth Engine Data Catalog: `NOAA/VIIRS/DNB/ANNUAL_V21`
- Earth Engine Data Catalog: `NOAA/DMSP-OLS/NIGHTTIME_LIGHTS`

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/gee_baseline.py experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`25 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/gee_baseline.py experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-18] v2026.02.18.22 Unified-Time-Params-For-GEE-And-Official-Download
### 目标
- 将“日期 + GEE 时间”逻辑统一为一套下载时间参数。
- 支持统一的单日/范围下载，系统自动按数据源判断对应时间粒度与下载范围。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `tests/official_daily_fastpath/test_monitor_helpers.py`
- `tests/official_daily_fastpath/test_gee_download_script.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 前端下载参数统一为：
  - `downloadTimeMode`: `single` / `range`
  - `downloadStartDate`
  - `downloadEndDate`（single 时自动等于 start）
- 移除 GEE 专属 `temporal + period` 输入控件；GEE 下载改为：
  - 根据所选 `downloadSource` 自动识别数据集时间粒度（日/月/年）
  - 根据 `start_date/end_date` 自动展开 period 列表并逐期下载
- 后端 `/api/download_data` 支持统一参数：
  - `start_date`, `end_date`（兼容旧 `date`）
  - GEE：范围多期自动下载并打包 zip（单期仍返回 tif）
  - Official：范围多日按天下载/裁剪，多个文件打包 zip
- 新增/补充核心 helper：
  - `_parse_download_date_range(...)`
  - `infer_temporal_resolution(...)`
  - `periods_from_date_range(...)`
- 边界保护：
  - Official 单次范围限制 `<=31` 天
  - GEE 单次范围限制 `<=90` 个 period

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py experiments/official_daily_ntl_fastpath/gee_baseline.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`29 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py experiments/official_daily_ntl_fastpath/gee_baseline.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-18] v2026.02.18.23 Download-TimeMode-Removed-StartEnd-Rule
### 目标
- 删除下载区“时间模式”按钮。
- 改为通过开始/结束日期自动判断：相同即单日，不同即范围。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### 关键变更
- UI 移除 `downloadTimeMode` 控件，仅保留：
  - `downloadStartDate`
  - `downloadEndDate`
- 前端下载参数逻辑调整：
  - `start_date == end_date` -> 单日语义
  - `start_date != end_date` -> 范围语义
- 清理已废弃时间模式相关 i18n 与事件绑定逻辑。

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
```

## [2026-02-19] v2026.02.19.Sidebar-ActionRow-Visual-Harmonization
### Scope
- Refined sidebar visual hierarchy in `app_ui.py` with a unified dark-night palette.
- Reworked action controls into one compact row: `Activate | Reset | Stop`.

### Key Updates
- Added dedicated button keys and key-scoped styling:
  - `activate_btn` (primary blue gradient)
  - `reset_btn` (secondary deep navy)
  - `interrupt_current_run_btn` (danger red gradient)
- Enforced equal button height and single-line labels for alignment consistency.
- Fixed low-contrast issues in `Test Cases` expander:
  - case query text color changed to high-contrast light blue
  - expander body/button typography and controls forced to readable contrast
- Harmonized sidebar select/uploader contrast:
  - model select text now always light on dark background
  - uploader button/dropzone colors aligned with sidebar palette

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
- Playwright checks confirmed:
  - action buttons are horizontally aligned and visually differentiated
  - model select text color is readable (`rgb(231, 241, 255)`)
  - expander inner texts/buttons are high-contrast on dark surfaces

## [2026-02-19] v2026.02.19.Sidebar-Expanded-Header-Contrast-Fix
### Scope
- Fixed sidebar expander headers occasionally turning light/white after expansion, causing low contrast text.

### File
- `app_ui.py`

### Key Fix
- Added high-specificity sidebar expander header overrides for all states:
  - `summary`
  - `details > summary`
  - `details[open] > summary`
- Forced dark gradient header background, light text/icon color, and consistent border/border-radius behavior on open state.
- Prevented nested expander headers (e.g., `Test Cases > Data Retrieval...`) from inheriting light background styles.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
- Playwright runtime CSS check:
  - expanded headers now keep dark gradient background
  - text stays readable (`rgb(219, 232, 255)`) across nested expanders

## [2026-02-18] v2026.02.18.24 GEE-Table-Fallback-Warning-For-Old-Backend
### 目标
- 在后端仍为旧版本（`/api/latest` 未返回 `gee_rows`）时，避免表格静默缺失 GEE 行。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### 关键变更
- `mergeRowsWithGee(payload)` 新增兼容分支：
  - 当 `payload.gee_rows` 为空/缺失时，表格顶部插入提示行：
    - `GEE (no gee_rows in /api/latest; restart monitor_server)`
- 这样用户可以直接识别“需重启后端进程”而不是误以为无 GEE 数据。

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
```

## [2026-02-18] v2026.02.18.25 Boundary-Fallback-Chain-And-Cascaded-StudyArea-Selectors
### 目标
- 边界获取在 AMap/OSM 失败时继续回退到 GEE，提升鲁棒性。
- 研究区域改为国家 -> 省/州 -> 市级的渐进式下拉交互。

### 修改文件
- `experiments/official_daily_ntl_fastpath/boundary_resolver.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `tests/official_daily_fastpath/test_boundary_naming.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增边界回退链路：
  - 中国优先：`amap -> osm -> gee`
  - 非中国优先：`osm -> amap -> gee`
- 新增 GEE 边界回退实现（FAO/GAUL level0/1/2）。
- 前端“研究区域”改为三级级联：
  - 国家、省/州、市级下拉
  - 查询/下载统一取最细粒度：市级优先，其次省/州，再次国家
- 修复并重写 `test_boundary_naming.py`，补充回退链顺序测试（含非目标变体）。

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/boundary_resolver.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`30 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/boundary_resolver.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-18] v2026.02.18.26 Official-StudyArea-Catalog-From-GAUL-And-Cascaded-Dropdowns
### 目标
- 用官方数据补全研究区域列表。
- 研究区域改为国家 -> 省/州 -> 市级的渐进式级联，并支持动态加载。

### 修改文件
- `experiments/official_daily_ntl_fastpath/study_area_catalog.py`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `tests/official_daily_fastpath/test_study_area_catalog.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增 `/api/study_areas`：
  - 数据源：`FAO/GAUL/2015`（GEE）
  - 支持参数：`country`、`province`
  - 返回：`countries/provinces/cities`
- 前端研究区域改为级联下拉：
  - 国家变化后动态加载省/州
  - 省/州变化后动态加载市级
  - 查询与下载统一使用最细粒度值（市 > 省 > 国家）
- 加入回退机制：
  - 若 `/api/study_areas` 调用失败，自动回退到本地内置列表（不阻断操作）。
- 新增 catalog 名称清洗与去重逻辑及单测。

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/study_area_catalog.py experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/boundary_resolver.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`32 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/study_area_catalog.py experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/boundary_resolver.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-18] v2026.02.18.27 StudyArea-List-Completeness-Boost-And-Source-Status
### 目标
- 解决“研究区域列表不完整”的可见问题。
- 明确当前列表来源（官方 GAUL 或回退列表）。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/study_area_catalog.py`
- `docs/Codex_变更记录.md`

### 关键变更
- `/api/study_areas` 拉取上限提升：默认 `2000`，最大 `10000`，减少列表截断。
- 前端调用 `/api/study_areas` 时固定携带 `limit=2000`。
- 研究区域级联下拉下方新增状态文本：
  - 官方目录：显示国家/省州/市级条目数
  - 回退目录：显示“有限列表”提示
- 回退列表增强：
  - 中国省级改为全量省级行政区（含直辖市/自治区/特别行政区/台湾）
  - 增加各省代表城市，减轻接口失败时的“太少”问题

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/study_area_catalog.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath`
- 结果：`32 passed`。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py experiments/official_daily_ntl_fastpath/study_area_catalog.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath
```

## [2026-02-19] v2026.02.19.01 Download-404-Diagnostic-Message
### 目标
- 当下载接口返回 404 时，给出可操作的诊断提示，避免用户只看到 `HTTP 404`。

### 修改文件
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### 关键变更
- `downloadDataFile()` 中对 `res.status === 404` 增加专门错误文本：
  - `download API route not found. Please restart monitor_server.py with latest code.`

### 验证结果
- 命令：`node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- 结果：通过（exit 0）。

### 复现命令
```bash
node --check experiments/official_daily_ntl_fastpath/web_ui/main.js
```

## [2026-02-19] v2026.02.19.02 Fix-MonitorServer-GEE-Project-Import
### 目标
- 修复 `/api/download_data` 在 GEE 分支中 `DEFAULT_GEE_PROJECT` 未定义的问题。

### 修改文件
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 在 GEE 下载分支补充：
  - `from experiments.official_daily_ntl_fastpath.gee_baseline import DEFAULT_GEE_PROJECT`

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py`
- 结果：通过（exit 0）。

### 复现命令
```bash
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/monitor_server.py
```

## [2026-02-19] v2026.02.19.03 Router-ZonalStats-SmallRange-DirectDownload
### 目标
- 将 `zonal_stats` 小规模任务（`image_count <= 6`）统一路由到 `direct_download`，覆盖年/月/日三种时间尺度。
- 保持大规模 `zonal_stats` 仍走 `gee_server_side`，避免过度放宽。

### 修改文件
- `tools/GEE_specialist_toolkit.py`
- `agents/NTL_Data_Searcher.py`
- `tests/test_gee_router_execution_mode.py`
- `docs/Codex_变更记录.md`

### 关键变更
- `tools/GEE_specialist_toolkit.py`:
  - 在 `_execution_mode()` 中新增优先规则：
    - 当 `analysis_intent == "zonal_stats"` 且 `estimated_image_count <= 6` 时，返回 `direct_download`。
  - 保留原有大任务路由逻辑（`zonal_stats > 6` 仍可走 `gee_server_side`）。
- `agents/NTL_Data_Searcher.py`:
  - 在 GEE 路由协议中补充一致性约束：
    - `zonal_stats` 且 `estimated_image_count <= 6` 时，优先 `direct_download`（年/月/日通用）。
- `tests/test_gee_router_execution_mode.py`:
  - 新增覆盖：
    - `annual` + `zonal_stats` + 1 景 -> `direct_download`
    - `monthly` + `zonal_stats` + 6 景 -> `direct_download`
    - `daily` + `zonal_stats` + 6 景（flood 变体）-> `direct_download`
    - `daily` + `zonal_stats` + 7 景 -> `gee_server_side`

### 验证结果
- 命令：`conda run -n NTL-GPT pytest -q tests/test_gee_router_execution_mode.py tests/test_data_searcher_prompt_constraints.py`
- 结果：`15 passed`。

### 复现命令
```bash
conda run -n NTL-GPT pytest -q tests/test_gee_router_execution_mode.py tests/test_data_searcher_prompt_constraints.py
```

## [2026-02-19] v2026.02.19.04 Add-Amap-GEE-ZonalStats-Template-Into-CodeGuide
### 目标
- 将“`Amap` 行政边界 + `GEE` 年度 NTL 分区统计”沉淀为可复用模板，纳入代码知识库候选语料（人工审核路径）。

### 修改文件
- `RAG/code_guide/Geospatial_Code_GEE/amap_boundary_gee_zonal_stats_template.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增标准模板脚本，覆盖完整流程：
  - `storage_manager.resolve_input_path` 读取 Amap 边界 Shapefile
  - `ee.ImageCollection("projects/sat-io/open-datasets/npp-viirs-ntl")` + `band="b1"`
  - `reduceRegions` 计算每个行政区 `ANTL`
  - 导出 `outputs/*.csv`
- 该模板与自动运行归档（`RAG/code_guide/tools_latest_runtime/*`）分离，便于人工筛选后进入长期知识资产。

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile RAG/code_guide/Geospatial_Code_GEE/amap_boundary_gee_zonal_stats_template.py`
- 结果：通过（exit 0）。

### 复现命令
```bash
conda run -n NTL-GPT python -m py_compile RAG/code_guide/Geospatial_Code_GEE/amap_boundary_gee_zonal_stats_template.py
```

## [2026-02-19] v2026.02.19.05 Curate-ToolsLatestRuntime-And-Ingest-CodeRAG
### 目标
- 对 `RAG/code_guide/tools_latest_runtime` 做“成功且有效”人工筛选辅助，按同类任务保留最完整脚本。
- 将精选脚本复制到独立目录并写入 `Code_RAG`，避免噪音样本（如 dedupe/repeat_fail 回归脚本）污染检索。

### 修改文件
- `scripts/curate_runtime_to_code_rag.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增脚本 `scripts/curate_runtime_to_code_rag.py`：
  - 扫描 `tools_latest_runtime/*.py + *.meta.json`
  - 依据代码结构、运行日志、任务关键词进行评分与分类
  - 同类保留 Top-N（本次使用 `--max-per-category 1`）
  - 自动同步 `tools_latest_runtime_curated`（清理陈旧文件）
  - 可直接写入 `Code_RAG`（`doc_type=runtime_template`, `source_bucket=tools_latest_runtime_curated`）
  - 使用内容哈希去重，避免重复入库
- 本次执行结果：
  - 候选：`51`
  - 精选：`7`
  - 写入目录：`RAG/code_guide/tools_latest_runtime_curated`
  - 入库新增：首次 `+16` 文档；复跑后去重新增 `+0`

### 产物
- 筛选报告：`reports/runtime_code_curation_report.json`
- 精选目录：`RAG/code_guide/tools_latest_runtime_curated`

### 验证结果
- 命令：`conda run -n NTL-GPT python scripts/curate_runtime_to_code_rag.py --max-per-category 1 --ingest --report-path reports/runtime_code_curation_report.json`
- 结果：执行成功，报告生成并完成入库。
- 命令：`conda run -n NTL-GPT python -c "from langchain_chroma import Chroma; from langchain_openai import OpenAIEmbeddings; from dotenv import load_dotenv; load_dotenv(); store=Chroma(collection_name='Code_RAG', persist_directory=r'RAG/Code_RAG', embedding_function=OpenAIEmbeddings(model='text-embedding-3-small')); col=store._collection; print('total', col.count()); print('curated_docs', len(col.get(where={'source_bucket':'tools_latest_runtime_curated'}, include=['metadatas']).get('ids', [])))"`
- 结果：`Code_RAG total=1136`，其中 `tools_latest_runtime_curated=17`。

### 复现命令
```bash
conda run -n NTL-GPT python scripts/curate_runtime_to_code_rag.py --max-per-category 1 --ingest --report-path reports/runtime_code_curation_report.json
```

## [2026-02-19] v2026.02.19.06 GeoCode-Recipes-Runtime-Hybrid-Refresh
### 目标
- 更新 `GeoCode_Knowledge_Recipes_tool`，在不臃肿的前提下利用精选 runtime 脚本。
- 保留静态 recipe 稳定性，同时按需注入 `tools_latest_runtime_curated` 的已验证模板。

### 修改文件
- `tools/geocode_knowledge_tool.py`
- `tests/test_geocode_knowledge_tool_runtime_mix.py`
- `docs/Codex_变更记录.md`

### 关键变更
- `GeoCodeKnowledgeInput` 新增参数：
  - `include_runtime: bool = True`
- recipe 体系升级为“静态 + runtime 混合池”：
  - 新增 fastpath 静态 recipe：`gee_annual_zonal_antl_fastpath`
    - 对齐当前工程实践：Amap 边界 + NPP-VIIRS-Like + workspace 文件协议
  - 原 `gee_annual_zonal_antl` 保留为 `legacy` 示例，避免硬中断旧提示记忆
  - 从 `RAG/code_guide/tools_latest_runtime_curated/*.py` 动态读取 runtime 模板（缓存）
- 轻量化控制（避免输出臃肿）：
  - runtime 代码自动截断（`RUNTIME_CODE_MAX_CHARS=2600`）
  - 返回 `full_code_path` 指向完整脚本
  - payload 增加 `recipe_pool` 统计（static/runtime/selected_runtime）
- 排序策略：
  - 维持关键词匹配为主
  - 对 `runtime_curated` 增加轻微优先分（+2），只做同分倾斜，不会压制强匹配静态 recipe

### 测试与验证
- 新增：`tests/test_geocode_knowledge_tool_runtime_mix.py`
  - `include_runtime=True` 时可纳入 runtime 池
  - `include_runtime=False` 时仅静态 recipe
  - runtime 代码截断上限约束
- 命令：`conda run -n NTL-GPT pytest -q tests/test_geocode_knowledge_tool_runtime_mix.py`
- 结果：`3 passed`
- 命令：`conda run -n NTL-GPT python -m py_compile tools/geocode_knowledge_tool.py scripts/curate_runtime_to_code_rag.py tests/test_geocode_knowledge_tool_runtime_mix.py`
- 结果：通过（exit 0）

### 复现命令
```bash
conda run -n NTL-GPT pytest -q tests/test_geocode_knowledge_tool_runtime_mix.py
conda run -n NTL-GPT python -m py_compile tools/geocode_knowledge_tool.py scripts/curate_runtime_to_code_rag.py tests/test_geocode_knowledge_tool_runtime_mix.py
```

## [2026-02-19] v2026.02.19.07 CodeAssistant-EngineerFirst-Trust-Rule
### 目标
- 优先信任 `NTL_Engineer` 的草稿方案，减少 `Code_Assistant` 不必要的 recipe 检索调用。

### 修改文件
- `agents/NTL_Code_Assistant.py`
- `tests/test_code_file_protocol_prompts.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 在 Code Assistant 执行顺序中新增硬约束 `Engineer-first trust rule (mandatory)`：
  - 首次执行前禁止调用 `GeoCode_Knowledge_Recipes_tool`
  - 仅在两种条件允许检索 recipe：
    1) 工程师草稿确实缺实现细节
    2) 执行失败且根因是“方法细节缺失”（而非数据/鉴权/路径问题）
  - 每个任务分支最多一次 recipe 检索，除非 Engineer 明确要求再次检索

### 测试与验证
- 更新 `tests/test_code_file_protocol_prompts.py` 断言上述规则存在，防止提示词回退。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_code_file_protocol_prompts.py tests/test_geocode_knowledge_tool_runtime_mix.py`
- 结果：`5 passed`

### 复现命令
```bash
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/test_code_file_protocol_prompts.py tests/test_geocode_knowledge_tool_runtime_mix.py
```


## [2026-02-19] v2026.02.19.03 Fix-GEE-Computed-Geometry-GeoJSON-Serialization
### 目标
- 修复下载时报错：`Cannot convert a computed geometry to GeoJSON`。

### 修改文件
- `experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- `tests/official_daily_fastpath/test_gee_download_script.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 新增 `_serialize_region_for_download(geom)`：
  - 优先 `geom.toGeoJSONString()`
  - 失败时回退到 `json.dumps(geom.getInfo())`
- `getDownloadURL` 的 `region` 改为使用该序列化函数。
- 新增两条测试：
  - 计算几何触发异常时回退 `getInfo()`
  - 普通几何直接走 `toGeoJSONString()`

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py`
- 结果：通过（exit 0）。
- 命令：`$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/official_daily_fastpath/test_gee_download_script.py`
- 结果：`12 passed`。

### 复现命令
```bash
conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py
PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/official_daily_fastpath/test_gee_download_script.py
```

## [2026-02-19] v2026.02.19.08 Sidebar-Expander-Border-Transparency
### 目标
- 提升侧边栏 `Data Availability In GEE` 与 `Test Cases` 折叠框边框观感，降低边框突兀感。

### 修改文件
- `app_ui.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 将侧边栏 expander 容器外边框透明度从 `rgba(121, 161, 255, 0.32)` 调整为 `rgba(121, 161, 255, 0.20)`。

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile app_ui.py`
- 结果：通过（exit 0）。

## [2026-02-19] v2026.02.19.09 Activate-Button-Match-Reset
### 目标
- 让侧边栏 `Activate` 按钮与 `Reset` 按钮颜色样式一致。

### 修改文件
- `app_ui.py`
- `docs/Codex_变更记录.md`

### 关键变更
- 将 `Activate` 按钮类型从 `type="primary"` 调整为 `type="secondary"`，与 `Reset` 统一。

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile app_ui.py`
- 结果：通过（exit 0）。

## [2026-02-19] v2026.02.19.10 Sidebar-ThreadStatus-And-Activate-Reminder-Contrast
### 目标
- 提升侧边栏 `Thread ID / Status` 可读性（同一行展示、白字高对比）。
- 将未激活提示 `Please click Activate...` 调整为白字高对比提示卡。

### 修改文件
- `app_ui.py`
- `Streamlit.py`
- `docs/Codex_变更记录.md`

### 关键变更
- `app_ui.py`
  - `Thread ID` 与 `Status` 合并到同一行渲染：`ntl-thread-status-row`
  - 去除 thread id 的 `<code>` 徽章样式，改为普通文本值显示
  - 状态文本使用 `ntl-status-text active/inactive` 高对比样式
- `Streamlit.py`
  - 未激活时由 `st.info(...)` 改为自定义深色卡片 + 白字提示（中英文）

### 验证结果
- 命令：`conda run -n NTL-GPT python -m py_compile app_ui.py Streamlit.py`
- 结果：通过（exit 0）。

## [2026-02-19] v2026.02.19.11 GitHub-Bootstrap-And-Safe-Publish
### 目标
- 将项目发布到 GitHub 仓库 `https://github.com/guihousun/NTL-GPT-Clone.git`。
- 确保“可运行项目基线”可推送，同时避免提交本地大数据、运行产物与凭据。

### 修改文件
- `.gitignore`
- `docs/Codex_变更记录.md`

### 关键变更
- 初始化并推送主分支：
  - `git init -b main`
  - `git remote add origin https://github.com/guihousun/NTL-GPT-Clone.git`
  - `git push -u origin main`
- 加强忽略规则，避免误传敏感/冗余内容：
  - 忽略本地数据与运行目录：`base_data/`、`user_data/`、`userdata_0217/`、`cache/`、`reports/`、`outputs/`、`utils/sessions/`、`experiments/**/workspace*`
  - 忽略 RAG 持久化向量库与压缩包：`RAG/Code_RAG/`、`RAG/Literature_RAG/`、`RAG/Solution_RAG/`、`RAG/RAG_Faiss/`、`RAG/*.zip`、`RAG/RAG.rar`
  - 忽略本地凭据：`tools/bigquery/*.json`
  - 忽略外部嵌套仓：`_external_refs/`

### 验证结果
- 命令：`git grep --cached -n "BEGIN PRIVATE KEY"`
- 结果：无命中（exit 1）。
- 命令：`git push -u origin main`
- 结果：成功，`main -> origin/main`。


## [2026-02-19] v2026.02.19.07 Searcher-Minimal-Patch-Qwen35Plus
### ??
- ???? `NTL_Knowledge_Base_Searcher` ????????????
- ??????? `openai:gpt-4.1-mini` ??? `qwen3.5-plus`?DashScope ??????
- ??? Code_RAG ????????? Code_RAG ??????

### ????
- `tools/NTL_Knowledge_Base_Searcher.py`

### ????
- ?? `init_chat_model` ? `ChatOpenAI`?
- ?? `_build_searcher_llm()`??? `DASHSCOPE_API_KEY` / `QWEN_API_KEY`?????
  - `base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"`
  - `model="qwen3.5-plus"`
- `agent()` ??????????????????????

### ??
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py`
- `conda run -n NTL-GPT python -m pytest -q tests/test_literature_searcher_model_provider.py`
- ???`1 passed`


## [2026-02-19] v2026.02.19.08 Reasoning-Flow-Node-Demo-And-Map
### ??
- ?????????????????
- ? `NTL_Knowledge_Base` ???????????
- ? Reasoning ??????? `Reasoning Map` ???????

### ????
- `app_ui.py`
- `app_logic.py`

### ????
- `app_ui.py`
  - ?? `NTL_Knowledge_Base_Searcher` ???????
    - `_build_kb_progress_nodes`
    - `_render_kb_progress_demo`
  - ??????????
    - `_escape_dot_label`
    - `_build_reasoning_dot`
    - `render_reasoning_map`
  - `render_kb_output` ???????? `globals()` ????????????? helper ?????
  - `render_content_layout` ???????????????????? `Reasoning Flow`??? `Reasoning Map`?
- `app_logic.py`
  - ?????????????? `Reasoning Map`?????????????

### ??
- `conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- `conda run -n NTL-GPT python -m pytest -q tests/test_kb_payload_normalization.py tests/test_kb_render_fallback_contract.py`
- `conda run -n NTL-GPT python -m pytest -q tests/test_app_runtime_resilience.py`
- ???`5 passed` + `4 passed`


## [2026-02-19] v2026.02.19.12 Interactive-Reasoning-Map-Cytoscape
### ??
- ?? Reasoning Map ??????????????????????????
- ???????????????? Tool ???????????

### ????
- `app_ui.py`
- `app_logic.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - `render_reasoning_map` ? `st.graphviz_chart` ??? `Cytoscape` ?????????????????????
  - ?????????????????
    - `_build_reasoning_graph_payload`
    - `_extract_tool_detail_nodes`
    - `_message_preview`
    - `_wrap_reasoning_label`
  - Tool ???? JSON payload ??? `steps`??? `Sub-step` ?????????????
  - ??????????????????????
- `app_ui.py` / `app_logic.py`
  - Reasoning ????????? `0.62/0.38` ??? `0.54/0.46`???????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_kb_payload_normalization.py tests/test_kb_render_fallback_contract.py tests/test_app_runtime_resilience.py`
- ???`9 passed in 2.98s`?


## [2026-02-19] v2026.02.19.13 Reasoning-Graph-Standalone-Tab-And-Tool-Return-Edge
### ??
- ? `Reasoning` ? `Map View` ?????? `Reasoning Graph` ????
- ???????????????`AI -> Tool -> AI`???????????

### ????
- `app_ui.py`
- `app_logic.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - `st.tabs` ? 3 ???? 4 ??`Reasoning / Reasoning Graph / Map View / Outputs`?
  - `Reasoning` ????????????
  - ???? `Reasoning Graph` ????????????????????????
  - ??????????`Tool` ???? `tool_call_edge` ? `return_edge` ??????? AI ??????????
- `app_logic.py`
  - ???????? `Reasoning` ?????????????????????????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_app_runtime_resilience.py`
- ???`4 passed in 2.53s`?


## [2026-02-19] v2026.02.19.14 Reasoning-Graph-Fullscreen-Handoff-Fix-And-Theme-Refresh
### ??
- ? `Reasoning Graph` ???????????
- ?? `transfer_to_code_assistant` ?????????? `Tool -> NTL_Engineer` ???????
- ???????????????????

### ????
- `app_ui.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - ?? `_infer_transfer_target_agent(tool_name)`??? `transfer_to_*` / `transfer_back_to_*` ???????
  - `_build_reasoning_graph_payload` ???
    - ?????`AI -> Tool -> AI(return)`
    - transfer ???`AI -> Tool -> TargetAI(handoff)`
  - ????? transfer ??? `AI -> AI` ?????????????
  - `render_reasoning_map` ??????????
    - `Fit` ?????
    - `Fullscreen` ??????????????????????
  - ??????? Tech Innovation ??????? + ?????/?????
- ??
  - ?? `tests/test_reasoning_graph_handoff_edges.py`?
    - ?? transfer_to_code_assistant ?? `handoff_edge` ???? `return_edge`
    - ??????????? `return_edge`

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py tests/test_reasoning_graph_handoff_edges.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`6 passed in 2.39s`?


## [2026-02-19] v2026.02.19.15 Reasoning-Graph-Streaming-Refresh
### ??
- ?? `Reasoning Graph` ?????????????????
- ??????????????????????

### ????
- `app_ui.py`
- `app_logic.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - ? `tab_reasoning_map` ?? `reasoning_graph_placeholder` ?????
  - ???? `not user_question` ????????????? `analysis_logs` ????
  - ??????????? `Streaming reasoning graph...` ???
  - `render_content_layout` ?? `handle_userinput` ??? `reasoning_graph_placeholder`?
- `app_logic.py`
  - `handle_userinput` ?????? `reasoning_graph_placeholder=None`?
  - ???? `delta_messages` ???????????????? `Reasoning Graph` ???

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`6 passed in 3.40s`?


## [2026-02-19] v2026.02.19.16 Reasoning-Graph-NameError-Hotfix
### ??
- ?? `Reasoning Graph` ??????`name 'name' is not defined`?

### ????
- `app_ui.py`
- `tests/test_reasoning_graph_render_no_nameerror.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - ???????????? f-string ????????
    - `cy.layout({ name: ... })` -> `cy.layout({{ name: ... }})`
- ??????
  - `tests/test_reasoning_graph_render_no_nameerror.py`
  - ?? `render_reasoning_map(...)` ?????? NameError??????? `components.html`?

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py tests/test_reasoning_graph_render_no_nameerror.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_render_no_nameerror.py tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`7 passed in 2.55s`?


## [2026-02-19] v2026.02.19.17 Reasoning-Graph-Visual-Refresh-And-Visibility-Reflow
### ??
- ?? `Reasoning Graph` ??????????????????
- ???????????????????/??????? tab ?????

### ????
- `app_ui.py`
- `tests/test_reasoning_graph_render_no_nameerror.py`
- `docs/Codex_????.md`

### ????
- ?????`app_ui.py`?
  - ?????????????????????????????
  - ??????????????????human/ai/tool/detail/system??
  - ????? metadata??? `Nodes`/`Edges` ???
- ????????`app_ui.py`?
  - ?? `runLayout()` + ???? `resize/fit`?60/220/700/1400ms??
  - ?? `MutationObserver`?`ResizeObserver`?`visibilitychange`?`window focus` ?????
  - ????????? tab ???????????
- ????
  - ?? `tests/test_reasoning_graph_render_no_nameerror.py`?
    - ???? HTML ??? `ResizeObserver` / `MutationObserver` / `visibilitychange` / ?? reflow ???

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py tests/test_reasoning_graph_render_no_nameerror.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_render_no_nameerror.py tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`8 passed in 2.86s`?


## [2026-02-19] v2026.02.19.18 Reasoning-Graph-Streaming-Stability-Mode
### ??
- ????? `Reasoning Graph` ???????
- ????????????????????????

### ????
- `app_ui.py`
- `app_logic.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - `render_reasoning_map(events, interactive=True)` ??????
    - `interactive=False`??? `st.graphviz_chart` ??????????????????
    - `interactive=True`??? Cytoscape ?????? Fit/Fullscreen??
  - ?? `_build_reasoning_dot(payload)` ?? Graphviz DOT ?????????
  - `Reasoning Graph` ????????`Interactive Graph Mode (Beta)`??????
- `app_logic.py`
  - ????????????? `interactive=False`??????????

### ????
- ????????????? iframe + JS ??????????? graphviz ???
- ???????? + ????????????????????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_render_no_nameerror.py tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`8 passed in 2.55s`?


## [2026-02-19] v2026.02.19.19 Remove-Interactive-Graph-Mode-Toggle
### ??
- ?? `Reasoning Graph` ??? `Interactive Graph Mode (Beta)` ?????????????????

### ????
- `app_ui.py`
- `docs/Codex_????.md`

### ????
- ?? `st.toggle("Interactive Graph Mode (Beta)")` UI ???
- ??????????? `render_reasoning_map(..., interactive=False)`??????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_render_no_nameerror.py tests/test_reasoning_graph_handoff_edges.py tests/test_app_runtime_resilience.py`
- ???`8 passed in 2.73s`?


## [2026-02-19] v2026.02.19.20 Reasoning-Graph-Balanced-Mode-Tool-Clustering
### ??
- ?? Reasoning Graph ?????????????????????????????????

### ????
- `app_ui.py`
- `app_logic.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `tests/test_reasoning_graph_tool_clustering.py`
- `tests/test_reasoning_graph_main_path_highlight.py`
- `tests/test_reasoning_graph_render_no_nameerror.py`
- `docs/Codex_????.md`

### ????
- `app_ui.py`
  - ????????????????
    - `_agent_node_id`
    - `_extract_tool_event`
    - `_cluster_consecutive_tools`
    - `_format_tool_cluster_label`
    - `_compute_main_path_edges`
  - `_build_reasoning_graph_payload(events, show_sub_steps=False)` ??????
    - `ToolEvent` ??????????
    - ?? Agent ?????????? `ToolCluster`
  - ?????????`#6,#7 Tool: xxx ? x2 ? last=success`?????+??+??????
  - ?? `show_sub_steps` ?????
    - ????? detail ??/?
    - ?????????? detail ??
  - `main_edge_ids` ?? payload?`_build_reasoning_dot` ?????????????????
- `app_ui.py`?Reasoning Graph tab?
  - ?? UI ???`Show Sub-steps`??? false??
  - ????????????? `show_sub_steps`?
- `app_logic.py`
  - `handle_userinput` ???? `reasoning_graph_show_sub_steps`?
  - ???????? `show_sub_steps` ? `render_reasoning_map(..., interactive=False, show_sub_steps=...)`?
- ??
  - ?? `tests/test_reasoning_graph_handoff_edges.py` ??? `tc_*` ???????
  - ?? `tests/test_reasoning_graph_tool_clustering.py`???????????xN?last_status????????
  - ?? `tests/test_reasoning_graph_main_path_highlight.py`??????????detail ????show_sub_steps ???
  - ?? `tests/test_reasoning_graph_render_no_nameerror.py` ???????????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_reasoning_graph_tool_clustering.py tests/test_reasoning_graph_main_path_highlight.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_graph_tool_clustering.py tests/test_reasoning_graph_main_path_highlight.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
- ???`13 passed in 3.19s`?

## [2026-02-19] v2026.02.19.21 Handoff-Back-Noise-Reduction-And-LangSmith-Alignment
### Scope
- Fix repeated `transfer_back_to_ntl_engineer` artifacts shown in reasoning graph.
- Reduce false-negative/false-error signals caused by supervisor-generated handoff-back control flow.

### Files
- `graph_factory.py`
- `app_ui.py`
- `scripts/langgraph_case_runner.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `tests/test_langgraph_case_runner_parsing.py`

### Changes
- Set `create_supervisor(..., add_handoff_back_messages=False)` in `graph_factory.py`.
- Filter synthetic handoff-back messages (`response_metadata.__is_handoff_back == true`) in `app_ui.py` reasoning-section builder.
- Ignore synthetic handoff-back control messages in `scripts/langgraph_case_runner.py` message analysis.
- Added regression tests to guarantee synthetic handoff-back is excluded from graph/statistics.

### Verification
- `python -m py_compile graph_factory.py app_ui.py scripts/langgraph_case_runner.py`
- `PYTHONPATH=. conda run -n NTL-GPT pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_langgraph_case_runner_parsing.py`
- Result: `6 passed`.

## [2026-02-19] v2026.02.19.22 Official-Daily-Monitor-3D-Orbit-Mode
### Scope
- Embed 3D Earth orbit monitoring into existing official_daily_ntl_fastpath monitor page.
- Keep existing 2D Leaflet/GIBS workflow intact; add 2D/3D switch in right panel.

### Files
- `experiments/official_daily_ntl_fastpath/orbit_registry.py`
- `experiments/official_daily_ntl_fastpath/orbit_service.py`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `tests/official_daily_fastpath/test_orbit_registry.py`
- `tests/official_daily_fastpath/test_orbit_service_fallback.py`
- `tests/official_daily_fastpath/test_orbit_feed_api.py`
- `docs/NTL-GPT_项目介绍_最新版.md`

### Changes
- Added fixed orbit-slot registry for 5 NTL-related slots:
  - `snpp_viirs` (37849), `noaa20_viirs` (43013), `noaa21_viirs` (54234), `sdgsat1` (49387), `luojia_slot` (43035).
- Added fallback chain for `luojia_slot` when LUOJIA TLE unavailable:
  - `35951 -> 29522 -> 28054`.
- Added orbit feed service with online CelesTrak fetch + local cache:
  - Cache file: `experiments/official_daily_ntl_fastpath/workspace_monitor/cache/orbit_feed.json`
  - Supports stale-cache degradation.
- Added new API endpoint:
  - `GET /api/orbit_feed?force_refresh=0|1&ttl_minutes=180`
- Frontend:
  - Added 2D/3D view switch.
  - Added Cesium lazy loading + satellite.js orbit propagation.
  - Added UTC full-day looping animation and controls (Play/Pause, 1x/60x/240x/600x, manual refresh).
  - Added orbit status feedback and explicit fallback legend display.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/orbit_registry.py experiments/official_daily_ntl_fastpath/orbit_service.py experiments/official_daily_ntl_fastpath/monitor_server.py`
- `$env:PYTHONPATH='.'; conda run --no-capture-output -n NTL-GPT pytest -q tests/official_daily_fastpath/test_orbit_registry.py tests/official_daily_fastpath/test_orbit_service_fallback.py tests/official_daily_fastpath/test_orbit_feed_api.py`
  - Result: `6 passed`
- `$env:PYTHONPATH='.'; conda run --no-capture-output -n NTL-GPT pytest -q tests/official_daily_fastpath/test_monitor_helpers.py tests/official_daily_fastpath/test_study_area_catalog.py`
  - Result: `7 passed`
- Orbit API smoke test:
  - `GET /api/orbit_feed?force_refresh=1`
  - Result: `slots=5`, `ok_or_fallback=5`, HTTP `200`.


## [2026-02-19] v2026.02.19.21 Disable-Show-Substeps-During-Run
### ??
- ???????????? `Show Sub-steps` ?? Streamlit rerun????? `thinking` ??/???

### ????
- `app_ui.py`
- `docs/Codex_????.md`

### ????
- ? `Reasoning Graph` ?? `Show Sub-steps` ??????????
  - ?? `is_running` ??
  - `is_running=True` ?????? `disabled=True`
  - ??????????????????????????
- ?????????????????????????????????

### ????
- ???`conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
- ??????exit 0??
- ???`conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_graph_main_path_highlight.py tests/test_reasoning_graph_tool_clustering.py tests/test_app_runtime_resilience.py`
- ???`9 passed in 2.70s`?

## [2026-02-21] v2026.02.21.01 Orbit-3D-Globe-Visibility-Fix
### Scope
- Fix 3D orbit view where users could not reliably see the globe body (only star/noise-like background or off-screen framing).
- Keep changes inside experiment workspace frontend only.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`

### Changes
- Added robust Cesium resize handling:
  - New `_resizeGlobeViewer()` and calls on 3D init, 3D mode switch, and window resize.
- Fixed layout sizing that could create oversized Cesium canvas:
  - `layout` fixed viewport height with internal panel scrolling.
  - `panel-map`/`view-stack` constrained to avoid canvas height explosion.
  - Control grid updated to reduce horizontal overflow on narrower screens.
- Improved 3D scene visibility defaults:
  - Disabled skybox/sky atmosphere to reduce misleading background noise.
  - Switched base imagery to Cesium bundled `NaturalEarthII` texture.
  - Added stable global camera setView for full-globe startup.
- Exposed `window.__ntl_globe` for easier runtime debugging.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
- Manual browser validation (`http://127.0.0.1:8765`):
  - Switch to `三维轨道`.
  - Confirm orbit status loads and globe body is visible.


## [2026-02-21] v2026.02.21.xx Tavily-IncludeDomains-Normalization
### Scope
- Fixed frequent `tavily_search` failures caused by invalid `include_domains`/`exclude_domains` argument types.

### Files
- `tools/TavilySearch.py`
- `agents/NTL_Data_Searcher.py`
- `tests/test_tavily_search_input_normalization.py`
- `tests/test_tavily_search_fallback_behavior.py`
- `tests/test_data_searcher_prompt_constraints.py`

### Changes
- Replaced direct Tavily tool export with a safe wrapper tool while keeping external tool name `tavily_search` unchanged.
- Added robust domain normalization supporting:
  - native list
  - JSON list string
  - comma-separated string
- Added graceful fallback: invalid domain filters are dropped without failing the whole query.
- Added lightweight diagnostics in tool output:
  - `normalized_domains_applied`
  - `domain_filter_dropped_reason` (when fallback occurs)
- Added Data_Searcher prompt constraints:
  - Only pass `include_domains` when explicitly needed.
  - Pass native list values instead of stringified lists.

### Verification
- `conda run --no-capture-output -n NTL-GPT pytest -q tests/test_tavily_search_input_normalization.py tests/test_tavily_search_fallback_behavior.py tests/test_data_searcher_prompt_constraints.py`
  - Result: `12 passed`
- `conda run --no-capture-output -n NTL-GPT python -m py_compile tools/TavilySearch.py agents/NTL_Data_Searcher.py tests/test_tavily_search_input_normalization.py tests/test_tavily_search_fallback_behavior.py`
  - Result: `exit 0`

## [2026-02-21] v2026.02.21.03 Orbit-3D-Center-Lock-Stabilization
### Scope
- Fix 3D globe drifting/off-center behavior during orbit rendering and refresh.
- Keep the globe visually centered and prevent random camera orientation changes.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`

### Changes
- Replaced center logic from `camera.viewBoundingSphere(center=Earth center)` to deterministic camera framing:
  - Fixed destination in ECEF space (`radius * ORBIT_CENTER_RANGE_FACTOR` on +X axis).
  - Fixed orientation vectors (`direction` toward Earth center + corrected `up`).
- Explicitly cleared `trackedEntity` before setting camera to avoid unexpected follow behavior.
- Retained locked camera controller settings (rotate/zoom/tilt/look disabled).

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`

## [2026-02-21] v2026.02.21.04 Orbit-Center-HardLock-And-Nightlight-Only
### Scope
- Fixed persistent 3D camera drift toward polar regions by adding stronger camera lock enforcement.
- Limited orbit feed policy to nightlight satellites only (removed non-target fallback replacement display).

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `experiments/official_daily_ntl_fastpath/orbit_registry.py`
- `experiments/official_daily_ntl_fastpath/orbit_service.py`
- `tests/official_daily_fastpath/test_orbit_registry.py`
- `tests/official_daily_fastpath/test_orbit_service_fallback.py`

### Changes
- 3D camera stabilization:
  - Disabled all Cesium camera inputs via `enableInputs=false` plus rotate/zoom/tilt/look off.
  - Added deterministic camera pose check and preRender center guard (`_attachGlobeCameraLock`) to reset when any drift occurs.
  - Kept fixed Earth-centered pose for orbit view.
- Orbit source policy:
  - Removed `LUOJIA -> DMSP` fallback chain from registry.
  - Corrected corrupted Chinese slot labels in orbit registry file (UTF-8 content).
  - Added `slot_policy` versioning in orbit feed cache to invalidate old cached fallback payloads automatically.
- Tests:
  - Updated registry test to assert LUOJIA has no fallback chain.
  - Updated orbit service test to assert LUOJIA becomes `unavailable` (instead of `fallback`) when TLE missing.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/orbit_registry.py experiments/official_daily_ntl_fastpath/orbit_service.py experiments/official_daily_ntl_fastpath/monitor_server.py`
  - Result: `exit 0`
- `$env:PYTHONPATH='.'; conda run --no-capture-output -n NTL-GPT pytest -q tests/official_daily_fastpath/test_orbit_registry.py tests/official_daily_fastpath/test_orbit_service_fallback.py tests/official_daily_fastpath/test_orbit_feed_api.py`
  - Result: `6 passed`

## [2026-02-21] v2026.02.21.05 KB-Streaming-Progress-And-Graph-Overlay
### Scope
- Implemented true streaming progress for `NTL_Knowledge_Base` to eliminate long retrieval vacuum periods.
- Synced live progress to both `Reasoning` and `Reasoning Graph` views.

### Files
- `tools/NTL_Knowledge_Base_Searcher.py`
- `app_logic.py`
- `app_ui.py`
- `tests/test_kb_stream_progress_events.py`
- `tests/test_app_logic_custom_stream_ingest.py`
- `tests/test_reasoning_graph_kb_progress_overlay.py`
- `tests/test_reasoning_progress_snapshot.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `tests/test_reasoning_graph_tool_clustering.py`
- `tests/test_reasoning_graph_main_path_highlight.py`
- `tests/test_reasoning_graph_render_no_nameerror.py`

### Changes
- Tool-side streaming events:
  - Added `kb_progress` custom events in `NTL_Knowledge_Base_Searcher` with phases:
    - `query_received`
    - `knowledge_retrieval`
    - `workflow_assembly`
    - `structured_output`
  - Added error-phase emission on exceptions.
- Runtime stream ingestion:
  - Extended `app_logic._iter_events` to include `custom` stream mode.
  - Added custom-event branch in `handle_userinput` to append progress into `analysis_logs` and refresh UI panels immediately.
- UI rendering:
  - Added live KB phase aggregation helpers.
  - Rendered streaming KB progress card in `Reasoning` as a real-time tool-output block.
  - Added temporary KB progress nodes in `Reasoning Graph` before final KB tool message is returned.
  - Auto-hide temporary KB progress nodes once final `NTL_Knowledge_Base` tool output appears.
- Stability fixes in KB searcher file:
  - Repaired malformed lines causing syntax/indentation failures in `tools/NTL_Knowledge_Base_Searcher.py`.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_kb_stream_progress_events.py tests/test_app_logic_custom_stream_ingest.py tests/test_reasoning_graph_kb_progress_overlay.py tests/test_reasoning_progress_snapshot.py tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_graph_tool_clustering.py tests/test_reasoning_graph_main_path_highlight.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
  - Result: `20 passed`
- `python -m py_compile tools/NTL_Knowledge_Base_Searcher.py app_logic.py app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.yy Engineer-QuickCheck-Tool-Alignment
### Scope
- Aligned Engineer tool registry with current handoff workflow requirements.

### Files
- `tools/__init__.py`
- `tests/test_engineer_tool_registry.py`

### Changes
- Added `geodata_quick_check_tool` to `Engineer_tools` so NTL_Engineer can perform lightweight pre-handoff file/boundary validation directly.
- Kept `geodata_inspector_tool` in `Code_tools` only to preserve lean role boundaries and avoid unnecessary Engineer-side heavy inspection calls.
- Added AST-based registry tests to lock tool-boundary behavior.

### Verification
- `conda run --no-capture-output -n NTL-GPT pytest -q tests/test_engineer_tool_registry.py tests/test_ntl_engineer_prompt_constraints.py`
  - Result: `7 passed`
- `C:\Users\HONOR\miniconda3\envs\NTL-GPT\python.exe -m py_compile tools/__init__.py tests/test_engineer_tool_registry.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.zz Auto-Return-Handoff-Contract-Fix
### Scope
- Fixed Engineer/Data_Searcher/Code_Assistant handoff contract mismatch causing invalid transfer-back tool errors and Code_Assistant idle handoff behavior.

### Files
- `agents/NTL_Data_Searcher.py`
- `agents/NTL_Code_Assistant.py`
- `agents/NTL_Engineer.py`
- `tests/test_data_searcher_prompt_constraints.py`
- `tests/test_code_file_protocol_prompts.py`
- `tests/test_ntl_engineer_prompt_constraints.py`

### Changes
- Switched Data_Searcher completion protocol from explicit `transfer_back_to_ntl_engineer` calls to supervisor auto-return via final structured JSON response.
- Updated Code_Assistant convergence/escalation protocol to return structured payloads directly (success / `needs_engineer_decision`) and explicitly avoid `transfer_back_to_ntl_engineer` calls.
- Added Engineer-side **handoff packet guard** before `transfer_to_code_assistant`:
  - required fields: `draft_script_name`, `draft_code`, `required_inputs`, `expected_outputs`, `execution_objective`
  - if incomplete, Engineer must not transfer.
- Added Engineer instruction to avoid post-handoff filler waiting messages.
- Updated prompt-contract tests to match new auto-return protocol and handoff guard constraints.

### Verification
- `conda run --no-capture-output -n NTL-GPT pytest -q tests/test_data_searcher_prompt_constraints.py tests/test_code_file_protocol_prompts.py tests/test_ntl_engineer_prompt_constraints.py`
  - Result: `13 passed`
- `C:\Users\HONOR\miniconda3\envs\NTL-GPT\python.exe -m py_compile agents/NTL_Data_Searcher.py agents/NTL_Code_Assistant.py agents/NTL_Engineer.py tests/test_data_searcher_prompt_constraints.py tests/test_code_file_protocol_prompts.py tests/test_ntl_engineer_prompt_constraints.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.06 ReasoningGraph-ToolLabel-Refine-And-Transfer-Skip
### Scope
- Refined Reasoning Graph tool labels and simplified transfer visualization.

### Files
- `app_ui.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `tests/test_reasoning_graph_tool_clustering.py`
- `tests/test_reasoning_graph_kb_progress_overlay.py`

### Changes
- Label policy updates:
  - Removed noisy `last=unknown` and `last=ok` from tool labels.
  - `last=` now appears only for `{fail,error,escalate,running}`.
  - Kept `Tool:` prefix for regular tools.
  - Removed `Tool:` prefix for `NTL_Knowledge_Base` labels.
- Transfer visualization updates:
  - `transfer_to_*` / `transfer_back_*` tool nodes are no longer rendered as standalone nodes.
  - Graph now draws direct `handoff_edge` between source agent and target agent for transfer steps.
- Styling updates:
  - Retained special style hooks for `tool_kb` (and `tool_transfer` fallback) to keep semantic differentiation.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_graph_tool_clustering.py tests/test_reasoning_graph_kb_progress_overlay.py tests/test_reasoning_graph_main_path_highlight.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
  - Result: `17 passed`
- `python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.07 ReasoningGraph-AutoReturn-Handoff-And-x1-Hide
### Scope
- Fixed missing auto-return edge from `Code_Assistant` back to `NTL_Engineer`.
- Simplified single-call tool labels by hiding `| x1`.

### Files
- `app_ui.py`
- `tests/test_reasoning_graph_handoff_edges.py`
- `tests/test_reasoning_graph_tool_clustering.py`

### Changes
- Graph transition logic:
  - In AI-to-AI transitions, render inferred `handoff_edge` when agent changes (covers supervisor auto-return cases without explicit transfer-back tool nodes).
  - Keeps non-AI transitions as `flow`.
- Tool cluster label policy:
  - `| xN` is shown only when `N > 1`.
  - Single-call nodes now display without count suffix.
- Added tests:
  - `Code_Assistant -> NTL_Engineer` auto-return handoff edge is present.
  - Single-call tool labels do not include `| x1`.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_graph_tool_clustering.py tests/test_reasoning_graph_main_path_highlight.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
  - Result: `16 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.08 KB-Output-Dedup-And-Progress-Panel-Slim
### Scope
- Removed duplicate `Tool Output: NTL_Knowledge_Base` blocks in Reasoning view.
- Simplified KB progress panel by removing repeated gray helper lines.

### Files
- `app_ui.py`

### Changes
- `render_reasoning_content`:
  - Added final-KB detection (`has_final_kb_tool`).
  - When final KB tool output exists, streaming `kb_progress` section is skipped to avoid duplicate tool-output expanders.
- `_render_kb_progress_nodes`:
  - Kept only stage title row by default.
  - Gray detail text is now shown only for error phases.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_reasoning_graph_kb_progress_overlay.py tests/test_reasoning_graph_handoff_edges.py tests/test_reasoning_progress_snapshot.py tests/test_app_runtime_resilience.py`
  - Result: `12 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.09 KB-SystemPrompt-Retrieval-Budget-Only
### Scope
- Applied a prompt-only routing constraint update for `NTL_Knowledge_Base_Searcher` (no logic refactor).

### Files
- `tools/NTL_Knowledge_Base_Searcher.py`

### Changes
- Updated the **Tool Selection** section in system prompt to enforce:
  - `NTL_Solution_Knowledge` priority first.
  - Default retrieval budget of **1-2 stores** (avoid querying all 3 by default).
  - Second store selection by mode:
    - `theory` -> `NTL_Literature_Knowledge`
    - `workflow/code/mixed/auto` -> `NTL_Code_Knowledge`
  - Single-store retrieval when Solution results are already high-confidence.
- No changes to runtime graph, tool binding logic, or output contract.

### Verification
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.10 KB-Disable-Fallback-Tool-Scoring
### Scope
- Disabled fallback tool scoring/replacement so workflow step names are no longer auto-overridden by heuristic inference.

### Files
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tests/test_kb_workflow_force_json.py`
- `tests/test_literature_query_routing_policy.py`

### Changes
- Disabled `_infer_tool_from_intent` scoring path (returns empty by policy).
- Disabled `_infer_tool_from_query` query-hardcoded mapping path (returns empty by policy).
- Removed invalid-step auto-rewrite behavior in workflow normalization:
  - no more bulk replacement of placeholder/invalid builtin tool names using inferred fallback tools.
  - invalid tool names now directly return `status: no_valid_tool` with explicit reason.
- Non-event plain-text `force_json` path now yields `no_valid_tool` instead of generating a guessed single-tool workflow.
- Event-impact fallback workflow generation remains unchanged.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_kb_workflow_force_json.py::test_workflow_validation_forces_json_when_model_returns_plain_text tests/test_kb_workflow_force_json.py::test_workflow_validation_builds_multistep_event_gee_fallback tests/test_literature_query_routing_policy.py::test_infer_tool_from_query_handles_official_earthquake_source_query tests/test_literature_query_routing_policy.py::test_infer_tool_from_query_generalizes_to_other_event_types`
  - Result: `4 passed`
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py tests/test_kb_workflow_force_json.py tests/test_literature_query_routing_policy.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.09 AI-Readability-Light-Polish
### Scope
- Improved AI reply readability while keeping the existing green NTL visual style.
- Applied consistent readability tweaks to AI markdown/table/code and output panel code/table blocks.

### Files
- `app_ui.py`
- `tests/test_ui_ai_readability_css_contract.py`

### Changes
- Added AI-specific CSS tokens in `:root`:
  - `--ntl-ai-bg-1`, `--ntl-ai-bg-2`, `--ntl-ai-text`, `--ntl-ai-muted`
  - `--ntl-ai-border`, `--ntl-ai-code-bg`, `--ntl-ai-code-text`
  - `--ntl-ai-table-border`, `--ntl-ai-table-head-bg`
- Refined `.chat-message.bot`:
  - Slightly brighter green gradient, subtle border, improved body typography (`1.00rem`, `line-height 1.62`, weight `500`).
- Unified bot markdown readability scope:
  - headings / strong / links / code / table in `.chat-message.bot .message` now use consistent contrast tokens.
- Added output-area readability scope in main panel:
  - code blocks and dataframe/table containers use harmonized border/background/text contrast.
- Reduced CSS conflict in main panel select styling by removing duplicated conflicting dark rule and keeping a single readable contrast rule.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py tests/test_ui_ai_readability_css_contract.py`
  - Result: `7 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.10 Reasoning-CodeBlock-Contrast-Fix
### Scope
- Fixed low-contrast text in `Reasoning` area `st.code` blocks (content looked blank/faded).

### Files
- `app_ui.py`

### Changes
- Added output-specific code block tokens:
  - `--ntl-output-code-bg`
  - `--ntl-output-code-text`
  - `--ntl-output-code-border`
- Updated main-panel code block selectors (`stCodeBlock`/`stCode`) to enforce:
  - dark background
  - high-contrast light text
  - explicit border/radius on `pre` surfaces
- Kept scope limited to main content panel; sidebar styles remain unchanged.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_ui_ai_readability_css_contract.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
  - Result: `7 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.11 DataSearcher-Visual-Harmony-And-Undefined-Tail-Filter
### Scope
- Improved visual harmony in Data_Searcher cards (reduced black/white mismatch).
- Filtered noisy trailing literals like `undefined` from mixed payload rendering.

### Files
- `app_ui.py`
- `tests/test_ui_noise_tail_filter.py`

### Changes
- Added lightweight UI chip style:
  - `.ntl-info-chip` for `Product Identifier` and `Storage Location` fields.
  - Replaced heavy `st.code(...)` blocks in `render_data_searcher_output` with chip rendering.
- Added tail-noise filter helper:
  - `_is_noise_tail_text(...)` suppresses empty/noise residuals: `undefined/null/none/nan`.
- Applied residual filtering in:
  - `render_data_searcher_output`
  - `render_kb_output`
- Added function-local fallbacks for helper resolution to keep compatibility with tests that execute extracted functions in isolated scopes.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_ui_noise_tail_filter.py tests/test_ui_ai_readability_css_contract.py tests/test_kb_render_fallback_contract.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py`
  - Result: `11 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.12 Reasoning-AI-Render-Unification-And-EmptySkip
### Scope
- Unified `Code_Assistant` rendering style with other AI agents in Reasoning view.
- Prevented empty AI payloads from rendering blank cards.

### Files
- `app_ui.py`
- `tests/test_reasoning_ai_render_contract.py`

### Changes
- `render_reasoning_content` AI branch:
  - Added `effective_messages` buffer.
  - Skip messages where content is empty after `strip()`.
  - Skip entire AI section if all messages are empty.
- Removed `Code_Assistant` special-case `st.code(...)` rendering.
  - Now follows the same text-render path as `NTL_Engineer` (except `Data_Searcher` structured renderer remains unchanged).

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_reasoning_ai_render_contract.py tests/test_reasoning_graph_render_no_nameerror.py tests/test_app_runtime_resilience.py tests/test_kb_render_fallback_contract.py`
  - Result: `9 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-21] v2026.02.21.13 Sidebar-Rollback-And-Reasoning-MinFix
### Scope
- Rolled `app_ui.py` back to the baseline sidebar style state for this branch (per request).
- Applied only two reasoning-view behavior fixes:
  - remove `Code_Assistant Stage: ...` micro captions
  - skip empty AI message payload rendering (`strip()` empty)
- Kept first AI agent heading visible to avoid “all skipped” perception when initial payload is empty.

### Files
- `app_ui.py`
- `tests/test_reasoning_ai_render_contract.py`

### Changes
- `render_reasoning_content`:
  - added `effective_messages` filtering before rendering AI message bodies
  - if no effective message exists, keep agent title and skip empty body card
  - removed stage-caption rendering from tool section

### Verification
- `C:\\Users\\HONOR\\miniconda3\\envs\\NTL-GPT\\python.exe -m py_compile app_ui.py`
  - Result: `exit 0`
- Pytest invocation in this shell returned non-zero without visible traceback due local runtime/output encoding crash; compile succeeded and source-level assertions confirm:
  - `Code_Assistant Stage:` string removed
  - empty-message guard present


## [2026-02-21] v2026.02.21.13 KB-NoValidTool-Preserve-Agent-Step-Titles
### Scope
- Kept agent-authored step titles/descriptions when tool names are invalid, instead of dropping workflow details.

### Files
- `tools/NTL_Knowledge_Base_Searcher.py`
- `tests/test_kb_workflow_force_json.py`

### Changes
- Added `_build_non_executable_workflow_payload(...)`:
  - converts invalid `builtin_tool` steps into `analysis_step`.
  - preserves original step titles from agent output (`name/tool_name/action`) and step descriptions.
  - keeps optional `input` payload for context.
- Updated invalid-tool handling in `_validate_and_normalize_workflow_output(...)`:
  - no inferred replacement tool is applied.
  - returns `status: no_valid_tool` **with preserved workflow steps** instead of empty workflow.
- Extended tests:
  - added case to assert invalid tool names still preserve step titles as `analysis_step`.
  - improved local stub for `normalize_workflow_payload` to surface invalid builtin names in test harness.

### Verification
- `$env:PYTHONPATH='.'; conda run -n NTL-GPT pytest -q tests/test_kb_workflow_force_json.py tests/test_literature_query_routing_policy.py::test_infer_tool_from_query_handles_official_earthquake_source_query tests/test_literature_query_routing_policy.py::test_infer_tool_from_query_generalizes_to_other_event_types`
  - Result: `7 passed`
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py tests/test_kb_workflow_force_json.py`
  - Result: `exit 0`


## [2026-02-22] v2026.02.22.01 Reasoning-Graph-Tab-Restore
### Scope
- Restored missing `Reasoning Graph` map panel and streaming render linkage in UI.

### Files
- `app_ui.py`

### Changes
- Restored reasoning-graph foundations in `app_ui.py`:
  - Added missing helpers for reasoning graph rendering:
    - `_normalize_content_to_text`
    - `_truncate_text`
    - `_agent_node_id`
    - `_infer_transfer_target_agent`
    - `_build_reasoning_graph_payload`
    - `_escape_dot_label`
    - `_build_reasoning_dot`
    - `_json_for_html_script`
    - `render_reasoning_map`
- Enhanced `_build_reasoning_sections`:
  - Re-enabled `kb_progress` extraction from both `kb_progress` and `custom` events.
  - Ignored synthetic handoff-back metadata messages.
- Restored `Reasoning Graph` tab in `render_content_layout`:
  - Tab order now includes: `Reasoning`, `Reasoning Graph`, `Map View`, `Outputs`.
  - Added `Show Sub-steps` toggle state (`reasoning_graph_show_sub_steps`).
  - Added graph history/current render blocks.
  - Reconnected `handle_userinput(...)` with `reasoning_graph_placeholder` and `reasoning_graph_show_sub_steps`.
- Updated `render_reasoning_content`:
  - Re-enabled streaming `kb_progress` panel render in reasoning timeline.
  - Preserved duplicate suppression when final KB tool output exists.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -c "import app_ui; from langchain_core.messages import HumanMessage,AIMessage; p=app_ui._build_reasoning_graph_payload([{'messages':[HumanMessage(content='hi'),AIMessage(content='ok',name='NTL_Engineer')]}]); print('nodes',len(p['nodes']),'edges',len(p['edges']))"`
  - Result: `nodes 4 edges 3`


## [2026-02-22] v2026.02.22.02 Reasoning-Graph-KBProgress-NameError-Hotfix
### Scope
- Hotfix for runtime crash after handoff: missing KB progress helper functions in `app_ui.py`.

### Files
- `app_ui.py`

### Changes
- Added missing helpers required by reasoning stream rendering:
  - `_kb_phase_specs`
  - `_build_kb_progress_nodes_from_records`
  - `_render_kb_progress_nodes`
- This fixes runtime error:
  - `name '_build_kb_progress_nodes_from_records' is not defined`
- Preserved compact UI policy:
  - progress detail text remains displayed only for error phases.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -c "import app_ui; rec=[{'event_type':'kb_progress','phase':'query_received','status':'done'},{'event_type':'kb_progress','phase':'knowledge_retrieval','status':'running'}]; nodes=app_ui._build_kb_progress_nodes_from_records(rec); print('nodes',len(nodes),nodes[0]['key'],nodes[1]['key'])"`
  - Result: `nodes 4 query_received knowledge_retrieval`


## [2026-02-22] v2026.02.22.03 KB-Prompt-FString-Brace-Escape-Hotfix
### Scope
- Fixed runtime handoff failure caused by unescaped JSON braces in `NTL_Knowledge_Base_Searcher` system prompt f-string.

### Files
- `tools/NTL_Knowledge_Base_Searcher.py`

### Changes
- Escaped the instructional JSON example braces in prompt text:
  - from: `{"type": "instruction", "description": "..."}`
  - to: `{{"type": "instruction", "description": "..."}}`
- This prevents Python f-string format parsing errors:
  - `Invalid format specifier ... for object of type 'str'`

### Verification
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Knowledge_Base_Searcher.py`
  - Result: `exit 0`


## [2026-02-22] v2026.02.22.04 Reasoning-Graph-WhiteTheme
### Scope
- Switched Reasoning Graph to a white-background, dark-text visual style for readability.

### Files
- `app_ui.py`

### Changes
- Static graph (Graphviz):
  - Set graph background to white (`bgcolor="#ffffff"`).
  - Increased default edge contrast from light slate to medium slate.
- Interactive graph (Cytoscape):
  - Changed canvas container to white background with light-gray border.
  - Enforced node label text color to dark (`#111827`).
  - Adjusted default node/edge palette for white theme readability.
  - Kept semantic color distinction for human/ai/tool/tool_kb nodes and handoff/return edges.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-22] v2026.02.22.05 Reasoning-Graph-Force-Static
### Scope
- Unified Reasoning Graph rendering mode to static graph only.

### Files
- `app_ui.py`

### Changes
- Updated Reasoning Graph tab rendering calls to always pass `interactive=False`:
  - history graph block
  - current-run graph block
- Streaming path in `app_logic.py` was already using static render; now all UI entrypoints are aligned.
- No change to graph payload logic or step grouping logic.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py`
  - Result: `exit 0`


## [2026-02-22] v2026.02.22.06 Reasoning-Graph-Human-Node-Label-Simplify
### Scope
- Simplified the node label immediately after `START` to avoid long query text overflow.

### Files
- `app_ui.py`

### Changes
- In `_build_reasoning_graph_payload(...)`, human node label is now fixed to:
  - `Human Query`
- Removed inline question text from the human node label.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`


## [2026-02-22] v2026.02.22.07 Reasoning-Graph-Consecutive-Tool-Range-Label
### Scope
- Collapsed consecutive same-tool calls into one node with sequence range label.

### Files
- `app_ui.py`

### Changes
- In `_build_reasoning_graph_payload(...)` tool-node construction:
  - Consecutive same-tool calls (already grouped in one step) are rendered as one node.
  - Label format changed to:
    - Multi-call: `#13-14 GEE_script_blueprint_tool*2`
    - Single-call: `#13 GEE_script_blueprint_tool`
  - Non-consecutive same tool remains separate nodes.
  - Transfer tools still keep direct agent-to-agent handoff edges (no transfer tool node).

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- Runtime sanity check (Python one-liner in `NTL-GPT` env) confirmed labels:
  - `['#1-2 GEE_script_blueprint_tool*2', '#3 NTL_download_tool', '#4 GEE_script_blueprint_tool']`


## [2026-02-22] v2026.02.22.08 Reasoning-Graph-KBProgress-Dedup-With-Final-KBTool
### Scope
- Removed duplicated KB semantics in graph when both streaming KB progress and final KB tool message exist.

### Files
- `app_ui.py`

### Changes
- In `_build_reasoning_graph_payload(...)`:
  - Added `has_final_kb_tool` detection across grouped events.
  - When final `NTL_Knowledge_Base` tool message exists, `kb_progress` node is no longer rendered in graph.
- Hardened KB tool styling match:
  - `tool_kb` classification now uses case-insensitive check (`ntl_knowledge_base`), avoiding style mismatch due casing.

### Verification
- `C:\\Users\\HONOR\\miniconda3\\envs\\NTL-GPT\\python.exe -m py_compile app_ui.py`
  - Result: `exit 0`
- AST-based payload check:
  - With final KB tool: `has_kbp False`
  - KB tool class with lowercase name: `#1 ntl_knowledge_base::tool_kb`


## [2026-02-22] v2026.02.22.09 Thread-Output-Isolation-And-Outputs-Consistency
### Scope
- Fixed cross-thread output leakage (`debug` vs current `thread_id`) and aligned Outputs panel/workspace reading with strict thread isolation.

### Files
- `tools/NTL_Code_generation.py`
- `app_logic.py`
- `app_ui.py`
- `tests/test_code_path_isolation_preflight.py`
- `tests/test_execute_output_workspace_audit.py`
- `tests/test_ui_outputs_thread_workspace.py`
- `tests/test_recent_outputs_thread_binding.py`
- `tests/test_run_thread_id_pinning.py`

### Changes
- `tools/NTL_Code_generation.py`
  - Hardened absolute-path detection:
    - `ABSOLUTE_PATH_PATTERNS` now matches both `C:\\...` and `C:/...` via `[A-Za-z]:[\\\\/]`.
  - Added artifact audit pipeline:
    - `_extract_absolute_paths(...)`
    - `_build_artifact_audit(...)`
  - `execute_geospatial_script(...)` now enforces strict preflight internally (`strict_mode=True` behavior regardless of input flag, while keeping public field for compatibility).
  - Added `artifact_audit` field to tool JSON responses (success/fail/cached/not-found/invalid-name).
  - If execution logs contain output paths outside current thread workspace outputs, execution is forced to:
    - `status: fail`
    - `error_type: CrossWorkspaceOutputError`
    - with explicit remediation suggestions.
- `app_logic.py`
  - `_collect_recent_outputs(...)` now accepts `thread_id` and resolves outputs explicitly by that id.
  - In `handle_userinput(...)`, pinned `run_thread_id` for full-run consistency:
    - config thread id
    - contextvar binding
    - recent-output collection
  - This avoids rerun-side drift when UI interactions (Stop/tabs/map params) happen during or after a run.
- `app_ui.py`
  - Replaced all implicit `storage_manager.get_workspace()` calls with explicit:
    - `storage_manager.get_workspace(st.session_state.get("thread_id", "debug"))`
  - Added Outputs-panel diagnostics for cross-thread artifacts:
    - warns when `execute_geospatial_script_tool` returns failed `artifact_audit`
    - shows current thread outputs dir + offending paths
    - provides copyable PowerShell recovery commands.

### One-time Recovery (thread `26cf1633`)
- Copied leaked files from debug workspace back to target thread workspace:
  - `user_data\\debug\\outputs\\shanghai_ntl_2020_cleaned.tif` -> `user_data\\26cf1633\\outputs\\`
  - `user_data\\debug\\outputs\\shanghai_ntl_2020_viridis.png` -> `user_data\\26cf1633\\outputs\\`

### Verification
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_code_path_isolation_preflight.py tests/test_execute_output_workspace_audit.py tests/test_ui_outputs_thread_workspace.py tests/test_recent_outputs_thread_binding.py tests/test_run_thread_id_pinning.py`
  - Result: `10 passed`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_code_error_handling_policy.py tests/test_code_execution_convergence_guard.py tests/test_app_runtime_resilience.py`
  - Result: `10 passed`
- `python -m py_compile tools/NTL_Code_generation.py app_logic.py app_ui.py tests/test_code_path_isolation_preflight.py tests/test_execute_output_workspace_audit.py tests/test_ui_outputs_thread_workspace.py tests/test_recent_outputs_thread_binding.py tests/test_run_thread_id_pinning.py`
  - Result: `exit 0`

## [2026-02-22] v2026.02.22.10 Final-Answer-Preference-Engineer-State-Fallback
### Scope
- Fixed final answer selection to prefer `NTL_Engineer` summary at end of run, avoiding stale worker message being shown as final output.

### Files
- `app_logic.py`
- `tests/test_app_logic_final_answer_selection.py`

### Changes
- `app_logic.py`
  - `_extract_meaningful_ai_text(...)` now supports `preferred_agents` and keeps robust fallback behavior.
  - Added `_get_state_messages(...)` helper to safely read persisted conversation messages.
  - In `handle_userinput(...)`, final answer selection now uses:
    1. last event (preferred `NTL_Engineer`),
    2. persisted state messages (preferred `NTL_Engineer`),
    3. persisted state fallback (latest meaningful AI text).
  - This ensures the final UI answer reflects engineer-level synthesis when available.
- `tests/test_app_logic_final_answer_selection.py`
  - Added tests for preferred-agent selection, fallback selection, and transfer-message filtering.

### Verification
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_final_answer_selection.py tests/test_app_runtime_resilience.py`
  - Result: `7 passed`
- `conda run -n NTL-GPT python -m py_compile app_logic.py tests/test_app_logic_final_answer_selection.py`
  - Result: `exit 0`

### Reproduce
```bash
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_final_answer_selection.py tests/test_app_runtime_resilience.py
conda run -n NTL-GPT python -m py_compile app_logic.py tests/test_app_logic_final_answer_selection.py
```

## [2026-02-22] v2026.02.22.11 Stream-Event-Nested-Message-Drain-Fix
### Scope
- Fixed reasoning-stream freeze where later agent/tool steps were not appended when LangGraph emitted nested namespaced payloads (subgraph updates).

### Files
- `app_logic.py`
- `tests/test_app_logic_nested_message_payload.py`

### Changes
- `app_logic.py`
  - Added nested message extraction pipeline for stream payloads:
    - `_iter_message_lists(...)`
    - `_message_fingerprint(...)`
    - `_collect_new_messages(...)`
  - `handle_userinput(...)` now ingests unseen `BaseMessage` objects from arbitrary nested payload shapes (not only top-level `{"messages": ...}`).
  - Added message-level dedupe via fingerprint set seeded from persisted state, preventing repeated rendering while keeping downstream steps visible.
  - Keeps existing custom `kb_progress` event rendering behavior unchanged.
- `tests/test_app_logic_nested_message_payload.py`
  - Added coverage for nested payload ingestion and dedupe behavior.

### Verification
- `conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_nested_message_payload.py tests/test_app_logic_custom_stream_ingest.py tests/test_app_logic_final_answer_selection.py tests/test_app_runtime_resilience.py`
  - Result: `10 passed`
- `conda run -n NTL-GPT python -m py_compile app_logic.py tests/test_app_logic_nested_message_payload.py`
  - Result: `exit 0`

### Reproduce
```bash
conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_nested_message_payload.py tests/test_app_logic_custom_stream_ingest.py tests/test_app_logic_final_answer_selection.py tests/test_app_runtime_resilience.py
conda run -n NTL-GPT python -m py_compile app_logic.py tests/test_app_logic_nested_message_payload.py
```

## [2026-02-22] v2026.02.22.12 UI-Reasoning-Dedupe-And-JSONL-Preview
### Scope
- Fixed duplicate tool-output rendering in Reasoning (notably repeated `transfer_to_*` cards).
- Removed extra chat placeholder blank before new-turn answer stream.
- Added `.jsonl/.ndjson` preview support in Outputs panel.

### Files
- `app_ui.py`
- `app_logic.py`
- `tests/test_reasoning_tool_message_dedupe.py`
- `tests/test_output_preview_jsonl_contract.py`

### Changes
- `app_ui.py`
  - Added `_dedupe_tool_messages(...)` and applied it in `render_reasoning_content(...)` tool section.
  - Reasoning tool panels now collapse duplicate stream artifacts (same tool name + tool_call_id + content).
  - Added output preview branch for `[".jsonl", ".ndjson"]`:
    - line-by-line parse with max 500 lines
    - dataframe preview for parsed records
    - fallback row with `_raw` for invalid JSON lines
    - parse-failure count caption
- `app_logic.py`
  - Replaced `chat_container.empty()` placeholder usage with direct `chat_container.container()` render for transient "Thinking and analyzing..." block to avoid extra blank placeholder gap.
- Tests
  - `tests/test_reasoning_tool_message_dedupe.py`: verifies duplicate tool messages are collapsed while distinct tool calls remain.
  - `tests/test_output_preview_jsonl_contract.py`: verifies JSONL/NDJSON preview branch exists.

### Verification
- `conda run -n NTL-GPT python -m pytest -q tests/test_reasoning_tool_message_dedupe.py tests/test_output_preview_jsonl_contract.py tests/test_app_runtime_resilience.py`
  - Result: `6 passed`
- `conda run -n NTL-GPT python -m py_compile app_ui.py app_logic.py tests/test_reasoning_tool_message_dedupe.py tests/test_output_preview_jsonl_contract.py`
  - Result: `exit 0`

## [2026-02-23] v2026.02.23.01 Sidebar-Data-Availability-Table-And-Monitor-Links
### Scope
- Upgraded sidebar `Data Availability In GEE` from bullet list to structured table.
- Added direct jump links from sidebar to the current Official Daily NTL Fast Monitor interface.

### Files
- `app_ui.py`
- `docs/Codex_变更记录.md`

### Changes
- Added `_render_data_availability_block()` in `app_ui.py`:
  - Renders a bilingual availability table (Annual/Monthly/Daily products, range, latency).
  - Includes:
    - `NPP-VIIRS-Like (Annual)`
    - `NPP-VIIRS (Annual)`
    - `DMSP-OLS (Annual)`
    - `VCMSLCFG (Monthly)`
    - `VNP46A2 (Daily)`
    - `VNP46A1 (Daily)`
- Replaced old caption bullets inside sidebar expander with the new table block.
- Added quick links in sidebar expander:
  - `http://127.0.0.1:8765/` (Fast Monitor UI)
  - `http://127.0.0.1:8765/api/latest` (Monitor availability API)
  - Uses `st.link_button` with markdown fallback for compatibility.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- `rg -n "_render_data_availability_block|http://127.0.0.1:8765|Data Availability In GEE" app_ui.py`
  - Result: expected matches found

## [2026-02-23] v2026.02.23.02 Sidebar-NTL-Availability-Snapshot-From-Monitor
### Scope
- Renamed sidebar availability module title to `NTL Data Availability`.
- Replaced static GEE bullet-table content with one-time monitor snapshot data (`/api/latest`) using the same row contract as monitor table.
- Kept user jump path simple with primary UI link, while API remains as note for scripts.

### Files
- `app_ui.py`
- `docs/Codex_变更记录.md`

### Changes
- Added monitor endpoint constants and one-time snapshot loader:
  - `MONITOR_UI_URL`, `MONITOR_API_URL`
  - `_load_ntl_availability_snapshot_once()`
  - Snapshot cached in `st.session_state["ntl_data_availability_snapshot_v1"]` and reused on reruns (no interval refresh).
- Updated `_render_data_availability_block()`:
  - Pulls `gee_rows + rows` from monitor payload and renders columns aligned with monitor table:
    - `Source`, `Global Latest`, `Global Lag (d)`, `BBox Latest`, `BBox Lag (d)` (localized labels in zh mode).
  - Shows snapshot timestamp/window once loaded.
  - Displays one primary button to open monitor UI.
  - Keeps API path as caption note for programmatic access.
- Updated expander title:
  - `Data Availability In GEE` -> `NTL Data Availability`

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- `rg -n "NTL Data Availability|_load_ntl_availability_snapshot_once|MONITOR_API_URL|MONITOR_UI_URL|api/latest" app_ui.py`
  - Result: expected matches found

## [2026-02-23] v2026.02.23.03 Sidebar-Monitor-Timeout-Waiting-State
### Scope
- Improved sidebar `NTL Data Availability` behavior when monitor snapshot request times out.
- Timeout/connection-not-ready now shows waiting state instead of hard error.

### Files
- `app_ui.py`
- `docs/Codex_变更记录.md`

### Changes
- Added timeout/waiting classification in `_load_ntl_availability_snapshot_once()`:
  - Detects waiting-like errors (`TimeoutError`, `socket.timeout`, `URLError` timeout/refused patterns).
  - Persists snapshot `state` as `ok|waiting|error`.
- Updated `_render_data_availability_block()`:
  - `waiting` state renders info-style waiting panel (not warning error).
  - Added `Retry Loading` button to clear snapshot cache and re-fetch on demand.
  - Keeps monitor UI jump link available in all states.

### Verification
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- `rg -n 'state\"\\s*:\\s*\"waiting\"|Retry Loading|正在等待 Monitor 服务响应|URLError|socket\\.timeout' app_ui.py`
  - Result: expected matches found

## [2026-02-23] v2026.02.23.04 Orbit-Source-RogueSpace-TLE-Json
### Scope
- Switched 3D orbit feed default source to Rogue Space sky API (`/TLE.json`), then filtered to project NTL satellite slots.
- Kept robust fallback to CelesTrak when Rogue source is temporarily unavailable.

### Files
- `experiments/official_daily_ntl_fastpath/orbit_service.py`
- `tests/official_daily_fastpath/test_orbit_service_rogue_source.py`
- `docs/Codex_变更记录.md`

### Changes
- Added Rogue source integration in orbit service:
  - New URL: `https://sky.rogue.space/TLE.json`
  - Parse `OBJECT_NAME`, `TLE_LINE1`, `TLE_LINE2`.
  - Extract NORAD CATNR from `TLE_LINE1` and build in-memory catalog.
  - Build candidate fetcher from this catalog and resolve only configured NTL slots.
- Default fetch flow in `build_orbit_feed(...)`:
  1. try Rogue catalog (`source=rogue_sky_tle_json`)
  2. if failed, fallback to CelesTrak (`source=celestrak_fallback`) and append startup error.
- Added tests for both paths:
  - Rogue primary path selected and CelesTrak not called.
  - Rogue failure path correctly falls back to CelesTrak (non-target variation).

### Verification
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/orbit_service.py experiments/official_daily_ntl_fastpath/monitor_server.py`
  - Result: `exit 0`
- `$env:PYTHONPATH='.'; conda run --no-capture-output -n NTL-GPT pytest -q tests/official_daily_fastpath/test_orbit_registry.py tests/official_daily_fastpath/test_orbit_service_fallback.py tests/official_daily_fastpath/test_orbit_feed_api.py tests/official_daily_fastpath/test_orbit_service_rogue_source.py`
  - Result: `8 passed`
- Runtime smoke:
  - `conda run --no-capture-output -n NTL-GPT python -c "from pathlib import Path; from experiments.official_daily_ntl_fastpath.orbit_service import build_orbit_feed; p=build_orbit_feed(Path('experiments/official_daily_ntl_fastpath/workspace_monitor'), force_refresh=True, ttl_minutes=180); print('source', p.get('source')); print('slots', len(p.get('slots',[]))); print('ok_like', sum(1 for x in p.get('slots',[]) if x.get('status') in {'ok','fallback'})); print('errors_head', p.get('errors',[])[:3])"`
  - Result: `source rogue_sky_tle_json`, `slots 5`, `ok_like 4`

## [2026-02-23] v2026.02.23.05 Orbit-3D-Rogue-Native-Embed-Mode
### Scope
- Switched 3D orbit view in monitor UI to Rogue Sky native interface embed.
- Stopped using local Cesium orbit renderer in active 3D path; keep 2D imagery path unchanged.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- UI structure:
  - Added `#rogueSkyWrap` + `#rogueSkyFrame` iframe + external open link.
  - Added IDs for control wrappers (`#layerWrap`, `#applyLayerWrap`, `#mapNote`) for mode-specific visibility.
- 3D mode behavior:
  - Added `activateRogueSkyView(forceReload)` and set `viewMode=3d` to use Rogue embed directly (`https://sky.rogue.space/`).
  - 3D now hides local layer/render/opacity controls and map note to avoid mixed interaction.
  - Added loading/ready/blocked orbit status texts for Rogue mode.
  - Added load timeout guard (12s) and fallback guidance (open in new tab) if embed is blocked or unresponsive.
- Safety:
  - Kept legacy Cesium code path in file but removed from active 3D switch path for easier rollback.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright E2E:
  - Open `http://127.0.0.1:8765/`
  - Switch `viewMode` to `3d`
  - Confirm:
    - `#rogueSkyFrame.src == "https://sky.rogue.space/"`
    - `#rogueSkyWrap` visible
    - status enters Rogue loading/ready state
    - local 2D controls hidden in 3D (`layerWrap/applyLayerWrap/opacityWrap/mapNote`)

## [2026-02-23] v2026.02.23.05 Thread-Bound-Output-Auto-Migration-And-UI-Path-Redaction
### Scope
- Implemented cross-thread output auto-recovery for `execute_geospatial_script_tool`.
- Enforced thread-bound storage path resolution during code execution runtime.
- Added UI-wide path redaction for tool JSON and mismatch notices to avoid exposing local absolute paths (e.g., `E:\...`).

### Files
- `tools/NTL_Code_generation.py`
- `app_ui.py`
- `tests/test_execute_output_thread_bound_write.py`
- `tests/test_execute_output_auto_migration.py`
- `tests/test_ui_path_redaction_contract.py`
- `tests/test_reasoning_tool_json_redaction.py`
- `tests/test_ui_outputs_thread_workspace.py`

### Changes
- `tools/NTL_Code_generation.py`
  - Added `_thread_bound_storage_paths(...)` context manager:
    - Temporarily binds `storage_manager.resolve_output_path/resolve_input_path` to current run thread when `thread_id` is omitted.
    - Prevents implicit fallback to `debug` during runtime script execution.
  - `_execute_code(...)` now runs under thread-bound storage context.
  - Added `_auto_migrate_cross_workspace_outputs(...)`:
    - Copies out-of-workspace files (outputs-only) back to current thread outputs.
    - Source files are preserved.
  - Extended `artifact_audit` with migration fields:
    - `auto_migration_attempted`, `auto_migration_success`, `migrated_paths`, `migration_failures`.
  - Updated `execute_geospatial_script(...)` success/failure behavior:
    - On cross-thread outputs + successful auto-migration:
      - return `status: success`
      - add `cross_workspace_recovered`, `auto_migrated_files`, `recovery_note`
    - On migration failure:
      - keep `status: fail` with `CrossWorkspaceOutputError`
      - include migration failure details.
- `app_ui.py`
  - Added path redaction helpers:
    - `_to_ui_relative_path(...)`
    - `_sanitize_paths_in_text(...)`
    - `_sanitize_paths_in_obj(...)`
  - Applied path redaction to:
    - Data_Searcher raw JSON rendering
    - KB raw/sources/step input rendering
    - generic tool JSON rendering in Reasoning flow
    - cross-thread output mismatch notice
  - Mismatch notice now supports recovered case:
    - shows `info` for auto-recovered outputs
    - shows redacted relative paths only.
- Tests
  - Added thread-bound path resolution test for execute flow.
  - Added auto-migration success/failure tests.
  - Added UI path redaction contract tests and reasoning tool JSON redaction test.
  - Extended UI workspace test with redaction-helper presence assertion.

### Verification
- `conda run -n NTL-GPT python -m pytest -q tests/test_execute_output_thread_bound_write.py tests/test_execute_output_auto_migration.py tests/test_execute_output_workspace_audit.py tests/test_ui_path_redaction_contract.py tests/test_reasoning_tool_json_redaction.py tests/test_ui_outputs_thread_workspace.py`
  - Result: `11 passed`
- `conda run -n NTL-GPT python -m pytest -q tests/test_code_execution_thread_context.py tests/test_code_script_persistence.py tests/test_code_execution_convergence_guard.py tests/test_code_path_isolation_preflight.py tests/test_app_runtime_resilience.py`
  - Result: `16 passed`
- `conda run -n NTL-GPT python -m py_compile tools/NTL_Code_generation.py app_ui.py tests/test_execute_output_thread_bound_write.py tests/test_execute_output_auto_migration.py tests/test_ui_path_redaction_contract.py tests/test_reasoning_tool_json_redaction.py`
  - Result: `exit 0`

## [2026-02-23] v2026.02.23.06 Lightweight-Download-Boundary-Policy-Optimization
### Scope
- Reduced redundant boundary-tool calls in lightweight download scenarios.
- Kept boundary rigor for execution/statistics paths only.
- Preserved all public tool interfaces.

### Files
- `agents/NTL_Data_Searcher.py`
- `agents/NTL_Engineer.py`
- `tests/test_data_searcher_prompt_constraints.py`
- `tests/test_ntl_engineer_prompt_constraints.py`
- `tests/test_boundary_policy_generalization.py`

### Changes
- `agents/NTL_Data_Searcher.py`
  - Replaced global boundary precheck with conditional strategy:
    - lightweight direct-download (`daily <=31` / `annual <=12` / `monthly <=24`) defaults to `NTL_download_tool` first.
    - boundary retrieval + `geodata_quick_check_tool` only for explicit boundary needs, analysis/execution tasks, ambiguity/failure fallback, or non-China explicit admin-boundary scenarios.
  - Added explicit policy:
    - no forced boundary shapefile output for successful lightweight direct-download tasks.
    - allow `Boundary_validation.validation_status = not_required`.
    - allow `boundary_source_tool = internal_gee_region_match` when no external boundary tool is called.
  - Updated output schema text for `Boundary_validation` to include:
    - `not_required/confirmed/pending`
    - optional `boundary_file`.
- `agents/NTL_Engineer.py`
  - Changed boundary gate from global mandatory to execution-path mandatory:
    - enforce `confirmed` before execution/analysis handoff to Code_Assistant.
    - added download-only bypass when coverage is complete (`missing_items` empty).
- Tests
  - Extended prompt-contract tests for both agents.
  - Added generalization test file covering:
    - target lightweight case (Shanghai annual download)
    - non-target variant (outside-China boundary route)
    - non-target variant (analysis path keeps confirmed-boundary requirement)

### Verification
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 C:\\Users\\HONOR\\miniconda3\\envs\\NTL-GPT\\python.exe -m pytest -q tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py tests/test_boundary_policy_generalization.py`
  - Result: `16 passed`
- `C:\\Users\\HONOR\\miniconda3\\envs\\NTL-GPT\\python.exe -m py_compile agents/NTL_Data_Searcher.py agents/NTL_Engineer.py tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py tests/test_boundary_policy_generalization.py`
  - Result: `exit 0`

## [2026-02-23] v2026.02.23.07 Orbit-3D-Rogue-Cleanup-Physical-Removal
### Scope
- Completed the cleanup pass for the Rogue Sky 3D migration.
- Physically removed deprecated local 3D orbit UI blocks (no hidden legacy controls left in DOM/CSS).

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- `index.html`
  - Removed legacy orbit controls block:
    - `#orbitControls`
    - `#orbitPlayPauseBtn`
    - `#orbitSpeed`
    - `#orbitRefreshBtn`
  - Removed deprecated 3D/legend containers:
    - `#globe3d`
    - `#orbitLegend`
  - Kept only Rogue Sky 3D container path (`#rogueSkyWrap`, `#rogueSkyFrame`, `#rogueSkyOpenLink`).
- `styles.css`
  - Removed obsolete style blocks and responsive rules for:
    - `#globe3d`
    - `.orbit-controls`
    - `.orbit-legend`
  - Simplified `.view-stack` child selector to `#map` + `#rogueSkyWrap`.
- `main.js`
  - Removed unused orbit i18n keys tied to deleted legacy controls and Cesium-era states:
    - `orbitLoading`, `orbitReady`, `orbitViewInitFailed`, `orbitNoData`
    - `orbitPause`, `orbitPlay`, `orbitSpeed`, `orbitRefresh`
  - Kept active Rogue status model keys only (`orbitIdle`, `orbitFailed`, `orbitRogueLoading`, `orbitRogueReady`, `orbitRogueBlocked`).

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- `rg -n "globe3d|orbitControls|orbitLegend|orbitPause|orbitSpeed|orbitRefresh" experiments/official_daily_ntl_fastpath/web_ui/index.html experiments/official_daily_ntl_fastpath/web_ui/styles.css experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: no matches (expected)

## [2026-02-23] v2026.02.23.08 Orbit-3D-InPage-MultiWindow-Per-Satellite
### Scope
- Adjusted 3D orbit mode from multi-tab popup behavior to in-page multi-window layout.
- Each NTL satellite now renders in its own embedded Rogue window inside the same page.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- `index.html`
  - Replaced single Rogue iframe with in-page grid container:
    - removed standalone `#rogueSkyFrame` block and popup action area
    - added `#rogueSkyGrid` inside `#rogueSkyWrap`
- `styles.css`
  - Refactored Rogue styles from single-frame to card-grid layout:
    - added `#rogueSkyGrid`, `.rogue-card`, `.rogue-card-head`, `.rogue-card-title`, `.rogue-card-link`, `.rogue-card-frame`
    - 2-column layout on desktop; collapses to 1 column on narrow screens
- `main.js`
  - Switched orbit 3D rendering logic to in-page multi-window strategy:
    - built 5 dedicated Rogue cards (`NPP`, `NOAA20`, `NOAA21`, `SDGSAT`, `LUOJIA`) with per-card iframe URLs
    - added dynamic card title/link localization (`zh/en`)
    - added per-cycle iframe load accounting (`loaded/failed/total`) and status reporting
  - Removed popup/multi-tab logic and related status strings.
  - Status now reflects same-page multi-window progress:
    - loading all windows
    - full ready
    - partial ready
    - blocked

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright smoke test (`http://127.0.0.1:8765`):
  - switch to `3D`
  - result:
    - `轨道状态：同页卫星窗口加载完成（5/5）`
    - `#rogueSkyGrid` shows 5 cards in-page
    - each card iframe has expected preloaded search text (`NPP`, `NOAA20`, `NOAA21`, `SDGSAT`, `LUOJIA`)

## [2026-02-23] v2026.02.23.09 Orbit-3D-InPage-Reduce-To-SDGSAT-And-NPP
### Scope
- Reduced in-page 3D orbit windows to only two satellites as requested.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Updated `NTL_ORBIT_TAB_TARGETS` from 5 entries to 2 entries:
  - kept: `snpp_viirs` (`NPP`)
  - kept: `sdgsat1` (`SDGSAT`)
  - removed: `noaa20_viirs`, `noaa21_viirs`, `luojia_slot`
- Existing grid/status logic remains generic and now auto-computes totals based on 2 targets.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`

## [2026-02-23] v2026.02.23.10 Orbit-3D-SNPP-Default-Search-Chips-And-FullHeight
### Scope
- Changed 3D orbit panel to default single-window SNPP view.
- Added in-page satellite search chips (including SDGSAT-1 and others) above the orbit panel.
- Fixed single-window layout to use full available height (no large blank lower area).

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- `experiments/official_daily_ntl_fastpath/web_ui/styles.css`
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- `index.html`
  - Added search hint section above 3D panel:
    - `#orbitSearchHints`
    - `#orbitHintChips`
- `main.js`
  - Reworked orbit model to single primary slot:
    - default primary view: `SNPP VIIRS`
  - Added user-driven search choices rendered as chips:
    - `SNPP VIIRS`, `SDGSAT-1`, `NOAA20 VIIRS`, `NOAA21 VIIRS`, `LUOJIA-1`
  - Clicking a chip reloads the same iframe with selected search term.
  - Added i18n key:
    - `orbitHintsLabel` (`zh/en`)
- `styles.css`
  - Added chip styles: `.orbit-hints`, `.orbit-hints-chips`, `.orbit-chip`
  - Fixed single-card sizing to fill full 3D container:
    - `#rogueSkyWrap { overflow: hidden }`
    - `#rogueSkyGrid { height: 100% }`
    - `.rogue-card { height: 100%; min-height: 0 }`
    - `.rogue-card-frame { height: 100%; min-height: 0 }`

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright runtime check:
  - force `viewMode=3d`
  - result:
    - `cards = 1`
    - chips include `SNPP VIIRS`, `SDGSAT-1`, `NOAA20 VIIRS`, `NOAA21 VIIRS`, `LUOJIA-1`
    - height check: `wrapH=713`, `cardH=691`, `frameH=654` (full-height behavior confirmed)

## [2026-02-23] v2026.02.23.11 Orbit-Search-Name-Fix-NOAA20-21-And-Add-JILIN1
### Scope
- Fixed Rogue search tokens for NOAA 20/21 (name mismatch issue).
- Added `吉林1号` (`JILIN 1`) as selectable orbit search chip.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Updated `ORBIT_SEARCH_CHOICES`:
  - `NOAA20` -> `NOAA 20`
  - `NOAA21` -> `NOAA 21`
  - added `JILIN 1` (`labelZh: 吉林1号`)
- Kept existing single-window SNPP default behavior.

### Verification
- Source-name confirmation from Rogue catalog (`https://sky.rogue.space/TLE.json`):
  - `NOAA 20` hits: `1`
  - `NOAA 21` hits: `1`
  - `NOAA20`/`NOAA21` hits: `0`
  - `JILIN` hits: `37`
  - `JILIN 1` hits: `1`
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright runtime check:
  - clicking `NOAA20 VIIRS` chip updates link to `...search=NOAA+20...`
  - clicking `吉林1号` chip updates link to `...search=JILIN+1...`

## [2026-02-23] v2026.02.23.10 Three-Agent-Latency-Policy-Unification
### Scope
- Implemented the agreed latency-first update for the three-agent stack without supervisor/schema refactors.
- Kept router mechanism, but aligned policy and thresholds across prompts and router runtime logic.

### Files
- `agents/NTL_Data_Searcher.py`
- `agents/NTL_Engineer.py`
- `agents/NTL_Code_Assistant.py`
- `tools/GEE_specialist_toolkit.py`
- `tests/test_data_searcher_prompt_constraints.py`
- `tests/test_ntl_engineer_prompt_constraints.py`
- `tests/test_gee_router_execution_mode.py`
- `tests/test_router_intent_generalization.py` (new)

### Changes
- `agents/NTL_Data_Searcher.py`
  - Unified lightweight threshold wording to:
    - daily `<=14`
    - monthly `<=12`
    - annual `<=12`
  - Added explicit **Conditional router rule**:
    - router required for GEE retrieval/planning tasks
    - router optional for pure local-file processing/inspection with explicit existing filenames and no GEE retrieval.
  - Removed conflicting narrative tied to daily `<=31`.
  - Kept completion gate / single-call / single-completion / first-night D+1 constraints.
- `agents/NTL_Engineer.py`
  - Aligned direct-download/server-side thresholds to:
    - daily `<=14` direct
    - monthly `<=12` direct
    - annual `<=12` direct
    - daily `>14` server-side
  - Added conditional router usage guidance consistent with Data_Searcher policy.
  - Preserved high-value handoff and execution constraints.
- `agents/NTL_Code_Assistant.py`
  - Performed lean prompt compression:
    - retained mandatory execution contract and escalation/convergence rules
    - reduced redundant library/dataset narration while preserving required dataset consistency cues.
- `tools/GEE_specialist_toolkit.py`
  - Updated `_execution_mode` thresholds to:
    - daily `>14` => `gee_server_side`, else `direct_download`
    - monthly `>12` => `gee_server_side`, else `direct_download`
    - annual `>12` => `gee_server_side`, else `direct_download`
  - Removed `zonal_stats <= 6` special-case branch.
  - Removed `zonal` keyword from server-side hard trigger terms so zonal tasks follow unified thresholds unless other strong server-side markers exist.
- Tests
  - Updated prompt and router assertions to match new unified policy.
  - Added cross-domain generalization regression:
    - earthquake / wildfire / conflict / flood queries all route via intent-based server-side trigger when appropriate.

### Verification
- `conda run -n NTL-GPT pytest tests/test_data_searcher_prompt_constraints.py tests/test_ntl_engineer_prompt_constraints.py tests/test_code_file_protocol_prompts.py tests/test_gee_router_execution_mode.py tests/test_gee_specialist_toolkit.py tests/test_router_intent_generalization.py -q`
  - Result: `34 passed`
- `conda run -n NTL-GPT pytest tests/test_code_execution_convergence_guard.py tests/test_code_error_handling_policy.py tests/test_app_logic_final_answer_selection.py -q`
  - Result: `9 passed`

## [2026-02-23] v2026.02.23.12 RogueSky-NOAA-Search-Token-Fix
### Scope
- Fixed 3D orbit query tokens so NOAA20/NOAA21/JILIN1 no longer appear as `%20` or `+` in Rogue Sky search input.
- Re-verified NOAA20 in-page 3D load status and token propagation.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Updated `ORBIT_SEARCH_CHOICES` search tokens:
  - `NOAA 20` -> `NOAA20`
  - `NOAA 21` -> `NOAA21`
  - `JILIN 1` -> `JILIN1`
- Kept display labels unchanged (`NOAA20 VIIRS`, `NOAA21 VIIRS`, `JILIN 1`).
- Hardened Rogue URL base normalization to avoid duplicated slash in generated links.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright 3D check (local `http://127.0.0.1:8765/`):
  - `NOAA20 VIIRS` chip:
    - link `https://sky.rogue.space/?search=NOAA20&slot=noaa20&from=ntl_fast_monitor`
    - iframe search input `NOAA20`
    - orbit status `同页卫星窗口加载完成（1/1）`
  - `NOAA21 VIIRS` chip:
    - link `https://sky.rogue.space/?search=NOAA21&slot=noaa21&from=ntl_fast_monitor`
    - iframe search input `NOAA21`

## [2026-02-23] v2026.02.23.13 RogueSky-NOAA-Display-Label-Space
### Scope
- Adjusted 3D satellite chip/card display labels to include a space between `NOAA` and orbit number while keeping searchable token stable.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Updated display labels only:
  - `NOAA20 VIIRS` -> `NOAA 20 VIIRS`
  - `NOAA21 VIIRS` -> `NOAA 21 VIIRS`
- Kept search tokens unchanged:
  - `NOAA20`, `NOAA21` (avoids `%20`/`+` parsing issue in embedded Rogue Sky)

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`

## [2026-02-23] v2026.02.23.14 RogueSky-NOAA-NORAD-Search-Fix
### Scope
- Fixed NOAA 20 / NOAA 21 3D search mismatch in embedded Rogue Sky caused by space encoding behavior.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Switched Rogue Sky search tokens from text names to NORAD catalog IDs:
  - `NOAA 20` -> `43013`
  - `NOAA 21` -> `54234`
- Kept visible chip/card labels unchanged (`NOAA 20 VIIRS`, `NOAA 21 VIIRS`).
- Added inline comment documenting why numeric tokens are used.

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright local check (`http://127.0.0.1:8765/`):
  - NOAA 20 chip:
    - link `...search=43013...`
    - iframe search input `43013`
  - NOAA 21 chip:
    - link `...search=54234...`
    - iframe search input `54234`
  - orbit status: `同页卫星窗口加载完成（1/1）`

## [2026-02-23] v2026.02.23.15 RogueSky-NOAA-INTLDES-Search-Fix
### Scope
- Fixed NOAA 20 / NOAA 21 still-not-visible issue in embedded Rogue Sky when using numeric catalog-number keywords.

### Files
- `experiments/official_daily_ntl_fastpath/web_ui/main.js`
- `docs/Codex_变更记录.md`

### Changes
- Replaced NOAA search tokens with verified no-space INTLDES aliases that Rogue Sky can resolve:
  - NOAA 20: `2017-073A`
  - NOAA 21: `2022-150A`
- Kept visible labels unchanged:
  - `NOAA 20 VIIRS`, `NOAA 21 VIIRS`

### Verification
- `node --check experiments/official_daily_ntl_fastpath/web_ui/main.js`
  - Result: `exit 0`
- Playwright monitor E2E (`http://127.0.0.1:8765/`):
  - `NOAA 20 VIIRS` chip => iframe input `2017-073A`, frame text contains `NOAA 20 2017-073A`
  - `NOAA 21 VIIRS` chip => iframe input `2022-150A`, frame text contains `NOAA 21 2022-150A`
  - orbit status `同页卫星窗口加载完成（1/1）`

## [2026-02-23] v2026.02.23.16 Official-Download-Robustness-And-Proven-Run
### Scope
- Fixed official raw download failure behavior under unstable network (`curl: (35) Recv failure`) and improved failure readability.
- Ensured official raw download flow does not fail-fast on first granule error.
- Completed a verified official-channel download run in `NTL-GPT` environment.

### Files
- `experiments/official_daily_ntl_fastpath/cmr_client.py`
- `experiments/official_daily_ntl_fastpath/monitor_server.py`
- `tests/official_daily_fastpath/test_cmr_parse.py`
- `docs/Codex_变更记录.md`

### Changes
- `cmr_client.download_file_with_curl`:
  - Added `curl` network hardening flags: `--ipv4`, `--retry 3`, `--retry-delay 2`, `--retry-all-errors`, `--connect-timeout 30`, `--max-time ...`.
  - Added integrity-first fallback: when `curl` exits nonzero but output exists, validate payload; if valid HDF/netCDF then accept (`curl_nonzero_but_payload_valid`).
  - Added sanitized error normalization to avoid unreadable mojibake in UI error text.
  - Added binary-safe `body_hint` (`binary_hdf5_signature_detected` / `binary_payload_head_hex=...`) instead of raw garbled bytes.
  - Added cleanup for invalid partial files.
- `monitor_server.build_download_data` (`provider=official`, `format=raw_h5`):
  - Removed fail-fast on first granule failure.
  - Continue downloading remaining granules and succeed if at least one file is valid.
  - Only fail when all candidate granules fail, with summarized details.
- Tests:
  - Added `curl nonzero + valid payload` acceptance test.
  - Added binary error-hint sanitization test.

### Verification
- `conda run -n NTL-GPT python -m pytest tests/official_daily_fastpath/test_cmr_parse.py tests/official_daily_fastpath/test_monitor_helpers.py -q`
  - Result: `11 passed`
- Proven official raw download run (Python API path in `NTL-GPT` env):
  - Query:
    - `provider=official`
    - `source=VJ102DNB`
    - `format=raw_h5`
    - `start_date=2026-02-18`
    - `end_date=2026-02-23`
    - `bbox=120.8,30.6,122.2,31.9`
  - Output:
    - `experiments/official_daily_ntl_fastpath/workspace_monitor/debug/proven_official_download/VJ102DNB_2026-02-18_to_2026-02-22_raw.zip`
    - size: `218784217` bytes
    - zip entries: `5` (`.nc` files)

## [2026-02-23] v2026.02.23.16 Manual-File-Understanding-And-User-History
### Scope
- Added user-scoped conversation history and manual file-understanding injection workflow (no auto token spend on upload).
- Kept existing upload behavior intact while extending upload types for understanding candidates.

### Files
- `app_ui.py`
- `Streamlit.py`
- `tests/test_history_store_injected_context.py`

### Changes
- Sidebar:
  - Added user identity input (`User`) that switches to user-scoped thread history.
  - Added thread selector (`History Threads`) to switch among same-user sessions.
  - `Reset` now creates a fresh thread with `history_store.generate_thread_id(user_id)` and binds it to user index.
- Upload:
  - Extended accepted types to include `pdf/png/jpg/jpeg/webp/bmp` (still upload-only by default).
- New manual panel:
  - `File Understanding (Manual)` section in sidebar.
  - User selects files + `Max PDF Pages` + `Top-N` + `Max Injected Chars`.
  - Click action to parse and upsert snippets into per-thread context index.
  - Added clear action to purge injected context.
- Streamlit main:
  - Mounted `app_ui.render_file_understanding_panel()` after uploader.
- Tests:
  - Added store-level tests for user-thread binding/listing and context retrieval relevance.

### Verification
- `python -m py_compile app_ui.py Streamlit.py app_logic.py app_state.py history_store.py file_context_service.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_history_store_injected_context.py tests/test_app_runtime_resilience.py`
  - Result: `6 passed`
- Note:
  - Existing unrelated test file currently fails in workspace baseline:
    - `tests/test_reasoning_graph_render_no_nameerror.py` expects `_wrap_reasoning_label`, missing from current baseline.

## [2026-02-24] v2026.02.24.01 Manual-Login-Download-Script
### Scope
- Added a manual-login download helper script so users can open official granule URLs in browser and finish Earthdata login themselves.

### Files
- `experiments/official_daily_ntl_fastpath/manual_login_download.py`
- `docs/Codex_变更记录.md`

### Changes
- New CLI script to:
  - query granule links by `source + date range + bbox`,
  - optionally append `token` query for `nrt3` links,
  - save all links to txt,
  - auto-open first N links in browser tabs for manual Earthdata login/download.

### Verification
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/manual_login_download.py`
  - Result: `exit 0`

## [2026-02-24] v2026.02.24.02 Manual-Login-BBox-Arg-Compatibility
### Scope
- Fixed CLI bbox argument parsing for PowerShell users where comma lists may be split into multiple values.

### Files
- `experiments/official_daily_ntl_fastpath/manual_login_download.py`
- `docs/Codex_变更记录.md`

### Changes
- `--bbox` now accepts both forms:
  - single string: `minx,miny,maxx,maxy`
  - four values: `minx miny maxx maxy`
- Added explicit validation and clearer error message for invalid bbox shapes.

### Verification
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/manual_login_download.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python experiments/official_daily_ntl_fastpath/manual_login_download.py --source VJ146A1 --start-date 2026-02-14 --end-date 2026-02-14 --bbox 120.8 30.6 122.2 31.9 --max-open 1`
  - Result: argument parsing and link generation succeeded (`granules_with_links=2`)

## [2026-02-24] v2026.02.24.03 Two-Agent-Ready-Official-Scripts
### Scope
- Added two standalone Python scripts for agent-friendly official-source operations:
  - global availability range scan (no bbox)
  - official download by bbox + date range

### Files
- `experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py`
- `experiments/official_daily_ntl_fastpath/download_official_ntl_by_bbox.py`
- `docs/Codex_变更记录.md`

### Changes
- `scan_official_ntl_availability.py`
  - Scans selected sources (`nrt_priority` or comma list).
  - Fetches collection-level time range from CMR Collections API.
  - Fetches latest global granule date (no bbox) via CMR Granules API.
  - Outputs both JSON and CSV for downstream agent consumption.
- `download_official_ntl_by_bbox.py`
  - Downloads official sources by `bbox + start/end date`.
  - Supports:
    - `--format raw_h5` (raw `.h5/.nc`, auto-zips multi-files)
    - `--format clipped_tif` (for `gridded_tile_clip` sources only)
  - Supports multiple sources in one run.
  - Emits a manifest JSON with per-source status/files.
  - Compatible bbox parsing:
    - comma string (`minx,miny,maxx,maxy`)
    - 4 args (`minx miny maxx maxy`)

### Verification
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py experiments/official_daily_ntl_fastpath/download_official_ntl_by_bbox.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py --sources nrt_priority --granule-start-date 2026-01-01 --granule-end-date 2026-02-24`
  - Result: generated JSON/CSV with `rows=5`
- `conda run -n NTL-GPT python experiments/official_daily_ntl_fastpath/download_official_ntl_by_bbox.py --sources VJ102DNB --start-date 2026-02-18 --end-date 2026-02-23 --bbox 120.8 30.6 122.2 31.9 --format raw_h5`
  - Result: `VJ102DNB: ok | files=1`, manifest generated

## [2026-02-23] v2026.02.23.17 Image-Understanding-Switched-To-VLM-E2E
### Scope
- Replaced image feature-statistics summarization path with end-to-end VLM understanding for manual file context injection.
- Target model path: DashScope-compatible `qwen3.5-plus` multimodal messages (`text + image_url`).

### Files
- `file_context_service.py`
- `app_logic.py`
- `tests/test_file_context_service_vlm_image.py`

### Changes
- Added `_image_vlm_summary(...)`:
  - Builds `HumanMessage(content=[{"type":"text"...}, {"type":"image_url", ...}])`
  - Calls `ChatOpenAI` with DashScope compatible endpoint for qwen models
  - Returns VLM-generated semantic understanding text (no image-stat fallback)
- Removed `_image_summary` usage in image branch; image context now comes from VLM output only.
- `inject_selected_files_to_context(...)` now passes current UI model (`cfg_model`) into file context builder.
- Added tests:
  - multimodal payload contract for VLM image invocation
  - PNG/JPG non-target variation coverage for generalized image ingestion behavior

### Verification
- `python -m py_compile file_context_service.py app_logic.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_file_context_service_vlm_image.py tests/test_history_store_injected_context.py`
  - Result: `4 passed`

## [2026-02-24] v2026.02.24.1 Image-QA-Retrieval-Fix-And-Manual-Defaults-Lock
### Scope
- Fixed image-question miss issues in manual file understanding by improving retrieval policy.
- Locked manual understanding parameters to fixed defaults (no user-facing sliders).

### Files
- `history_store.py`
- `app_ui.py`
- `tests/test_history_store_injected_context.py`

### Changes
- Retrieval policy improvements for injected context:
  - Added explicit filename mention shortcut (e.g., `t6.png写了什么`) to prioritize exact file chunks.
  - Added score boost for `source_file`/file stem matches in query.
  - Added image-question fallback (`图片/图像/这张图/image/picture/...`) to use latest injected image snippets when semantic score is low.
- Sidebar manual understanding UI:
  - Removed user-adjustable sliders (`Max PDF Pages`, `Top-N`, `Max Injected Chars`).
  - Enforced fixed defaults: `120 / 4 / 6000`.
  - Preserved manual-trigger-only behavior.
- Tests:
  - Added filename mention retrieval test (`t6.png` target case).
  - Added non-target variation test for generic image question fallback.

### Verification
- `python -m py_compile app_ui.py history_store.py app_logic.py file_context_service.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_history_store_injected_context.py tests/test_file_context_service_vlm_image.py`
  - Result: `6 passed`

## [2026-02-24] v2026.02.24.2 Auto-Image-Understanding-Gate-And-Fixed-Manual-Params
### Scope
- Added automatic image-understanding trigger path for explicit image questions without requiring manual button click.
- Locked manual understanding tuning parameters to fixed defaults (no user adjustment).

### Files
- `app_logic.py`
- `tests/test_app_logic_auto_image_injection.py`

### Changes
- Auto image-injection gate in QA runtime:
  - Trigger only when question has explicit image filename (`*.png/*.jpg/...`) or clear image intent keywords.
  - If filename provided, inject that image context first.
  - If generic image question, inject latest uploaded image context.
  - Skip re-injection when same file signature already exists in injected context store.
  - Fail-safe behavior: injection exceptions do not break main QA flow.
- Manual panel parameter policy:
  - Fixed defaults enforced: `Max PDF Pages=120`, `Top-N=4`, `Max Injected Chars=6000`.
  - Removed user-facing sliders for these values.
- Added tests:
  - explicit filename trigger
  - generic image intent trigger (latest image)
  - non-image query no-trigger behavior

### Verification
- `python -m py_compile app_logic.py app_ui.py history_store.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_auto_image_injection.py tests/test_history_store_injected_context.py tests/test_file_context_service_vlm_image.py`
  - Result: `9 passed`

## [2026-02-24] v2026.02.24.3 Reasoning-Auto-Image-Trigger-Notice
### Scope
- Added explicit reasoning-line observability for auto image understanding trigger.

### Files
- `app_logic.py`
- `app_ui.py`
- `tests/test_app_logic_auto_image_injection.py`
- `tests/test_reasoning_auto_image_notice.py`

### Changes
- Auto image injector now returns structured event payload:
  - `event_type=auto_image_understanding_triggered`
  - `files=[...]`
  - `trigger_reason=explicit_filename|image_intent_keyword`
- `handle_userinput(...)` appends this event into `analysis_logs` as a custom record before normal stream processing.
- Reasoning renderer now recognizes and renders this event as an info line:
  - `Auto image understanding triggered: <file>`
- Added tests for event payload and reasoning section grouping contract.

### Verification
- `python -m py_compile app_logic.py app_ui.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_app_logic_auto_image_injection.py tests/test_reasoning_auto_image_notice.py`
  - Result: `4 passed`

## [2026-02-24] v2026.02.24.4 Remove-Reasoning-Graph-Show-Substeps-Toggle
### Scope
- Removed `Show Sub-steps` toggle from Reasoning Graph tab per UI simplification request.

### Files
- `app_ui.py`

### Changes
- Deleted `st.toggle("Show Sub-steps")` control from `render_content_layout()` Reasoning Graph tab.
- Fixed graph rendering mode to default `show_sub_steps=False` without exposing user toggle.

### Verification
- `python -m py_compile app_ui.py`
  - Result: `exit 0`

## [2026-02-24] v2026.02.24.5 Scan-NTL-Availability-Include-GEE-Products
### Scope
- Extended `scan_ntl_availability.py` capability to scan project-used GEE nightlight products together with official sources.

### Files
- `experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py`
- `experiments/official_daily_ntl_fastpath/scan_ntl_availability.py`
- `tests/official_daily_fastpath/test_scan_ntl_availability_gee.py`

### Changes
- Added `--include-gee` and `--gee-project` options to the availability scanner.
- Added GEE product scan integration using the same project product registry from `gee_baseline.py`.
- Added GEE time-range scan (`range_start/range_end`) and latest-date/lag into output rows.
- Unified output schema to include `source_type`, `dataset_id`, `temporal_resolution`, and error fields for both official and GEE rows.
- Added `scan_ntl_availability.py` wrapper as a direct entrypoint name.
- Added tests for both:
  - target case: include GEE rows
  - non-target variation: no `--include-gee` keeps official-only rows

### Verification
- `conda run -n NTL-GPT python -m py_compile experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py experiments/official_daily_ntl_fastpath/scan_ntl_availability.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python experiments/official_daily_ntl_fastpath/scan_ntl_availability.py --sources nrt_priority --granule-start-date 2026-01-01 --granule-end-date 2026-02-24 --include-gee`
  - Result: `official_rows=5`, `gee_rows=7`, `rows=12`
- `conda run -n NTL-GPT python -m pytest -q tests/official_daily_fastpath/test_scan_ntl_availability_gee.py`
  - Result: `2 passed`

## [2026-02-24] v2026.02.24.6 Sidebar-NTL-Availability-Local-Scan-First
### Scope
- Fixed empty `NTL Data Availability` sidebar table by switching to local script-driven snapshot loading.
- Added robust fallback chain and schema normalization for monitor/local payload variants.

### Files
- `app_ui.py`
- `experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py`
- `tests/test_ui_ntl_availability_snapshot.py`

### Changes
- Sidebar loading path now prioritizes local scanner execution:
  - Runs `experiments/official_daily_ntl_fastpath/scan_ntl_availability.py` once per page session.
  - Reads latest `official_ntl_availability_*.json` from monitor workspace outputs.
- Added fallback strategy:
  - If local scan fails but cached local output exists, show cached table.
  - If local output is unavailable, fallback to `http://127.0.0.1:8765/api/latest`.
- Added payload normalization for mixed contracts:
  - supports monitor fields (`gee_rows` + `rows`, bbox latest)
  - supports local scan fields (`collection_time_start/end`, global latest)
- Sidebar table now includes availability range columns (`Available Start/End`), with clearer source caption.
- Added query window fields in scanner output payload:
  - `granule_start_date`
  - `granule_end_date`
- Updated waiting message to generic `data service` wording.

### Verification
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py experiments/official_daily_ntl_fastpath/scan_official_ntl_availability.py experiments/official_daily_ntl_fastpath/scan_ntl_availability.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_ui_ntl_availability_snapshot.py`
  - Result: `3 passed`
- `conda run -n NTL-GPT python experiments/official_daily_ntl_fastpath/scan_ntl_availability.py --sources nrt_priority --granule-start-date 2026-02-01 --granule-end-date 2026-02-24 --include-gee`
  - Result: `official_rows=5`, `gee_rows=7`, `rows=12`

## [2026-02-24] v2026.02.24.7 Sidebar-Reset-Label-To-New
### Scope
- Updated sidebar reset-related user-facing text from `Reset` semantics to `New`, without changing internal logic or identifiers.

### Files
- `app_ui.py`

### Changes
- Changed sidebar action button label:
  - from `_tr("重置", "Reset")`
  - to `_tr("新建", "New")`
- Changed post-action notice text:
  - from `_tr("系统已重置。", "System reset.")`
  - to `_tr("已创建新会话。", "New session created.")`
- Kept all internal behavior and identifiers unchanged:
  - `key="reset_btn"` unchanged
  - `app_state.reset_chat()` unchanged
  - CSS selector `.st-key-reset_btn` unchanged

### Verification
- `rg -n "重置|Reset|系统已重置|System reset|新建|New|已创建新会话|New session created" app_ui.py`
  - Result: only `新建/New` and `已创建新会话/New session created` remain in sidebar action area
- `rg -n "reset_btn|reset_chat\\(|st-key-reset_btn" app_ui.py app_state.py`
  - Result: internal key/function/CSS selector preserved as required

## [2026-02-24] v2026.02.24.8 Guest-Thread-Isolation-Anonymous-Default
### Scope
- Fixed default `guest` identity leakage risk by switching first-entry identity to anonymous unique user IDs.
- Blocked `guest/debug/default` as reserved usernames in sidebar user switch flow.
- Removed implicit cross-user thread binding when current thread is not owned by selected user.

### Files
- `history_store.py`
- `app_state.py`
- `app_ui.py`
- `tests/test_user_identity_isolation.py`
- `tests/test_user_reserved_name_policy.py`
- `tests/test_user_thread_no_cross_bind.py`

### Changes
- `history_store.py`
  - Added reserved-name policy:
    - `RESERVED_USER_IDS = {"guest", "debug", "default"}`
    - `is_reserved_user_id(...)`
    - `is_reserved_user_name(...)`
  - Added anonymous identity helper:
    - `generate_anonymous_user_id()` (`anon-xxxxxxxx`)
- `app_state.py`
  - Removed default `guest` initialization in `init_app()`.
  - Added first-entry / reserved-ID migration to anonymous identity.
  - When identity is migrated, force a fresh per-user thread and clear in-memory chat history.
  - Kept existing thread/history storage schema and binding APIs.
- `app_ui.py` (`render_sidebar`)
  - Added anonymous-session caption near user input.
  - Added reserved-name guard for `guest/debug/default` (reject switch, keep current user).
  - Removed implicit binding path:
    - deleted behavior equivalent to `bind_thread_to_user(current_user_id, current_tid)` for unknown current thread.
  - New behavior for unknown current thread:
    - switch to latest owned thread if exists; otherwise create new owned thread.
  - Reset/New action now ensures target user is non-reserved; falls back to new anonymous user when needed.

### Verification
- `conda run -n NTL-GPT pytest -q tests/test_user_identity_isolation.py tests/test_user_reserved_name_policy.py tests/test_user_thread_no_cross_bind.py tests/test_history_store_injected_context.py`
  - Result: `13 passed`
- `conda run -n NTL-GPT pytest -q tests/test_ui_outputs_thread_workspace.py tests/test_app_runtime_resilience.py`
  - Result: `7 passed`

## [2026-02-24] v2026.02.24.9 Enforce-Username-Creation-Before-Activation
### Scope
- Tightened identity policy from "anonymous default allowed" to "username setup required before activation/new session".
- Added `anonymous` to reserved-name policy to avoid effectively shared generic identity labels.

### Files
- `history_store.py`
- `app_ui.py`
- `tests/test_user_reserved_name_policy.py`
- `tests/test_user_identity_gate_ui.py`

### Changes
- Reserved names now include: `guest`, `debug`, `default`, `anonymous`.
- Sidebar behavior:
  - Shows explicit onboarding hint: create username first.
  - If username is empty or reserved, switch is rejected and warning is shown.
  - History thread selector remains hidden/disabled until username is ready.
- Action buttons:
  - `Activate` and `New` are disabled until a valid non-reserved username is set.
- Existing cross-user thread safety behavior remains:
  - no implicit bind of unknown `current_tid` to current user.

### Verification
- `conda run -n NTL-GPT pytest -q tests/test_user_identity_isolation.py tests/test_user_reserved_name_policy.py tests/test_user_thread_no_cross_bind.py tests/test_user_identity_gate_ui.py tests/test_history_store_injected_context.py`
  - Result: `15 passed`
- `conda run -n NTL-GPT pytest -q tests/test_ui_outputs_thread_workspace.py tests/test_app_runtime_resilience.py`
  - Result: `7 passed`

## [2026-02-24] v2026.02.24.7 Sidebar-Availability-GEE-First-Ordering
### Scope
- Adjusted sidebar NTL availability table ordering so GEE rows are always listed before official-source rows.

### Files
- `app_ui.py`
- `tests/test_ui_ntl_availability_snapshot.py`

### Changes
- Added row typing and ordering helpers:
  - `_is_gee_row(...)`
  - `_order_availability_rows(...)`
- Extended normalized rows with `source_type` passthrough.
- Applied ordering at snapshot build stage so all render paths (local scan / monitor API fallback) consistently show GEE-first order.
- Added regression tests:
  - source_type-driven GEE-first ordering
  - source-name fallback (`GEE ...`) ordering

### Verification
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_ui_ntl_availability_snapshot.py`
  - Result: `5 passed`

## [2026-02-24] v2026.02.24.5 Uploaded-PDF-Image-Understanding-As-Engineer-Tools
### Scope
- Switched from runtime auto intent-gating to explicit Engineer tool invocation for uploaded PDF/image understanding.
- Registered dedicated LangChain tools for PDF and image understanding.

### Files
- `tools/uploaded_file_understanding_tool.py`
- `tools/__init__.py`
- `agents/NTL_Engineer.py`
- `app_logic.py`
- `tests/test_uploaded_understanding_tools_registry.py`

### Changes
- Added and registered three tools:
  - `uploaded_pdf_understanding_tool`
  - `uploaded_image_understanding_tool`
  - `uploaded_file_understanding_tool`
- Updated tool descriptions with invocation intent guidance:
  - PDF summary/read/extract requests -> `uploaded_pdf_understanding_tool`
  - image/photo/screenshot description -> `uploaded_image_understanding_tool`
- Updated Engineer system prompt to prioritize uploaded-file understanding tools for these requests.
- Removed runtime auto-injection gate from `handle_userinput` (no implicit image/pdf auto parse in app logic).
- Manual trigger UI remains hidden (already removed from `Streamlit.py` render path).
- Added registry test asserting uploaded understanding tools are present in `Engineer_tools`.

### Verification
- `python -m py_compile app_logic.py tools/uploaded_file_understanding_tool.py tools/__init__.py agents/NTL_Engineer.py Streamlit.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_uploaded_understanding_tools_registry.py tests/test_engineer_tool_registry.py tests/test_history_store_injected_context.py tests/test_file_context_service_vlm_image.py`
  - Result: `9 passed`

## [2026-02-24] v2026.02.24.6 Uploaded-Understanding-Tool-Card-Rendering
### Scope
- Added dedicated reasoning UI rendering cards for uploaded-file understanding tools.

### Files
- `app_ui.py`

### Changes
- Added `render_uploaded_understanding_output(...)` to render:
  - status
  - target files
  - injection stats
  - warnings
  - relevant snippets (source/type/page/score/text)
  - raw JSON popover fallback
- In reasoning tool-output branch, routed tool names below to dedicated renderer:
  - `uploaded_pdf_understanding_tool`
  - `uploaded_image_understanding_tool`
  - `uploaded_file_understanding_tool`

### Verification
- `python -m py_compile app_ui.py app_logic.py tools/uploaded_file_understanding_tool.py tools/__init__.py agents/NTL_Engineer.py Streamlit.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_uploaded_understanding_tools_registry.py tests/test_engineer_tool_registry.py tests/test_ntl_engineer_prompt_constraints.py tests/test_file_context_service_vlm_image.py`
  - Result: `12 passed`

## [2026-02-24] v2026.02.24.7 Hotfix-AppLogic-Re-Import
### Scope
- Fixed runtime `NameError: name 're' is not defined` in `app_logic` during final answer extraction.

### Files
- `app_logic.py`

### Changes
- Restored missing `import re` at module top.

### Verification
- `python -m py_compile app_logic.py`
  - Result: `exit 0`


## [2026-02-24] v2026.02.24.8 Uploaded-Understanding-Status-Semantics-Fix
### Scope
- Fixed misleading status semantics for uploaded PDF/image understanding tool outputs in Reasoning panel.

### Files
- `tools/uploaded_file_understanding_tool.py`
- `app_ui.py`
- `tests/test_uploaded_understanding_status.py`

### Changes
- Refined tool status mapping in `uploaded_file_understanding_tool`:
  - `success`: relevant snippets found.
  - `context_injected_no_match`: parsing/index injection succeeded, but current query had no direct snippet hit.
  - `no_relevant_snippet`: neither direct hit nor meaningful injected context for this query.
- Updated UI renderer for uploaded understanding cards:
  - Added explicit info message for `context_injected_no_match` to avoid false failure perception.
- Added regression tests for the three statuses above.

### Verification
- `python -m py_compile tools/uploaded_file_understanding_tool.py app_ui.py tests/test_uploaded_understanding_status.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_uploaded_understanding_status.py tests/test_uploaded_understanding_tools_registry.py`
  - Result: `4 passed`


## [2026-02-24] v2026.02.24.9 Uploaded-Filename-Match-Robustness
### Scope
- Fixed uploaded PDF/image filename matching for long Chinese/English names with spaces and brackets.

### Files
- `history_store.py`
- `tools/uploaded_file_understanding_tool.py`
- `tests/test_history_store_injected_context.py`

### Changes
- Added normalized filename matching (whitespace-insensitive) for query/file alignment.
- Retrieval path now falls back to normalized source-name match when regex mention extraction misses.
- Default uploaded-file picker now also uses normalized filename matching for robust target selection.
- Added regression tests for:
  - Chinese long filename with brackets + `) .pdf` query variant.
  - English filename with spaces + `.pdf` spacing variant.

### Verification
- `python -m py_compile history_store.py tools/uploaded_file_understanding_tool.py tests/test_history_store_injected_context.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_history_store_injected_context.py tests/test_uploaded_understanding_status.py`
  - Result: `9 passed`


## [2026-02-24] v2026.02.24.10 ChatInput-Paste-Upload-To-Inputs
### Scope
- Enabled chat input attachment upload path so pasted/sent screenshots can be saved directly into current thread `inputs/`.

### Files
- `app_ui.py`
- `tests/test_chat_input_file_support.py`

### Changes
- Upgraded `get_user_input()` to use Streamlit chat attachments:
  - `st.chat_input(..., accept_file="multiple", file_type=[images,pdf])`
- Added normalization helpers for `st.chat_input` return payload (`str | ChatInputValue`).
- Added chat-attachment persistence to workspace:
  - saves files into `user_data/<thread_id>/inputs/`
  - collision-safe naming (`name.ext` -> `name_1.ext` ...)
- UX behavior:
  - if user submits attachments without text, files are still saved and assistant posts a short confirmation.

### Verification
- `python -m py_compile app_ui.py tests/test_chat_input_file_support.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_chat_input_file_support.py`
  - Result: `3 passed`


## [2026-02-24] v2026.02.24.11 ChatInput-CtrlV-Screenshot-Support
### Scope
- Added GPT-like paste/upload behavior on main chat input using a multimodal Streamlit component.

### Files
- `app_ui.py`
- `tests/test_chat_input_file_support.py`

### Changes
- Integrated `st-chat-input-multimodal` as preferred chat input backend (fallback to native `st.chat_input` if unavailable).
- Main input now supports text + pasted/uploaded files in one control.
- Added decoder for multimodal component file payload (`base64` / data URL).
- Preserved thread workspace isolation: pasted files are saved to current `inputs/` with collision-safe names.

### Verification
- `python -m py_compile app_ui.py tests/test_chat_input_file_support.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_chat_input_file_support.py`
  - Result: `4 passed`

- Added dependency pin in `requirements.txt`:
  - `st-chat-input-multimodal==1.0.6`

## [2026-02-24] v2026.02.24.12 Anonymous-Display-Blank-Username-Input
### Scope
- Changed default anonymous username display from `anonymous` to blank in sidebar input.
- Kept isolation behavior unchanged (`user_id` remains unique `anon-*`).

### Files
- `app_state.py`
- `app_ui.py`
- `tests/test_user_identity_gate_ui.py`

### Changes
- Anonymous bootstrap now sets `st.session_state["user_name"] = ""`.
- For existing anonymous `user_id` sessions, fallback keeps username blank instead of restoring a display name.
- Sidebar user input default now uses blank value for anonymous sessions.
- `New` action anonymous fallback also keeps blank username display.
- Added regression test to prevent reintroducing `"anonymous"` as sidebar default input value.

### Verification
- `conda run -n NTL-GPT pytest -q tests/test_user_identity_isolation.py tests/test_user_reserved_name_policy.py tests/test_user_identity_gate_ui.py`
  - Result: command fallback to `python -m pytest`, `8 passed`

## [2026-02-24] v2026.02.24.8 NTL-Availability-Shared-1h-Cache-With-Refresh-Lock
### Scope
- Implemented shared 1-hour local cache for sidebar `NTL Data Availability` to avoid per-user repeated refreshes.
- Added refresh lock so multi-user/multi-thread sessions do not trigger concurrent scan jobs.

### Files
- `app_ui.py`
- `tests/test_ui_ntl_availability_snapshot.py`

### Changes
- Added shared cache policy constants:
  - `_NTL_SCAN_REFRESH_SECONDS = 3600`
  - `_NTL_SCAN_LOCK_FILE`
  - `_NTL_SCAN_LOCK_STALE_SECONDS`
- Added cache/lock helpers:
  - `_scan_age_seconds(...)`
  - `_is_scan_fresh(...)`
  - `_try_acquire_scan_refresh_lock(...)`
  - `_release_scan_refresh_lock(...)`
- Updated availability loading flow:
  - If latest local scan JSON is fresh (<=1h), return directly for all users (`local_cache_fresh_1h`).
  - If stale/missing, only lock holder runs scan refresh; others use existing cache (`shared refresh in progress, using local cache`).
  - After refresh attempt, reload latest local JSON and serve it.
  - Fallback to monitor API remains as final fallback.
- UX optimization:
  - Initial render now skips spinner when fresh local cache already exists.

### Verification
- `conda run --no-capture-output -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_ui_ntl_availability_snapshot.py`
  - Result: `7 passed`
- `conda run --no-capture-output -n NTL-GPT python -m pytest -q tests/official_daily_fastpath/test_scan_ntl_availability_gee.py`
  - Result: `2 passed`

## [2026-02-24] v2026.02.24.13 Stop-Idle-Info-Notice-Removed
### Scope
- Removed idle info toast after pressing `Stop` when no task is running.

### Files
- `app_ui.py`

### Changes
- In sidebar `Stop` action handler, deleted the `else` branch that showed:
  - `当前没有正在运行的任务。 / No task is currently running.`
- Behavior now:
  - Running task: keep existing interrupt request flow and warning.
  - No running task: no extra UI message.

### Verification
- `rg -n "No task is currently running|当前没有正在运行的任务" app_ui.py`
  - Result: no matches
- `conda run -n NTL-GPT python -m py_compile app_ui.py`
  - Result: `exit 0`

## [2026-02-24] v2026.02.24.14 Multimodal-Chat-Input-Paste-Focus-Fix
### Scope
- Fixed multimodal chat input becoming non-editable/non-sendable after image paste.
- Kept chat input positioning behavior, but removed fragile deep iframe style overrides.

### Files
- `app_ui.py`

### Changes
- Simplified `styleMultimodalFrame(...)` in `scroll_to_bottom()`:
  - Removed deep in-iframe overrides for root wrapper, input shell, textarea, buttons, and drop-hint layers.
  - Kept only safe container/frame shell cleanup (`transparent`, `no border/shadow/outline`).
  - Switched from fixed frame height to dynamic height based on iframe document scroll height, capped at `220px`.
- Goal: avoid blocking overlays or broken focus chain after pasted attachments.

### Verification
- `python -m py_compile app_ui.py`
  - Result: `exit 0`
- `conda run -n NTL-GPT python -m pytest -q tests/test_chat_input_file_support.py tests/test_file_context_service_vlm_image.py`
  - Result: `6 passed`

## [2026-02-24] v2026.02.24.15 Sidebar-TestCases-DataCenter-Gap-Tightening
### Scope
- Reduced excessive vertical gap between sidebar `Test Cases` block and `Data Center` section.
- Kept existing layout and controls unchanged; only spacing and divider style adjusted.

### Files
- `app_ui.py`

### Changes
- Added tighter sidebar section spacing styles:
  - `[data-testid="stSidebar"] h3` margins reduced.
  - new `.ntl-sidebar-divider-tight` compact gradient divider class.
- Replaced `render_download_center()` separator from default markdown `---` to:
  - `st.sidebar.markdown("<div class='ntl-sidebar-divider-tight'></div>", unsafe_allow_html=True)`

### Verification
- `python -m py_compile app_ui.py`
  - Result: `exit 0`
- `rg -n "ntl-sidebar-divider-tight" app_ui.py`
  - Result: style class and usage lines found
