# Q17 分析复核：SDGSAT-1 光类型分类

> **身份：Codex-subagent case-evidence simulation。** 本文件是对既有正式 Q17 证据包的独立复核，不是部署版 NTL-GPT/Deep Agents 的运行记录，也不属于 200 题 benchmark。

## 复核范围与输入

本复核只读既有正式产物，未修改原始栅格、旧分类结果、手稿、图件或 benchmark：

- experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-class-statistics.json
- experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-reference-comparison.json
- experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-analyst-log.md
- experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-SDGSAT1-shanghai-light-classification.tif

## 固定规则与正式统计

正式包记录的有序规则为：

1. 有效 RRLI/RBLI 且 RRLI > 9 → class 2 RLED；
2. 其余有效像元且 RBLI > 0.57 → class 1 WLED；
3. 其余有效像元 → class 3 Other；
4. 无效 index 像元 → NoData=255。

该顺序和阈值是固定的，正式包注明未进行阈值调优。既有统计为：

| 类别 | 像元数 | 有效 index 像元占比 | 正式包平面面积（km²） |
|---|---:|---:|---:|
| WLED | 4,211,496 | 43.0441% | 6,738.3936 |
| RLED | 244,523 | 2.4992% | 391.2368 |
| Other | 5,328,117 | 54.4567% | 8,524.9872 |
| 合计有效 | 9,784,136 | 100.0000% | 15,654.6176 |

总栅格像元为 52,484,500，NoData 为 42,700,364；三类之和与有效 index 像元数一致。面积是 EPSG:32651 中 40 m × 40 m 像元的平面栅格面积，不能直接称为实测照明 footprint。

## 独立读回与数值复核

我以只读方式对正式分类 GeoTIFF 做了分块扫描（rasterio block-window read），没有重跑原始指数或调整规则。读回结果为：

~~~text
shape = 9250 × 5674; nodata = 255
code 1 = 4,211,496; code 2 = 244,523; code 3 = 5,328,117; code 255 = 42,700,364
total = 52,484,500; valid(1,2,3) = 9,784,136
~~~

上述四类计数、有效总数和总像元数均与 formal-class-statistics.json 一致。由正式混淆矩阵独立重算：共同语义像元为 9,782,275，主对角线为 8,684,952，因此

~~~text
8,684,952 / 9,782,275 = 0.8878253780434511 = 88.7825378%
~~~

## 88.78% 的正确解释

正式 formal-reference-comparison.json 将 88.78% 定义为新分类与较早实现文件在共同语义掩膜上的总体一致率。较早文件是实现参考，不是独立真值；其 code 0/NoData 语义也被正式包排除。因而本复核采用：

**88.78% = implementation agreement（实现一致率），不是 accuracy（准确率）。**

没有现场验证的灯具类型标签、独立标注或地面真值，不能宣称总体准确率、分类精度、召回率代表真实地物正确性，也不能据此证明 Jia et al. 阈值的泛化能力。IoU/precision/recall 同样只能描述相对该实现参考文件的语义重合，不能改称 ground-truth accuracy。

## 可用结论

- 可以报告：在固定 RRLI > 9、RBLI > 0.57 的有序规则下，正式全幅栅格产生了上述三类计数和像元面积统计。
- 可以报告：当前新结果与较早实现参考在共同语义掩膜上的 88.78% implementation agreement，并说明共同掩膜和 code 0 排除规则。
- 可以将该包作为一次可审计的确定性分类流程证据，但措辞必须标明本轮为 Codex-subagent simulation；它不能证明部署版 NTL-GPT 或 Deep Agents 的性能。

## 不可用结论

- 不能把 88.78% 写成分类 accuracy、总体精度或 ground-truth accuracy。
- 不能把三类面积写成独立测量的照明范围、灯具类型真实面积或现场调查结果。
- 不能从该包推断阈值最优、跨区域/跨日期泛化、因果机制或经济/社会含义。
- 不能从本轮模拟推断部署版 runtime 已运行、四角色系统性能、Full-vs-Single 优势或 benchmark 结果。

## 结论状态

accepted_with_boundaries：固定规则、像元统计和实现一致率可用；accuracy 及独立真值相关结论不支持。

