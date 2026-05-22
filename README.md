# NTL-GPT

NTL-GPT is an open-source Streamlit application for nighttime light analysis. It combines multi-agent orchestration, geospatial tooling, Google Earth Engine workflows, and official VIIRS data processing in a single local workspace.

## Quick Start

macOS / Linux (`bash`):

```bash
cd /path/to/NTL-GPT-stable
conda env create -f environment.yml
conda activate NTL-GPT-stable
cp .env.example .env
python check_env.py
streamlit run Streamlit.py
```

Windows (`PowerShell`):

```powershell
Set-Location E:\NTL-GPT-stable
conda env create -f environment.yml
conda activate NTL-GPT-stable
Copy-Item .env.example .env
python check_env.py
streamlit run Streamlit.py
```

## Configure `.env`

Required:

- `DASHSCOPE_API_KEY`
- `DASHSCOPE_Qwen_plus_KEY`
- `DASHSCOPE_Qwen_plus_URL`
- `DASHSCOPE_Coding_URL`

Optional:

- `MINIMAX_API_KEY`
- `MINIMAX_Coding_URL`
- `GEE_DEFAULT_PROJECT_ID`
- `EARTHDATA_TOKEN`
- `NTL_TOOL_PROFILE`
- `NTL_USER_DATA_DIR`
- `NTL_SHARED_DATA_DIR`
- `NTL_CONTEXTILY_TMP`
- `NTL_HISTORY_DB_URL`
- `NTL_LANGGRAPH_POSTGRES_URL`
- `NTL_MAX_ACTIVE_RUNS`
- `NTL_MAX_ACTIVE_RUNS_PER_USER`
- `NTL_THREAD_WORKSPACE_QUOTA_MB`
- `NTL_USER_WORKSPACE_QUOTA_MB`
- `NTL_EMBEDDING_PROVIDER`
- `NTL_EMBEDDING_MODEL`
- `NTL_EMBEDDING_BASE_URL`
- `NTL_EMBEDDING_DIMENSIONS`
- `NTL_EMBEDDING_API_KEY`
- `NTL_FORCE_NATIVE_CHAT_INPUT`

## Main Capabilities

Available after basic setup:

- chat-based task handling
- local tool orchestration
- knowledge-guided geospatial code generation
- account/password login
- per-thread workspace isolation
- configurable run concurrency and workspace quotas

Additional setup for Google Earth Engine:

- set `GEE_DEFAULT_PROJECT_ID`
- authenticate locally with Earth Engine if needed

## Runtime Execution Model

NTL-GPT intentionally does not enable remote DeepAgents sandbox providers by default. Google Earth Engine authentication, local credential caches, GDAL/PROJ/Rasterio/GeoPandas native libraries, local RAG assets, `base_data`, and per-thread workspaces are expected to be available on the host machine.

Generated geospatial code is executed through the project-local subprocess workspace model:

- DeepAgents filesystem backends provide virtual file routing and skill discovery.
- `tools/NTL_Code_generation.py` runs generated code in a subprocess with the current thread workspace as the working directory.
- Relative `inputs/...` and `outputs/...` paths resolve under `user_data/<thread_id>/`.
- This is not a vendor-hosted secure sandbox; safety relies on preflight checks, path protocol enforcement, subprocess timeouts, and workspace scoping.
- `/shared/...` maps to `base_data/...` and is treated as shared read-only source data.

## Multi-User Runtime Model

The Streamlit runtime isolates work by thread:

- each thread uses its own `user_data/<thread_id>/inputs`, `outputs`, `memory`, and history records
- one run at a time is allowed per thread
- different threads can run concurrently in background Python threads
- global and per-user active-run limits are controlled by `NTL_MAX_ACTIVE_RUNS` and `NTL_MAX_ACTIVE_RUNS_PER_USER`
- per-thread and per-user workspace storage quotas are controlled by `NTL_THREAD_WORKSPACE_QUOTA_MB` and `NTL_USER_WORKSPACE_QUOTA_MB`

Set a limit to `0` to disable it.

## PostgreSQL Persistence

For production or multi-user use, configure PostgreSQL in `.env`:

```env
NTL_HISTORY_DB_URL=postgresql://ntl_gpt:your_password@127.0.0.1:5432/ntl_gpt
NTL_LANGGRAPH_POSTGRES_URL=postgresql://ntl_gpt:your_password@127.0.0.1:5432/ntl_gpt
```

`NTL_HISTORY_DB_URL` stores users, password hashes, chat history, threads, profiles, and related app state. If it is empty, history storage falls back to `NTL_LANGGRAPH_POSTGRES_URL`.

`NTL_LANGGRAPH_POSTGRES_URL` is reserved for LangGraph/Postgres-backed runtime memory and checkpoint storage where supported by the installed LangGraph packages.

Local PostgreSQL and Docker PostgreSQL use the same URL format. Only the host name changes:

- PostgreSQL installed directly on the same machine: `127.0.0.1:5432`
- Docker PostgreSQL exposed with `-p 5432:5432`, while Streamlit runs in local conda: `127.0.0.1:5432`
- Docker Compose where Streamlit and PostgreSQL run on the same Docker network: use the service name, for example `postgres:5432`

Example local database bootstrap:

```sql
CREATE USER ntl_gpt WITH PASSWORD 'your_password';
CREATE DATABASE ntl_gpt OWNER ntl_gpt;
GRANT ALL PRIVILEGES ON DATABASE ntl_gpt TO ntl_gpt;
```

Example Docker PostgreSQL:

```bash
docker run --name ntl-gpt-postgres \
  -e POSTGRES_USER=ntl_gpt \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=ntl_gpt \
  -p 5432:5432 \
  -d postgres:16
```

After editing `.env`, run:

```bash
python check_env.py
```

Additional setup for official VIIRS downloads:

- set `EARTHDATA_TOKEN`

DashScope channel mapping:

- `DASHSCOPE_API_KEY` is used with `DASHSCOPE_Coding_URL`
- `DASHSCOPE_Qwen_plus_KEY` is used with `DASHSCOPE_Qwen_plus_URL`

## RAG Embeddings

The local NTL knowledge-base tools use DashScope embeddings by default through the OpenAI-compatible API:

```env
NTL_EMBEDDING_PROVIDER=dashscope
NTL_EMBEDDING_MODEL=text-embedding-v4
NTL_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
NTL_EMBEDDING_DIMENSIONS=1024
```

If `NTL_EMBEDDING_API_KEY` is empty, the embedding client uses `DASHSCOPE_Qwen_plus_KEY`. `OPENAI_API_KEY` is only needed if you explicitly set `NTL_EMBEDDING_PROVIDER=openai`.

If an existing `RAG/*_RAG` Chroma store was built with OpenAI embeddings, rebuild it after switching to DashScope so stored document vectors and query vectors come from the same embedding model.

Model channel mapping:

- `qwen3.5-plus` and `qwen3.6-plus` use the DashScope coding channel.
- `MiniMax-M2.7` uses `MINIMAX_API_KEY` and `MINIMAX_Coding_URL`.
- `GPT-5.4`, `GPT-5.4-mini`, and `GPT-5.4-nano` use the OpenAI channel; API model names are normalized to lowercase.

## Startup Check

Run this before first launch:

```bash
python check_env.py
```

The checker verifies:

- required environment variables
- key project files
- core Python imports

## Cloud Demo

A temporary public demo is available at:

[https://ntl-gpt.gischaser.cn/](https://ntl-gpt.gischaser.cn/)

## Notes

- `environment.yml` is the supported installation entry for this repository.
