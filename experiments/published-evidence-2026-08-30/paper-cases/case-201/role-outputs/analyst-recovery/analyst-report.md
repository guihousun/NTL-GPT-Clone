# Case 201 Analyst recovery

状态：已完成本地 CSV 描述性重算；未部署 runtime，未执行 benchmark。

## 输入与口径

- 输入：`formal-q18-analysis-ready.csv`、`formal-event-context.json`、`formal-observation-package.json`。
- 事件锚点：`2025-03-28` UTC product date；该行在源数据中标记为 `first_post_event_local_night_interpreted`，解释的 Yangon local-night date 为 `2025-03-29`。
- 基线：仅使用 observation JSON 声明的连续事件前日期；每日 AOI 均值必须为有限值且 `qa_valid_pixel_count > 0` 才计入。
- 25 km 与 50 km 支持范围分别计算，不合并、不加权池化；2026 年 later follow-up rows 未用于计算。

## 结果

| 支持范围 | 合格基线 n | 基线均值 (nW cm⁻² sr⁻¹) | 2025-03-28 均值 | 绝对变化 | 百分比变化 |
|---:|---:|---:|---:|---:|---:|
| 25 km | 6 | 1.482538771460 | 1.043512511975 | -0.439026259486 | -29.61% |
| 50 km | 7 | 0.833819996481 | 0.874851273979 | 0.041031277498 | +4.92% |

按公式 `100 × (event mean − baseline mean) / baseline mean`，验证值为：25 km **−29.61%**，50 km **+4.92%**。

## 解释边界

这些是两个独立支持范围内的描述性夜间灯光均值变化。结果不证明因果关系、损害、恢复或统计显著性；本次重算也不使用 later date。

验证详情见 `validation.json`，逐文件校验信息见 `artifact-manifest.json`。
