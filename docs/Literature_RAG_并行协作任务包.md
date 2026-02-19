# Literature_RAG 并行协作任务包（给第二个 Codex）
更新时间：2026-02-17

## 1. 当前现状（必须先读）
1. `Literature_RAG` 目前为空集合（count=0）。
2. `agents/NTL_Knowledge_Base_manager.py` 目前仅支持两个 profile：`solution`、`code`，没有 `literature` profile。
3. 现有文献源目录已存在：`RAG/literature base`（以 PDF 为主，含中英文文献）。
4. 检索工具已预留：`tools/NTL_Knowledge_Base.py` 中有 `NTL_Literature_Knowledge`，但因为库为空，当前无有效召回。
5. `tools/NTL_Knowledge_Base_Searcher.py` 已接入 Literature store，但优先级仍是 Solution + Code。

## 2. 本轮目标（Literature_RAG）
1. 给 `NTL_Knowledge_Base_manager.py` 增加 `literature` profile。
2. 将 `RAG/literature base` 的 PDF 文献稳定入库到 `RAG/Literature_RAG`（collection: `Literature_RAG`）。
3. 入库 metadata 结构化，至少包含：
`source_file`, `doc_type=literature_paper`, `language`, `title`, `year`, `topic_tags`, `quality_tier`
4. 去重规则可复用当前哈希策略，避免重复页/重复文献。
5. 生成重建报告：`RAG/Literature_RAG/rebuild_report.json`。

## 3. 并行分工（推荐）
### Codex-A（你当前主会话）
1. 负责 ingestion 框架改造：
`agents/NTL_Knowledge_Base_manager.py`
2. 增加 profile 参数：
`--profile literature`
3. 增加默认参数：
- `--literature-dir`（默认 `RAG/literature base`）
- `--persist-dir RAG/Literature_RAG`
- `--collection-name Literature_RAG`
4. 增加测试：
- `tests/test_literature_rag_ingestion_manager.py`
- 断言构建不报错、集合非空、报告字段完整

### Codex-B（并行会话）
1. 负责文献清洗与检索质量：
`tools/NTL_Knowledge_Base.py`
`tools/NTL_Knowledge_Base_Searcher.py`
2. 优化 Literature 检索参数（准确率优先）：
- `k` 建议 5-8
- `score_threshold` 建议 0.22-0.30（按实际命中调）
3. 补测试：
- `tests/test_literature_kb_retriever_config.py`
- `tests/test_literature_kb_smoke_queries.py`
4. 产出 10 条文献问答烟测结论（是否命中论文来源、是否有理论/公式片段）。

## 4. 建议命令
```bash
conda run -n NTL-GPT python agents/NTL_Knowledge_Base_manager.py \
  --profile literature \
  --literature-dir "RAG/literature base" \
  --persist-dir RAG/Literature_RAG \
  --collection-name Literature_RAG \
  --reset \
  --report-path RAG/Literature_RAG/rebuild_report.json
```

## 5. 验收标准
1. `Literature_RAG` 集合 count > 0（建议 >= 300 个 chunk，视文献总量而定）。
2. `NTL_Literature_Knowledge` 查询不再返回 `empty_store`。
3. 至少 10 条文献类问题中，命中率 >= 8/10。
4. 返回内容包含来源信息（文献标题/文件名/页段），可追溯。

## 6. 给第二个 Codex 的可复制提示词
```text
你现在负责 NTL-GPT 的 Literature_RAG 优化。请只做文献检索侧工作，不改 Solution/Code 逻辑。

背景：
- Literature_RAG 当前为空。
- 文献源目录在 RAG/literature base（PDF 为主）。
- NTL_Literature_Knowledge 已存在但无内容可检索。

你的任务：
1) 完善 tools/NTL_Knowledge_Base.py 的 Literature retriever 参数（准确率优先）。
2) 完善 tools/NTL_Knowledge_Base_Searcher.py 中 Literature 调用策略与输出稳定性。
3) 新增并通过测试：
   - tests/test_literature_kb_retriever_config.py
   - tests/test_literature_kb_smoke_queries.py
4) 给出 10 条文献查询烟测结果和参数建议。

约束：
- 不改 app_ui 协议。
- 不改 Solution_RAG / Code_RAG 逻辑。
- 保持 UTF-8 编码。
```

