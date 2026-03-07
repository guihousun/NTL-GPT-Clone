# NTL-GPT 冲突夜光分析工具链说明

本文档单独说明当前仓库中与“冲突事件夜间灯光分析”直接相关的工具、脚本、目录组织与推荐使用方式。它是总架构文档的专题版，重点面向以下场景：

- 冲突/空袭/受袭击点叠加夜光分析
- 港口/海峡/城市战损区的日尺度夜光变化分析
- 官方夜光数据的检索、下载、预处理、制图与专题汇报
- 夜光与 AIS 等辅助数据的融合分析

## 1. 适用范围

当前这套工具链主要围绕两类官方夜光数据组织：

1. `VJ102DNB` + `VJ103DNB`
   适合做精确重采样、辐射值保留、冲突场景日尺度合成分析。
2. `VJ146A1`
   适合做更直接的格网产品裁剪、区域对比和专题制图。

当前已在仓库中实际用于：

- 伊朗 / 以色列冲突夜光分析
- 德黑兰 / 卡拉季受袭区分析
- 霍尔木兹海峡港口 / 冲突点 / 夜光叠加制图

## 2. 工具链总览

### 2.1 正式工具

| 层级 | 工具名 | 路径 | 作用 |
| --- | --- | --- | --- |
| 全链路 | `official_vj_dnb_fullchain_tool` | `tools/official_vj_dnb_pipeline_tool.py` | 统一完成查询、下载、预处理、可选 GIF 制图 |
| 预处理 | `official_vj_dnb_preprocess_tool` | `tools/official_vj_dnb_preprocess_tool.py` | 对下载后的 `VJ102DNB/VJ103DNB` 精确产品做预处理 |
| 转 tif | `convert_vj102_vj103_precise_to_tif_tool` | `tools/official_vj_dnb_preprocess_tool.py` | 将精确产品转成 GeoTIFF |
| 制图/GIF | `official_vj_dnb_gif_tool` | `tools/official_vj_dnb_gif_tool.py` | 夜光专题制图、冲突点叠加、港口点叠加、边界叠加、GIF 输出 |
| 制图底层脚本 | 无独立 tool 名 | `tools/official_vj_dnb_map_renderer.py` | `official_vj_dnb_gif_tool` 底层正式渲染脚本 |
| AIS 融合 | `official_ntl_ais_fusion_tool` | `tools/official_ntl_ais_fusion_tool.py` | 夜光-AIS 融合分析 |

### 2.2 辅助脚本

| 类型 | 路径 | 作用 |
| --- | --- | --- |
| LAADS 查询 | `tools/query_vj_dnb_laads_json.py` | 查询指定时间和 bbox 的 `VJ102DNB/VJ103DNB` 下载清单 |
| LAADS 下载 | `tools/download_vj_dnb.py` | 根据查询 JSON 下载数据 |
| 事件点抓取 | `tools/fetch_inss_arcgis_strikes.py` | 抓取 INSS ArcGIS 受袭击点并做空间 enrich |
| 空间辅助 | `tools/spatial_join_utils.py` | 冲突点与行政区划/国家/类型等做空间连接 |
| 兼容入口 | `experiments/official_daily_ntl_fastpath/make_ntl_daily_gif.py` | 已降级为兼容转发器，实际转发到 `tools/official_vj_dnb_map_renderer.py` |

## 3. 推荐工作流

### 3.1 工作流 A：官方 VJ102/VJ103 精确产品冲突分析

适用：

- 需要尽量保留原始观测细节
- 需要自定义重采样和日合成策略
- 需要构建冲突夜光专题图

推荐步骤：

1. 用 `tools/query_vj_dnb_laads_json.py` 查询目标时间范围和 bbox
2. 用 `tools/download_vj_dnb.py` 下载原始 `VJ102DNB/VJ103DNB`
3. 用 `official_vj_dnb_preprocess_tool` 或 `convert_vj102_vj103_precise_to_tif_tool` 转成 GeoTIFF
4. 用 `official_vj_dnb_gif_tool` 做制图、叠加冲突点/港口点/边界并导出 GIF
5. 如需船只活动分析，再接 `official_ntl_ais_fusion_tool`

