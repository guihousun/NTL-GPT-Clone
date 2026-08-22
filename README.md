<p align="center">
  <img src="assets/ntl-gpt-console.png" width="100%" alt="NTL-GPT logged-in workspace running a nighttime-light analysis">
</p>

<h1 align="center">NTL-GPT：面向夜间灯光遥感任务的多智能体协同框架</h1>

<p align="center">
  <strong>NTL-GPT: A Collaborative Multi-Agent System for Automating Nighttime Light Remote Sensing Tasks</strong>
</p>

<p align="center">
  <a href="https://ntl-gpt.gischaser.cn/"><img alt="Live demo" src="https://img.shields.io/badge/live_demo-ntl--gpt.gischaser.cn-0f766e?style=flat-square"></a>
  <img alt="Python 3.11" src="https://img.shields.io/badge/python-3.11-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Streamlit 1.55" src="https://img.shields.io/badge/streamlit-1.55-FF4B4B?style=flat-square&logo=streamlit&logoColor=white">
  <img alt="Google Earth Engine" src="https://img.shields.io/badge/Google_Earth_Engine-ready-4285F4?style=flat-square&logo=googleearthengine&logoColor=white">
  <a href="LICENSE"><img alt="License: AGPL-3.0-only" src="https://img.shields.io/badge/license-AGPL--3.0--only-663399?style=flat-square"></a>
  <img alt="Status" src="https://img.shields.io/badge/status-research_preview-f59e0b?style=flat-square">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="docs/mcp/ntl-gis-core.md">GIS MCP</a> ·
  <a href="docs/mcp/ntl-download.md">Download MCP</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="LICENSE">License</a>
</p>

NTL-GPT is a local-first Streamlit application for nighttime-light analysis. It combines coordinated agents, deterministic GIS tools, Google Earth Engine workflows, official VIIRS/Earthdata acquisition, local RAG, and isolated per-thread workspaces in one reproducible research environment.

> NTL-GPT is under active development. Validate outputs before using them in operational or scientific decisions.

The interface keeps conversation, agent reasoning, data inputs, generated outputs, maps, and result previews together. The header image shows the authenticated workspace completing a Shanghai district ANTL workflow with built-in retrieval and zonal-statistics tools.

## What It Does

| Capability | Included workflows |
|---|---|
| NTL data retrieval | NPP-VIIRS, NPP-VIIRS-like, DMSP-OLS, VNP46A1, VNP46A2, SDGSAT-1 |
| Cloud processing | GEE catalog planning, direct export, batch export, server-side reduction |
| Official acquisition | Earthdata/CMR HDF5 retrieval, country or BBox download, mosaicking, progress and audit manifests |
| Local GIS | Validation, reprojection, clipping, mosaicking, zonal statistics, NTL metrics, trend and anomaly analysis |
| Agent workflows | Data Searcher, optional Code Assistant review, and NTL Engineer orchestration |
| Research runtime | Account login, PostgreSQL history, concurrent runs, cancellation, quotas, and thread isolation |
| Interoperability | Local stdio MCP services for GIS and download operations; EasyGEE and QGIS handoffs |

## Architecture

```mermaid
flowchart LR
    UI["Streamlit UI"] --> ENG["NTL Engineer"]
    ENG --> SEARCH["Data Searcher"]
    ENG -. optional review .-> CODE["Code Assistant"]
    SEARCH --> GEE["Google Earth Engine"]
    SEARCH --> EARTH["NASA Earthdata / CMR"]
    ENG --> TOOLS["Runtime GIS and NTL tools"]
    TOOLS --> MCP["ntl-gis-core / ntl-download MCP"]
    UI --> STORE["PostgreSQL history"]
    UI --> WORK["Per-thread workspace"]
    WORK --> INPUTS["inputs/"]
    WORK --> OUTPUTS["outputs/"]
    WORK --> MEMORY["memory/"]
```

