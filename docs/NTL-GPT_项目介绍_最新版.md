# NTL-GPT 项目介绍（最新版）
**Nighttime Light Multi-Agent Geospatial Intelligence System**  
版本日期：2026-02-08（MD 同步更新：2026-02-17）

## 一、项目定位
NTL-GPT（数字星眸）是一个面向夜间灯光遥感（NTL）城市分析的多智能体系统，目标是把传统需要人工串联的数据检索、预处理、统计分析和结果导出流程，升级为一句话驱动的自动化工作流。  
系统聚焦城市治理与科研场景，支持从夜光影像获取、行政边界确认、指标计算到结果文件输出的端到端执行，并强调结果可追溯、流程可复现、执行可验证。

## 二、系统总体架构
当前系统基于 `LangChain + LangGraph` 构建，采用 Supervisor 架构：由 `NTL_Engineer` 统一规划与调度，`Data_Searcher` 和 `Code_Assistant` 两个子智能体分工协作。  
前端采用 Streamlit 实现交互与结果展示；后端通过结构化工具（`StructuredTool`）连接 Google Earth Engine（GEE）、`rasterio`、`geopandas`、`shapely` 等能力栈。

## 三、项目架构细化
### 3.1 分层架构
- UI 层：`Streamlit.py` / `app_ui.py`
- 编排层：`app_agents.py` / `graph_factory.py` / LangGraph Supervisor
- 智能体层：`NTL_Engineer`、`Data_Searcher`、`Code_Assistant`
- 工具层：`tools/*.py`（`StructuredTool`）
- 存储层：`storage_manager` + `user_data/<thread_id>/inputs|outputs`

### 3.2 控制流
用户请求进入 `NTL_Engineer` -> 先做知识与时空约束审查 -> 按需派发 `Data_Searcher` 获取数据或生成 GEE 执行方案 -> 派发 `Code_Assistant` 按 Geo-CodeCoT v2 验证与执行 -> 回收结果并输出。

### 3.3 数据流
所有输入统一来自当前线程 `inputs`（或 `base_data` 回退）；所有产物统一写入当前线程 `outputs`；智能体间通过结构化 JSON 交换计划、边界、元数据与执行状态。

### 3.4 角色边界协议
- `Data_Searcher` 不负责最终执行。
- `Code_Assistant` 不得改仓库源码，只能测试/执行并写 `outputs`。
- `NTL_Engineer` 负责最终决策与失败重试策略。

## 四、核心智能体职责（最新实现）
1. `NTL_Engineer`（主智能体）：需求拆解、工具路由、边界复核、执行监督与结论汇总。  
2. `Data_Searcher`（数据助手）：数据检索与数据计划生成，覆盖 GEE / OSM / Amap / Tavily / BigQuery 等来源。  
3. `Code_Assistant`（代码助手）：严格执行 Geo-CodeCoT v2，先分块验证再整段执行，输出 CSV/PNG/TIF 与脚本元信息。

## 五、GEE 工作流增强
系统强化了 GEE 专项工具链：`GEE_dataset_router_tool`、`GEE_script_blueprint_tool`、`GEE_catalog_discovery_tool`、`GEE_dataset_metadata_tool`。  
长时序高负载任务采用云端优先策略：当请求超过 31 景日尺度影像或属于重计算意图时，优先走 `gee_server_side`，避免本地批量下载导致性能与稳定性问题。

## 六、准确性与安全约束
1. 行政边界强约束：命名行政区不可替换为自定义 bbox；边界需带来源工具、CRS、bounds、validation_status。  
2. 执行边界清晰：`Code_Assistant` 只读源码、仅写分析输出（`outputs`）。  
3. 路径治理：统一通过 `storage_manager` 管理线程工作区，避免硬编码绝对路径。  
4. 流程闭环：边界非 confirmed 或代码验证失败时，必须回传 `NTL_Engineer` 重检/重规划。

## 七、数据与文件管理机制
项目通过 `storage_manager` 实现会话级隔离：每个 `thread_id` 对应独立 `user_data/<thread_id>/inputs` 与 `outputs`。  
输入支持用户上传与 Data_Searcher 检索双来源；输出统一落在当前线程 `outputs`，便于审计、回放与并发。

## 八、前端与部署
前端由 Streamlit 构建，支持问答式任务提交、推理过程展示、文件结果回显与地图/表格可视化。  
系统已部署在华为云 ECS（项目记录地址：`http://139.9.165.59:8501/`）。  
近期界面能力更新包括回答末尾自动附加耗时信息（Time cost）。

## 九、近期关键更新（2026-02）
1. 数据检索路由增强：轻量年度/月度范围优先直接下载，避免不必要转入 Code Assistant。  
2. 代码执行治理增强：支持脚本保存与按文件执行，增强可回放与可审计性。  
3. 错误升级策略增强：区分简单错误（限次自修）与复杂错误（上报 Engineer 决策）。  
4. 中国 GDP 官方源增强：新增 `China_Official_GDP_tool`，优先直连国家统计局官方结构化接口。  
5. 栅格统计效率增强：`NTL_raster_statistics` 新增多文件批处理（`ntl_tif_paths`）支持。

## 十、典型应用场景
1. 社会经济估算：GDP、人口、用电等指标时空分析。  
2. 城市空间识别：建成区、道路照明、城市扩张与结构演化。  
3. 灾害与事件评估：结合时序夜光与外部信息进行影响分析。  
4. 科研自动化：将复杂地理处理流程转为可复用、可验证、可追踪的执行链。

