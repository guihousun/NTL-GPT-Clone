# NTL Earthdata Tools MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `ntl-earthdata-tools` stdio MCP service for official NASA CMR/Earthdata search, HDF inspection, durable downloads, VNP46A2 country mosaics, and VJ DNB preprocessing.

**Architecture:** Move reusable Earthdata, HDF, VNP46A2, and VJ DNB logic into framework-neutral `ntl_toolkit.core.earthdata` modules. Expose synchronous discovery/inspection tools and submit long operations to the persistent Job Runtime; retain existing NTL-GPT LangChain tool names through thin adapters after parity tests pass.

**Tech Stack:** Python 3.11, Pydantic 2, FastMCP/Python MCP SDK, NASA CMR JSON API, `curl`, h5py, GeoPandas, Rasterio, NumPy, OSMnx, Earth Engine API, pytest 8, the shared SQLite Job Runtime.

## Global Constraints

- Complete `2026-07-11-ntl-job-runtime-implementation.md` before this plan.
- Keep credentials in process environment or `NTL_MCP_ENV_FILE`; MCP parameters and results must never contain token values.
- Use official NASA CMR/Earthdata HDF5 for country-scale non-gap-filled VNP46A2 `DNB_BRDF_Corrected_NTL` rasters.
- Use GEE only for latest-date clamping unless the caller sets `no_gee_latest=true` with an authoritative availability decision.
- Relative paths resolve under `NTL_MCP_WORKDIR`; absolute local paths remain supported for external MCP clients.
- Never delete or overwrite user files. Retry operations target only explicit failed country-days.
- `no_granules` is an availability state, not a transport failure.
- A complete VNP46A2 run requires `downloaded_without_mosaic=0`; `mosaic_all_nodata` requires valid HDF5, successful mosaic, and pixel scan evidence.
- Preserve the existing LangChain names `official_vnp46a2_h5_country_mosaic_tool`, `official_vj_dnb_fullchain_tool`, `official_vj_dnb_preprocess_tool`, and `convert_vj102_vj103_precise_to_tif_tool`.
- Use `conda run -n NTL-GPT-Stable` for validation. Live Earthdata tests are opt-in with `pytest -m earthdata_live`.
- Add package dependencies `h5py>=3.10,<4`, `osmnx>=2,<3`, and `earthengine-api>=1.6,<2`; keep `curl` as an externally validated executable rather than a Python dependency.

---

## Target File Structure

```text
packages/ntl_toolkit/src/ntl_toolkit/
├── schemas/earthdata.py
├── core/earthdata/
│   ├── __init__.py
│   ├── cmr.py
│   ├── hdf.py
│   ├── download.py
│   ├── vnp46a2.py
│   └── vj_dnb.py
└── adapters/
    ├── langchain/earthdata.py
    └── mcp/
        ├── earthdata.py
        └── earthdata_capabilities.json
mcp_servers/earthdata_tools_server.py
packages/ntl_toolkit/tests/
├── test_earthdata_schemas.py
├── test_earthdata_cmr.py
├── test_earthdata_hdf.py
├── test_earthdata_jobs.py
├── test_vnp46a2_country_pipeline.py
├── test_vj_dnb_jobs.py
├── test_mcp_earthdata.py
└── test_langchain_earthdata_parity.py
docs/mcp/ntl-earthdata-tools.md
```

### Task 1: Define Earthdata Requests and Environment Contract

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/schemas/earthdata.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/schemas/__init__.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/runtime/environment.py`
- Create: `packages/ntl_toolkit/tests/test_earthdata_schemas.py`

**Interfaces:**
- Consumes: `JobRecord`, `ToolResult`, runtime environment loading.
- Produces: request models and `earthdata_token(env_name="EARTHDATA_TOKEN") -> str | None` used by all Earthdata handlers.

- [ ] **Step 1: Write failing request validation tests**

```python
def test_vnp_request_normalizes_iso3_and_targets() -> None:
    request = VNP46A2CountryMosaicRequest(
        start_date="2026-02-13",
        end_date="2026-02-14",
        countries=["isr"],
        targets=["isr:2026-02-13"],
        output_root="outputs/israel",
    )
    assert request.countries == ["ISR"]
    assert request.targets == ["ISR:2026-02-13"]