NTL-GPT runs geospatial code and tools on the local host because Earth Engine credentials, GDAL/PROJ libraries, RAG assets, shared reference data, and thread workspaces must remain available. It is a workspace-isolated local subprocess model, not a vendor-hosted sandbox.

## Quick Start

### 1. Create the environment

Windows PowerShell:

```powershell
git clone https://github.com/guihousun/NTL-GPT-Clone.git NTL-GPT
Set-Location .\NTL-GPT
conda env create -f environment.yml
conda activate NTL-GPT-stable
Copy-Item .env.example .env
```

macOS or Linux:

```bash
git clone https://github.com/guihousun/NTL-GPT-Clone.git NTL-GPT
cd NTL-GPT
conda env create -f environment.yml
conda activate NTL-GPT-stable
cp .env.example .env
```

### 2. Configure services

Set these values in `.env`:

```env
DeepSeek_API_KEY=your_key
DeepSeek_Coding_URL=your_openai_compatible_endpoint
DASHSCOPE_API_KEY=your_key
DASHSCOPE_Qwen_plus_KEY=your_key
DASHSCOPE_Qwen_plus_URL=your_openai_compatible_endpoint
```

For GEE and official Earthdata downloads, also configure:

```env
GEE_DEFAULT_PROJECT_ID=your_gee_project
EARTHDATA_TOKEN=your_earthdata_token
```

Never commit `.env`, API keys, database passwords, Earthdata tokens, or Earth Engine credentials.

### 3. Validate and launch

```powershell
python check_env.py
python -m streamlit run Streamlit.py --server.address 127.0.0.1 --server.port 8501
```

