# NTL-GPT 模型架构、工具与 Skill 说明

本文档说明当前仓库中 NTL-GPT 的运行架构、核心脚本、工具系统、Skill 系统与工作区协议。重点面向开发、维护与排障，不是面向最终用户的产品介绍。

## 1. 系统总览

当前 NTL-GPT 是一个基于 Streamlit + LangGraph/Deep Agents 的多代理夜间灯光遥感分析系统。运行时可以概括为 6 层：

1. `Streamlit.py`
   负责页面入口、语言切换、初始化和页面装配。
2. `app_ui.py`
   负责聊天界面、推理面板、地图视图、文件上传和结果预览。
3. `app_logic.py`
   负责一次用户 run 的创建、事件流消费、错误收敛、历史记录与运行状态恢复。
4. `app_agents.py` + `graph_factory.py`
   负责构建主代理图、子代理、模型实例、Deep Agents 文件后端和 Skill 来源。
5. `agents/*.py`
   负责各代理的 system prompt 与知识侧辅助逻辑。
6. `tools/*.py`
   负责数据检索、GEE 路由、代码执行、指标估算、官方流水线等具体能力。

从执行链路看，用户问题的主流程如下：

1. UI 在 `Streamlit.py` 中接收问题。
2. `app_logic.start_user_run(...)` 生成一次后台 run。
3. `app_agents.get_ntl_graph(...)` 调用 `graph_factory.build_ntl_graph(...)` 构建 `NTL_Engineer` 主代理。
4. 主代理按需要顺序委派给 `Knowledge_Base_Searcher`、`Data_Searcher`、`Code_Assistant`。
5. 子代理在各自工具集和 Skill 支持下完成规划、检索、代码执行与结果生成。
6. 结果通过 `app_logic.consume_active_run_events()` 回流到 UI，并写入线程工作区。

## 2. 模型与代理架构

### 2.1 主代理图

主代理图的构建入口是：

- `app_agents.py`
- `graph_factory.py`

其中：

- `app_agents.py` 中的 `get_ntl_graph(...)` 是 Streamlit 层对代理图工厂的稳定封装。
- `graph_factory.py` 中的 `build_ntl_graph(...)` 是真正的组图入口。

### 2.2 模型分工

`graph_factory.py` 当前的模型分工如下：

- 主模型：由 `_build_llm(...)` 构建，供 `NTL_Engineer` 使用。
- `Data_Searcher`：默认继承主模型。
- `Code_Assistant`：默认继承主模型。
- `Knowledge_Base_Searcher`：单独使用 `qwen-plus`。

这意味着当前不是“四个代理四套模型”，而是“一个主模型 + 一个知识库子代理专用模型”的结构。

### 2.3 代理角色

| 代理名 | 角色 | Prompt 脚本 | 相对路径 |
| --- | --- | --- | --- |
| `NTL_Engineer` | 主控代理，负责任务理解、顺序委派、整合最终答案 | `NTL_Engineer.py` | `agents/NTL_Engineer.py` |
| `Data_Searcher` | 数据检索与元数据核验代理 | `NTL_Data_Searcher.py` | `agents/NTL_Data_Searcher.py` |
| `Code_Assistant` | 地理空间代码执行与脚本修复代理 | `NTL_Code_Assistant.py` | `agents/NTL_Code_Assistant.py` |
| `Knowledge_Base_Searcher` | 工作流/方法论/领域知识代理 | `NTL_Knowledge_Subagent.py` | `agents/NTL_Knowledge_Subagent.py` |

### 2.4 委派策略

`graph_factory.py` 中主代理 prompt 已明确写死了当前运行策略：

- 委派是顺序的，不是并行的。
- `Knowledge_Base_Searcher` 用于方法、流程与任务级规划。
- `Data_Searcher` 用于数据、AOI、时间范围、来源与元数据核验。
- `Code_Assistant` 用于代码生成、验证与执行。

## 3. 核心脚本索引

### 3.1 运行入口与 UI 层

