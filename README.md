# NTL-Claw(NTL-GPT)

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
- `GEE_DEFAULT_PROJECT_ID`
- `EARTHDATA_TOKEN`
- `NTL_TOOL_PROFILE`
- `NTL_CONTEXTILY_TMP`

## Main Capabilities

Available after basic setup:

- chat-based task handling
- local tool orchestration
- knowledge-guided geospatial code generation

Additional setup for Google Earth Engine:

- set `GEE_DEFAULT_PROJECT_ID`
- authenticate locally with Earth Engine if needed

## Runtime Execution Model

NTL-Claw intentionally does not enable remote DeepAgents sandbox providers by default. Google Earth Engine authentication, local credential caches, GDAL/PROJ/Rasterio/GeoPandas native libraries, local RAG assets, `base_data`, and per-thread workspaces are expected to be available on the host machine.

Generated geospatial code is executed through the project-local subprocess workspace model:

- DeepAgents filesystem backends provide virtual file routing and skill discovery.
- `tools/NTL_Code_generation.py` runs generated code in a subprocess with the current thread workspace as the working directory.
- Relative `inputs/...` and `outputs/...` paths resolve under `user_data/<thread_id>/`.
- This is not a vendor-hosted secure sandbox; safety relies on preflight checks, path protocol enforcement, subprocess timeouts, and workspace scoping.

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