def test_request_models_do_not_accept_token_values() -> None:
    fields = VNP46A2CountryMosaicRequest.model_fields
    assert "token" not in fields
    assert "authorization" not in fields
    assert fields["token_env"].default == "EARTHDATA_TOKEN"
```

- [ ] **Step 2: Run tests and confirm missing models**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_earthdata_schemas.py -q`

Expected: collection fails because Earthdata schemas are absent.

- [ ] **Step 3: Implement exact request models**

```python
class GranuleSearchRequest(BaseModel):
    short_name: str
    start_date: date
    end_date: date
    bbox: tuple[float, float, float, float] | None = None
    page_size: int = Field(default=200, ge=1, le=2000)


class GranuleDownloadRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    output_root: str
    token_env: str = "EARTHDATA_TOKEN"
    timeout_sec: int = Field(default=600, ge=60, le=1800)


class VNP46A2CountryMosaicRequest(BaseModel):
    start_date: date
    end_date: date
    countries: list[str] = Field(min_length=1)
    output_root: str
    targets: list[str] = Field(default_factory=list)
    workers: int = Field(default=4, ge=1, le=8)
    download_timeout: int = Field(default=600, ge=60, le=1800)
    no_gee_latest: bool = False
    package_results: bool = True
    token_env: str = "EARTHDATA_TOKEN"


class CoverageAuditRow(BaseModel):
    iso3: str
    date: date
    audit_status: str
    h5_count: int = 0
    valid_h5_count: int = 0
    mosaic_file: str = ""
    valid_pixel_probe: int | None = None


class CoverageAudit(BaseModel):
    complete: bool
    rows: list[CoverageAuditRow]
    status_counts: dict[str, int]
```

Also define `VJDNBPreprocessRequest`, `HDFInspectRequest`, and validators for date order, bbox order, ISO3, target membership, environment variable names, and output paths.

- [ ] **Step 4: Add credential lookup without logging values and run tests**

`earthdata_token` checks `os.environ` after `load_runtime_environment()` and returns the value only to the core download function. Tests assert missing token returns `None` and monkeypatched tokens never appear in serialized models.

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_earthdata_schemas.py -q`

Expected: all schema and credential-isolation tests pass.

- [ ] **Step 5: Commit Earthdata contracts**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/schemas/earthdata.py packages/ntl_toolkit/src/ntl_toolkit/schemas/__init__.py packages/ntl_toolkit/src/ntl_toolkit/runtime/environment.py packages/ntl_toolkit/tests/test_earthdata_schemas.py
git commit -m "feat: define Earthdata request contracts"
```

### Task 2: Migrate CMR Search, Availability, HDF Inspection, and Download

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/__init__.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/cmr.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/hdf.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/download.py`
- Create: `packages/ntl_toolkit/tests/test_earthdata_cmr.py`
- Create: `packages/ntl_toolkit/tests/test_earthdata_hdf.py`

**Interfaces:**
- Consumes: Task 1 request models, `JobContext`, `run_cancellable_subprocess`.
- Produces: `search_granules`, `check_product_availability`, `inspect_hdf_product`, and `download_granules_handler`.

- [ ] **Step 1: Write failing fixture-driven CMR and synthetic-HDF tests**

```python
def test_search_granules_parses_cmr_fixture(monkeypatch, cmr_fixture) -> None:
    monkeypatch.setattr(cmr, "fetch_json", lambda url: cmr_fixture)
    records = cmr.search_granules(GranuleSearchRequest(
        short_name="VNP46A2",
        start_date=date(2026, 2, 13),
        end_date=date(2026, 2, 13),
    ))
    assert records[0].producer_granule_id.startswith("VNP46A2.A2026044")
    assert records[0].download_url.startswith("https://")


def test_inspect_hdf_rejects_gap_filled_substitute(tmp_path: Path) -> None:
    path = make_hdf(tmp_path, dataset="Gap_Filled_DNB_BRDF_Corrected_NTL")
    result = inspect_hdf_product(path, required_dataset="DNB_BRDF_Corrected_NTL")
    assert result.status == "failed"
    assert result.error.code == "HDF_DATASET_MISSING"
```

- [ ] **Step 2: Run tests and verify missing core modules**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_earthdata_cmr.py packages/ntl_toolkit/tests/test_earthdata_hdf.py -q`

Expected: collection fails because `ntl_toolkit.core.earthdata` is absent.

- [ ] **Step 3: Port and generalize canonical implementations**