| 脚本名 | 相对路径 | 作用 |
| --- | --- | --- |
| `Streamlit.py` | `Streamlit.py` | 应用入口，设置页面、初始化状态、调用 UI 与逻辑层 |
| `app_ui.py` | `app_ui.py` | 页面结构、聊天、地图、推理面板、上传与预览 |
| `app_logic.py` | `app_logic.py` | run 生命周期、流式事件、错误兜底、历史写入 |
| `app_agents.py` | `app_agents.py` | Streamlit 到 LangGraph 的代理图包装层 |
| `app_state.py` | `app_state.py` | 全局配置和会话状态常量 |

### 3.2 图构建与工作区层

| 脚本名 | 相对路径 | 作用 |
| --- | --- | --- |
| `graph_factory.py` | `graph_factory.py` | 组装主代理、子代理、模型、Skill 来源、Deep Agents backend |
| `storage_manager.py` | `storage_manager.py` | 线程工作区管理、虚拟路径映射、输入输出解析 |
| `.ntl-gpt/NTL_AGENT_MEMORY.md` | `.ntl-gpt/NTL_AGENT_MEMORY.md` | 每个线程首次运行时复制到 `memory/` 的初始代理记忆 |

### 3.3 代理与知识库相关脚本

| 脚本名 | 相对路径 | 作用 |
| --- | --- | --- |
| `NTL_Engineer.py` | `agents/NTL_Engineer.py` | 主控代理 prompt |
| `NTL_Data_Searcher.py` | `agents/NTL_Data_Searcher.py` | 数据检索代理 prompt |
| `NTL_Code_Assistant.py` | `agents/NTL_Code_Assistant.py` | 代码执行代理 prompt |
| `NTL_Knowledge_Subagent.py` | `agents/NTL_Knowledge_Subagent.py` | 知识库子代理 prompt |
| `NTL_Knowledge_Base_manager.py` | `agents/NTL_Knowledge_Base_manager.py` | 知识库管理逻辑 |
| `NTL_Knowledge_Base_manager_FAISS.py` | `agents/NTL_Knowledge_Base_manager_FAISS.py` | FAISS 版知识库管理逻辑 |
| `ntl_paper_ingestor.py` | `agents/ntl_paper_ingestor.py` | 文献导入 |
| `ntl_paper_preprocessor.py` | `agents/ntl_paper_preprocessor.py` | 文献预处理 |
| `ntl_paper_retriever.py` | `agents/ntl_paper_retriever.py` | 文献检索 |

### 3.4 工具系统相关脚本

| 脚本名 | 相对路径 | 作用 |
| --- | --- | --- |
| `__init__.py` | `tools/__init__.py` | 工具导出表、工具组、懒加载与 JSON-safe 包装入口 |
| `NTL_Code_generation.py` | `tools/NTL_Code_generation.py` | 代码保存、读取、执行、验证核心工具 |
| `tool_json_safety.py` | `tools/tool_json_safety.py` | 工具结果递归 JSON 安全清洗 |

## 4. 工作区与文件协议

当前 NTL-GPT 采用线程级工作区。根管理器位于：

- `storage_manager.py`

每个线程工作区默认有三个子目录：

- `inputs/`
- `outputs/`
- `memory/`

### 4.1 虚拟路径映射

`graph_factory.py` 中配置了 Deep Agents 的虚拟路径：

| 虚拟路径 | 实际含义 |
| --- | --- |
| `/data/raw/<file>` | 当前线程 `inputs/<file>` |
| `/data/processed/<file>` | 当前线程 `outputs/<file>` |
| `/memories/<file>` | 当前线程 `memory/<file>` |
| `/shared/<file>` | 仓库级共享数据目录 `base_data/<file>` |
| `/skills/<skill_dir>` | 仓库内 Skill 根目录 `.ntl-gpt/skills/<skill_dir>` |

### 4.2 文件权限边界

当前最外层约束由 `storage_manager.py` 和 Deep Agents backend 共同保证：

- 不允许绝对路径直接写入。
- 不允许 `..` 目录穿越。
- `/shared/...` 是只读数据源。
- 工作区相对路径可以解析到 `inputs/`、`outputs/`、`memory/`。

这意味着代理在工作区内部已经比较自由，但仍然被限制在线程工作区和共享数据边界之内。

## 5. Tool 系统设计

### 5.1 注册方式

工具统一注册在：

- `tools/__init__.py`

该文件当前不是“启动时一次性 import 全部工具”，而是：

