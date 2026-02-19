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
