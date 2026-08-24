# 给“NTL-GPT改稿 论文写作”任务的案例证据交接

## 本交接的性质

本轮是 **Codex-subagent case-evidence simulation**，不是部署版 NTL-GPT/Deep Agents trace，也不能覆盖或替代 200 题 benchmark 与 Full-vs-Single 结果。请在写作中将其作为案例资产复核与工作流证据，而非性能证据。

## 可更新的 Q19 事实

- 时间基准和完整基线：UTC，2026-01-01—02-27（strict n=47, mean 67.231835 nW cm⁻² sr⁻¹）。
- 2026-02-28—04-07 strict：55.619916，**−17.271%**；2026-04-08—21 strict：61.358263，**−8.736%**。
- 图面截止 2026-07-31；4/22—7/31 只能叫 extended monitoring，不能叫统一停火或恢复期。
- City of Tehran 不可无条件称为 highest-ranked city。可写为：在精确坐标、保留攻击记录的受控子集内，它在 20 个候选 ADM2 中排名第一（142/248）；完整总体排名因坐标缺失而 indeterminate。最稳妥的正文写法是“the selected City of Tehran ADM2 AOI”。

## Q17 / Q18 必改点

- Q17：保留固定 RRLI/RBLI 分类、输出 GeoTIFF 与 88.78% implementation agreement；删除/改写本轮完成全套去条带/辐射定标的说法，不能称 accuracy。Event Tracker 对该非事件分类请求是条件性跳过。
- Q18：正式支持对必须改为 **25 km −29.61%（n=6）** 与 **50 km +4.92%（n=7）**，不是旧的 25/100 km 与 +20.56%。表述为尺度敏感的首夜描述性比较；不写恢复、因果、停电、损毁或显著性。

## 交接路径

- Q19: `engineer/paper-facing-evidence-q19.md`；`validation/engineer-q19-validation.json`
- 全部可用/不可用矩阵: `validation/paper-evidence-matrix.md`
- 角色审计: `role-outputs/review-event-tracker/`、`review-data-searcher/`、`review-analyst/`
- 总结: `engineer/engineer-final-report.md`

活动手稿和附件在本轮没有修改；写作任务自行决定具体正文、图注和附件更新。