## 十一、并行 Codex 协作建议（加速开发）
建议采用“双 Codex + 明确边界”并行模式：
- Codex-A（主线）：智能体路由、提示词、协议与 UI 渲染稳定性。
- Codex-B（并行）：工具能力扩展、数据源补强、测试补齐与基准回归。

并行规则建议：
1. 两个会话尽量修改不同文件集合，避免冲突。  
2. 共同遵守“先测后合并”，每个分支交付时附带最小测试结果。  
3. 大改动前写简短实施清单，避免重复劳动。  
4. 合并前统一跑一轮核心回归：RAG、Data_Searcher、Code_Assistant、UI 渲染。

## 十二、官方 Daily NTL 快速实验流（独立工作区）
为解决 GEE 日尺度产品常见的 3-4 天延迟问题，项目新增了独立实验流：
`experiments/official_daily_ntl_fastpath`。该实验流不改动主链路与工具注册，仅做“官方源更快可用性”的并行验证。

### 12.1 实验边界
- 仅新增实验文件与测试，不修改 `agents/`、`tools/`、`app_*.py`、`RAG/guidence_json/*.json` 主流程文件。
- 入口为独立 CLI：`experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py`。
- 支持同次执行三源：`VJ146A2,VJ146A1,VJ102DNB`。
- `VJ102DNB` 本轮定位为 feasibility-only（可用性验证），不承诺直接产出区域日影像。

### 12.2 能力组成
- 源注册中心：`source_registry.py` 统一管理 `processing_mode`、`variable_candidates`、`night_only`。
- 边界解析：`boundary_resolver.py`（中国优先 AMap，失败回退 OSM）。
- 官方检索下载：`cmr_client.py`（`curl` 子进程访问 CMR，规避 conda 环境中 `requests` TLS EOF 问题）。
- A1/A2 栅格处理：`gridded_pipeline.py`（变量匹配、拼接、裁剪输出）。
- NOAA20 可行性：`noaa20_feasibility.py`（NIGHT granule 存在性与链路结论）。
- GEE 对照：`gee_baseline.py` 查询同区域 `NASA/VIIRS/002/VNP46A2` 最新日期并计算 `lead_days_vs_gee`。

### 12.3 输出契约
- `outputs/availability_report.json`
- `outputs/availability_report.csv`
- `outputs/VJ146A1/<date>/*_clipped.tif`（有有效 Earthdata 鉴权时）
- `outputs/VJ146A2/<date>/*_clipped.tif`（有有效 Earthdata 鉴权时）
- `outputs/VJ102DNB/feasibility.json`

### 12.4 当前验证结论（2026-02-18）
- 上海（AMap）与仰光（OSM）两区域都已跑通元数据层验证与 GEE 对照报告落盘。
- 在当前环境未提供有效 `EARTHDATA_TOKEN` 的情况下，A1/A2 下载状态为 `auth_missing` 或 `download_failed`（明确报错，不再误当 HDF 处理）。
- 日期领先性已可计算：示例中 `VJ146A1` / `VJ102DNB` 最新可用日期为 `2026-02-11`，对照 GEE `2026-02-10`，`lead_days_vs_gee = +1`。
- 若配置有效 `EARTHDATA_TOKEN`，可继续验证 A1/A2 区域裁剪日影像输出链路。

### 12.5 NRT 优先增强与监控网页（2026-02-18）
- `run_fast_daily_ntl.py` 默认源切换为 `nrt_priority`，当前顺序：
  - `VJ146A1_NRT -> VJ146A1 -> VJ146A2 -> VJ102DNB_NRT -> VJ102DNB`
- 新增独立监控服务：
  - `experiments/official_daily_ntl_fastpath/monitor_server.py`
  - `experiments/official_daily_ntl_fastpath/web_ui/index.html`
- 监控页支持两类能力：
  - 实时查询各源最新可用日期（global / bbox）与 lag days；
  - GIBS 全球渲染叠加（`VIIRS_SNPP_DayNightBand`、`VIIRS_NOAA20_DayNightBand`、`VIIRS_NOAA21_DayNightBand`）。
  - 图层加载状态提示（`loading / success / partial / failed`），用于快速判断渲染是否真正成功。
  - 区域快照渲染模式（Region Snapshot），可切换 `China / Shanghai / Custom BBox`，降低全球瓦片失败时的使用门槛。
  - 交互改为两步：左侧 `Query Availability` 查询数据，右侧 `Load Imagery` 手动上图，避免“参数变化后状态不明确”。
- 启动方式：
  - `conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py --host 127.0.0.1 --port 8765`
  - 浏览器打开 `http://127.0.0.1:8765`

### 12.6 3D Earth Orbit Monitor (2026-02-19)
- The monitor page now supports 2D/3D view switching in the right panel.
- New 3D mode uses CesiumJS and renders NTL-related satellite orbit tracks over a dark globe.
- Orbit source strategy: online CelesTrak fetch + local cache (workspace_monitor/cache/orbit_feed.json).
- New API endpoint:
  - GET /api/orbit_feed
  - Query params: force_refresh=0|1, ttl_minutes (default 180)
- Five fixed orbit slots:
  - snpp_viirs (37849)
  - noaa20_viirs (43013)
  - noaa21_viirs (54234)
  - sdgsat1 (49387)
  - luojia_slot (43035, with fallback chain 35951 -> 29522 -> 28054)
- If LUOJIA TLE is unavailable, the UI shows fallback substitution explicitly instead of silent failure.
- Orbit animation runs as UTC full-day loop and supports speed control (1x/60x/240x/600x).
