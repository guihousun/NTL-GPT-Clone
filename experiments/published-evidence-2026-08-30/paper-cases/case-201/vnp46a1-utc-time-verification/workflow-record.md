# Codex 工作流记录

这是一个 Codex 脚本与子智能体的案例辅助核验，不是部署版 NTL-GPT / Deep Agents trace，也不产生 benchmark 指标。

| 责任 | 实际工作 | 产物 | 状态 |
|---|---|---|---|
| Engineer（本会话） | 固定输入合同；以 CMR 定位官方粒度；以已认证 Python bearer 下载并校验 HDF5 身份；只读取 `UTC_Time`，计算事件像元与 25/50 km 时间摘要 | `source/`、`scripts/`、`results/` | 完成 |
| Independent validation（Codex 子智能体） | 对事件时区、HDF5 身份、`UTC_Time` 元数据/摘要、正式 Q18 VNP46A2 immutability 和“不得用 system timestamp 替代 UTC_Time”作交叉复核 | `validation/independent-audit/` | 完成；source-backed audit 通过 |
| Engineer closeout | 重新读取 source/result/validation，验证记录完整性并限定论文可写范围 | `validation/engineer-validation.json`、`paper-facing-evidence.md` | 完成 |

子智能体没有代替官方数据读取，也没有生成伪造的 `UTC_Time` 数值。它的结论与主流程一致：需要可用的 Earthdata 下载授权后，才可运行 `scripts/analyze_utc_time.py` 产生事件像元与 25/50 km 的真实统计。