1. `_EXPORTS` 维护工具名到模块导出名的映射。
2. `_GROUPS` 维护不同代理使用的工具组。
3. `LazyToolCollection` 在真正访问工具组时才加载模块。
4. 所有工具都先经过 `wrap_tool_json_safe(...)` 包装后再交给代理图。

### 5.2 工具组

当前运行时主要有三个工具组：

| 工具组 | 供谁使用 | 说明 |
| --- | --- | --- |
| `data_searcher_tools` | `Data_Searcher` | 数据源发现、下载、边界、GEE 路由、官方流水线 |
| `Code_tools` | `Code_Assistant` | 代码知识、代码验证、脚本执行、地理数据快速检查 |
| `Engineer_tools` | `NTL_Engineer` | 主控层直接调用的通用分析/预处理/估算/官方工具 |

知识库子代理没有使用上述三组，而是单独直接挂载：

- `tools/NTL_Knowledge_Base_Searcher.py` 中的 `NTL_Knowledge_Base`

### 5.3 JSON 安全包装

工具结果的最外层安全清洗在：

- `tools/tool_json_safety.py`

其作用是避免 `NaN`、`Inf`、部分非 JSON 安全对象直接穿过工具边界，导致 run 在工具输出序列化时失败。

### 5.4 工具分类

为了便于维护，当前工具可以按能力域分为以下几类。这里的分类是“职责分类”，不是运行时工具组替代品；一个工具可能同时属于某个运行时工具组和某个能力分类。

| 分类 | 代表工具 | 主要脚本 |
| --- | --- | --- |
| 行政区划、地理编码与边界查询 | `geocode_tool`、`reverse_geocode_tool`、`get_administrative_division_tool`、`get_administrative_division_geoboundaries_tool` | `tools/GaoDe_tool.py`、`tools/global_admin_boundary_fetch.py` |
| 数据发现、下载与外部检索 | `NTL_download_tool`、`NDVI_download_tool`、`LandScan_download_tool`、`google_bigquery_search`、`Tavily_search` | `tools/GEE_download.py`、`tools/Other_image_download.py`、`tools/Google_Bigquery.py`、`tools/TavilySearch.py` |
| GEE 路由、蓝图与元数据 | `GEE_dataset_router_tool`、`GEE_script_blueprint_tool`、`GEE_catalog_discovery_tool`、`GEE_dataset_metadata_tool` | `tools/GEE_specialist_toolkit.py` |
| 代码生成、检查与执行 | `GeoCode_COT_Validation_tool`、`execute_geospatial_script_tool`、`GeoCode_Knowledge_Recipes_tool`、`geodata_inspector_tool` | `tools/NTL_Code_generation.py`、`tools/geocode_knowledge_tool.py`、`tools/geodata_inspector_tool.py` |
| 夜光预处理与校正 | `SDGSAT1_strip_removal_tool`、`SDGSAT1_radiometric_calibration_tool`、`VNP46A2_angular_correction_tool`、`dmsp_evi_preprocess_tool` | `tools/NTL_preprocess.py` |
| 城市结构与道路提取 | `urban_extraction_by_thresholding_tool`、`svm_urban_extraction_tool`、`electrified_detection_tool`、`detect_urban_centres_tool`、`otsu_road_extraction_tool` | `tools/NTL_urban_structure_extract.py`、`tools/main_road.py` |
| 指数、统计、趋势与异常分析 | `SDGSAT1_index_tool`、`vnci_index_tool`、`NTL_raster_statistics_tool`、`NTL_Trend_Analysis`、`detect_ntl_anomaly_tool` | `tools/SDGSAT1_INDEX.py`、`tools/NPP_viirs_index_tool.py`、`tools/NTL_raster_stats.py`、`tools/NTL_trend_detection_tool.py`、`tools/NTL_anomaly_detection_tool.py` |
| 指标估算与经济建模 | `NTL_estimate_indicator_provincial_tool`、`DEI_estimate_city_tool`、`China_Official_GDP_tool` | `tools/NTL_estimate_indicator.py`、`tools/China_official_stats.py` |
| 官方 VJ DNB 工作流 | `official_vj_dnb_fullchain_tool`、`official_vj_dnb_preprocess_tool`、`convert_vj102_vj103_precise_to_tif_tool`、`official_vj_dnb_gif_tool` | `tools/official_vj_dnb_pipeline_tool.py`、`tools/official_vj_dnb_preprocess_tool.py`、`tools/official_vj_dnb_gif_tool.py`、`tools/official_vj_dnb_map_renderer.py` |
| 融合分析与专题工具 | `official_ntl_ais_fusion_tool` | `tools/official_ntl_ais_fusion_tool.py` |
| 知识与文档理解 | `NTL_Knowledge_Base`、`uploaded_pdf_understanding_tool` | `tools/NTL_Knowledge_Base_Searcher.py`、`tools/uploaded_file_understanding_tool.py` |

