# Local Stdio Download MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a local `ntl-download` stdio MCP for synchronous GEE raster exports and audited official VNP46A2 Earthdata HDF5 country downloads, with progress and recoverable manifests.

**Architecture:** `ntl-gis-core` stays network-independent. A sibling FastMCP adapter calls focused package modules for safe output paths, sanitized manifests, explicit GEE export, and VNP46A2 phase execution. NTL-GPT reuses those functions through wrappers instead of starting an MCP process.

**Tech Stack:** Python 3.11, FastMCP/MCP stdio, Pydantic v2, earthengine-api, geemap, h5py, GeoPandas/Rasterio, pytest, `NTL-GPT-Stable`.

## Global Constraints

- Local stdio only: no HTTP server, Job Runtime, database, or remote queue.
- Long calls remain synchronous, emit MCP progress, and write sanitized manifests.
- GEE credentials and `EARTHDATA_TOKEN` come only from process environment or `NTL_MCP_ENV_FILE`; never tool arguments, results, logs, or manifests.
- Relative paths resolve below captured `NTL_MCP_WORKDIR`; outputs reserve a suffix and never overwrite.
- GEE package code must not import Streamlit, LangChain, or `storage_manager`.
- Official VNP46A2 means only country-scale daily non-gap-filled `DNB_BRDF_Corrected_NTL`; preserve existing audit and retry semantics.
- Keep `C:\\Users\\27334\\.agents\\skills\\vnp46a2-official-h5-country-mosaic\\SKILL.md` unchanged.

---

### Task 1: Add Download Runtime and Explicit GEE Export Core

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/downloads.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/runtime/__init__.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/gee_download.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/core/__init__.py`
- Test: `packages/ntl_toolkit/tests/test_download_runtime.py`
- Test: `packages/ntl_toolkit/tests/test_gee_download_core.py`

**Interfaces:**
- Produces `DownloadProgress = Callable[[float, float | None, str], None]`.
- Produces `sanitize_download_text(text: str) -> str`, `resolve_download_output(raw: str, workdir: Path) -> Path`, `write_download_manifest(path: Path, payload: dict[str, Any]) -> Path`, and `read_download_manifest(path: Path) -> dict[str, Any]`.
- Produces `GeeDownloadRequest`, `validate_gee_request(request) -> None`, and `download_gee_raster(request, *, progress=None) -> ToolResult`.

- [ ] **Step 1: Write the failing runtime tests**

```python
def test_manifest_redacts_bearer_and_keeps_progress(tmp_path: Path) -> None:
    manifest = write_download_manifest(
        tmp_path / "run.json",
        {"phase": "download", "note": "Authorization: Bearer abc.def.ghi", "completed": 2},
    )
    payload = read_download_manifest(manifest)
    assert payload["note"] == "Authorization: Bearer <REDACTED>"
    assert payload["completed"] == 2


def test_download_output_reserves_existing_path(runtime_workspace: Path) -> None:
    first = resolve_download_output("outputs/export.tif", runtime_workspace)
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"existing")
    assert resolve_download_output("outputs/export.tif", runtime_workspace).name == "export_001.tif"
```

- [ ] **Step 2: Write the failing GEE request and mocked export tests**

```python
def test_gee_request_rejects_reverse_dates(tmp_path: Path) -> None:
    request = GeeDownloadRequest(
        dataset_id="NASA/VIIRS/002/VNP46A2",
        band="Gap_Filled_DNB_BRDF_Corrected_NTL",
        start_date="2026-04-21", end_date="2026-04-20",
        bbox=[34.0, 29.0, 35.0, 30.0], output=str(tmp_path / "out.tif"),
    )
    with pytest.raises(ValueError, match="end_date"):
        validate_gee_request(request)


