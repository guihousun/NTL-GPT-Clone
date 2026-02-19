# NTL-GPT Parallel Evaluation Runbook (CN)

更新时间: 2026-02-06

## 1. 现状诊断（基于你的仓库）

- Appendix B 标准评测集: 70 cases
  - `data retrieval and preprocessing`: 30
  - `NTL spatial statistic and querying`: 30
  - `NTL application and modeling`: 10
- 你当前 UI 使用的 `test_cases.xlsx`: 44 usable cases
  - 缺失 26 个案例，其中包含高难案例 `#68`、`#70`
- 论文里最能体现模型差异的瓶颈在 `NTL application and modeling`
  - Appendix B 显示该类成功率显著低于前两类

结论: 评委说“实验太少”是合理的，当前测试集覆盖不足且对高难能力展示不够。

## 2. 本方案目标

1. 把评测从 44 恢复到 70（与论文一致）。
2. 增加“高难+扰动”扩展集，重点展示 NTL-GPT 的云端地理编程能力与稳定性。
3. 建立可并行、可复现、可审计的实验流水线，让多个 NTL-GPT/Codex 同时跑并自动汇总。

## 3. 已提供的执行工具

位置: `experiments/parallel_eval/`

- `build_benchmark_pack.py`
  - 从 Appendix B + test_cases 自动生成:
    - `benchmark/canonical_70_cases.csv`
    - `benchmark/current_test_cases_44.csv`
    - `benchmark/missing_26_cases.csv`
    - `benchmark/priority_hard_cases.csv`
    - `benchmark/shard_01.csv ... shard_N.csv`
- `aggregate_results.py`
  - 从统一落盘目录自动聚合，输出:
    - `analysis/summary_overall.csv`
    - `analysis/summary_by_category.csv`
    - `analysis/summary_by_case.csv`
- `templates/attempt_result_template.json`
- `templates/case_result_template.json`

## 4. 一键准备

在项目根目录运行:

```powershell
python experiments/parallel_eval/build_benchmark_pack.py --workers 8
```

建议: `workers` 设置为你并行实例数（例如 4/6/8）。

## 5. 并行执行协议（多 NTL-GPT + 多 Codex）

### 5.1 分片与分工

- 每个实例领取一个 shard 文件（`shard_XX.csv`）
- 每个 case 最多 3 次尝试（与论文口径一致）
  - Attempt 1: 原始请求
  - Attempt 2: 固定补充提示 `try again; fix previous errors only`
  - Attempt 3: 固定补充提示 `final retry; prioritize robust execution`

### 5.2 目录规范（必须统一）

```text
experiments/parallel_eval/runs/<exp_id>/<model>/<worker>/case_<id>/
  attempt_1.json
  attempt_2.json
  attempt_3.json
  case_result.json
  final_answer.md
  events.jsonl
  outputs_manifest.json
```

### 5.3 记录字段（最小必需）

- `success` (bool)
- `hallucination` (bool)
- `execution_error` (bool)
- `runtime_s`
- `output_files`
- `attempt_count` / `attempts_used`

> 按模板写可直接被 `aggregate_results.py` 消费。

## 6. 扩展实验矩阵（用于“实验不够”问题）

## Tier A: 论文一致复现实验（必须）

- 完整跑 70 cases
- 报告指标:
  - Success@3（论文主指标）
  - Pass@1（新增，体现稳定性）
  - Hallucination case frequency
  - Execution-error case frequency
  - Category-level success

## Tier B: 高难增强集（建议 +30 cases）

重点围绕 4 个方向生成扰动样例（每方向 7-8 个）:

1. **长时序日尺度任务（>31 images）**
- 验证是否走 GEE server-side 而不是本地下载

2. **跨源混合与时段边界**
- DMSP/VIIRS 跨年拼接、月/日边界（闰年、月初月末）

3. **空间几何鲁棒性**
- CRS mismatch、invalid geometry、小面元 + 大分辨率冲突

4. **应用建模复杂任务**
- SDG 7.1.1、Urban Center Detection、DEI/Population 泛化

## Tier C: 稳定性压力测试（建议 +20 cases）

- 同一任务 5 次重复运行（不同 thread_id）
- 统计方差:
  - 输出文件数量一致性
  - 数值指标偏差
  - tool-call 轨迹稳定性

## 7. 论文展示建议（直接对应评委问题）

新增 4 张图 + 2 张表:

1. 图1: Pass@1 vs Success@3（3模型对比）
2. 图2: Category-level success（含新增 Tier B）
3. 图3: Hallucination / Execution-error 双轴图
4. 图4: 高难任务（#68/#70 及扰动集）成功率条形图
5. 表1: Case-level hardest 10（错误类型+修复路径）
6. 表2: Multi-agent ablation（禁用 Data_Searcher / 禁用 Geo-CodeCoT / 禁用 Recipe 检索）

## 8. 让 NTL-GPT 特点“可被看见”的关键对照

必须加 3 组消融（同一测试集）:

- Full system (Engineer + Data_Searcher + Code_Assistant + Geo-CodeCoT v2)
- No Geo-CodeCoT preflight
- Single-agent baseline

报告这三项差值:

- Success@3 提升
- Hallucination 下降
- 高难类别（modeling）提升

## 9. 结果汇总命令

```powershell
python experiments/parallel_eval/aggregate_results.py
```

输出位于 `experiments/parallel_eval/analysis/`。

## 10. 建议的执行节奏（3天）

- Day 1: 跑 Tier A（70）+ 修复流程
- Day 2: 跑 Tier B（+30）
- Day 3: 跑 Tier C（+20）+ 聚合 + 出图表

总计建议样本规模: 120。

---

如果你下一步确认，我可以继续把 **Tier B + Tier C 的 50 条扩展案例** 自动生成成标准 CSV（含 category、difficulty、expected outputs、判分规则），可直接导入你现有 UI/批处理流程。

## 附录：NTL-VLM 基准结果聚合（新增）

如果你已经跑完 `benchmarks/ntl_vlm_mvp` 的评测输出（`reports/overall.csv`、`reports/by_task.csv`、`reports/by_split.csv`），可以用以下命令把结果同步到本目录分析区：

```powershell
python experiments/parallel_eval/aggregate_ntl_vlm_scores.py `
  --benchmark-root benchmarks/ntl_vlm_mvp `
  --out-dir experiments/parallel_eval/analysis
```

输出：

- `analysis/ntl_vlm_summary_overall.csv`
- `analysis/ntl_vlm_summary_by_task.csv`
- `analysis/ntl_vlm_summary_by_split.csv`