## 6. Tool 清单

下表基于 `tools/__init__.py` 当前 `_EXPORTS` 与 `_GROUPS` 整理。`groups` 表示该工具目前被哪些代理工具组使用。

| Tool 名 | 来源脚本 | 相对路径 | groups | 说明 |
| --- | --- | --- | --- | --- |
| `NTL_composite_local_tool` | `NTL_Composite.py` | `tools/NTL_Composite.py` | `Engineer_tools` | 本地合成类工具 |
| `SDGSAT1_strip_removal_tool` | `NTL_preprocess.py` | `tools/NTL_preprocess.py` | `Engineer_tools` | SDGSAT-1 条带去除 |
| `SDGSAT1_radiometric_calibration_tool` | `NTL_preprocess.py` | `tools/NTL_preprocess.py` | `Engineer_tools` | SDGSAT-1 辐射定标 |
| `VNP46A2_angular_correction_tool` | `NTL_preprocess.py` | `tools/NTL_preprocess.py` | `Engineer_tools` | VNP46A2 角度校正 |
| `dmsp_evi_preprocess_tool` | `NTL_preprocess.py` | `tools/NTL_preprocess.py` | `Engineer_tools` | DMSP/EVI 预处理 |
| `SDGSAT1_index_tool` | `SDGSAT1_INDEX.py` | `tools/SDGSAT1_INDEX.py` | `Engineer_tools` | SDGSAT-1 指数计算 |
| `vnci_index_tool` | `NPP_viirs_index_tool.py` | `tools/NPP_viirs_index_tool.py` | `Engineer_tools` | VIIRS/NPP 指数计算 |
| `urban_extraction_by_thresholding_tool` | `NTL_urban_structure_extract.py` | `tools/NTL_urban_structure_extract.py` | `Engineer_tools` | 阈值法城市提取 |
| `svm_urban_extraction_tool` | `NTL_urban_structure_extract.py` | `tools/NTL_urban_structure_extract.py` | `Engineer_tools` | SVM 城市提取 |
| `electrified_detection_tool` | `NTL_urban_structure_extract.py` | `tools/NTL_urban_structure_extract.py` | `Engineer_tools` | 通电区域检测 |
| `detect_urban_centres_tool` | `NTL_urban_structure_extract.py` | `tools/NTL_urban_structure_extract.py` | `Engineer_tools` | 城市中心探测 |
| `NTL_raster_statistics_tool` | `NTL_raster_stats.py` | `tools/NTL_raster_stats.py` | `Engineer_tools` | 栅格统计 |
| `NTL_Daily_ANTL_Statistics` | `NTL_raster_stats_GEE.py` | `tools/NTL_raster_stats_GEE.py` | 无直接工具组 | GEE 日尺度统计 |
| `NTL_Trend_Analysis` | `NTL_trend_detection_tool.py` | `tools/NTL_trend_detection_tool.py` | `Engineer_tools` | 趋势分析 |
| `otsu_road_extraction_tool` | `main_road.py` | `tools/main_road.py` | `Engineer_tools` | Otsu 道路提取 |
| `detect_ntl_anomaly_tool` | `NTL_anomaly_detection_tool.py` | `tools/NTL_anomaly_detection_tool.py` | `Engineer_tools` | 夜光异常检测 |
| `NTL_Knowledge_Base` | `NTL_Knowledge_Base_Searcher.py` | `tools/NTL_Knowledge_Base_Searcher.py` | 无直接工具组 | 知识库检索，供知识子代理直接挂载 |
| `get_administrative_division_tool` | `GaoDe_tool.py` | `tools/GaoDe_tool.py` | `data_searcher_tools` | 行政区查询 |
| `poi_search_tool` | `GaoDe_tool.py` | `tools/GaoDe_tool.py` | `data_searcher_tools` | POI 检索 |
| `reverse_geocode_tool` | `GaoDe_tool.py` | `tools/GaoDe_tool.py` | `data_searcher_tools` | 逆地理编码 |
| `geocode_tool` | `GaoDe_tool.py` | `tools/GaoDe_tool.py` | `data_searcher_tools` | 地理编码 |
| `get_administrative_division_osm_tool` | `GaoDe_tool.py` | `tools/GaoDe_tool.py` | 无直接工具组 | OSM 行政边界查询 |
| `NTL_download_tool` | `GEE_download.py` | `tools/GEE_download.py` | `data_searcher_tools` | 夜光数据下载 |
| `get_administrative_division_geoboundaries_tool` | `global_admin_boundary_fetch.py` | `tools/global_admin_boundary_fetch.py` | `data_searcher_tools` | GeoBoundaries 行政边界查询 |
| `NDVI_download_tool` | `Other_image_download.py` | `tools/Other_image_download.py` | `data_searcher_tools` | NDVI 下载 |
| `LandScan_download_tool` | `Other_image_download.py` | `tools/Other_image_download.py` | `data_searcher_tools` | LandScan 下载 |
| `google_bigquery_search` | `Google_Bigquery.py` | `tools/Google_Bigquery.py` | `data_searcher_tools` | BigQuery 检索 |
| `Tavily_search` | `TavilySearch.py` | `tools/TavilySearch.py` | `data_searcher_tools` | 通用联网搜索 |
| `China_Official_GDP_tool` | `China_official_stats.py` | `tools/China_official_stats.py` | `data_searcher_tools` | 中国官方 GDP 数据 |
| `geodata_inspector_tool` | `geodata_inspector_tool.py` | `tools/geodata_inspector_tool.py` | `Code_tools` | 地理数据检查 |
| `geodata_quick_check_tool` | `geodata_inspector_tool.py` | `tools/geodata_inspector_tool.py` | 无直接工具组 | 地理数据快速检查 |
| `GeoCode_COT_Validation_tool` | `NTL_Code_generation.py` | `tools/NTL_Code_generation.py` | `Code_tools` | 代码链路验证 |
| `execute_geospatial_script_tool` | `NTL_Code_generation.py` | `tools/NTL_Code_generation.py` | `Code_tools` | 地理空间脚本执行 |
| `GeoCode_Knowledge_Recipes_tool` | `geocode_knowledge_tool.py` | `tools/geocode_knowledge_tool.py` | `Code_tools` | 代码知识配方 |
| `GEE_dataset_router_tool` | `GEE_specialist_toolkit.py` | `tools/GEE_specialist_toolkit.py` | `data_searcher_tools` | GEE 数据集路由 |
| `GEE_script_blueprint_tool` | `GEE_specialist_toolkit.py` | `tools/GEE_specialist_toolkit.py` | `data_searcher_tools` | GEE 脚本蓝图 |
| `GEE_catalog_discovery_tool` | `GEE_specialist_toolkit.py` | `tools/GEE_specialist_toolkit.py` | `data_searcher_tools` | GEE 目录发现 |
| `GEE_dataset_metadata_tool` | `GEE_specialist_toolkit.py` | `tools/GEE_specialist_toolkit.py` | `data_searcher_tools` | GEE 元数据查询 |
| `NTL_estimate_indicator_provincial_tool` | `NTL_estimate_indicator.py` | `tools/NTL_estimate_indicator.py` | `Engineer_tools` | 省级指标估算 |
| `DEI_estimate_city_tool` | `NTL_estimate_indicator.py` | `tools/NTL_estimate_indicator.py` | `Engineer_tools` | 城市 DEI 估算 |
| `official_vj_dnb_fullchain_tool` | `official_vj_dnb_pipeline_tool.py` | `tools/official_vj_dnb_pipeline_tool.py` | `data_searcher_tools`, `Engineer_tools` | 官方 VJ DNB 全链路流水线 |
| `official_vj_dnb_preprocess_tool` | `official_vj_dnb_preprocess_tool.py` | `tools/official_vj_dnb_preprocess_tool.py` | `data_searcher_tools`, `Engineer_tools` | 官方 VJ DNB 预处理 |
| `convert_vj102_vj103_precise_to_tif_tool` | `official_vj_dnb_preprocess_tool.py` | `tools/official_vj_dnb_preprocess_tool.py` | `data_searcher_tools`, `Engineer_tools` | VJ102/VJ103 精确产品转 TIF |
| `official_vj_dnb_gif_tool` | `official_vj_dnb_gif_tool.py` | `tools/official_vj_dnb_gif_tool.py` | `data_searcher_tools`, `Engineer_tools` | 官方 VJ DNB 完整制图与 GIF 生成；底层正式渲染脚本为 `tools/official_vj_dnb_map_renderer.py` |
| `official_ntl_ais_fusion_tool` | `official_ntl_ais_fusion_tool.py` | `tools/official_ntl_ais_fusion_tool.py` | `data_searcher_tools`, `Engineer_tools` | 官方夜光-AIS 融合分析 |
| `uploaded_pdf_understanding_tool` | `uploaded_file_understanding_tool.py` | `tools/uploaded_file_understanding_tool.py` | `Engineer_tools` | 上传 PDF 理解 |

