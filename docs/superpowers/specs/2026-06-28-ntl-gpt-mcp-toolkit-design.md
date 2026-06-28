# NTL-GPT 通用 MCP 工具集设计

日期：2026-06-28

## 1. 目标

将 NTL-GPT 中稳定、原子、可复用的 GIS、夜间灯光、GEE 和 Earthdata 能力整理为本机 stdio MCP 工具集，同时保留 NTL-GPT 当前 LangChain/Deep Agents 调用接口。

本设计不将全部现有工具机械转换为 MCP，也不让 NTL-GPT 反向依赖 MCP。领域算法只保留一份，由 LangChain 和 MCP 两个适配器共享。

首期面向本机 Codex、Claude Desktop 和 OpenClaw，统一使用 `NTL-GPT-Stable` Conda 环境。

## 2. 已确认的设计决策

- 采用共享 Core + LangChain/MCP 双适配器。
- 代码放在 NTL-GPT 仓库内，作为可安装子包。
- 一个项目提供三个 stdio 服务配置：`ntl-gis-core`、`ntl-gee-tools`、`ntl-earthdata-tools`。
- 实施顺序为 GIS Core、GEE、Earthdata。
- 文件路径可以指向本机任意位置。
- 不提供删除工具，不默认覆盖已有输出；重名时自动分配新文件名。
- 凭据从进程环境或 `NTL_MCP_ENV_FILE` 指定的 `.env` 加载，不进入工具参数和结果。
- 短任务同步执行；下载、批处理和云端导出使用持久化 job。
- 工具统一返回结构化结果和简短文本摘要。
- 现有 NTL-GPT 工具保持公开名称和调用方式，逐个通过行为一致性测试后切换到共享 Core。

## 3. 非目标

以下能力不进入首期通用 MCP：

- Streamlit UI、账号、历史记录和会话状态。
- `graph_factory.py` 中的多智能体编排。
- Agent prompts、skills 和完整 ConflictNTL 工作流。
- NTL Knowledge Base 和 RAG。
- 任意 Python 代码执行。
- 将 NTL-GPT 改造成 MCP 客户端。
- 远程 streamable HTTP 部署和远程用户认证。

`Auth: Unsupported` 对本机 stdio MCP 是可接受状态。本机进程权限构成当前信任边界。

## 4. 仓库结构

```text
D:\NTL-GPT-main\
├── packages\
│   └── ntl_toolkit\
│       ├── pyproject.toml
│       ├── src\ntl_toolkit\
│       │   ├── schemas\
│       │   ├── core\
│       │   │   ├── vector\
│       │   │   ├── raster\
│       │   │   ├── gee\
│       │   │   ├── earthdata\
│       │   │   └── jobs\
│       │   ├── adapters\
│       │   │   ├── langchain\
│       │   │   └── mcp\
│       │   └── runtime\
│       └── tests\
└── mcp_servers\
    ├── gis_core_server.py
    ├── gee_tools_server.py
    └── earthdata_tools_server.py
```

### 4.1 `schemas`

定义 Pydantic 请求、结果、错误、输出文件和 job 模型。Schema 不依赖 LangChain 或 MCP。

### 4.2 `core`

保存纯 Python 领域逻辑。Core 不导入 Streamlit、LangChain、FastMCP，不读取 `st.session_state`、LangGraph `RunnableConfig` 或 `current_thread_id`。

### 4.3 `adapters/langchain`

保留现有 NTL-GPT 工具名称，负责把当前线程工作区路径转换为显式绝对路径，然后调用 Core。

### 4.4 `adapters/mcp`

负责 FastMCP 注册、tool annotations、文本摘要和 structured content，不包含领域算法。

### 4.5 `runtime`

负责环境加载、路径解析、无覆盖写入、日志脱敏、job 持久化、取消和状态恢复。

## 5. 服务与工具目录

### 5.1 `ntl-gis-core`

首批工具：

```text
validate_environment
inspect_vector
inspect_raster
filter_points_by_polygon
spatial_join_points_to_admin
buffer_points_aeqd
dissolve_intersections
clip_raster
reproject_raster
mosaic_rasters
calculate_zonal_statistics
calculate_ntl_metrics
composite_ntl_rasters
analyze_ntl_trend
detect_ntl_anomaly
validate_geodata
```

