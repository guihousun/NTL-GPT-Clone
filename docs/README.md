# NTL-GPT Documentation

This directory contains public operator and integration documentation. Start with the root [README](../README.md) for installation and the project overview.

## Deployment

- [Windows Server operations](deployment/windows-server.md): update, launch, Nginx, HTTPS, PostgreSQL, backup, and troubleshooting.

## MCP Services

- [`ntl-gis-core`](mcp/ntl-gis-core.md): local deterministic GIS and nighttime-light tools.
- [`ntl-download`](mcp/ntl-download.md): GEE export and official VNP46A1/VNP46A2 Earthdata download tools.

## Development Records

Historical implementation plans are local engineering records and are not part of the public runtime distribution. Current behavior is documented by the README, MCP guides, tests, source code, and `.ntl-gpt/skills/` contracts.

## Documentation Rules

- Keep commands aligned with `environment.yml`, `check_env.py`, and `Streamlit.py`.
- Never include API keys, tokens, passwords, private data paths, or user workspace contents.
- Prefer concise operator guidance over internal implementation transcripts.
- Update the relevant guide whenever a public entrypoint or environment variable changes.
