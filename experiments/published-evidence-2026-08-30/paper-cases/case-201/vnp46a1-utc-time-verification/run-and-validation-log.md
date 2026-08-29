# 运行与验证日志

| UTC 时间 | 操作 | 结果 |
|---|---|---|
| 2026-08-20T03:44:28Z | CMR 按事件附近 bbox 查询 `VNP46A1` | 返回 2 个粒度，包含指定 A2025087 h27v06 文件 |
| 2026-08-20T03:44:47Z | 现有 CMR/curl 官方下载路径 | 失败；Windows Schannel `SEC_E_NO_CREDENTIALS` |
| 2026-08-20T03:48:54Z | Python `requests` + 已配置 bearer token，仅读取响应头与首段 | HTTP 401、`application/json`、非 HDF5 签名 |
| 2026-08-20T03:48:54Z | 不带登录态的 OPeNDAP 元数据页探针 | HTTP 200，但页面标题为 `Earthdata Login`，未公开 `UTC_Time` 元数据 |
| 2026-08-20T03:59:42Z | 更新现有 Earthdata 认证后，以 Python `requests` bearer 路径下载同一目标 | HTTP 200；`binary/octet-stream`；HDF5 签名通过；50,906,798 bytes；SHA-256 `2e069d830228f76dff936ef6dddefd76bd5b21779fa03cb1cca4d0c59670e7ba` |
| 2026-08-20 | 只读取官方 HDF5 的 `UTC_Time` 层 | 震中像元 19.945845 UTC 小时，即 2025-03-28 19:56:45 UTC / 2025-03-29 02:26:45 `Asia/Yangon`；25 km 9,895 个、50 km 39,575 个有效时间像元均映射到当地 2025-03-29 |
| 2026-08-20 | 时间合同 pytest | 3 passed |
| 2026-08-20 | 工程验证 | 11/11 checks passed；确认既有 Q18 VNP46A2 CSV/ObservationPackage hashes 不变 |

运行时从 `runtime/.worktrees/hierarchical-multiagent-experiments` 的已有 Earthdata resolver 读取配置；令牌内容、cookie 和授权响应体均未落盘或输出。

本次下载和计算未打开 VNP46A2 辐亮度字段、未重算 25/50 km 辐亮度比较、未生成图件。下面命令保留为可重复运行入口：

```powershell
$py = 'local-runtime/deepagents-075-clean-conda/python.exe'
$root = 'vault/ntl-gpt/experiments/q18-vnp46a1-utc-time-verification-2026-08-20'
$repo = 'runtime/.worktrees/hierarchical-multiagent-experiments'
& $py "$root\scripts\retrieve_vnp46a1_source.py" --repo-root $repo --source-dir "$root\source"
& $py "$root\scripts\analyze_utc_time.py" --h5 "$root\source\VNP46A1.A2025087.h27v06.002.2025088113623.h5" --results-dir "$root\results"
& $py -m pytest -q "$root\tests\test_time_contract.py"
```