def test_gee_export_reports_all_phases(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []
    monkeypatch.setattr(gee_download, "_initialize_ee", lambda project: fake_ee)
    monkeypatch.setattr(gee_download, "_export_image", fake_export_writing_tif)
    result = download_gee_raster(valid_request(tmp_path), progress=lambda _, __, msg: events.append(msg))
    assert result.status == "succeeded"
    assert events == ["initializing Earth Engine", "selecting imagery", "exporting GeoTIFF", "validating output", "completed"]
```

- [ ] **Step 3: Confirm RED**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_download_runtime.py packages/ntl_toolkit/tests/test_gee_download_core.py -q
```

Expected: collection fails because the new runtime/core modules are absent.

- [ ] **Step 4: Implement the minimal safe APIs**

```python
def sanitize_download_text(text: str) -> str:
    text = re.sub(r"(Authorization:\s*Bearer\s+)[^\s]+", r"\1<REDACTED>", text)
    return re.sub(r"\bBearer\s+[^\s]+", "Bearer <REDACTED>", text)


class GeeDownloadRequest(BaseModel):
    dataset_id: str
    band: str
    start_date: date
    end_date: date
    bbox: tuple[float, float, float, float]
    output: str
    reducer: Literal["first", "mean", "median", "mosaic"] = "first"
    scale: int = Field(default=500, ge=1, le=10000)
    crs: str = "EPSG:4326"
    project: str | None = None


def download_gee_raster(request: GeeDownloadRequest, *, progress: DownloadProgress | None = None) -> ToolResult:
    validate_gee_request(request)
    _report(progress, 0, 4, "initializing Earth Engine")
    ee = _initialize_ee(request.project)
    _report(progress, 1, 4, "selecting imagery")
    image = _materialize_image(ee, request)
    _report(progress, 2, 4, "exporting GeoTIFF")
    output = _export_image(image, request)
    _report(progress, 3, 4, "validating output")
    _validate_geotiff(output)
    _report(progress, 4, 4, "completed")
    return ToolResult.succeeded(
        tool="download_gee_raster", summary="Downloaded GEE raster.",
        outputs=[OutputArtifact(path=str(output), media_type="image/tiff")],
    )
```

Use end-exclusive `filterDate(start, end + 1 day)`, a WGS84 bbox AOI, delayed `ee`/`geemap` imports, and no OAuth call. Convert missing initialization to a failed `ToolResult` with `GEE_NOT_INITIALIZED` and an EasyGEE suggestion.

- [ ] **Step 5: Verify and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_download_runtime.py packages/ntl_toolkit/tests/test_gee_download_core.py packages/ntl_toolkit/tests/test_paths.py -q
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m py_compile packages/ntl_toolkit/src/ntl_toolkit/runtime/downloads.py packages/ntl_toolkit/src/ntl_toolkit/core/gee_download.py
git add packages/ntl_toolkit/src/ntl_toolkit/runtime/downloads.py packages/ntl_toolkit/src/ntl_toolkit/runtime/__init__.py packages/ntl_toolkit/src/ntl_toolkit/core/gee_download.py packages/ntl_toolkit/src/ntl_toolkit/core/__init__.py packages/ntl_toolkit/tests/test_download_runtime.py packages/ntl_toolkit/tests/test_gee_download_core.py
git commit -m "feat: add local download runtime and GEE core"
```

Expected: tests pass and compilation exits `0`.

### Task 2: Add Official VNP46A2 Earthdata Execution and Inspection

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/vnp46a2_download.py`
- Test: `packages/ntl_toolkit/tests/test_vnp46a2_download_core.py`

**Interfaces:**
- Consumes Task 1 and existing checked-in `tools/vnp46a2_official_h5/` scripts.
- Produces `Vnp46a2DownloadRequest`, `run_vnp46a2_download(request, *, progress=None) -> ToolResult`, and `inspect_vnp46a2_run(run_root) -> ToolResult`.

- [ ] **Step 1: Write failing phase and recovery tests**

```python
def test_vnp_full_mode_runs_all_phases(monkeypatch, tmp_path: Path) -> None:
    messages: list[str] = []
    monkeypatch.setattr(vnp46a2_download, "_run_phase", fake_successful_phase)
    result = run_vnp46a2_download(
        Vnp46a2DownloadRequest(
            start_date="2026-02-13", end_date="2026-02-14", countries=["ISR"],
            output_root=str(tmp_path / "runs"), phase="full", execution_mode="run",
        ),
        progress=lambda _, __, message: messages.append(message),
    )
    assert result.status == "succeeded"
    assert messages == ["prepare", "download", "mosaic", "audit", "completed"]


def test_inspect_vnp_run_exposes_exact_retry_targets(tmp_path: Path) -> None:
    write_fixture_audit(tmp_path, statuses=["mosaic_valid", "retry_download"])
    result = inspect_vnp46a2_run(tmp_path)
    assert result.metrics["retry_targets"] == ["ISR:2026-02-14"]
```

- [ ] **Step 2: Confirm RED**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vnp46a2_download_core.py -q
```

Expected: collection fails because `ntl_toolkit.core.vnp46a2_download` is absent.

- [ ] **Step 3: Implement phase-oriented subprocess execution**

```python
def run_vnp46a2_download(request: Vnp46a2DownloadRequest, *, progress: DownloadProgress | None = None) -> ToolResult:
    commands = _build_phase_commands(request)
    if request.execution_mode == "plan":
        return ToolResult.succeeded(
            tool="download_vnp46a2_official_h5_country",
            summary="Prepared VNP46A2 execution plan.", metrics={"commands": commands},
        )
    if "download" in request.phase_list and not os.getenv(request.token_env):
        return ToolResult.failed(
            tool="download_vnp46a2_official_h5_country",
            error=ToolError(
                code="EARTHDATA_TOKEN_MISSING", message=f"{request.token_env} is not configured.",
                suggestion="Set the token in NTL_MCP_ENV_FILE or the process environment.",
            ),
        )
    for index, phase in enumerate(request.phase_list, start=1):
        _report(progress, index - 1, len(request.phase_list), phase)
        outcome = _run_phase(phase, commands[phase], request.output_root)
        _write_phase_manifest(request.output_root, outcome)
        if outcome.returncode:
            return _failed_phase_result(outcome)
    _report(progress, len(request.phase_list), len(request.phase_list), "completed")
    return inspect_vnp46a2_run(request.run_root)
```

Preserve `plan`, `prepare`, `download`, `mosaic`, `audit`, `organize`, `full`, `targets`, `workers`, `download_timeout`, `no_gee_latest`, `force`, and `skip_pixel_scan`. Stream sanitized subprocess output through progress. Return failed/incomplete audit statuses rather than a false success; `no_granules` and validated `mosaic_all_nodata` remain terminal availability states.

- [ ] **Step 4: Verify and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_vnp46a2_download_core.py tests/test_official_vnp46a2_h5_country_tool.py -q
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m py_compile packages/ntl_toolkit/src/ntl_toolkit/core/vnp46a2_download.py
git add packages/ntl_toolkit/src/ntl_toolkit/core/vnp46a2_download.py packages/ntl_toolkit/tests/test_vnp46a2_download_core.py
git commit -m "feat: add official VNP46A2 download core"
```

Expected: mocked tests require neither an Earthdata token nor network access.

### Task 3: Expose `ntl-download` over Stdio

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/download.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/download_capabilities.json`
- Create: `mcp_servers/download_server.py`
- Modify: `packages/ntl_toolkit/pyproject.toml`
- Test: `packages/ntl_toolkit/tests/test_mcp_download.py`

**Interfaces:**
- Consumes Tasks 1-2 and FastMCP `Context.report_progress(progress, total, message)`.
- Produces `build_download_mcp() -> FastMCP`, console entry `ntl-download`, and four tools: `validate_download_environment`, `download_gee_raster`, `download_vnp46a2_official_h5_country`, `inspect_download_run`.

- [ ] **Step 1: Write failing sealed-catalog, progress, and stdio smoke tests**

```python
def test_download_catalog_is_sealed() -> None:
    tools = asyncio.run(build_download_mcp().list_tools())
    assert [tool.name for tool in tools] == [
        "validate_download_environment", "download_gee_raster",
        "download_vnp46a2_official_h5_country", "inspect_download_run",
    ]
    assert all(tool.inputSchema["additionalProperties"] is False for tool in tools)


def test_vnp_adapter_forwards_mcp_progress(monkeypatch, runtime_workspace: Path) -> None:
    events: list[tuple[float, float | None, str | None]] = []
    monkeypatch.setattr(download_adapter, "run_vnp46a2_download", fake_vnp_result)
    result = download_adapter._run_vnp_tool(FakeContext(events), valid_vnp_arguments(runtime_workspace))
    assert events[-1] == (4.0, 4.0, "completed")
    assert result["status"] == "succeeded"
```

- [ ] **Step 2: Confirm RED**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_mcp_download.py -q
```

Expected: collection fails because the download MCP adapter is absent.

- [ ] **Step 3: Implement the adapter and launcher**

```python
def build_download_mcp() -> FastMCP:
    load_runtime_environment()
    workdir = runtime_workdir()
    mcp = StrictFastMCP("ntl-download", instructions=_SERVER_INSTRUCTIONS)

    @mcp.tool(name="download_vnp46a2_official_h5_country", annotations=_WRITE_NEW, structured_output=True)
    def download_vnp46a2_official_h5_country(ctx: Context, **kwargs: Any) -> dict[str, Any]:
        request = _resolve_vnp_request(kwargs, workdir)
        result = run_vnp46a2_download(
            request, progress=lambda done, total, message: ctx.report_progress(done, total, message),
        )
        return _payload(result)

    return mcp
```

Copy the sealed-schema behavior from `gis_core.StrictFastMCP`, but exclude injected `Context` from client parameters. Publish `ntl://download/capabilities` and `ntl://schemas/result-v1`. The readiness tool reports token presence only as a boolean and initializes GEE only when asked, without OAuth. Add:

```toml
[project.scripts]
ntl-download = "ntl_toolkit.adapters.mcp.download:main"
```

The launcher must add only `packages/ntl_toolkit/src` to `sys.path` and must not print to stdout before MCP starts.

- [ ] **Step 4: Verify and commit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_mcp_download.py packages/ntl_toolkit/tests/test_download_runtime.py packages/ntl_toolkit/tests/test_gee_download_core.py packages/ntl_toolkit/tests/test_vnp46a2_download_core.py -q
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m py_compile packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/download.py mcp_servers/download_server.py
git add packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/download.py packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/download_capabilities.json mcp_servers/download_server.py packages/ntl_toolkit/pyproject.toml packages/ntl_toolkit/tests/test_mcp_download.py
git commit -m "feat: add local download MCP"
```

Expected: direct and subprocess stdio tests pass without live network access.

### Task 4: Document Local Use and Consolidate Project Skill Guidance

**Files:**
- Create: `docs/mcp/ntl-download.md`
- Modify: `README.md`
- Modify: `packages/ntl_toolkit/README.md`
- Modify: `C:\\Users\\27334\\.agents\\skills\\ntl-gpt-project\\SKILL.md`
- Test: `packages/ntl_toolkit/tests/test_download_documentation.py`

**Interfaces:**
- Consumes the Task 3 command and VNP46A2 audit contract.
- Produces copy-ready Codex local stdio config and a compact route in `ntl-gpt-project`.

- [ ] **Step 1: Write failing documentation and skill retrieval checks**

```python
def test_download_docs_configure_env_file_without_secret_value() -> None:
    text = (REPO_ROOT / "docs/mcp/ntl-download.md").read_text(encoding="utf-8")
    assert "ntl-download" in text
    assert "NTL_MCP_ENV_FILE" in text
    assert "EARTHDATA_TOKEN=<" not in text


def test_project_skill_routes_raw_country_vnp_to_official_h5() -> None:
    text = Path(r"C:\Users\27334\.agents\skills\ntl-gpt-project\SKILL.md").read_text(encoding="utf-8")
    assert "DNB_BRDF_Corrected_NTL" in text
    assert "downloaded_without_mosaic" in text
    assert "ntl-download" in text
```

- [ ] **Step 2: Confirm RED**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_download_documentation.py -q
```

Expected: fail because the MCP documentation and skill route are absent.

- [ ] **Step 3: Write docs and update the global project skill**

Use this exact configuration, with no credentials embedded:

```toml
[mcp_servers.ntl-download]
command = "C:/Users/27334/miniconda3/Scripts/conda.exe"
args = ["run", "-n", "NTL-GPT-Stable", "python", "D:/NTL-GPT-main/mcp_servers/download_server.py"]
env = { NTL_MCP_WORKDIR = "D:/NTL-GPT-data" }
```

Add this compact route to `ntl-gpt-project`:

```markdown
- `ntl-download`: local stdio GEE raster export and official VNP46A2 HDF5 country mosaics. It is synchronous but reports MCP progress and writes manifests; recover after interruption with `inspect_download_run` and retry only returned ISO3/date targets.
- Use official HDF5 only for explicit raw daily country raster requests. Require `DNB_BRDF_Corrected_NTL`, valid HDF5, completed mosaics, and no `downloaded_without_mosaic` audit state before declaring success.
```

Keep the standalone VNP46A2 skill untouched. Explain that EasyGEE handles GEE readiness, authentication planning, catalog search, quota, and preview.

- [ ] **Step 4: Verify, commit repository docs, and report the external skill edit**

```powershell
$env:PYTHONPATH = (Resolve-Path 'packages\ntl_toolkit\src').Path
& 'C:\Users\27334\miniconda3\Scripts\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_download_documentation.py packages/ntl_toolkit/tests/test_mcp_download.py -q
python -c "from pathlib import Path; [Path(p).read_text(encoding='utf-8') for p in ['README.md', 'packages/ntl_toolkit/README.md', 'docs/mcp/ntl-download.md', r'C:\\Users\\27334\\.agents\\skills\\ntl-gpt-project\\SKILL.md']]; print('utf8_ok')"
git diff --check
git add docs/mcp/ntl-download.md README.md packages/ntl_toolkit/README.md packages/ntl_toolkit/tests/test_download_documentation.py
git commit -m "docs: document local download MCP"
```

Expected: checks pass. The global project skill is outside the repository; report its path and verification result. Do not delete the old standalone VNP46A2 skill.

## Final Verification

- [ ] Run `$env:PYTHONPATH = (Resolve-Path 'packages\\ntl_toolkit\\src').Path; & 'C:\\Users\\27334\\miniconda3\\Scripts\\conda.exe' run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests -q`.
- [ ] Run the direct stdio initialize/list/call smoke test and confirm no launcher output reaches stdout.
- [ ] Run `git diff c7d9a96..HEAD --stat` and `git diff --check c7d9a96..HEAD`.
- [ ] Confirm the standalone global VNP46A2 skill still exists and remains unchanged.

