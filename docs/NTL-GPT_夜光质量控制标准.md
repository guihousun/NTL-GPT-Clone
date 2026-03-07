# NTL-GPT 夜光质量控制标准

本文档说明当前仓库中 `VJ146A1` / `VJ146A2` 格网夜光产品的质量控制规则、模式分级、字段要求与使用建议。

当前实现位置主要在：

- `experiments/official_daily_ntl_fastpath/source_registry.py`
- `experiments/official_daily_ntl_fastpath/gridded_pipeline.py`

## 1. 适用范围

当前质量控制标准适用于：

- `VJ146A1`
- `VJ146A2`

其中：

- `VJ146A1` 当前使用的 QA 字段为 `QF_Cloud_Mask`、`QF_DNB`
- `VJ146A2` 当前使用的 QA 字段为 `Mandatory_Quality_Flag`、`QF_Cloud_Mask`、`Snow_Flag`

## 2. 总体原则

质量控制分为 4 档：

1. `none`
2. `balanced`
3. `strict`
4. `clear_only`

当前默认模式是：

- `balanced`

总体设计原则：

- `none` 仅做数值有效性过滤，不做 QA 掩膜
- `balanced` 适合日尺度事件分析，兼顾覆盖和稳定性
- `strict` 适合更保守的正式核验
- `clear_only` 适合“尽量去掉明显有云像元”的场景

## 3. 缺失字段处理

当前行为如下：

- `qa_mode = none` 时，不要求 QA 字段存在
- `qa_mode = balanced / strict / clear_only` 时，要求该产品的必需 QA 字段全部存在
- 若必需 QA 字段缺失，当前实现会直接报错，不再静默跳过

这意味着：

- 生产结果不能再在“缺 QA 波段”的情况下以 QA 模式继续输出
- QA 结果具备明确的字段完整性前提

## 4. 通用基础过滤

无论使用哪一档模式，都会先做基础有效性判断：

- 像元值必须是有限数值
- 像元值不能等于 `nodata`

只有通过基础过滤的像元，才会进入 QA 规则判断。

## 5. VJ146A1 标准

### 5.1 使用字段

- `DNB_At_Sensor_Radiance`
- `QF_Cloud_Mask`
- `QF_DNB`

### 5.2 `none`

规则：

- 只保留 `finite` 且不等于 `nodata` 的像元

说明：

- 不做云、阴影、卷云、雪冰、DNB 质量异常过滤
- 仅适合快速预览，不适合正式分析结论

### 5.3 `balanced`

规则：

- 必须是夜间像元
- `cloud_mask_quality >= 1`
- `cloud_confidence <= 1`
- 不允许 `shadow`
- 不允许 `cirrus`
- 不允许 `snow`
- `QF_DNB` 中若出现严重异常位，则掩膜

当前纳入严重异常过滤的 `QF_DNB` 位值为：

- `2`
- `4`
- `16`
- `256`
- `512`
- `1024`
- `2048`

说明：

- 这是当前默认模式
- 目标是去掉明显问题像元，但不把覆盖压得过低

### 5.4 `strict`

规则：

- 必须是夜间像元
- `cloud_mask_quality >= 2`
- `cloud_confidence == 0`
- 不允许 `shadow`
- 不允许 `cirrus`
- 不允许 `snow`
- `QF_DNB == 0`

说明：

- 比 `balanced` 更保守
- 要求云判断更可靠，且 DNB 质量位完全无异常

### 5.5 `clear_only`

规则：

- 必须是夜间像元
- `cloud_mask_quality == 3`
- `cloud_confidence == 0`
- 不允许 `shadow`
- 不允许 `cirrus`
- 不允许 `snow`
- `QF_DNB == 0`

说明：

- 这是当前最激进的云过滤模式
- 目标是尽量只保留“确认晴空”的像元
- 会显著减少有效像元覆盖

## 6. VJ146A2 标准

### 6.1 使用字段

- `Gap_Filled_DNB_BRDF-Corrected_NTL`
- `Mandatory_Quality_Flag`
- `QF_Cloud_Mask`
- `Snow_Flag`

### 6.2 `none`

规则：

- 只保留 `finite` 且不等于 `nodata` 的像元

### 6.3 `balanced`

规则：

- `Mandatory_Quality_Flag == 0`
- 必须是夜间像元
- `cloud_mask_quality >= 1`
- `cloud_confidence <= 1`
- 不允许 `shadow`
- 不允许 `cirrus`
- 不允许 `snow`
- `Snow_Flag == 0`

说明：

- 这是当前默认模式
- 兼顾高质量主检索与时序覆盖

### 6.4 `strict`

规则：

- 先满足全部 `balanced`
- 再额外要求：
  - `cloud_mask_quality >= 2`
  - `cloud_confidence == 0`

### 6.5 `clear_only`

规则：

- `Mandatory_Quality_Flag == 0`
- 必须是夜间像元
- `cloud_mask_quality == 3`
- `cloud_confidence == 0`
- 不允许 `shadow`
- 不允许 `cirrus`
- 不允许 `snow`
- `Snow_Flag == 0`

说明：

- 用于尽量排除明显云污染像元
- 会明显压缩有效像元数量

## 7. 关于 `QF_DNB == 0`

`QF_DNB == 0` 的含义是：

- DNB 质量标志中没有任何已编码问题位被置位

它表示：

- DNB 仪器/观测质量没有被标记出已知异常

它不直接等于：

- 无云

因此：

- 云相关过滤主要依赖 `QF_Cloud_Mask`
- `QF_DNB` 主要用于补充约束 DNB 本身的质量异常

## 8. 模式使用建议

推荐优先级如下：

1. 日尺度事件分析默认用 `balanced`
2. 结果核验、关键日期复查可用 `strict`
3. 若目标是尽量去掉明显云像元，可用 `clear_only`
4. `none` 只用于快速浏览或调试

如果任务目标是：

- 保持时间序列覆盖稳定：优先 `balanced`
- 保守分析、减少可疑像元：优先 `strict`
- 明确要压掉更多疑似云像元：优先 `clear_only`

## 9. 当前已确认事实

在当前仓库中的伊朗批次：

- `base_data/Iran_War/data/imagery/vj146a1/iran_israel_conflict_2026/vj146a1_0225_0304/`

对其原始 `VJ146A1` 文件检查结果为：

- 共 54 个 `.h5`
- `QF_Cloud_Mask` 在 54/54 文件中存在
- `QF_DNB` 在 54/54 文件中存在

因此，这一批 `VJ146A1` 可以合法使用 `balanced`、`strict`、`clear_only` 三档 QA 模式。

## 10. 后续扩展建议

如需进一步加强质量控制，可继续评估以下字段是否纳入规则：

- `QF_VIIRS_M10`
- `QF_VIIRS_M11`
- `QF_VIIRS_M12`
- `QF_VIIRS_M13`
- `QF_VIIRS_M15`
- `QF_VIIRS_M16`
- `Glint_Angle`
- `Solar_Zenith`
- `Lunar_Zenith`
- `Moon_Illumination_Fraction`

但这些规则应单独定义为新的模式，不建议直接修改当前 `balanced` / `strict` 的语义，以免破坏已有结果的可比性。
