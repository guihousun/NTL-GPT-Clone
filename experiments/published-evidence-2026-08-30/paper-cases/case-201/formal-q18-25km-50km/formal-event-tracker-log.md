# Q18 正式 Event Tracker 过程记录

## 角色与边界

- 正式链路：外部控制器 → `NTL Engineer` → `NTL Event Tracker`。
- 本角色只固定事件身份、时间、位置、震级、深度、来源时点、人道数字与来源冲突。
- 本角色没有调用其他 specialist，也没有分析夜间灯光、停电、恢复、损毁或因果。
- 先前由外部控制器直接派发形成的 `event-context.json` 与 `event-tracker-log.md` 未作为正式链产物复用。

## 直接核对的输入

1. USGS 官方域名搜索快照  
   `runtime/experiments/hierarchical_smoke/fixtures/event_sources/usgs_official_domain_search.json`  
   SHA-256: `E70612ADD1A878B8B7CF0E2975AEF309F023465849DEFA83B73BA8E16F843DCB`
2. ReliefWeb 官方域名搜索快照  
   `runtime/experiments/hierarchical_smoke/fixtures/event_sources/reliefweb_official_domain_search.json`  
   SHA-256: `7C087F14AEDAE780740F9C0FAAEE57AAB12154296E5E987E7C2753D0AE830980`
3. 已核事件字段的项目派生参考  
   `vault/ntl-gpt/data/benchmark-v1/fixtures/verified-reference/BV1-015/outputs/myanmar_earthquake_2025_official_event.json`  
   SHA-256: `85F9E272C0D67CD2AEA57A0F7FAD910D3FD39D58D6B15681F12F01337175F745`

未读取 reference manifest，也未读取其中的 `gold_answer`。

## 事件身份固定

- USGS event id：`us7000pn9s`。
- 主震：Mww 7.7，深度 10.0 km，USGS review status 为 `reviewed`。
- UTC：`2025-03-28T06:20:52Z`。
- Asia/Yangon：`2025-03-28T12:50:52+06:30`；由 UTC 加 6 小时 30 分钟得到。ReliefWeb 以分钟精度独立写为 06:20 UTC / 12:50 local。
- 震中：WGS 84 / EPSG:4326，纬度 22.011、经度 95.936；明确的 GIS 顺序为 `(lon, lat) = (95.936, 22.011)`。
- USGS 搜索快照直接给出事件页、时间、坐标、M 7.7 与深度；`mww` 和 `reviewed` 两个字段由项目已核派生参考补充，且在正式 JSON 中保留了这一来源限制，未把它伪装成第二个独立外部来源。

给定快照足以固定主震，因此没有进行 live 网页刷新。这里的 as-of 是“快照于 2026-08-10 被检查”；它不表示所有人道数字都更新到了该日。

## 保留而不消解的来源冲突

ReliefWeb 材料对数分钟后的强震存在不一致：

- 灾害页、UNOSAT 综合评估摘要和 AHA Centre 情况更新写为 M6.4，其中材料给出 06:32 UTC、10 km；
- HNRP Flash Addendum 写为 M6.7，只说“minutes later”，给定摘要没有精确时间或深度。

正式上下文没有在 M6.4 与 M6.7 之间择一，也没有把“aftershock”和“second earthquake”强行统一。下游若只需分析锚点，应使用主震 `2025-03-28T06:20:52Z`，并把后续强震列为潜在时间混杂；若方法必须使用后续事件的精确参数，应另行做事件级核验。

## 人道数字的处理

没有拼接不同日期、不同机构和不同统计口径：

- 2025-03-29 OCHA Flash Update #1：初步报告为逾 1,000 人死亡、逾 2,200 人受伤、约 200 人失踪。
- 2025-04-11 ECHO（灾害页摘要注明 Myanmar 数字来自 AHA Centre）：3,603 人死亡、141 人失踪、4,817 人受伤；近 20 万人流离失所，其中 40,896 人在 127 个临时安置点；另列泰国 30 人死亡、38 人受伤。
- 2025-04-25 UNOSAT 摘要援引 UN OCHA Situation Report No. 4：约 3,800 人确认死亡、逾 5,100 人受伤、至少 116 人失踪；逾 110 万人需要人道援助、近 60 万人已获援助。
- 2025 年 4 月 HNRP Flash Addendum：受影响地区人口、最严重地区人口和援助需求是规划口径，已与伤亡和流离失所数字分开。

这些数字只能写成“某来源在某日的报告/估计”，不能被当作同一时点的最终总数。

## 验收结果

- 主震身份、UTC/本地时间、WGS84 坐标、Mww、深度与 review status：已明确。
- UTC 到 Asia/Yangon 转换：已核对。
- M6.4 / M6.7 冲突：已显式保留。
- 人道数字：按来源和报告日期分开。
- 搜索快照、派生参考与 live source 的权威层级：已区分。
- 夜间灯光与因果判断：未执行。

## 给 NTL Engineer 的正式 handoff

可直接交给 NTL Data Searcher / NTL Analyst 的事件锚点为：USGS `us7000pn9s`，Mww 7.7，10.0 km，`2025-03-28T06:20:52Z` / `2025-03-28T12:50:52+06:30`（Asia/Yangon），WGS84 `(95.936, 22.011)`。推荐安全措辞：

> We anchor the temporal analysis to the USGS-reviewed Mww 7.7 mainshock near Mandalay and Sagaing at 06:20:52 UTC (12:50:52 Asia/Yangon) on 28 March 2025. ReliefWeb materials also report a strong subsequent earthquake within minutes, but disagree on whether its magnitude was 6.4 or 6.7; this discrepancy is preserved as a source limitation. Any nighttime-light change is treated as observational evidence and does not by itself prove outage, damage, recovery, or earthquake causation.

正式结构化产物：`formal-event-context.json`。