说明：

- `wrap_tool_json_safe` 位于 `tools/tool_json_safety.py`，是内部包装器，不是面向代理规划的业务工具，因此未放入上表主清单。
- `NTL_Daily_ANTL_Statistics`、`get_administrative_division_osm_tool`、`geodata_quick_check_tool`、`NTL_Knowledge_Base` 当前虽然在 `_EXPORTS` 中，但不在三大主工具组里，属于可导出但未直接纳入当前主代理工具组的能力。
- `experiments/official_daily_ntl_fastpath/make_ntl_daily_gif.py` 现已降级为兼容转发器，实际正式实现位于 `tools/official_vj_dnb_map_renderer.py`。

### 6.1 `official_vj_dnb_gif_tool` 当前完整制图能力

当前 `official_vj_dnb_gif_tool` 已不再只是“简单 GIF 导出器”，而是官方 VJ DNB 制图入口。其底层调用：

- `tools/official_vj_dnb_map_renderer.py`

当前支持的核心能力包括：

- 日尺度 GeoTIFF 序列渲染为 GIF
- 夜光设色控制：`cmap`
- 夜光透明度控制：`ntl_alpha`
- 低亮度像元透明：`transparent_below`
- 分类渲染：`continuous`、`equal_interval`、`quantile`、`stddev`
- 分类参数：`class_bins`、`stddev_range`
- 视图范围裁剪：`view_bbox`
- 底图开关与样式：`basemap_style`
- 指定在线瓦片 provider：`basemap_provider`
- 底图透明度：`basemap_alpha`
- 点图层叠加：`overlay_vector`
- 点标签字段：`overlay_label_field`
- 点分类字段：`overlay_point_class_field`
- 点样式映射：`point_style_map`
- 单样式点控制：`point_size`、`point_color`、`point_edge`
- 边界叠加：`boundary_vector`、`boundary_edge_color`、`boundary_linewidth`、`boundary_alpha`
- 色标开关：`show_colorbar`

