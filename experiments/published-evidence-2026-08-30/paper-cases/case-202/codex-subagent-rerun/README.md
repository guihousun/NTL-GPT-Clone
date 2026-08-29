# Codex 子智能体案例证据重做（2026-08-17）

## 身份与边界

本目录记录一次 **Codex-subagent case-evidence simulation**。主协调者按 NTL Engineer 的职责组织三个真实 Codex 子智能体：NTL Event Tracker、NTL Data Searcher 与 NTL Analyst。各角色的输入、输出、验证与局限均留在本目录。

这不是部署版 NTL-GPT 或 Deep Agents runtime 的执行记录；不伪造模型调用、角色遥测、结构化包交接或系统运行状态。本目录也不是 200 题 benchmark、Full-vs-Single 对比或其资源消耗的一部分。

## 本轮目标

优先重做 Q19：以 City of Tehran 的 geoBoundaries ADM2 行政区为候选 AOI，按 **2026-01-01 至 2026-02-27 UTC** 的完整冲突前基线重新计算描述性比较与图件输入。旧 Q19 任何使用 2026-02-14 至 2026-02-27 基线的数值仅作可追溯输入，不能直接复用为本轮结果。

随后对已验证的 Q18（缅甸地震正式 25/50 km）与 Q17（SDGSAT-1 分类）补做同一类型的角色参与和证据边界复核；不重写其已有数据或图件。

## 目录说明

- `experiment-contract.md`：冻结的问题、时间、输入、允许结论与禁止结论。
- `engineer/`：协调、验收、跨角色核验和最终 paper-facing evidence record。
- `role-outputs/event-tracker/`：事件来源、空间筛选、城市排名与时间线核验。
- `role-outputs/data-searcher/`：产品、AOI、日序列、QA 与输入完整性核验。
- `role-outputs/analyst/`：重算脚本、可复算表、图件输入、独立验证与分析结论。
- `input-manifests/`：只读来源路径、文件哈希和读取状态。
- `derived/`：本轮新生成的可复算表和图件输入；不覆盖既有案例资产。
- `validation/`：Engineer 的独立复核和结论边界矩阵。

## 旧资产与引用范围

本轮仅引用、不会改写以下旧资产：

- `../paper-case-multiagent-2026-08-13/Q19-tehran-city-longseries/`
- `../paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/`
- `../paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/`
- `../../decisions/2026-08-17-q18-formal-25km-50km-supports.md`
- `../../deliverables/figure-drafts/ntl-gpt-case-figures-unified-2026-08-17-v9-formal-25km-50km/`

## Status

`q19_accepted_with_boundaries` — Event Tracker、Data Searcher 和 Analyst recovery 已产生可审计 Q19 证据；Engineer 三方复算通过。下一步是 Q17/Q18 的同型角色证据复核和全包证据矩阵。
