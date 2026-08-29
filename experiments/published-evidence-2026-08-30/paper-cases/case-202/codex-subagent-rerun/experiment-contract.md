# 实验合同：Codex 子智能体案例证据重做

## 1. 目的

为 JAG 活动稿的案例叙述补齐可审查的工作流与科学证据；不评价部署版 NTL-GPT 性能，也不替代 benchmark。

## 2. 角色与职责

| 角色 | 真实承担者 | 有界职责 | 必交产物 |
|---|---|---|---|
| NTL Engineer | 本任务主协调者 | 冻结合同、验收、路由、交叉复核、结论边界 | `engineer/acceptance-log.md`、最终 evidence record |
| NTL Event Tracker | Codex 子智能体 | 事件来源、时间语义、行政区空间归属与排名 | 事件审计、排名表、局限 |
| NTL Data Searcher | Codex 子智能体 | AOI、产品、观测日期、日序列与 QA 输入完整性 | 输入/QA 审计、来源清单、局限 |
| NTL Analyst | Codex 子智能体 | 按冻结输入重算描述统计、图件输入与独立数值检查 | 脚本、表格、结果、验证 |

每个角色只能在其 `role-outputs/<role>/` 子目录新增本轮产物。角色不得改动活动手稿、既有案例资产、图件附件、Zotero、benchmark 或 runtime 仓库。

## 3. Q19 冻结分析合同

- AOI：`City of Tehran`，以既有 Q19 中记录的 geoBoundaries ADM2/canonical Shahrestan 几何为唯一候选行政区；需重验几何/元数据。
- 时间基准：UTC。所有日期窗口采用闭区间并在代码中明确处理。
- 冲突前基线：**2026-01-01 至 2026-02-27 UTC**，不得缩短为 2026-02-14 至 2026-02-27。
- 后续窗口：沿既有已审计事件合同读取；若事件日期或语义不能从来源证实，只能保留为“未支持”或中性观察期，不得自行补写。
- 夜间灯光产品：既有 Q19 数据包声明的 VNP46A2 日产品与已记录 QA 口径；必须由 Data Searcher 核验具体 band、有效性规则、可用日期和缺口。
- 输出：日尺度图件输入、窗口汇总表、计算脚本、结果 JSON、独立复算/一致性检查。

## 4. 事件城市选择规则

1. Event Tracker 必须说明来源、查询/快照日期、保留规则、行政区归属算法和完整性限制。
2. 仅当可复算的排名表明确支持时，Engineer 才能将 City of Tehran 写为“highest-ranked city”。
3. 若排名不支持或输入不完整，案例可继续使用 City of Tehran 作为预先指定的行政 AOI，但相关文字必须改为中性表述，且最终矩阵标明“highest-ranked”不可用。

## 5. 可写与不可写

可写：已核验产品/日期/AOI、描述性窗口比较、观测缺口、来源覆盖边界、角色实际生成的文件。

不可写：由本模拟证明部署版 NTL-GPT 已运行、Deep Agents 运行成功、四角色系统性能、Full-vs-Single 优势、事件造成夜间灯光变化、恢复轨迹或连续主动监测。

## 6. 验收最低条件

- 每一个主结论有路径、哈希或脚本以及读回验证。
- 至少一个角色的输出由另一角色或 Engineer 独立复核。
- 任何未通过的来源/数据/计算门不得被修辞掩盖；标为 `unsupported`、`partial` 或 `blocked`。
- 角色输出、实验记录与最终交接显式说明本轮为 Codex-subagent simulation。