### 3.2 工作流 B：VJ146A1 区域冲突/港口专题图

适用：

- 已有区域裁剪后的 `VJ146A1` tif
- 更关注快速对比、制图和讲故事式展示

推荐步骤：

1. 准备 `VJ146A1` 裁剪后 tif 序列
2. 准备事件点、港口点、边界图层
3. 用 `official_vj_dnb_gif_tool` 输出专题图和 GIF

这一条链在霍尔木兹海峡、德黑兰、卡拉季三个专题中已经实际跑通过。

## 4. 当前制图能力

`official_vj_dnb_gif_tool` 当前已经具备完整专题制图能力，不再只是简单动画导出器。

### 4.1 夜光渲染

- `cmap`：自定义设色方案
- `ntl_alpha`：夜光透明度
- `transparent_below`：低亮度像元透明
- `classification_mode`：`continuous` / `equal_interval` / `quantile` / `stddev`
- `class_bins`
- `stddev_range`
- `show_colorbar`

### 4.2 空间范围

- `view_bbox`：控制显示窗口
- `input_dir`：控制参与渲染的 tif 序列

### 4.3 底图

- `basemap_style`：`dark` / `light` / `none`
- `basemap_provider`：可指定在线瓦片 provider
- `basemap_alpha`

注意：

- 底图依赖 `contextily`
- 当前仓库已经修复了 `contextily` 在 Windows 临时目录权限下的缓存问题，默认改为仓库内安全缓存目录

### 4.4 点图层与边界图层

- `overlay_vector`
- `overlay_label_field`
- `overlay_point_class_field`
- `point_style_map`
- `point_size`
- `point_color`
- `point_edge`
- `boundary_vector`
- `boundary_edge_color`
- `boundary_linewidth`
- `boundary_alpha`

这意味着当前已支持：

- 冲突点
- 港口点
- 地震点
- 行政区边界
- 研究区边界

并支持“按类别不同符号渲染”，例如：

- 港口点：红色圆点
- 冲突点：黄色菱形

## 5. 事件数据与辅助数据

### 5.1 冲突事件点

当前主要使用：

- `tools/fetch_inss_arcgis_strikes.py`

数据归档位置示例：

- `base_data/Iran_War/data/event_feeds/inss_arcgis_strikes_latest/`

### 5.2 港口点

当前霍尔木兹海峡港口点归档在：

- `base_data/Iran_War/data/ports/hormuz/`

### 5.3 边界数据

当前边界数据归档在：

- `base_data/Iran_War/data/boundaries/`

包括：

- 伊朗多级行政边界
- 以色列边界缓存

## 6. 当前目录组织

以 `Iran_War` 为例，现已整理成如下结构：

```text
base_data/Iran_War/
  data/
    imagery/
      vj102dnb_vj103dnb/
      vj146a1/
    boundaries/
    event_feeds/
    ports/
    reference_maps/
  analysis/
    scripts/
      common/
      events/
        iran_israel_conflict_2026/
    results/
      events/
        iran_israel_conflict_2026/
    outputs/
      events/
        iran_israel_conflict_2026/
```

### 6.1 数据层

- `data/imagery/vj102dnb_vj103dnb/`
  放 `VJ102DNB/VJ103DNB` 处理后的影像数据
- `data/imagery/vj146a1/`
  放 `VJ146A1` 裁剪后影像与归档副本

### 6.2 脚本层

- `analysis/scripts/common/`
  放通用统计、通用整理、通用报告拼接脚本
- `analysis/scripts/events/iran_israel_conflict_2026/`
  放伊朗-以色列冲突专用分析脚本

### 6.3 结果层

- `analysis/results/events/iran_israel_conflict_2026/`
  放最终报告、图件、GIF、表格
- `analysis/outputs/events/iran_israel_conflict_2026/`
  放中间分析输出和专题渲染输出

## 7. 伊朗 / 霍尔木兹相关脚本

### 7.1 公共脚本

