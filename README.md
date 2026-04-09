# NTL-GPT-Clone

NTL-GPT is an open-source Streamlit application for nighttime light analysis. It combines multi-agent orchestration, geospatial tooling, Google Earth Engine workflows, and official VIIRS data processing in a single local workspace.

## Quick Start

```bash
conda env create -f environment.yml
conda activate NTL-GPT-stable
cp .env.example .env
python check_env.py
streamlit run Streamlit.py
```

PowerShell:

```powershell
conda env create -f environment.yml
conda activate NTL-GPT-stable
Copy-Item .env.example .env
python check_env.py
streamlit run Streamlit.py
```

## Configure `.env`

Required:

- `DASHSCOPE_Qwen_plus_KEY`
- `DASHSCOPE_Qwen_plus_URL`
- `DASHSCOPE_Coding_URL`

Optional:

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

Additional setup for official VIIRS downloads:

- set `EARTHDATA_TOKEN`

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
- `.env.example` is a template; copy it to `.env` before running the app.
