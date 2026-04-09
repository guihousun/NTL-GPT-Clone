# NTL-GPT-Clone

A temporary, anonymous demo of our multi-agent system is available at:

[https://ntl-gpt.gischaser.cn/](https://ntl-gpt.gischaser.cn/)

This is the free cloud-based trial version. Some newer features may not be available yet, and occasional bugs may occur. For questions or feedback, contact `51273901095@stu.ecnu.edu.cn`.

## Local Setup

Recommended for new users:

```bash
conda env create -f environment.yml
conda activate NTL-GPT-stable
```

Create a local environment file:

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, fill these variables in `.env`:

- `DASHSCOPE_Qwen_plus_KEY`
- `DASHSCOPE_Qwen_plus_URL`
- `DASHSCOPE_Coding_URL`

Optional but commonly needed:

- `EARTHDATA_TOKEN`: required for official VIIRS / Earthdata downloads
- `NTL_TOOL_PROFILE`: defaults to `default`
- `NTL_CONTEXTILY_TMP`: useful if basemap cache permissions are unstable

For personal Google Earth Engine use:

- `GEE_DEFAULT_PROJECT_ID`: your own Google Cloud project id for Earth Engine

The stable build is intended for personal use. Fill your own GEE project id in `.env`, and let Earth Engine use your normal local auth flow if needed.

Run the app:

```bash
streamlit run Streamlit.py
```

## Notes

- `environment.yml` is the recommended install path for this project.
- `.env.example` is a template only. Do not commit a real `.env`.
