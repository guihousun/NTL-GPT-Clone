# 活动稿可使用／仍不可使用证据矩阵

本矩阵只给论文写作任务提供证据边界，不修改活动手稿或图件附件。

| 案例 | 可使用的论文陈述 | 必须修改或补足 | 不可使用的陈述 |
|---|---|---|---|
| Q17 SDGSAT-1 | 固定 RRLI/RBLI 有序规则、分类 GeoTIFF、像元统计，以及与旧实现的 88.78% implementation agreement；当前请求不需 Event Tracker，条件性跳过是合理路由。 | 将“Data Searcher 完成去条带、椒盐去噪和辐射定标”改为“核验用户提供的 analysis-ready RGB，并构建 RRLI/RBLI”。 | 88.78% classification accuracy；独立真值、最优阈值、跨区域泛化，或本模拟证明部署版 runtime。 |
| Q18 Myanmar | USGS 主震、16 个官方 VNP46A2 HDF5、严格 QA、25 km −29.61%（n=6）和 50 km +4.92%（n=7）的首个事件后本地夜描述性比较。 | 将活动稿和图注中的旧 25/100 km、+20.56% 改成 25/50 km、+4.92%；明确两个支持范围方向相反。 | 恢复轨迹、停电/损毁/地震因果、显著性、真实影响半径或连续监测。 |
| Q19 Tehran | geoBoundaries ADM2/Shahrestan、2026-01-01—02-27 UTC 完整基线；严格 QA 的冲突期 −17.271%、固定 4/8—4/21 分析期 −8.736%；日序列到 7/31。 | 把无条件“highest-ranked city”改为“在精确坐标、保留事件子集内排名第一的 ADM2”，或仅称预先定义的 City of Tehran AOI。 | 将 4/22 写为停火结束；总体最高排名、municipality/功能城市、因果／恢复／持续实时监测，或部署版 runtime 证据。 |
| 全部案例 | 可作为 Codex 子智能体案例证据模拟，展示职责边界、可审查输入/输出和科学限制。 | Section III 或方法补充中应区分模拟案例证据与 runtime/benchmark 证据。 | 用于证明 Deep Agents 已部署运行、200 题性能或 Full 相对 Single 的净增益。 |

详细机器可读版见 `paper-evidence-matrix.csv`。