Port `GranuleRecord`, URL construction, payload parsing, acquisition-day grouping, download-link selection, HDF5 signature checks, bearer redaction, and curl download behavior from `tools/vnp46a2_official_h5/cmr_client.py`. Use injected `fetch_json` in unit tests and never include authorization headers in exceptions.

```python
records = parse_granules_payload(fetch_json(build_cmr_query_url(request)))
records.sort(key=lambda item: (item.time_start, item.producer_granule_id))
return records
```

Implement these exact functions: `search_granules(request: GranuleSearchRequest) -> list[GranuleRecord]`, `check_product_availability(short_name: str, start_date: date, end_date: date) -> ToolResult`, `inspect_hdf_product(path: Path, required_dataset: str | None = None) -> ToolResult`, and `download_granules_handler(context: JobContext, request: dict[str, Any]) -> ToolResult`. Search results are sorted by acquisition time and granule id; the handler reserves each output path before starting curl and registers only HDF-signature-valid files.

- [ ] **Step 4: Run offline CMR/HDF tests including 401 and truncated HDF cases**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_earthdata_cmr.py packages/ntl_toolkit/tests/test_earthdata_hdf.py -q`

Expected: fixture search, empty availability, 401 classification, HDF signature, required dataset, shape, and tiny-read validation tests pass.

- [ ] **Step 5: Commit the common Earthdata core**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/earthdata packages/ntl_toolkit/tests/test_earthdata_cmr.py packages/ntl_toolkit/tests/test_earthdata_hdf.py
git commit -m "feat: add CMR and HDF Earthdata core"
```

