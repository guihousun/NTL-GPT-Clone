"""Rewrite manuscript tail sections into RESULTS AND DISCUSSION and CONCLUSION."""

from __future__ import annotations

from pathlib import Path


EN_REPLACEMENT = """## IV. RESULTS AND DISCUSSION

### A. Event Retrieval and Screening Results

The current ConflictNTL workflow has completed event retrieval, event screening, AOI generation, same-day AOI aggregation, official VNP46A1 CMR query, and local HDF5 smoke testing. Table I summarizes the current pipeline outputs. From 3,093 ISW records in the experiment window, 3,008 records passed the first source/geometry screening stage, and 1,420 events were promoted into the NTL candidate queue. Iran and Israel account for 1,235 of these candidates, while 185 events are retained as spillover/context records.

| Stage | Current output |
|---|---:|
| ISW records in experiment window | 3,093 |
| Round-1 event candidates | 3,008 |
| Promoted NTL candidates | 1,420 |
| Iran/Israel main-focus NTL candidates | 1,235 |
| Spillover/context NTL candidates | 185 |
| Analysis units after same-day AOI aggregation | 930 |
| VNP46A1 CMR query associations for target window | 1,106 |
| Unique official VNP46A1 HDF5 granules after deduplication | 553 |
| Local VNP46A1 smoke-test daily AOI rows | 5 |

These results indicate that the agent-assisted event triage step is necessary before imagery processing. The workflow filters source and geometry eligibility before NTL applicability, reducing the risk that air-defense activity, unknown-target explosions, or non-fixed-target records enter the remote-sensing analysis chain.

### B. AOI Aggregation and Official Data Retrieval

The 1,420 NTL candidate events were aggregated into 930 analysis units after same-day spatial aggregation. This reduction reflects the need to avoid repeated NTL statistics over highly overlapping same-day buffers or identical administrative AOIs. The resulting analysis units provide the spatial basis for source-aligned NTL statistics.

The CMR query returned 1,106 query associations from February 20 to April 10, 2026 for the full ConflictNTL AOI extent. After deduplication by official HDF5 granule, these records correspond to 553 unique VNP46A1 files that can be reused across all intersecting analysis units. This confirms that granule-level deduplication is required because multiple units and query dates can refer to the same official tile-date file.

### C. VNP46A1 Processing Status and Expected NTL Outputs

A local VNP46A1 HDF5 file was used to verify the technical path for reading `DNB_At_Sensor_Radiance`, `UTC_Time`, quality fields, and AOI-level statistics. This smoke test is not interpreted as a scientific result because the test image date does not align with the event windows of the selected AOIs; it only validates the data path and statistic extraction.

After full VNP46A1 download and processing, the expected outputs are: event screening summaries, AOI aggregation summaries, daily AOI-level VNP46A1 statistics, and ranked source-aligned NTL change signals. These signals should be reported as candidate conflict-associated NTL anomalies rather than confirmed damage. Group summaries by country, site type, and AOI type can further compare energy, industrial, airport, port, military-site, urban, and administrative AOIs.

### D. Discussion and Limitations

The proposed workflow shifts conflict-related NTL analysis from retrospective case selection to event-triggered analysis. Its main value is that it makes event retrieval, screening, AOI construction, official data querying, quality control, and reporting explicit and reproducible. Event records preserve original ISW attributes and renderer classifications; AOI construction follows documented rules; VNP46A1 granules are recorded through official CMR metadata; and statistics are computed with explicit temporal windows and quality flags.

The main limitation is that source-aligned NTL changes are not equivalent to confirmed conflict damage. Clouds, lunar conditions, fires, industrial flaring, seasonal activity, displacement, reporting uncertainty, and non-conflict human activity can all affect observed radiance. Therefore, consistent with agentic disaster-response studies, ConflictNTL outputs should be treated as inputs for expert review and source triangulation rather than as automatic causal conclusions.

### E. Planned Figures and Tables

Figure 1: ConflictNTL event-triggered multi-agent workflow, including event retrieval, two-stage screening, AOI generation, VNP46A1 retrieval, QA/statistics, and report generation.

Figure 2: Spatial distribution of promoted NTL candidate events and aggregated analysis units.

Figure 3: Official VNP46A1 granule coverage and analysis windows.

Figure 4: Example AOI-level daily NTL time series with baseline, event, and recovery windows.

Table I: Current pipeline outputs and counts.

Table II: Data sources and products.

Table III: Two-stage event screening rules.

Table IV: Top source-aligned NTL decrease/increase AOIs after full processing.

## V. CONCLUSION

This Letter presents ConflictNTL, an agent-assisted event-triggered workflow for linking open-source conflict monitoring with daily nighttime light remote sensing. Using U.S. and Israeli strikes in Iran during the 2026 Middle East conflict as the case study, the workflow retrieves and screens conflict events, constructs analysis units, queries official NASA LAADS VNP46A1 granules, and prepares AOI-level NTL statistics in a reproducible manner.

The current implementation demonstrates the feasibility of scaling from thousands of open-source event records to a structured set of NTL-ready analysis units and deduplicated official VNP46A1 granules. The framework does not claim automatic damage confirmation. Instead, it provides a traceable pipeline for generating source-aligned candidate NTL change signals that can support expert review, source triangulation, and subsequent conflict-impact assessment.

"""


