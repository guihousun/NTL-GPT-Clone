# Q18 VNP46A1 UTC_Time 辅助时间核验

## 范围

本实验只读取 NASA VNP46A1 Collection 2 的 `UTC_Time` 层，核验 2025-03-28 UTC 产品日与缅甸地震后首个 `Asia/Yangon` 当地夜间之间的时间对应关系。

它不是 benchmark，不重新计算、替换或调参 Q18 的 VNP46A2 辐亮度结果。VNP46A2 仍是 Q18 的辐亮度产品；VNP46A1 仅用作带逐像元 UTC 时间字段的辅助时相证据。

## 固定输入

- 主震：USGS `us7000pn9s`，`2025-03-28T06:20:52Z`；地点 `95.936E, 22.011N`。
- 当地时区：`Asia/Yangon`（UTC+06:30）。
- 官方同日同瓦片目标：`VNP46A1.A2025087.h27v06.002.2025088113623.h5`，Collection 2，h27v06，UTC 产品日 2025-03-28。
- 官方数据入口：<httplocal-path/VNP46A1.A2025087.h27v06.002.2025088113623.h5.html>。
- 空间支持：25 km 和 50 km WGS84 大地测量圆，采用与 `paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/` 相同的中心点与缓冲定义。

## 结论边界

- 仅 `UTC_Time` 逐像元字段可用于本实验的观测时刻判定；禁止由 `system:time_start` 推断精确采集时刻。
- 不对无效或缺失 `UTC_Time` 插补。
- 若精确产品日不符合既定合格条件，报告该首夜无合格观测；不得以后一日期替代后仍称“首夜”。
- 任何结果不构成损毁、停电、恢复或因果效应的证据。
- 该包为 Codex 脚本与独立复核生成的案例辅助证据，不是部署版 NTL-GPT trace 或性能评测。

## 预期产物

- `source/`：官方源、文件身份与认证/下载状态；
- `scripts/`：可复算脚本；
- `results/`：逐像元摘要、CSV 与 JSON；
- `validation/`：独立复核；
- `paper-facing-evidence.md`：可写与不可写的论文表述。

## 当前状态（2026-08-20）

已完成。CMR 定位的目标 HDF5 通过现有 Earthdata bearer token 以 Python `requests` 下载，并验证为 HDF5 文件：50,906,798 bytes，SHA-256 为 `2e069d830228f76dff936ef6dddefd76bd5b21779fa03cb1cca4d0c59670e7ba`。此前 Windows curl 的 Schannel 传输失败已记录为环境诊断，不影响此后的已认证 Python 下载。

实际读取的官方 `UTC_Time` 字段位于 `HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/UTC_Time`，其元数据为 `View Time (UTC)`、`decimal hours`、有效范围 0–24。震中所在像元为 19.945845 UTC 小时，即 2025-03-28 19:56:45 UTC / 2025-03-29 02:26:45 `Asia/Yangon`；25 km（9,895 个有效时间像元）和 50 km（39,575 个）支持中的全部有效时间像元也都对应当地 2025-03-29。故 A2025087 的 UTC 产品日可以以逐像元时间字段支持为震后首个当地夜间，而非将产品日机械加一天。

这不变更或重算既有 Q18 VNP46A2 辐亮度结果。详见 `run-and-validation-log.md`、`results/utc-time-analysis.json`、`validation/` 和 `paper-facing-evidence.md`。