典型制图场景包括：

- 夜光变化动画
- 冲突点 / 港口点 / 地震点叠加
- 行政区边界或研究区边界叠加
- 深色或浅色在线底图专题图
- 霍尔木兹海峡、城市战损区、港口活动区等局部窗口专题图

## 7. Skill 系统设计

### 7.1 运行时 Skill 根目录

运行时 Skill 根目录由 `graph_factory.py` 定义为：

- `.ntl-gpt/skills/`

并通过 Deep Agents 虚拟路径暴露为：

- `/skills/`

主代理和三个子代理当前都挂载了同一个 Skill 来源：

- `/skills/`

### 7.2 当前仓库内运行时 Skill 清单

| Skill 名 | 目录 | `SKILL.md` 相对路径 | 作用概述 |
| --- | --- | --- | --- |
| `code-generation-execution-loop` | `code-generation-execution-loop` | `.ntl-gpt/skills/code-generation-execution-loop/SKILL.md` | 规范代码生成、保存、读取、执行、验证和一次修复的闭环 |
| `gee-ntl-date-boundary-handling` | `gee-ntl-date-boundary-handling` | `.ntl-gpt/skills/gee-ntl-date-boundary-handling/SKILL.md` | 处理 GEE 夜光日期窗口、首夜选择、AOI 边界与鲁棒 reduce 设置 |
| `gee-routing-blueprint-strategy` | `gee-routing-blueprint-strategy` | `.ntl-gpt/skills/gee-routing-blueprint-strategy/SKILL.md` | 统一 GEE 检索路径、边界策略、task level 协议、元数据和完成检查 |
| `ntl-gdp-regression-analysis` | `ntl-gdp-regression-analysis` | `.ntl-gpt/skills/ntl-gdp-regression-analysis/SKILL.md` | 规范 ANTL-GDP 建模、模型比较、诊断与指标估算输出 |
| `NTL-workflow-guidance` | `NTL-workflow-guidance` | `.ntl-gpt/skills/NTL-workflow-guidance/SKILL.md` | 从本地 JSON 工作流模板中快速检索任务方案，优先于知识库自由检索 |
| `workflow-self-evolution` | `workflow-self-evolution` | `.ntl-gpt/skills/workflow-self-evolution/SKILL.md` | 为其他 NTL Skill 提供失败归因、学习决策、版本回退和自演化元能力 |

