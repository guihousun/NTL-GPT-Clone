# Q18 VNP46A1 UTC_Time 独立复核（source-backed）

## 结论

独立复核通过：官方 HDF5 身份、字节数、SHA-256、HDF5 signature、UTC_Time 元数据、事件点时刻和 25/50 km 摘要均一致。由此可以安全支持：A2025087（2025-03-28 UTC-indexed）对应震后首个 Asia/Yangon 当地夜间（2025-03-29），但该结论仅是时相对应关系，不是因果、损毁、停电或恢复证据。

## 核验结果

- HDF5：`VNP46A1.A2025087.h27v06.002.2025088113623.h5`，50,906,798 bytes，SHA-256 `2e069d830228f76dff936ef6dddefd76bd5b21779fa03cb1cca4d0c59670e7ba`；manifest 与实际文件一致，HDF5 signature 为 `894844460d0a1a0a`。
- 当前 source manifest 文件本身：1,516 bytes，SHA-256 `e579e18a605bd005d31a6a5bb03efa441259146edf599111408a9654da4cb0d2`；其下载记录与实际 HDF5 的字节数、SHA-256 和 signature 一致。
- UTC_Time：`HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/UTC_Time`，`View Time (UTC)`，单位 `decimal hours`，范围 `[0, 24]`，scale/offset `1.0/0.0`。
- 事件时刻：`2025-03-28T06:20:52Z` → `2025-03-28T12:50:52+06:30`；独立 ZoneInfo 换算一致。
- 事件像元：UTC 小时 `19.945844650269`，UTC `2025-03-28T19:56:45.040741Z`，当地 `2025-03-29T02:26:45.040741+06:30`；位于主震之后且为 2025-03-29 当地日期。
- 25 km：n=9895，UTC_Time min/median/mean/max = `19.944793701172` / `19.945844650269` / `19.945848703987` / `19.946893692017`；全部 2025-03-29 当地日期。
- 50 km：n=39575，UTC_Time min/median/mean/max = `18.270952224731` / `19.945844650269` / `19.944281822055` / `19.947944641113`；全部 2025-03-29 当地日期。
- 工程验证：当前 engineer-validation 的全部检查为 true。
- 正式 Q18 VNP46A2 CSV SHA-256：`3c6777a41aa074a1357d25938120b026ab9cd7afa86bea3f419fbde64ce9d554`；ObservationPackage SHA-256：`7d9379dd8f066a37ac876a05ea346de797d2dfd40bc891a21592aa684255a804`；均与冻结值一致。
- 时间来源限制：未从 `system:time_start` 推断观测时间；本审计没有读取或计算 VNP46A2 辐亮度。

## 可安全采用与限界

可以安全写入：VNP46A1 的逐像元 `UTC_Time` 显示，2025-03-28 UTC 产品中的事件像元及 25/50 km 支持像元均在主震之后观测，并换算到 2025-03-29 的 Asia/Yangon 当地时间；因此 A2025087 可作为 Q18 的震后首个当地夜间时相证据。

不能由本审计写出：地震导致停电或损毁、恢复轨迹/恢复率、统计显著性或因果效应。VNP46A1 只提供时间核验，Q18 的辐亮度数值仍以未改动的 VNP46A2 正式资产为准。

“首个”应限定为当前 Q18 同瓦片时序和既定震前上下文中的首个震后合格当地夜间观测；本审计不声称对所有全球观测源进行了穷尽式覆盖检索。

机器可读明细见 [audit.json](audit.json)。