Open [http://127.0.0.1:8501](http://127.0.0.1:8501). The public research preview is available at [https://ntl-gpt.gischaser.cn/](https://ntl-gpt.gischaser.cn/).

## Configuration

| Group | Variables |
|---|---|
| Frontend models | `DeepSeek_API_KEY`, `DeepSeek_Coding_URL` |
| Internal VLM and RAG | `DASHSCOPE_API_KEY`, `DASHSCOPE_Qwen_plus_KEY`, `DASHSCOPE_Qwen_plus_URL`, `NTL_VLM_MODEL` |
| Embeddings | `NTL_EMBEDDING_PROVIDER`, `NTL_EMBEDDING_MODEL`, `NTL_EMBEDDING_BASE_URL`, `NTL_EMBEDDING_DIMENSIONS`, `NTL_EMBEDDING_API_KEY` |
| Data services | `GEE_DEFAULT_PROJECT_ID`, `EARTHDATA_TOKEN`, `amap_api_key` |
| Persistence | `NTL_HISTORY_DB_URL`, `NTL_LANGGRAPH_POSTGRES_URL` |
| Runtime limits | `NTL_MAX_ACTIVE_RUNS`, `NTL_MAX_ACTIVE_RUNS_PER_USER`, `NTL_THREAD_WORKSPACE_QUOTA_MB`, `NTL_USER_WORKSPACE_QUOTA_MB` |
| Paths and MCP | `NTL_USER_DATA_DIR`, `NTL_SHARED_DATA_DIR`, `NTL_CONTEXTILY_TMP`, `NTL_MCP_ENV_FILE`, `NTL_MCP_WORKDIR`, `NTL_MCP_STATE_DIR` |
| UI compatibility | `NTL_FORCE_NATIVE_CHAT_INPUT`, `NTL_USE_CUSTOM_MULTIMODAL_CHAT_INPUT` |

See [`.env.example`](.env.example) for the maintained template and run `python check_env.py` after every configuration change.

### PostgreSQL

PostgreSQL is recommended for multi-user and production deployments:

```env
NTL_HISTORY_DB_URL=postgresql://ntl_gpt:your_password@127.0.0.1:5432/ntl_gpt
NTL_LANGGRAPH_POSTGRES_URL=postgresql://ntl_gpt:your_password@127.0.0.1:5432/ntl_gpt
```

```sql
CREATE USER ntl_gpt WITH PASSWORD 'your_password';
CREATE DATABASE ntl_gpt OWNER ntl_gpt;
GRANT ALL PRIVILEGES ON DATABASE ntl_gpt TO ntl_gpt;
```

Local PostgreSQL and Docker PostgreSQL use the same URL format. Use `127.0.0.1` when Streamlit and PostgreSQL are exposed on the same host; use the Compose service name only when both services share a Docker network.

## Local MCP Services

The repository includes two standalone stdio MCP servers. They do not require the Streamlit application or PostgreSQL.

| Service | Purpose | Guide |
|---|---|---|
| `ntl-gis-core` | Deterministic vector, raster, NTL metrics, zonal statistics, trend and anomaly operations | [Setup and tools](docs/mcp/ntl-gis-core.md) |
| `ntl-download` | geoBoundaries retrieval, explicit GEE exports, batch-task tracking, VNP46A1/VNP46A2 Earthdata downloads and recovery manifests | [Setup and tools](docs/mcp/ntl-download.md) |

Install both through the editable `packages/ntl_toolkit` package included in `environment.yml`. External MCP clients should use a dedicated work directory rather than the Streamlit `user_data` tree.

## Workspace Model

Every conversation thread receives an isolated workspace:

```text
user_data/<thread_id>/
├── inputs/     # uploads and retrieved source data
├── outputs/    # generated rasters, vectors, tables and figures
└── memory/     # thread-local runtime state and failed-run records
```

One run is allowed per thread. Different threads may run concurrently subject to global and per-user limits. Generated paths are resolved through `storage_manager.py`, and shared `base_data` is treated as read-only source data.

## Repository Layout

```text
NTL-GPT/
├── Streamlit.py              # application entrypoint
├── app_ui.py                 # interface and result rendering
├── app_logic.py              # run lifecycle and event streaming
├── graph_factory.py          # agent graph and tool routing
├── agents/                   # agent prompts and definitions
├── tools/                    # runtime geospatial and NTL tools
├── packages/ntl_toolkit/     # reusable GIS/download core
├── mcp_servers/              # local stdio MCP entrypoints
├── .ntl-gpt/skills/          # runtime workflow skills
├── RAG/                      # local knowledge indexes and references
├── tests/                    # application regression tests
├── evaluations/              # MCP evaluation fixtures
├── assets/                   # README/UI assets and runtime models
└── docs/                     # deployment and MCP documentation
```

## Documentation

- [Documentation index](docs/README.md)
- [Windows Server deployment and operations](docs/deployment/windows-server.md)
- [`ntl-gis-core` MCP](docs/mcp/ntl-gis-core.md)
- [`ntl-download` MCP](docs/mcp/ntl-download.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Development

Use the project environment for all checks:

```powershell
conda activate NTL-GPT-stable
python -m py_compile Streamlit.py app_logic.py app_agents.py graph_factory.py
python -m pytest tests -q
python -m pytest packages/ntl_toolkit/tests -q
```

Changes to routing or tools should test the target prompt and at least one neighboring scenario. New paths must remain inside the active thread workspace, and secrets or generated user data must never be committed.

## Contributing

Issues and focused pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes, especially for agent routing, execution safety, storage paths, or dataset semantics.

Contributions must include a Developer Certificate of Origin sign-off. Use `git commit -s` and read the repository [DCO](DCO) before submitting a pull request.

## License

Original NTL-GPT program source code is licensed under the [GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`). Modified versions offered through a network service must provide their corresponding source code to users as required by the license.

The AGPL grant does not automatically apply to third-party code, imported documents, literature corpora, datasets, model weights, generated vector indexes, user uploads, credentials, or service-provider content. See [Data and Model Policy](DATA_AND_MODEL_POLICY.md) and [Third-Party Notices](THIRD_PARTY_NOTICES.md) before reusing or redistributing those materials.

Copyright remains with the applicable copyright holders. The software is provided without warranty under the terms of the AGPL-3.0-only license.

For vulnerabilities or accidental credential exposure, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