现有 `conflictntl-gis-tools` 是 `core/vector` 的原型。其 `_read_points`、`_write_vector` 和五个本地 GIS 执行能力迁入共享 Core。网络工具 `download_geoboundary` 保留在兼容服务，第二阶段迁入数据访问服务。只有全部能力完成替代后，旧服务才进入 deprecated 状态。

### 5.2 `ntl-gee-tools`

第二阶段工具：

```text
validate_environment
download_geoboundary
discover_datasets
get_dataset_metadata
check_dataset_availability
resolve_dataset_route
plan_server_side_reduction
submit_image_download
submit_table_reduction
get_job_status
cancel_job
list_job_outputs
```

国家级、多省级、长时间序列和多要素统计默认生成服务端 `reduceRegions` 表格，不以下载全国 GeoTIFF 作为主路径。数据集选择和事件日期判断仍由 skills 负责。

### 5.3 `ntl-earthdata-tools`

第三阶段工具：

```text
validate_environment
search_granules
check_product_availability
inspect_hdf_product
submit_granule_download
submit_vnp46a2_country_mosaic
submit_vj_dnb_preprocess
convert_vj102_vj103_to_geotiff
get_job_status
cancel_job
list_job_outputs
```

### 5.4 MCP Resources

说明性内容不占用工具列表，改为 resources：

```text
ntl://gis/capabilities
ntl://gee/capabilities
ntl://earthdata/capabilities
ntl://schemas/result-v1
ntl://schemas/job-v1
```

## 6. 调用与适配流程

```text
NTL-GPT Agent
  -> LangChain adapter
  -> ntl_toolkit core

Codex / Claude Desktop / OpenClaw
  -> FastMCP adapter
  -> ntl_toolkit core
```

每个能力由 Request Schema、Core Function 和 Adapter 组成。例如：

```text
ZonalStatisticsRequest
  -> core.raster.calculate_zonal_statistics()
  -> NTL_raster_statistics_tool
  -> calculate_zonal_statistics MCP tool
```

现有 LangChain 工具只有在 parity tests 通过后才切换到共享 Core。迁移过程不改变 Streamlit、Agent prompt 和线程工作区的外部行为。

## 7. 路径与写入策略

- 绝对路径直接解析。
- 相对路径相对于 `NTL_MCP_WORKDIR`。
- 未设置 `NTL_MCP_WORKDIR` 时使用 MCP 启动目录。
- 输入不存在时返回 `INPUT_NOT_FOUND`。
- 输出目录可以自动创建。
- 输出文件已存在时不覆盖，而是生成 `_001`、`_002` 等后缀。
- 不提供删除、清空目录或批量移动工具。
- Shapefile 可以读取；新矢量输出默认推荐 GeoPackage 或 GeoJSON。

自由路径仅适用于已确认的本机单用户 stdio 场景。未来远程部署必须重新设计目录白名单和认证。

## 8. 环境与凭据

建议配置：

```text
NTL_MCP_ENV_FILE=D:\NTL-GPT-main\.env
NTL_MCP_WORKDIR=D:\Research_vault
NTL_MCP_STATE_DIR=D:\NTL-GPT-main\.ntl-mcp
```

加载顺序：

1. 已存在的进程环境变量。
2. `NTL_MCP_ENV_FILE` 指定的文件。
3. GEE、Earthdata 等官方本机认证缓存。

任何 token、API key、数据库 URL 和认证文件内容都不得进入工具参数、返回值和未脱敏日志。

## 9. 长任务作业模型

检查、过滤和小型统计同步执行。下载、批处理、GEE 导出和大范围预处理创建 job。

```text
.ntl-mcp\
├── jobs.sqlite
└── jobs\
    └── <job_id>\
        ├── request.json
        ├── status.json
        ├── stdout.log
        ├── stderr.log
        └── outputs.json
```

状态机：

```text
queued -> running -> succeeded
                  -> failed
                  -> cancelled
```

MCP server 重启后仍可查询已有 job。取消操作终止任务，但不删除已生成文件。

## 10. 统一返回与错误协议

成功结果示例：