### Task 3: Migrate the VNP46A2 Country Pipeline into Shared Core

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/vnp46a2.py`
- Create: `packages/ntl_toolkit/tests/test_vnp46a2_country_pipeline.py`
- Modify: `tools/vnp46a2_official_h5_country_tool.py`
- Modify: `tools/vnp46a2_official_h5/*.py`

**Interfaces:**
- Consumes: CMR/HDF core, Job Runtime, `VNP46A2CountryMosaicRequest`.
- Produces: `plan_vnp46a2_country_mosaic(request)`, `vnp46a2_country_mosaic_handler(context, request)`, and reusable phase functions.

- [ ] **Step 1: Write failing parity tests against the canonical scripts**

```python
def test_plan_contains_audited_phase_order(tmp_path: Path) -> None:
    request = make_request(tmp_path, countries=["ISR"])
    plan = plan_vnp46a2_country_mosaic(request)
    assert plan.phases == ["prepare", "download", "mosaic", "audit", "organize"]
    assert plan.band == "DNB_BRDF_Corrected_NTL"


def test_audit_marks_download_without_mosaic_incomplete(synthetic_run: Path) -> None:
    add_valid_hdf(synthetic_run, "ISR", "2026-02-13")
    audit = audit_country_days(synthetic_run, countries=["ISR"], dates=[date(2026, 2, 13)])
    assert audit.rows[0].audit_status == "downloaded_without_mosaic"
    assert audit.complete is False
```

- [ ] **Step 2: Run tests and confirm shared pipeline APIs are missing**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vnp46a2_country_pipeline.py -q`

Expected: collection fails because `vnp46a2.py` is absent.

- [ ] **Step 3: Move phase logic behind explicit library functions**

Port country specs, OSM 0.001-degree boundary preparation, date clamping, country-day CMR search, HDF validation, tile conversion, dateline handling, country clipping, audit, and package indexing from `tools/vnp46a2_official_h5`. Preserve exact audit labels.

```python
PHASES = ("prepare", "download", "mosaic", "audit", "organize")
for phase_index, phase in enumerate(PHASES, start=1):
    context.raise_if_cancelled()
    context.update_progress(current=phase_index - 1, total=len(PHASES), phase=phase, message=f"Starting {phase}")
```

Implement these exact functions: `prepare_boundaries(context: JobContext, request: VNP46A2CountryMosaicRequest) -> list[JobOutput]`, `download_country_days(context: JobContext, request: VNP46A2CountryMosaicRequest) -> list[JobOutput]`, `mosaic_country_days(context: JobContext, request: VNP46A2CountryMosaicRequest) -> list[JobOutput]`, `audit_country_days(run_root: Path, *, countries: list[str], dates: list[date], pixel_scan: bool = True) -> CoverageAudit`, `package_country_results(run_root: Path, package_root: Path, *, copy: bool = False) -> list[JobOutput]`, and `vnp46a2_country_mosaic_handler(context: JobContext, request: dict[str, Any]) -> ToolResult`. The handler advances progress by country-day and phase, checks cancellation between every country-day, and fails completion when the audit reports any `downloaded_without_mosaic` row.

Convert existing scripts into CLI adapters that parse arguments and call these functions; they no longer contain duplicate domain implementations. Convert `tools/vnp46a2_official_h5_country_tool.py` into a LangChain adapter that plans synchronously and submits through the shared runner for background execution.

- [ ] **Step 4: Run synthetic pipeline and existing runtime parity tests**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vnp46a2_country_pipeline.py tests/test_official_vnp46a2_h5_country_tool.py -q`

Expected: dateline, non-gap-filled band, retry targets, no-granules, all-nodata, no-overwrite, audit gate, package index, and legacy tool schema tests pass without network access.

- [ ] **Step 5: Commit VNP46A2 shared-core migration**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/vnp46a2.py packages/ntl_toolkit/tests/test_vnp46a2_country_pipeline.py tools/vnp46a2_official_h5 tools/vnp46a2_official_h5_country_tool.py
git commit -m "feat: migrate VNP46A2 country pipeline to shared core"
```

### Task 4: Add VJ DNB Job Handlers and LangChain Parity

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/vj_dnb.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/langchain/earthdata.py`
- Create: `packages/ntl_toolkit/tests/test_vj_dnb_jobs.py`
- Create: `packages/ntl_toolkit/tests/test_langchain_earthdata_parity.py`
- Modify: `tools/official_vj_dnb_pipeline_tool.py`
- Modify: `tools/official_vj_dnb_preprocess_tool.py`

**Interfaces:**
- Consumes: Job Runtime, CMR/download core, existing VJ conversion logic.
- Produces: `vj_dnb_preprocess_handler`, `convert_vj102_vj103_to_geotiff`, and unchanged legacy StructuredTool names.

- [ ] **Step 1: Write failing handler and parity tests**

```python
def test_vj_handler_registers_daily_outputs(fake_vj_inputs, job_context) -> None:
    result = vj_dnb_preprocess_handler(job_context, fake_request(fake_vj_inputs))
    assert result.status == "succeeded"
    assert all(output.path.endswith(".tif") for output in result.outputs)


def test_legacy_tool_names_remain_stable() -> None:
    assert official_vj_dnb_fullchain_tool.name == "official_vj_dnb_fullchain_tool"
    assert official_vj_dnb_preprocess_tool.name == "official_vj_dnb_preprocess_tool"
    assert convert_vj102_vj103_precise_to_tif_tool.name == "convert_vj102_vj103_precise_to_tif_tool"
```

- [ ] **Step 2: Run tests and verify handler absence**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vj_dnb_jobs.py packages/ntl_toolkit/tests/test_langchain_earthdata_parity.py -q`

Expected: collection fails because shared VJ handlers and adapters are missing.

- [ ] **Step 3: Move orchestration into shared handlers**

Port source selection, CMR query, official download, QA modes, VJ102/VJ103 conversion, daily output discovery, and manifest generation. Use `JobContext.update_progress`, `run_cancellable_subprocess`, and `JobContext.add_output`. Keep GIF rendering outside this Earthdata service; it remains a separate local visualization tool.

```python
typed_request = VJDNBPreprocessRequest.model_validate(request)
context.update_progress(current=0, total=None, phase="query", message="Querying official VJ DNB granules")
result = convert_vj102_vj103_to_geotiff(typed_request)
for output in result.outputs:
    context.add_output(Path(output.path), media_type=output.media_type, role=output.role)
return result
```

Implement `convert_vj102_vj103_to_geotiff(request: VJDNBPreprocessRequest) -> ToolResult` and `vj_dnb_preprocess_handler(context: JobContext, request: dict[str, Any]) -> ToolResult`. Conversion returns a `ToolResult` synchronously for explicit local inputs; the job handler performs network query/download and calls the converter, updating progress once per acquisition day.

Legacy LangChain adapters resolve thread paths, preserve public schemas, and call shared core or submit handlers. They do not call MCP.

- [ ] **Step 4: Run VJ tests plus existing tool import checks**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vj_dnb_jobs.py packages/ntl_toolkit/tests/test_langchain_earthdata_parity.py tests/test_runtime_governance.py -q`

Expected: shared handler, cancellation, output registration, path isolation, and legacy-name tests pass.

- [ ] **Step 5: Commit VJ shared-core migration**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/earthdata/vj_dnb.py packages/ntl_toolkit/src/ntl_toolkit/adapters/langchain/earthdata.py packages/ntl_toolkit/tests/test_vj_dnb_jobs.py packages/ntl_toolkit/tests/test_langchain_earthdata_parity.py tools/official_vj_dnb_pipeline_tool.py tools/official_vj_dnb_preprocess_tool.py
git commit -m "feat: add shared VJ DNB Earthdata handlers"
```

### Task 5: Build the `ntl-earthdata-tools` MCP Adapter

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/earthdata.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/earthdata_capabilities.json`
- Create: `mcp_servers/earthdata_tools_server.py`
- Modify: `packages/ntl_toolkit/pyproject.toml`
- Create: `packages/ntl_toolkit/tests/test_mcp_earthdata.py`

**Interfaces:**
- Consumes: all Earthdata core functions and `PersistentJobRunner`.
- Produces: `build_earthdata_mcp() -> FastMCP`, console entry point `ntl-earthdata-tools`, 12 fixed MCP tools, and three resources.

- [ ] **Step 1: Write failing catalog and stdio tests**

```python
EXPECTED_TOOLS = [
    "validate_environment",
    "search_granules",
    "check_product_availability",
    "inspect_hdf_product",
    "submit_granule_download",
    "plan_vnp46a2_country_mosaic",
    "submit_vnp46a2_country_mosaic",
    "submit_vj_dnb_preprocess",
    "convert_vj102_vj103_to_geotiff",
    "get_job_status",
    "cancel_job",
    "list_job_outputs",
]


def test_earthdata_tool_catalog_is_fixed() -> None:
    server = build_earthdata_mcp()
    assert [tool.name for tool in asyncio.run(server.list_tools())] == EXPECTED_TOOLS
```

- [ ] **Step 2: Run tests and verify adapter absence**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_mcp_earthdata.py -q`

Expected: collection fails because `build_earthdata_mcp` is missing.

- [ ] **Step 3: Implement strict MCP tools and resources**

Reuse `StrictFastMCP` by moving it from `gis_core.py` to `adapters/mcp/common.py`, updating GIS imports, and testing both servers. Register read-only annotations for search/status/inspect and open-world write annotations for submit/cancel tools. Instantiate one store and runner per server process, register `download_granules`, `vnp46a2_country_mosaic`, and `vj_dnb_preprocess` handlers. Add `h5py>=3.10,<4`, `osmnx>=2,<3`, and `earthengine-api>=1.6,<2` to `pyproject.toml`, include `earthdata_capabilities.json` as package data, add the `earthdata_live` pytest marker, and expose:

```text
ntl://earthdata/capabilities
ntl://schemas/result-v1
ntl://schemas/job-v1
```

`submit_*` returns the queued `JobRecord` immediately. `cancel_job` returns the updated record. `list_job_outputs` returns only registered paths and media types, never scanned arbitrary directories.

- [ ] **Step 4: Run stdio smoke and wheel-entry-point tests**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_mcp_gis_core.py packages/ntl_toolkit/tests/test_mcp_earthdata.py -q`

Expected: both MCP servers initialize over stdio, schemas reject extra fields, resources list in deterministic order, queued job status survives a second store instance, and wheel metadata includes `ntl-earthdata-tools = ntl_toolkit.adapters.mcp.earthdata:main`.

- [ ] **Step 5: Commit the Earthdata MCP server**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp packages/ntl_toolkit/pyproject.toml packages/ntl_toolkit/tests/test_mcp_gis_core.py packages/ntl_toolkit/tests/test_mcp_earthdata.py mcp_servers/earthdata_tools_server.py
git commit -m "feat: add ntl-earthdata-tools MCP server"
```

### Task 6: Document, Configure, and Validate the Complete Service

**Files:**
- Create: `docs/mcp/ntl-earthdata-tools.md`
- Modify: `packages/ntl_toolkit/README.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `check_env.py`

**Interfaces:**
- Consumes: finished Job Runtime and Earthdata MCP.
- Produces: reproducible installation/configuration instructions and offline/live validation gates.

- [ ] **Step 1: Add failing environment and documentation assertions**

```python
def test_earthdata_environment_reports_token_presence_without_value(monkeypatch) -> None:
    monkeypatch.setenv("EARTHDATA_TOKEN", "secret-value")
    payload = validate_earthdata_environment()
    text = json.dumps(payload)
    assert payload["metrics"]["earthdata_token_configured"] is True
    assert "secret-value" not in text
```

- [ ] **Step 2: Run complete offline suite before documentation**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests tests/test_official_vnp46a2_h5_country_tool.py tests/test_runtime_governance.py -q`

Expected: all implemented tests pass except the new documentation/environment assertions.

- [ ] **Step 3: Document exact local configuration**

Document this Codex MCP shape without embedding a token:

```toml
[mcp_servers.ntl-earthdata-tools]
command = "C:\\Users\\27334\\miniconda3\\Scripts\\conda.exe"
args = ["run", "-n", "NTL-GPT-Stable", "python", "D:\\NTL-GPT-main\\mcp_servers\\earthdata_tools_server.py"]
env = { NTL_MCP_WORKDIR = "C:\\Users\\27334\\NTL-GPT-MCP", NTL_MCP_ENV_FILE = "D:\\NTL-GPT-main\\.env" }
```

Update `.env.example` descriptions for `EARTHDATA_TOKEN`, `NTL_MCP_JOB_DB`, and `NTL_MCP_JOB_WORKERS`. Update `check_env.py` to report configured/not-configured status only.

- [ ] **Step 4: Run offline suite, package build, and opt-in live probes**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests tests/test_official_vnp46a2_h5_country_tool.py tests/test_runtime_governance.py -q`

Run: `conda run -n NTL-GPT-Stable python -m pip wheel --no-deps --wheel-dir .tmp-wheel packages/ntl_toolkit`

Optional live validation when credentials and network are explicitly available:

`conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests -m earthdata_live -q`

Expected: offline suite and wheel build pass. Live probe searches one historical VNP46A2 day and downloads at most one granule into a temporary directory; it does not run a country matrix.

- [ ] **Step 5: Commit documentation and environment checks**

```powershell
git add docs/mcp/ntl-earthdata-tools.md packages/ntl_toolkit/README.md README.md .env.example check_env.py
git commit -m "docs: document ntl-earthdata-tools setup"
```

### Task 7: Register the Server and Perform End-to-End Acceptance

**Files:**
- Modify: no tracked source files unless acceptance exposes a defect.

**Interfaces:**
- Consumes: `mcp_servers/earthdata_tools_server.py`, local `.env`, Codex MCP configuration.
- Produces: a working global `ntl-earthdata-tools` registration and an acceptance record in the final implementation report.

- [ ] **Step 1: Install the package in editable mode**

Run: `conda run -n NTL-GPT-Stable python -m pip install -e D:\NTL-GPT-main\packages\ntl_toolkit`

Expected: installation succeeds and `import ntl_toolkit` resolves to `D:\NTL-GPT-main\packages\ntl_toolkit\src\ntl_toolkit`.

- [ ] **Step 2: Register the stdio server with absolute paths**

Run through the Codex MCP CLI using the exact executable available in the current Codex installation. Set `NTL_MCP_WORKDIR=C:\Users\27334\NTL-GPT-MCP` and `NTL_MCP_ENV_FILE=D:\NTL-GPT-main\.env`; do not copy the token into Codex config.

Expected: `codex mcp get ntl-earthdata-tools` reports enabled stdio transport and masked environment values.

- [ ] **Step 3: Run a credential-safe stdio acceptance sequence**

Initialize the server, list tools/resources, call `validate_environment`, search one historical VNP46A2 day, submit a synthetic local handler job in test mode, poll it to terminal status, and list its output.

Expected: fixed 12-tool catalog, three resources, no credential values in responses, durable job status, and a registered output path.

- [ ] **Step 4: Verify repository and server boundaries**

Run: `git diff --check`

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests tests/test_official_vnp46a2_h5_country_tool.py tests/test_runtime_governance.py -q`

Expected: no whitespace errors, no generated data or credentials in Git status, and all offline tests pass.

- [ ] **Step 5: Commit only acceptance-driven fixes, if any**

If no source defect was found, create no commit. If a defect was fixed, stage only the affected source and its regression test, then commit with `fix: harden Earthdata MCP acceptance`.
