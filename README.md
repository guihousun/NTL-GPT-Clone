# NTL-Claw-Clone

NTL-Claw is an open-source Streamlit application for nighttime light analysis. It combines multi-agent orchestration, geospatial tooling, Google Earth Engine workflows, and official VIIRS data processing in a single local workspace.

## Quick Start

macOS / Linux (`bash`):

```bash
cd /path/to/NTL-Claw-stable
conda env create -f environment.yml
conda activate NTL-Claw-stable
cp .env.example .env
python check_env.py
streamlit run Streamlit.py
```

Windows (`PowerShell`):

```powershell
Set-Location E:\NTL-Claw-stable
conda env create -f environment.yml
conda activate NTL-Claw-stable
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
- `OPENAI_API_KEY`
- `GEE_DEFAULT_PROJECT_ID`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `GOOGLE_OAUTH_SCOPES`
- `NTL_TOKEN_ENCRYPTION_KEY`
- `EARTHDATA_TOKEN`
- `NTL_TOOL_PROFILE`
- `NTL_USER_DATA_DIR`
- `NTL_SHARED_DATA_DIR`
- `NTL_CONTEXTILY_TMP`
- `NTL_MAX_ACTIVE_RUNS`
- `NTL_MAX_ACTIVE_RUNS_PER_USER`
- `NTL_THREAD_WORKSPACE_QUOTA_MB`
- `NTL_USER_WORKSPACE_QUOTA_MB`
- `NTL_LOCAL_ADMIN_HOST`
- `NTL_LOCAL_ADMIN_PORT`
- `NTL_LOCAL_ADMIN_ACTOR`
- `NTL_FORCE_NATIVE_CHAT_INPUT`
- `NTL_STREAMING_MAIN_REFRESH_SECONDS`
- `NTL_STREAMING_GRAPH_REFRESH_SECONDS`
- `NTL_LANGGRAPH_POSTGRES_URL`
- `NTL_LANGGRAPH_POSTGRES_AUTO_SETUP`
- `NTL_DEEPAGENTS_MEMORY_BACKEND`
- `NTL_MEMORY_NAMESPACE_SCOPE`
- `NTL_ADMIN_USERNAMES`

## Main Capabilities

Available after basic setup:

- chat-based task handling
- local tool orchestration
- knowledge-guided geospatial code generation

Additional setup for Google Earth Engine:

- set `GEE_DEFAULT_PROJECT_ID`
- authenticate locally with Earth Engine if needed

GEE pipeline selection:

- `Default pipeline` uses the hosted project from `GEE_DEFAULT_PROJECT_ID` and remains the fallback path.
- `My GEE pipeline` lets each logged-in user save a personal GEE Project ID from the sidebar.
- If Google OAuth is configured, users can connect their Google account and the refresh token is encrypted with `NTL_TOKEN_ENCRYPTION_KEY`.
- `GOOGLE_OAUTH_REDIRECT_URI` defaults to `http://localhost:8501`; for deployment, set it to the production Streamlit URL and add the same URI to the Google Cloud OAuth client.
- Each run injects the effective `gee_project_id` into LangGraph metadata and the runtime system context so generated GEE scripts use `ee.Initialize(project="...")`.
- Generated-code execution receives the current user's encrypted refresh token through thread-local runtime context and initializes Earth Engine with user credentials when available.

Generate a Fernet encryption key for OAuth token storage:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Admin console:

- Set `NTL_ADMIN_USERNAMES` to a comma-separated list of usernames that should become admins when registered, for example `NTL_ADMIN_USERNAMES=owner,operator`.
- Run `python admin_local.py` to start the local admin page on `http://127.0.0.1:8502` by default.
- `NTL_LOCAL_ADMIN_HOST` and `NTL_LOCAL_ADMIN_PORT` control the local bind address.
- The local admin page can list users, see account/GEE status, inspect workspace usage, clear thread `inputs/outputs/memory`, disable or enable users, reset a user's GEE pipeline, and delete threads.
- Admin actions are written to `admin_audit_logs`; OAuth refresh tokens are never displayed.

Streaming and input fallback controls:

- `NTL_FORCE_NATIVE_CHAT_INPUT=1` forces Streamlit's native chat input when the multimodal input component has deployment-specific rendering issues.
- `NTL_STREAMING_MAIN_REFRESH_SECONDS` and `NTL_STREAMING_GRAPH_REFRESH_SECONDS` tune live response refresh intervals. Lower values feel more immediate but increase WebSocket traffic.

## Runtime Execution Model

NTL-Claw intentionally does not enable remote DeepAgents sandbox providers by default. Google Earth Engine authentication, local credential caches, GDAL/PROJ/Rasterio/GeoPandas native libraries, local RAG assets, `base_data`, and per-thread workspaces are expected to be available on the host machine.

Generated geospatial code is executed through the project-local subprocess workspace model:

- DeepAgents filesystem backends provide virtual file routing and skill discovery.
- `tools/NTL_Code_generation.py` runs generated code in a subprocess with the current thread workspace as the working directory.
- Relative `inputs/...` and `outputs/...` paths resolve under `user_data/<thread_id>/`.
- This is not a vendor-hosted secure sandbox; safety relies on preflight checks, path protocol enforcement, subprocess timeouts, and workspace scoping.
- `/shared/...` maps to `base_data/...` and is routed through a read-only backend; generated outputs must go to `/outputs/...`.

## Multi-User Runtime Model

The local Streamlit runtime isolates work by `thread_id`:

- each thread uses its own `user_data/<thread_id>/inputs`, `outputs`, `memory`, and `history` folders
- one run at a time is allowed per thread
- different threads can run concurrently in background Python threads
- global and per-user active-run limits are controlled by `NTL_MAX_ACTIVE_RUNS` and `NTL_MAX_ACTIVE_RUNS_PER_USER`
- per-thread and per-user workspace storage quotas are controlled by `NTL_THREAD_WORKSPACE_QUOTA_MB` and `NTL_USER_WORKSPACE_QUOTA_MB`

Development mode uses in-process LangGraph state:

- `MemorySaver` for checkpoints
- `InMemoryStore` for LangGraph store
- filesystem-backed `/memories/...` under each thread workspace

Production persistence can be enabled with:

```bash
NTL_LANGGRAPH_POSTGRES_URL=postgresql://user:password@host:5432/dbname
NTL_LANGGRAPH_POSTGRES_AUTO_SETUP=1
NTL_DEEPAGENTS_MEMORY_BACKEND=auto
NTL_MEMORY_NAMESPACE_SCOPE=thread
```

When `NTL_LANGGRAPH_POSTGRES_URL` is set, NTL-Claw uses LangGraph `PostgresSaver` and `PostgresStore`. With `NTL_DEEPAGENTS_MEMORY_BACKEND=auto`, `/memories/...` is routed to DeepAgents `StoreBackend` and namespaced as `(assistant_id, user_id, thread_id)` by default. Set `NTL_MEMORY_NAMESPACE_SCOPE=user` only if cross-thread user memory sharing is desired and concurrent memory writes are acceptable for that deployment.

Additional setup for official VIIRS downloads:

- set `EARTHDATA_TOKEN`

DashScope channel mapping:

- `DASHSCOPE_API_KEY` is used with `DASHSCOPE_Coding_URL`
- `DASHSCOPE_Qwen_plus_KEY` is used with `DASHSCOPE_Qwen_plus_URL`

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