### 7.3 Skill 在架构中的作用

当前 Skill 不是替代工具，而是补充代理的“执行策略”和“领域流程约束”：

- Tool 决定“能做什么”。
- Skill 决定“在什么情况下优先怎么做”。

例如：

- `NTL-workflow-guidance` 更偏任务级工作流模板检索。
- `gee-routing-blueprint-strategy` 更偏数据检索路径与 GEE 决策策略。
- `code-generation-execution-loop` 更偏 Code Assistant 的执行闭环约束。

## 8. 当前架构的几个关键特征

### 8.1 懒加载工具

`tools/__init__.py` 当前使用懒加载。好处是：

- 降低启动时的重型导入成本。
- 减少一次性导入所有科学计算依赖导致的环境崩溃风险。
- 只在代理真正访问某组工具时才加载目标模块。

### 8.2 工具输出最外层 JSON 清洗

当前工具结果在外层统一经过 `tools/tool_json_safety.py`，用于降低如下失败风险：

- `NaN`
- `Inf`
- 非 JSON 安全结构

这层保护的是“工具返回值”，不是“坏 schema 默认值”本身。因此工具定义阶段仍然应避免把 `NaN` 写进参数默认值。

### 8.3 工作区内相对路径能力

`storage_manager.py` 与 `tools/NTL_Code_generation.py` 当前已经支持工作区内相对路径，而不再只允许文件 basename。这使代理可以在工作区内部组织更复杂的目录结构，例如：

- `outputs/reports/summary.md`
- `outputs/jobs/run_a/script.py`
- `memory/notes/step_1.md`

同时仍保留最外层边界，不允许路径穿越和 `/shared` 写入。

## 9. 维护建议

如果后续还要继续演进当前架构，建议遵守以下顺序：

1. 先看 `graph_factory.py`
   这里决定了模型、代理、Skill 来源和文件后端，是运行骨架。
2. 再看 `tools/__init__.py`
   这里决定了每个代理真实能访问哪些工具。
3. 然后看 `storage_manager.py`
   这里决定了代理能以什么路径模型访问文件。
4. 最后看各代理 prompt 和具体工具脚本
   这里才是业务能力与行为细节。

## 10. 结论

当前 NTL-GPT 的核心结构可以概括为：

- UI 层：`Streamlit.py` + `app_ui.py`
- 运行控制层：`app_logic.py`
- 图构建层：`app_agents.py` + `graph_factory.py`
- 代理层：`NTL_Engineer` + 3 个子代理
- 工具层：`tools/__init__.py` 管理的懒加载工具集合
- Skill 层：`.ntl-gpt/skills/` 下的运行时策略模板
- 存储层：`storage_manager.py` 管理的线程工作区与虚拟路径

如果你要继续扩展能力，最值得优先维护的三个中心文件是：

- `graph_factory.py`
- `tools/__init__.py`
- `storage_manager.py`

因为这三个文件分别控制了“怎么组图”“能调用什么”“能访问哪里”。