CN_REPLACEMENT = """## IV. RESULTS AND DISCUSSION

### A. 事件检索与筛选结果

当前 ConflictNTL 工作流已经完成事件检索、事件筛选、AOI 构建、同日 AOI 聚合、官方 VNP46A1 CMR 查询和本地 HDF5 小样本验证。表 I 总结了当前 pipeline 输出。从实验窗口内 3,093 条 ISW 事件记录出发，3,008 条记录通过第一阶段来源和几何筛选，1,420 条事件进入夜光候选队列。其中，伊朗和以色列主体分析候选事件为 1,235 条，另有 185 条事件作为 spillover/context records 保留。

| 阶段 | 当前结果 |
|---|---:|
| 实验窗口内 ISW 事件记录 | 3,093 |
| 第一阶段 event candidates | 3,008 |
| 进入夜光候选队列事件 | 1,420 |
| 伊朗/以色列主体分析候选事件 | 1,235 |
| 外溢/context 候选事件 | 185 |
| 聚合后的 analysis units | 930 |
| 目标窗口内 VNP46A1 CMR 查询关联记录 | 1,106 |
| 去重后的唯一官方 VNP46A1 HDF5 granules | 553 |
| 本地 VNP46A1 smoke test 生成的 AOI 日统计记录 | 5 |

这些结果说明，在进入影像处理之前开展 agent-assisted event triage 是必要的。工作流先判断来源和几何可用性，再判断夜光适用性，从而降低防空活动、未知目标爆炸或无固定目标记录进入遥感分析链条的风险。

### B. AOI 聚合与官方数据检索

1,420 条夜光候选事件经过同日空间聚合后形成 930 个 analysis units。这一减少反映了同日高度重叠 buffer 或相同管理区 AOI 不能重复统计的必要性。聚合后的 analysis units 构成了后续 source-aligned NTL statistics 的空间基础。

CMR 查询已经为完整 ConflictNTL AOI 范围返回 2026-02-20 至 2026-04-10 的 1,106 条查询关联记录。按官方 HDF5 granule 去重后，这些记录对应 553 个唯一 VNP46A1 文件，可供所有相交 analysis units 复用。这说明 granule 级去重是必要的，因为多个 analysis units 和多个查询日期可能指向同一个官方 tile-date 文件。

### C. VNP46A1 处理状态与预期夜光结果

本地已有 VNP46A1 HDF5 文件用于验证 `DNB_At_Sensor_Radiance`、`UTC_Time`、质量字段和 AOI 级统计读取链条。该 smoke test 不作为科学结果解读，因为测试影像日期与所选 AOI 的事件窗口并不匹配；它只说明数据读取和统计链条可运行。

在完成全量 VNP46A1 下载和处理后，预期输出包括事件筛选汇总、AOI 聚合汇总、AOI 日尺度 VNP46A1 统计，以及按变化幅度排序的 source-aligned NTL change signals。这些信号应表述为 candidate conflict-associated NTL anomalies，而不是 confirmed damage。后续还可以按国家、目标类型和 AOI 类型分组，比较 energy、industrial、airport、port、military site、urban 和 administrative AOIs 的夜光变化差异。

### D. 讨论与局限

本文工作流将冲突夜光分析从事后人工选题推进为事件触发式分析。其主要价值在于，把事件检索、事件筛选、AOI 构建、官方数据查询、质量控制和报告生成组织为明确、可追踪和可复现的链条。事件记录保留 ISW 原始字段和 renderer 分类；AOI 构建采用明确规则；VNP46A1 数据通过官方 CMR metadata 记录 granule 来源；统计窗口、质量控制和变化指标也明确写入输出文件。

本文的主要限制是，事件源对齐的夜光变化并不等于确认的冲突损伤。云、月光、火灾、工业燃烧、季节性活动、人口流动、报告误差和其他非冲突因素都可能影响夜光辐亮度。因此，与 agentic disaster-response 文献一致，ConflictNTL 输出应作为专家复核和独立信源交叉验证的输入，而不是自动因果结论。

### E. 图表计划

图 1：ConflictNTL 事件触发式多智能体工作流，包括事件检索、两阶段筛选、AOI 构建、VNP46A1 检索、QA/statistics 和报告生成。

图 2：进入夜光候选队列的事件点和聚合后 analysis units 的空间分布。

图 3：VNP46A1 官方 granule 覆盖和分析时间窗口。

图 4：典型 AOI 的日尺度 NTL 时间序列，标注 baseline、event window 和 recovery window。

表 I：当前 pipeline 输出和数量统计。

表 II：数据源与产品说明。

表 III：两阶段事件筛选规则。

表 IV：全量处理后 Top N 夜光下降和上升 AOI。

## V. CONCLUSION

本文提出 ConflictNTL，一个用于连接开源冲突监测和日尺度夜间灯光遥感的 agent-assisted event-triggered workflow。以 2026 年中东冲突期间美国和以色列对伊朗的打击为案例，ConflictNTL 能够检索和筛选冲突事件、构建分析单元、查询 NASA LAADS 官方 VNP46A1 granules，并以可复现方式准备 AOI 级夜光统计。

当前实现表明，该框架能够将数千条开源事件记录转化为结构化的夜光分析单元和去重后的官方 VNP46A1 granule 清单。该框架不自动确认损伤或因果关系，而是提供一条可追踪的 pipeline，用于生成 source-aligned candidate NTL change signals，并支持后续专家复核、多源验证和冲突影响评估。

"""


def replace_tail(path: Path, start_marker: str, end_marker: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker)
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def main() -> int:
    replace_tail(
        Path("docs/ConflictNTL_Letter_Manuscript_Draft.md"),
        "## IV. CURRENT EXPERIMENTAL STATUS",
        "## References",
        EN_REPLACEMENT,
    )
    replace_tail(
        Path("docs/ConflictNTL_Letter_Manuscript_Draft_CN.md"),
        "## IV. 当前实验进展",
        "## 参考文献",
        CN_REPLACEMENT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