| 路径 | 作用 |
| --- | --- |
| `base_data/Iran_War/analysis/scripts/common/build_named_area_metrics.py` | 指定区域统计与差异图 |
| `base_data/Iran_War/analysis/scripts/common/build_vj_ntl_story_report.py` | 拼接专题故事报告 |
| `base_data/Iran_War/analysis/scripts/common/reorganize_iran_war_layout.py` | 重整 `Iran_War` 目录 |
| `base_data/Iran_War/analysis/scripts/common/sort_event_result_files.py` | 整理事件结果目录散落文件 |

### 7.2 事件专用脚本

| 路径 | 作用 |
| --- | --- |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/analyze_iran_ntl_0221_0227.py` | 0221-0227 阶段分析 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/analyze_iran_ntl_0227_0301.py` | 0227-0301 阶段分析 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/build_arcgis_replica_map.py` | 地图复刻 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/build_iran_ntl_combined_report.py` | 综合报告构建 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/check_arcgis_embed.py` | ArcGIS 嵌入检查 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/iran_event_report_config.py` | 报告配置 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/iran_event_report_pipeline.py` | 报告流水线 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/iran_event_report_shared.py` | 共享逻辑 |
| `base_data/Iran_War/analysis/scripts/events/iran_israel_conflict_2026/rebuild_iran_event_report.py` | 重建报告 |

## 8. 推荐入口

如果目标是“让 NTL-GPT 直接完成冲突夜光分析”，建议优先使用：

1. `official_vj_dnb_fullchain_tool`
2. `official_vj_dnb_preprocess_tool`
3. `official_vj_dnb_gif_tool`
4. `official_ntl_ais_fusion_tool`（需要 AIS 时）

如果目标是“复用伊朗 / 霍尔木兹现成专题”：

1. 数据从 `base_data/Iran_War/data/` 取
2. 脚本从 `base_data/Iran_War/analysis/scripts/` 取
3. 成果从 `base_data/Iran_War/analysis/results/events/iran_israel_conflict_2026/` 取

### 8.1 区域专题案例建议进入 Skill workflow

像“德黑兰局部窗口”和“霍尔木兹海峡港口窗口”这类区域专题，建议作为 workflow 案例沉淀，而不是继续把固定区域参数硬编码进通用 Tool。

推荐原则：

- `tools/` 负责正式通用能力
  - 数据查询与下载
  - `qa_mode`
  - 通用裁剪
  - 通用叠加制图
  - GIF 输出
- `Skill workflow` 负责专题编排
  - 区域 bbox 预设
  - 特定事件点/港口点/边界图层选择
  - 白底 `viridis` 等专题风格组合
  - 某个事件窗口的固定输出组织方式

当前已补入一个对应案例：

- `.ntl-gpt/skills/NTL-workflow-guidance/references/workflows/event_impact_assessment.json`
  - `Q22`
- `.ntl-gpt/skills/NTL-workflow-guidance/references/code/event_impact_assessment/Q22_iran_vj146a1_tehran_hormuz_workflow.py`

这个案例使用：

- `official_vj_dnb_fullchain_tool`
  负责 `VJ146A1` gridded 全链路和 `qa_mode`
- `official_vj_dnb_gif_tool`
  负责德黑兰和霍尔木兹两套专题图/GIF 输出

因此后续如果再出现：

- 新城市局部窗口
- 新港口专题
- 新事件专题风格

优先补 workflow case，而不是继续膨胀正式 Tool 参数表。

## 9. 当前结论

当前仓库已经具备一条完整的冲突夜光分析能力链：

- 官方数据查询
- 官方数据下载
- 精确预处理
- 裁剪与 GeoTIFF 化
- 冲突点 / 港口点 / 边界叠加制图
- GIF 输出
- 可选 AIS 融合
- 事件专题脚本与报告脚本分层组织

后续扩展时，建议保持以下原则：

- 数据统一进 `data/`
- 公共代码统一进 `analysis/scripts/common/`
- 事件代码统一进 `analysis/scripts/events/<event_name>/`
- 结果统一进 `analysis/results/events/<event_name>/`
- 中间输出统一进 `analysis/outputs/events/<event_name>/`
