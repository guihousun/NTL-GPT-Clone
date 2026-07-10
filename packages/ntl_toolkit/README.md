# ntl-toolkit

Shared installable domain core for NTL-GPT GIS and nighttime-light workflows.

## Install

From the repository root in the `NTL-GPT-Stable` environment:

```powershell
python -m pip install -e packages/ntl_toolkit
```

The package exposes the `ntl-gis-core` stdio entry point. The checked-in
launcher at `mcp_servers/gis_core_server.py` is equivalent and is the form
used by the client examples in [`docs/mcp/ntl-gis-core.md`](../../docs/mcp/ntl-gis-core.md).

## Runtime contract

- Relative paths resolve below `NTL_MCP_WORKDIR`; absolute Windows paths are
  also accepted.
- Inputs are read from the selected workspace. Generated files are written to
  the requested output location with an automatic suffix when a file exists.
- Tools never delete or overwrite files. `validate_environment`, inspection,
  NTL metric calculation, and geodata validation are read-only.
- Credentials are loaded from the process environment or
  `NTL_MCP_ENV_FILE`; they are not tool arguments or result fields.

See [`tool_migration_manifest.json`](tool_migration_manifest.json) for legacy
capability mappings and parity status.
