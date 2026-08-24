# Codex 子智能体案例证据重做：Engineer 最终报告

## 结论

本轮完成了一个可审查的 **Codex-subagent case-evidence simulation**：Event Tracker、Data Searcher 与 Analyst 分别形成真实本地审计/计算文件，Engineer 验收并实施独立复算。该产物可为活动稿的案例叙述补证，但不构成部署版 NTL-GPT、Deep Agents runtime、200 题 benchmark 或 Full-vs-Single 性能证据。

## 实际执行范围

| 案例 | 实际工作 | 状态 |
|---|---|---|
| Q19 Tehran | 事件空间选择审计、VNP46A2 日表/AOI/QA 审计、完整基线重算、独立 Analyst crosscheck、Engineer 第三方验证和图件输入封装 | accepted with boundaries |
| Q18 Myanmar | 对现有正式 25/50 km 资产的事件、数据和分析复核 | usable with revision |
| Q17 SDGSAT-1 | 对现有正式分类资产的条件路由、数据 lineage 和分析统计复核 | usable with revision |

## Q19 更新后的数值（严格 QA 主结果）

- Baseline, 2026-01-01—02-27 UTC: **67.231835 nW cm⁻² sr⁻¹**, 47 qualified days.
- Conflict evaluation, 2026-02-28—04-07: **55.619916**, 20 days, **−17.271%** versus the complete baseline.
- Fixed 2026-04-08—04-21 evaluation window: **61.358263**, 11 days, **−8.736%**.
- Extended monitoring, 2026-04-22—07-31: **59.752430**, 83 days, **−11.125%**.

Permissive QA sensitivity is retained in `role-outputs/analyst-recovery/q19-window-summary.csv`; it does not reverse the sign of the first two comparisons.

The event source can establish only a qualified selection result: City of Tehran is first among 20 candidate ADM2 areas in the exact-coordinate retained-event subset (142/248), whereas a complete overall city rank remains indeterminate. This changes the permissible manuscript wording.

## Verification record

- Q19 Data Searcher read 428 CSV/JSONL rows and verified 19 input checks.
- Q19 Event Tracker produced a 20-row spatial ranking, source hashes and explicit coordinate coverage limits.
- Q19 Analyst recovery recomputed the full baseline; a separate Analyst crosscheck independently matched all eight QA/window combinations.
- Engineer validation then compared the source CSV, both Analyst outputs, the event selection boundary and the generated figure-input constraints: 11/11 checks passed.
- Q17 Data Searcher reopened the four GeoTIFFs and checked four index locations; Q17 Analyst blockwise read back class totals.
- Q18 Data Searcher read all 16 HDF5 inputs and their QA datasets; Q18 Analyst recomputed the two formal table contrasts.

## Required manuscript-facing boundary

Use `validation/paper-evidence-matrix.md` as the direct writing guide. The two most consequential revisions are:

1. Q18 must use the formal 25 km / 50 km values, not the old 25 km / 100 km pair.
2. Q19 must not claim City of Tehran was highest-ranked overall; it may use the exact-coordinate-subset qualification or simply state that it was the selected ADM2 AOI.

## Files and reproducibility

- Q19 evidence record: `paper-facing-evidence-q19.md` and `.json`.
- Q19 source checks: `verify_q19_inputs.py`, `validate_q19_recompute.py`, and `validation/engineer-q19-validation.json`.
- Q19 future-figure tables: Analyst-owned `role-outputs/analyst-recovery/q19-figure-input-*.csv`; Engineer independent packaging in `derived/`.
- Case-wide writing boundary: `validation/paper-evidence-matrix.md` and `.csv`.

No activity in this directory modified the active manuscript, manuscript attachments, Zotero, benchmark source records, existing case packages, or runtime repository.
