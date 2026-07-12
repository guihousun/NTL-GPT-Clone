# Local Stdio Download MCP Design

## Goal

Provide one local-only stdio MCP service for long-running GEE and official
Earthdata downloads. It must work from Codex and share the same download core
with NTL-GPT without requiring a web server, Job Runtime, database, or remote
MCP deployment.

## Scope

The new service is named `ntl-download`. It is a sibling of the existing
`ntl-gis-core` service, not a replacement for it.

| Layer | Responsibility |
| --- | --- |
| `ntl-gis-core` | Deterministic local vector, raster, and NTL analysis. |
| `ntl-download` | GEE raster download and audited official VNP46A2 Earthdata HDF5 country mosaics. |
| EasyGEE | GEE readiness, authentication planning, catalog search, quotas, and map preview. It remains an independent optional MCP. |
| NTL-GPT | Thread-aware UI/runtime wrappers around the shared download core. It must not start an MCP subprocess to call itself. |

The existing global `vnp46a2-official-h5-country-mosaic` skill remains in
place. Its reusable routing and audit guidance is copied into the
`ntl-gpt-project` skill; users may disable the old standalone skill locally.

## Service Contract

`ntl-download` uses FastMCP over stdio. It is local and single-user. It has no
authentication endpoint and never accepts credentials as tool parameters.

The server captures `NTL_MCP_WORKDIR` at startup. Relative paths resolve under
that directory; absolute Windows paths are allowed. Download outputs must be
explicit paths under the selected workdir or a user-supplied absolute output
directory. Existing outputs are not silently overwritten.

### Tools

| Tool | Mode | Contract |
| --- | --- | --- |
| `validate_download_environment` | read-only | Reports dependency availability, GEE initialization readiness without OAuth, and whether the configured Earthdata environment variable is present. It never prints secret values. |
| `download_gee_raster` | write | Downloads one selected GEE image or collection reduction to GeoTIFF using local Earth Engine credentials. It accepts an explicit dataset, band, UTC date window, AOI GeoJSON or bounding box, scale, CRS, and output path. |
| `download_vnp46a2_official_h5_country` | write | Runs the official VNP46A2 non-gap-filled HDF5 pipeline in `plan`, `prepare`, `download`, `mosaic`, `audit`, `organize`, or `full` mode. It preserves ISO3/date retry targets and audit rules. |
| `inspect_download_run` | read-only | Reads the VNP46A2 manifest/audit files or a GEE sidecar manifest and returns current phase, counts, artifacts, errors, and precise retry targets. |

All tools return structured JSON with an operation status, actual artifact
paths, and actionable errors. Output-producing tools use no-overwrite output
reservation. `EARTHDATA_TOKEN` and GEE credentials are read only from the
environment or an explicitly configured local dotenv file.

## Progress and Long Runs

Downloads execute synchronously. The MCP call remains active until the selected
operation reaches a terminal result. No duration cap is imposed by the MCP.

During execution the server sends MCP progress notifications and writes a
sanitized run manifest. At minimum it reports:

1. GEE: initialization, AOI validation, collection/image selection, export or
   download progress, local file validation, and completed artifact path.
2. Earthdata: boundary preparation, CMR discovery, country-day and granule
   counts, downloaded/failed HDF5 counts, mosaic counts, audit summary, and
   retry targets.

If a client disconnects, files and manifests remain at the requested output
location. A later `inspect_download_run` call shows actual progress. Retrying a
VNP46A2 subset must use the stored ISO3/date targets instead of restarting a
complete run.

## Shared-Core Boundary

Network-independent validation, path resolution, manifest writing, sanitizing,
and VNP46A2 command construction live in `packages/ntl_toolkit`. The MCP
adapter calls those functions directly. NTL-GPT adapters call the same functions
but translate its thread workspace paths through `storage_manager`.

The new GEE core must not import Streamlit, `storage_manager`, or LangChain.
The legacy `tools/GEE_download.py` remains available during migration; the new
adapter supports an explicit AOI/data contract rather than legacy natural
language administrative-boundary guessing.

## Routing Rules

- Use GEE for a bounded AOI, a known collection/band, and cloud-side filtering
  or reduction before a local GeoTIFF export.
- Use official Earthdata HDF5 only for explicit raw country-scale daily
  non-gap-filled VNP46A2 `DNB_BRDF_Corrected_NTL` raster retrieval.
- Do not use country-scale raster downloads as the default solution for
  national statistics, rankings, or many-feature summaries; use GEE server-side
  reductions for those requests.
- `no_granules` is availability information, not a transport failure. A
  `401` needs a refreshed Earthdata token. Do not mark a run complete while
  `downloaded_without_mosaic` is nonzero.

## Documentation and Skill Changes

- Add `docs/mcp/ntl-download.md` with Conda/Codex stdio configuration, tool
  catalog, environment variables, progress behavior, and recovery guidance.
- Update root `README.md` and `packages/ntl_toolkit/README.md` with the second
  local MCP entry point.
- Update the global `ntl-gpt-project` skill with the routing/audit/progress
  rules above and a compact cross-reference to the local `ntl-download` MCP.
- Do not delete or modify the standalone global VNP46A2 skill.

## Verification

- Unit tests cover path confinement, dotenv precedence, credential redaction,
  tool schemas, sidecar/manifest parsing, VNP46A2 phase and retry arguments,
  and GEE request validation without live credentials.
- MCP stdio smoke tests initialize `ntl-download`, list tools, call environment
  validation, call VNP46A2 `plan`, and inspect a fixture manifest.
- A mocked GEE export verifies structured progress and no-overwrite artifact
  reservation. A mocked VNP46A2 subprocess verifies phase progress, sanitizing,
  and failure recovery.
- Live download execution is opt-in and is not required for automated tests.

## Non-Goals

- No Job Runtime, SQLite/PostgreSQL state, HTTP server, multi-user sharing, or
  remote task queue.
- No automatic OAuth flow. EasyGEE provides credential-safe authentication
  guidance and environment checks; the download MCP reports missing GEE setup.
- No migration or deletion of every legacy NTL-GPT tool in this change.