```json
{
  "schema": "ntl.tool.result.v1",
  "status": "succeeded",
  "tool": "calculate_zonal_statistics",
  "summary": "Calculated statistics for 31 polygons.",
  "outputs": [
    {
      "path": "D:/data/results/stats.csv",
      "media_type": "text/csv",
      "role": "primary"
    }
  ],
  "metrics": {
    "feature_count": 31,
    "elapsed_seconds": 8.4
  },
  "warnings": [],
  "error": null,
  "job_id": null
}
```

错误对象示例：

```json
{
  "code": "INPUT_NOT_FOUND",
  "message": "Raster input does not exist.",
  "details": {"path": "D:/data/ntl.tif"},
  "suggestion": "Check the path or call inspect_raster first."
}
```

工具不能只返回 traceback。内部异常应转换为稳定错误码，同时保留脱敏诊断日志。

## 11. MCP Annotations

- 检查类工具：`readOnlyHint=true`。
- 生成类工具：`readOnlyHint=false`。
- 所有工具：`destructiveHint=false`。
- 纯检查和确定性无副作用操作：`idempotentHint=true`。
- 自动分配新输出文件名的生成操作：`idempotentHint=false`，避免把重复调用误判为同一结果。
- 网络检索和下载：`openWorldHint=true`。

## 12. 迁移登记

创建：

```text
packages/ntl_toolkit/tool_migration_manifest.json
```

示例：

```json
{
  "legacy_tool": "NTL_raster_statistics_tool",
  "core_function": "raster.calculate_zonal_statistics",
  "mcp_tool": "calculate_zonal_statistics",
  "status": "migrated",
  "parity_tests": ["single_raster", "batch_rasters", "missing_input"]
}
```

状态：

```text
planned | extracting | parity_testing | migrated | deprecated
```

## 13. 测试策略

### 13.1 Core 单元测试

覆盖 Windows 绝对路径、中文路径、CRS 缺失、CRS 不一致、空数据、无有效像元、单要素、多要素和无覆盖输出。

### 13.2 行为一致性测试

对 legacy LangChain tool、共享 Core 和 MCP adapter 比较：

- 要素数量与 CRS。
- 栅格尺寸、分辨率和 nodata。
- NTL 指标允许误差。
- 输出能否被 Rasterio 或 GeoPandas 重新打开。

### 13.3 MCP 集成测试

验证 `tools/list`、`resources/list`、`tools/call`、结构化错误、无覆盖写入、job 重启恢复和任务取消，并使用 MCP Inspector 做人工验收。

### 13.4 网络测试

默认测试 mock GEE 和 Earthdata；真实凭据测试使用：

```text
pytest -m gee_live
pytest -m earthdata_live
```

### 13.5 Agent 评估

每个服务创建 10 个独立、只读、复杂、稳定、可验证的评估问题。答案必须能从结构化返回值验证。

## 14. 发布门槛

`ntl-gis-core` 首版必须满足：

- 16 个工具均有输入 schema、结构化输出和 annotations。
- 所有写入默认不覆盖。
- 中文路径和 Windows 路径测试通过。
- Core 不依赖 Streamlit、LangChain 或 FastMCP。
- 现有 ConflictNTL GIS 工具 parity tests 通过。
- 关键 NTL 本地工具 parity tests 通过。
- MCP Inspector 可稳定启动和调用。
- 文档包含 Codex、Claude Desktop 和 OpenClaw stdio 配置示例。

达到上述门槛后才进入 `ntl-gee-tools`，随后进入 `ntl-earthdata-tools`。

## 15. 主要风险与控制

- **自由路径风险**：仅限本机单用户 stdio，不提供删除和默认覆盖。
- **工具面膨胀**：工作流知识留在 skills，MCP 只暴露原子能力。
- **两套实现漂移**：禁止复制算法，LangChain 和 MCP 必须共享 Core。
- **原生地理依赖复杂**：首期统一复用 `NTL-GPT-Stable`。
- **凭据泄漏**：环境加载、返回值和日志统一脱敏。
- **长任务超时**：使用持久化 job，而不是长期阻塞工具调用。
- **迁移回归**：每个工具通过 parity tests 后才切换适配器。
