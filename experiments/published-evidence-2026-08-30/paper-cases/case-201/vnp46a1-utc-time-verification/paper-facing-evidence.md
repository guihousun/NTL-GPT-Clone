# Q18 VNP46A1 UTC_Time 辅助核验：论文边界

## 已实际验证的时间链

主震发生于 `2025-03-28T06:20:52Z`，在 `Asia/Yangon` 为 `2025-03-28T12:50:52+06:30`。从官方 Earthdata 下载并校验的同日同瓦片 VNP46A1 Collection 2 HDF5 文件为 `VNP46A1.A2025087.h27v06.002.2025088113623.h5`（50,906,798 bytes；SHA-256 `2e069d830228f76dff936ef6dddefd76bd5b21779fa03cb1cca4d0c59670e7ba`）。

该文件实际 `UTC_Time` 字段的元数据为 `View Time (UTC)`、`decimal hours`、有效范围 0–24。震中所在像元为 19.945845 UTC 小时，即 `2025-03-28T19:56:45.040741Z` 或 `2025-03-29T02:26:45.040741+06:30`。这晚于主震；25 km 支持中 9,895 个有效时间像元、50 km 支持中 39,575 个有效时间像元均映射到 `Asia/Yangon` 当地 2025-03-29。

因此，2025-03-28 UTC 索引的 A2025087 产品可由逐像元 `UTC_Time` 支持为地震后的首个当地夜间；这不是把 UTC 产品日机械加一天得到的结论。

## 可安全用于 Section 5.2 的表述

活动稿中“时间敏感夜间灯光分析需要正确的时间对齐，而不是仅选择事件后的第一个产品日期”以及主震 UTC/当地时刻的事实换算均可保留。

可将关于产品日的句子收束为：

> The 28 March UTC-indexed VNP46A2 product was interpreted as the first post-event local night using an auxiliary per-pixel VNP46A1 `UTC_Time` check, rather than by mechanically shifting the product date to local time.

若需给出一项可审查的具体证据，可补：

> At the pixel containing the epicentre, the auxiliary VNP46A1 `UTC_Time` field recorded 19.945845 UTC hours on 28 March, corresponding to 02:26:45 on 29 March in Asia/Yangon; all valid `UTC_Time` pixels in the 25 km and 50 km supports also mapped to 29 March local time.

## 仍不可写的内容

- 不得将 VNP46A1 用作 Q18 辐亮度、质量控制或变化计算产品；Q18 辐亮度结果仍来自已冻结的 VNP46A2 正式资产。
- 不得从时间对齐推出地震造成停电、损毁、恢复或任何因果效应。
- 不得把 CMR `time_start`、系统时间戳或产品日期本身写成逐像元观测时刻；精确时相依据仅为本实验实际读取的 `UTC_Time` 字段。
- 不得将此 Codex 脚本与独立复核的案例辅助证据表述为部署版 NTL-GPT trace、benchmark 结果或性能证据。
