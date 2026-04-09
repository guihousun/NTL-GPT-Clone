# NTL-GPT-Clone

NTL-GPT is a Streamlit-based multi-agent workspace for nighttime light analysis. The stable public build focuses on local use: chat-driven data search, geospatial processing, official VIIRS workflows, and code-assisted NTL analysis.

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

## Environment

Fill these required values in `.env`:

- `DASHSCOPE_Qwen_plus_KEY`
- `DASHSCOPE_Qwen_plus_URL`
- `DASHSCOPE_Coding_URL`

Common optional values:

- `GEE_DEFAULT_PROJECT_ID`
- `EARTHDATA_TOKEN`
- `NTL_TOOL_PROFILE`
- `NTL_CONTEXTILY_TMP`

## Capability Tiers

Works after basic setup:

- chat interface
- local tool orchestration
- knowledge-guided geospatial code generation

Needs `GEE_DEFAULT_PROJECT_ID` and local Earth Engine auth:

- Google Earth Engine download and analysis tools

Needs `EARTHDATA_TOKEN`:

- official VIIRS / Earthdata download workflows

## Startup Check

Run this before first launch:

```bash
python check_env.py
```

It verifies:

- required environment variables
- key project files
- core Python imports

## Notes

- `environment.yml` is the only supported install path for the public stable build.
- `.env.example` is a template only. Do not commit a real `.env`.
- A temporary cloud demo is available at [https://ntl-gpt.gischaser.cn/](https://ntl-gpt.gischaser.cn/).
