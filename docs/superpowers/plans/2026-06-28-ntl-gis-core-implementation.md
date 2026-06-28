# NTL GIS Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-ready `ntl-gis-core` stdio MCP server and migrate the matching NTL-GPT LangChain tools onto one shared Python core without changing current NTL-GPT behavior.

**Architecture:** Add an installable `ntl_toolkit` package under `packages/` with framework-free schemas, runtime path handling, vector/raster/NTL core functions, and separate LangChain and FastMCP adapters. Keep the existing public tool names in `tools/`, expose 16 atomic MCP tools from `mcp_servers/gis_core_server.py`, and migrate each legacy wrapper only after parity tests pass.

**Tech Stack:** Python 3.11, Pydantic 2, FastMCP/Python MCP SDK, LangChain StructuredTool adapters, GeoPandas, Rasterio, Shapely, PyProj, NumPy, Pandas, SciPy, pytest.

---

## Scope Boundary

This plan implements only `ntl-gis-core`. It deliberately does not implement GEE network tools, Earthdata downloads, or the persistent long-running job runner. The shared result and job schemas are introduced now; the SQLite job executor is added in the later `ntl-gee-tools` plan when a tool first needs it.

## Target File Structure

```text
packages/ntl_toolkit/
├── pyproject.toml
├── README.md
├── src/ntl_toolkit/
│   ├── __init__.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── errors.py
│   │   ├── jobs.py
│   │   └── results.py
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── environment.py
│   │   └── paths.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── vector.py
│   │   ├── raster.py
│   │   └── ntl.py
│   └── adapters/
│       ├── __init__.py
│       ├── langchain/
│       │   ├── __init__.py
│       │   ├── composite.py
│       │   ├── inspection.py
│       │   ├── raster_stats.py
│       │   └── temporal.py
│       └── mcp/
│           ├── __init__.py
│           └── gis_core.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    ├── test_langchain_parity.py
    ├── test_mcp_gis_core.py
    ├── test_ntl_core.py
    ├── test_paths.py
    ├── test_raster_core.py
    ├── test_results.py
    └── test_vector_core.py

mcp_servers/
└── gis_core_server.py

evaluations/
└── ntl_gis_core.xml
```

## Task 1: Scaffold the Installable Package

**Files:**
- Create: `packages/ntl_toolkit/pyproject.toml`
- Create: `packages/ntl_toolkit/README.md`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/__init__.py`
- Create: package `__init__.py` files shown above
- Modify: `environment.yml`
- Test: `packages/ntl_toolkit/tests/test_package_import.py`

- [ ] **Step 1: Write the failing package import test**

```python
def test_package_exposes_version() -> None:
    import ntl_toolkit

    assert ntl_toolkit.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the test and verify the package does not exist**

Run:

```powershell
python -m pytest packages/ntl_toolkit/tests/test_package_import.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ntl_toolkit'`.

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ntl-toolkit"
version = "0.1.0"
description = "Shared GIS and nighttime-light execution core for NTL-GPT and MCP clients"
requires-python = ">=3.11,<3.13"
dependencies = [
  "mcp>=1.9,<2",
  "pydantic>=2.7,<3",
  "numpy>=1.26,<3",
  "pandas>=2.2,<3",
  "geopandas>=0.14,<2",
  "rasterio>=1.3,<2",
  "shapely>=2,<3",
  "pyproj>=3.6,<4",
  "scipy>=1.11,<2",
  "python-dotenv>=1,<2",
]

[project.optional-dependencies]
test = ["pytest>=8,<9"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Add the package version and empty package modules**

```python
# packages/ntl_toolkit/src/ntl_toolkit/__init__.py
__version__ = "0.1.0"
```

Create empty `__init__.py` files in `schemas`, `runtime`, `core`, `adapters`, `adapters/langchain`, and `adapters/mcp`.

- [ ] **Step 5: Add MCP and pytest to the supported Conda environment**

Under the existing `pip:` section in `environment.yml`, add:

```yaml
      - mcp>=1.9,<2
      - pytest>=8,<9
      - -e ./packages/ntl_toolkit
```

- [ ] **Step 6: Install the package in editable mode and rerun the test**

Run:

```powershell
python -m pip install -e "packages/ntl_toolkit[test]"
python -m pytest packages/ntl_toolkit/tests/test_package_import.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit the scaffold**

```powershell
git add environment.yml packages/ntl_toolkit
git commit -m "Scaffold shared NTL toolkit package"
```

## Task 2: Define Stable Results, Errors, and Job Schemas

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/schemas/errors.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/schemas/results.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/schemas/jobs.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/schemas/__init__.py`
- Test: `packages/ntl_toolkit/tests/test_results.py`

- [ ] **Step 1: Write failing schema tests**

```python
from ntl_toolkit.schemas import OutputArtifact, ToolError, ToolResult


def test_success_result_serializes_stable_schema() -> None:
    result = ToolResult.succeeded(
        tool="inspect_raster",
        summary="Raster inspected.",
        outputs=[OutputArtifact(path="D:/data/a.tif", media_type="image/tiff", role="input")],
        metrics={"width": 10, "height": 20},
    )
    payload = result.model_dump(mode="json")
    assert payload["schema"] == "ntl.tool.result.v1"
    assert payload["status"] == "succeeded"
    assert payload["error"] is None


def test_failure_result_keeps_actionable_error() -> None:
    result = ToolResult.failed(
        tool="inspect_raster",
        error=ToolError(
            code="INPUT_NOT_FOUND",
            message="Raster input does not exist.",
            details={"path": "D:/missing.tif"},
            suggestion="Check the path.",
        ),
    )
    assert result.status == "failed"
    assert result.error.code == "INPUT_NOT_FOUND"
```

- [ ] **Step 2: Run the tests and verify imports fail**

Run:

```powershell
python -m pytest packages/ntl_toolkit/tests/test_results.py -v
```

Expected: FAIL because the schema classes are not defined.

- [ ] **Step 3: Implement the error and result schemas**

```python
# schemas/errors.py
from typing import Any
from pydantic import BaseModel, Field


class ToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    suggestion: str | None = None
```

```python
# schemas/results.py
from typing import Any, Literal
from pydantic import BaseModel, Field
from .errors import ToolError


class OutputArtifact(BaseModel):
    path: str
    media_type: str
    role: str = "primary"


class ToolResult(BaseModel):
    schema: Literal["ntl.tool.result.v1"] = "ntl.tool.result.v1"
    status: Literal["succeeded", "failed", "cancelled"]
    tool: str
    summary: str
    outputs: list[OutputArtifact] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: ToolError | None = None
    job_id: str | None = None

    @classmethod
    def succeeded(cls, *, tool: str, summary: str, outputs=None, metrics=None, warnings=None):
        return cls(
            status="succeeded",
            tool=tool,
            summary=summary,
            outputs=list(outputs or []),
            metrics=dict(metrics or {}),
            warnings=list(warnings or []),
        )

    @classmethod
    def failed(cls, *, tool: str, error: ToolError, summary: str | None = None):
        return cls(status="failed", tool=tool, summary=summary or error.message, error=error)
```

- [ ] **Step 4: Define job models without implementing the runner**

```python
# schemas/jobs.py
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    schema: Literal["ntl.job.v1"] = "ntl.job.v1"
    job_id: str
    tool: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime
    request: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
```

Export all four classes from `schemas/__init__.py`.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
python -m pytest packages/ntl_toolkit/tests/test_results.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/schemas packages/ntl_toolkit/tests/test_results.py
git commit -m "Define NTL tool result schemas"
```

## Task 3: Implement Environment Loading and Non-Overwriting Paths

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/environment.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/paths.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/runtime/__init__.py`
- Test: `packages/ntl_toolkit/tests/test_paths.py`

- [ ] **Step 1: Write failing Windows and Unicode path tests**

```python
from pathlib import Path
from ntl_toolkit.runtime.paths import resolve_local_path, reserve_output_path


def test_relative_path_uses_configured_workdir(tmp_path: Path) -> None:
    workdir = tmp_path / "专业数据"
    workdir.mkdir()
    assert resolve_local_path("夜间灯光/a.tif", workdir) == workdir / "夜间灯光" / "a.tif"


def test_existing_output_gets_numeric_suffix(tmp_path: Path) -> None:
    output = tmp_path / "result.tif"
    output.write_bytes(b"existing")
    assert reserve_output_path(output).name == "result_001.tif"


def test_existing_numbered_outputs_increment(tmp_path: Path) -> None:
    (tmp_path / "result.tif").write_bytes(b"x")
    (tmp_path / "result_001.tif").write_bytes(b"x")
    assert reserve_output_path(tmp_path / "result.tif").name == "result_002.tif"
```

- [ ] **Step 2: Verify the tests fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_paths.py -v
```

Expected: FAIL because runtime path functions do not exist.

- [ ] **Step 3: Implement explicit path resolution and output reservation**

```python
# runtime/paths.py
from pathlib import Path


def resolve_local_path(raw_path: str | Path, workdir: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(workdir).expanduser() / path
    return path.resolve(strict=False)


def require_input_path(raw_path: str | Path, workdir: str | Path) -> Path:
    path = resolve_local_path(raw_path, workdir)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path


def reserve_output_path(raw_path: str | Path) -> Path:
    requested = Path(raw_path).expanduser().resolve(strict=False)
    requested.parent.mkdir(parents=True, exist_ok=True)
    if not requested.exists():
        return requested
    for index in range(1, 10000):
        candidate = requested.with_name(f"{requested.stem}_{index:03d}{requested.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to reserve output path for {requested}")
```

- [ ] **Step 4: Implement environment loading**

```python
# runtime/environment.py
import os
from pathlib import Path
from dotenv import dotenv_values


def load_runtime_environment() -> dict[str, str]:
    env_file = os.getenv("NTL_MCP_ENV_FILE", "").strip()
    loaded: dict[str, str] = {}
    if env_file:
        for key, value in dotenv_values(Path(env_file)).items():
            if value is not None and key not in os.environ:
                os.environ[key] = value
                loaded[key] = value
    return loaded


def runtime_workdir() -> Path:
    return Path(os.getenv("NTL_MCP_WORKDIR", os.getcwd())).expanduser().resolve()
```

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_paths.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/runtime packages/ntl_toolkit/tests/test_paths.py
git commit -m "Add MCP runtime path handling"
```

## Task 4: Migrate the Local ConflictNTL Vector Operations into Core

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/vector.py`
- Test: `packages/ntl_toolkit/tests/test_vector_core.py`
- Test fixtures: `packages/ntl_toolkit/tests/fixtures/vector/`
- Reference only: `D:/Research_vault/raw/mcp/conflictntl-gis-tools/server.py`

- [ ] **Step 1: Create deterministic vector fixtures**

In `conftest.py`, create two square polygons and three points in EPSG:4326:

```python
import geopandas as gpd
from shapely.geometry import Point, box


def write_vector_fixtures(root):
    admin = gpd.GeoDataFrame(
        {"shapeName": ["west", "east"], "iso3": ["TST", "TST"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    points = gpd.GeoDataFrame(
        {"event_id": [1, 2, 3]},
        geometry=[Point(0.5, 0.5), Point(1.5, 0.5), Point(3, 3)],
        crs="EPSG:4326",
    )
    admin.to_file(root / "admin.geojson", driver="GeoJSON")
    points.to_file(root / "points.geojson", driver="GeoJSON")
```

- [ ] **Step 2: Write failing tests for all five migrated operations**

```python
from ntl_toolkit.core.vector import (
    buffer_points_aeqd,
    dissolve_intersections,
    filter_points_by_polygon,
    inspect_vector,
    spatial_join_points_to_admin,
)


def test_filter_points_keeps_two_matches(vector_fixture_dir, tmp_path):
    result = filter_points_by_polygon(
        vector_fixture_dir / "points.geojson",
        vector_fixture_dir / "admin.geojson",
        tmp_path / "filtered.geojson",
    )
    assert result.status == "succeeded"
    assert result.metrics["feature_count"] == 2


def test_spatial_join_marks_unmatched_point(vector_fixture_dir, tmp_path):
    result = spatial_join_points_to_admin(
        vector_fixture_dir / "points.geojson",
        vector_fixture_dir / "admin.geojson",
        tmp_path / "joined.geojson",
    )
    assert result.metrics == {"feature_count": 3, "matched_count": 2, "unmatched_count": 1}


def test_aeqd_buffer_and_dissolve(vector_fixture_dir, tmp_path):
    buffered = buffer_points_aeqd(
        vector_fixture_dir / "points.geojson", tmp_path / "buffers.geojson", radius_km=10
    )
    dissolved = dissolve_intersections(buffered.outputs[0].path, tmp_path / "clusters.geojson")
    assert buffered.metrics["feature_count"] == 3
    assert dissolved.metrics["cluster_count"] >= 1
```

Add direct metadata assertions for `inspect_vector` and a CSV longitude/latitude input test matching the old `_read_points` behavior.

- [ ] **Step 3: Run tests and verify missing functions fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_vector_core.py -v
```

Expected: FAIL on imports from `ntl_toolkit.core.vector`.

- [ ] **Step 4: Implement vector reading and writing helpers**

Implement `_read_points`, `_read_vector`, and `_write_vector` using the algorithms in `D:/Research_vault/raw/mcp/conflictntl-gis-tools/server.py`, but replace direct output paths with `reserve_output_path()` and return `ToolResult`.

Do not migrate `download_geoboundary` in this task. It remains in the compatibility server until the second-stage data-access plan because it performs an open-world network operation.

Required callable contracts:

- `inspect_vector(path: str | Path) -> ToolResult`
- `filter_points_by_polygon(points_path, polygon_path, output_path, *, lon_col="longitude", lat_col="latitude", predicate="within") -> ToolResult`
- `spatial_join_points_to_admin(points_path, admin_path, output_path, *, lon_col="longitude", lat_col="latitude", admin_name_col="shapeName", admin_iso_col="iso3", prefix="admin") -> ToolResult`
- `buffer_points_aeqd(points_path, output_path, *, radius_km, lon_col="longitude", lat_col="latitude") -> ToolResult`
- `dissolve_intersections(polygons_path, output_path, *, id_col="cluster_id") -> ToolResult`

For each function, catch `FileNotFoundError`, missing CRS, invalid geometry, and unsupported predicates and convert them to stable `ToolError` codes.

- [ ] **Step 5: Run vector tests and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_vector_core.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/vector.py packages/ntl_toolkit/tests
git commit -m "Add shared vector GIS core"
```

## Task 5: Add Raster Inspection and Validation

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/raster.py`
- Test: `packages/ntl_toolkit/tests/test_raster_core.py`
- Reference: `tools/geodata_inspector_tool.py:202-329`

- [ ] **Step 1: Create a small raster fixture**

```python
import numpy as np
import rasterio
from rasterio.transform import from_origin


def write_raster(path, values=None):
    array = np.asarray(values if values is not None else [[1, 2], [3, -9999]], dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=array.shape[1],
        height=array.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=-9999,
    ) as dst:
        dst.write(array, 1)
```

- [ ] **Step 2: Write failing inspection and validation tests**

```python
from ntl_toolkit.core.raster import inspect_raster, validate_geodata


def test_inspect_raster_reports_grid_and_stats(raster_fixture):
    result = inspect_raster(raster_fixture, mode="full")
    assert result.metrics["crs"] == "EPSG:4326"
    assert result.metrics["width"] == 2
    assert result.metrics["valid_count"] == 3
    assert result.metrics["mean"] == 2.0


def test_validate_geodata_detects_grid_mismatch(raster_fixture, shifted_raster_fixture):
    result = validate_geodata(raster_paths=[raster_fixture, shifted_raster_fixture])
    assert "GRID_MISMATCH" in result.warnings
```

- [ ] **Step 3: Verify tests fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_raster_core.py -v
```

Expected: FAIL because raster core functions are missing.

- [ ] **Step 4: Implement raster inspection**

Extract framework-free logic from `_raster_basic_stats`, `_raster_report`, `_vector_report`, and `_bbox_intersect` in `tools/geodata_inspector_tool.py` into:

Required callable contracts:

- `inspect_raster(path, *, mode="full", sample_pixels=0) -> ToolResult`
- `validate_geodata(*, raster_paths=None, vector_paths=None) -> ToolResult`

`inspect_raster` must mask nodata before statistics. `validate_geodata` must report readability, CRS, bounding-box intersection, raster grid compatibility, empty datasets, and invalid geometries without mutating inputs.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_raster_core.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/raster.py packages/ntl_toolkit/tests/test_raster_core.py
git commit -m "Add raster inspection and validation core"
```

## Task 6: Add Raster Clip, Reprojection, and Mosaic Operations

**Files:**
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/core/raster.py`
- Test: `packages/ntl_toolkit/tests/test_raster_core.py`

- [ ] **Step 1: Write failing transform tests**

```python
from ntl_toolkit.core.raster import clip_raster, mosaic_rasters, reproject_raster


def test_clip_raster_writes_reopenable_output(raster_fixture, clip_polygon, tmp_path):
    result = clip_raster(raster_fixture, clip_polygon, tmp_path / "clip.tif")
    with rasterio.open(result.outputs[0].path) as ds:
        assert ds.width == 1
        assert ds.height == 1


def test_reproject_raster_changes_crs(raster_fixture, tmp_path):
    result = reproject_raster(raster_fixture, tmp_path / "projected.tif", dst_crs="EPSG:3857")
    with rasterio.open(result.outputs[0].path) as ds:
        assert ds.crs.to_string() == "EPSG:3857"


def test_mosaic_rasters_preserves_union_extent(adjacent_rasters, tmp_path):
    result = mosaic_rasters(adjacent_rasters, tmp_path / "mosaic.tif")
    with rasterio.open(result.outputs[0].path) as ds:
        assert ds.width == 4
        assert ds.height == 2
```

- [ ] **Step 2: Run the new tests and verify they fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_raster_core.py -k "clip or reproject or mosaic" -v
```

Expected: FAIL on missing functions.

- [ ] **Step 3: Implement the three operations**

Required callable contracts:

- `clip_raster(raster_path, vector_path, output_path, *, all_touched=False) -> ToolResult`
- `reproject_raster(raster_path, output_path, *, dst_crs, resampling="bilinear") -> ToolResult`
- `mosaic_rasters(raster_paths, output_path, *, method="first") -> ToolResult`

Use `rasterio.mask.mask`, `rasterio.warp.calculate_default_transform`, `rasterio.warp.reproject`, and `rasterio.merge.merge`. Reject incompatible band counts and reserve output paths before opening writers. For `method="mean"`, maintain a valid-value sum array and a valid-observation count array, divide only where count is greater than zero, and write nodata elsewhere; do not pass unsupported `mean` directly to `rasterio.merge.merge`.

- [ ] **Step 4: Run the complete raster test file and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_raster_core.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/raster.py packages/ntl_toolkit/tests/test_raster_core.py
git commit -m "Add core raster transformations"
```

## Task 7: Migrate NTL Metrics and Zonal Statistics

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/core/ntl.py`
- Test: `packages/ntl_toolkit/tests/test_ntl_core.py`
- Reference: `tools/NTL_raster_stats.py:61-324`

- [ ] **Step 1: Write failing metric tests with known values**

```python
import numpy as np
from ntl_toolkit.core.ntl import calculate_ntl_metrics, calculate_ntl_metrics_for_raster


def test_calculate_ntl_metrics_known_array():
    values = np.array([[0.0, 2.0], [4.0, np.nan]], dtype="float32")
    metrics = calculate_ntl_metrics(values, pixel_area=1.0, selected=["TNTL", "LArea", "ANTL", "MaxNTL"])
    assert metrics == {"TNTL": 6.0, "LArea": 2.0, "ANTL": 2.0, "MaxNTL": 4.0}


def test_calculate_ntl_metrics_for_raster_returns_structured_result(raster_fixture):
    result = calculate_ntl_metrics_for_raster(
        raster_fixture,
        band=1,
        selected=["TNTL", "ANTL", "MaxNTL"],
    )
    assert result.status == "succeeded"
    assert result.metrics["TNTL"] == 6.0
    assert result.metrics["ANTL"] == 2.0
```

- [ ] **Step 2: Write failing zonal-statistics tests**

```python
from ntl_toolkit.core.ntl import calculate_zonal_statistics


def test_zonal_statistics_returns_one_row_per_polygon(raster_fixture, admin_fixture, tmp_path):
    result = calculate_zonal_statistics(
        raster_paths=[raster_fixture],
        vector_path=admin_fixture,
        output_path=tmp_path / "stats.csv",
        selected_indices=["TNTL", "ANTL", "MaxNTL"],
    )
    assert result.status == "succeeded"
    assert result.metrics["polygon_count"] == 2
    assert result.metrics["raster_count"] == 1
```

- [ ] **Step 3: Verify tests fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_ntl_core.py -v
```

Expected: FAIL because NTL core functions are missing.

- [ ] **Step 4: Extract the metric functions without workspace state**

Move `calc_TNTL`, `calc_LArea`, `calc_3DPLand`, `calc_3DED`, `calc_3DLPI`, `calc_ANTL`, and `calc_indices_per_polygon` from `tools/NTL_raster_stats.py` into `core/ntl.py`. Replace implicit path resolution with explicit `Path` arguments.

Required callable contracts:

- `calculate_ntl_metrics(values, *, pixel_area, selected=None) -> dict[str, float | None]`
- `calculate_ntl_metrics_for_raster(raster_path, *, band=1, selected=None) -> ToolResult`
- `calculate_zonal_statistics(*, raster_paths, vector_path, output_path, selected_indices=None, only_global=False) -> ToolResult`

Preserve the current metric formulas for parity. Use actual raster pixel area in projected units when available and include a warning when geographic-degree area is used.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_ntl_core.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/ntl.py packages/ntl_toolkit/tests/test_ntl_core.py
git commit -m "Add shared NTL statistics core"
```

## Task 8: Migrate Composite, Trend, and Anomaly Algorithms

**Files:**
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/core/ntl.py`
- Test: `packages/ntl_toolkit/tests/test_ntl_core.py`
- Reference: `tools/NTL_Composite.py:21-94`
- Reference: `tools/NTL_trend_detection_tool.py:32-136`
- Reference: `tools/NTL_anomaly_detection_tool.py:32-100`

- [ ] **Step 1: Write failing composite tests**

```python
from ntl_toolkit.core.ntl import composite_ntl_rasters


def test_mean_composite_uses_valid_pixels_only(two_raster_fixtures, tmp_path):
    result = composite_ntl_rasters(two_raster_fixtures, tmp_path / "mean.tif", method="mean")
    with rasterio.open(result.outputs[0].path) as ds:
        actual = ds.read(1, masked=True)
    assert float(actual[0, 0]) == 2.0
```

- [ ] **Step 2: Write failing trend and anomaly tests**

```python
from ntl_toolkit.core.ntl import analyze_ntl_trend, detect_ntl_anomaly


def test_linear_trend_detects_positive_slope(time_series_rasters, admin_fixture, tmp_path):
    result = analyze_ntl_trend(
        time_series_rasters,
        admin_fixture,
        tmp_path / "trend",
    )
    assert result.status == "succeeded"
    assert any(item.role == "slope" for item in result.outputs)


def test_anomaly_defaults_to_latest_image(time_series_with_spike, tmp_path):
    result = detect_ntl_anomaly(
        time_series_with_spike,
        tmp_path / "anomaly.tif",
        k_sigma=2.0,
    )
    assert result.metrics["target_index"] == len(time_series_with_spike) - 1
    assert result.metrics["anomaly_pixel_count"] == 1
```

- [ ] **Step 3: Run the tests and verify missing functions fail**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_ntl_core.py -k "composite or trend or anomaly" -v
```

Expected: FAIL on imports.

- [ ] **Step 4: Implement framework-free algorithms**

Required callable contracts:

- `composite_ntl_rasters(raster_paths, output_path, *, method="mean") -> ToolResult`
- `analyze_ntl_trend(raster_paths, vector_path, output_prefix) -> ToolResult`
- `detect_ntl_anomaly(raster_paths, output_path, *, target_index=None, k_sigma=3.0) -> ToolResult`

Extract the current numeric behavior from the three referenced legacy files. Add explicit checks for identical raster grids, at least two time steps for trend, at least three baseline observations for anomaly, finite `k_sigma > 0`, and valid target index.

- [ ] **Step 5: Run all NTL tests and commit**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_ntl_core.py -v
```

Expected: PASS.

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/core/ntl.py packages/ntl_toolkit/tests/test_ntl_core.py
git commit -m "Add composite trend and anomaly core"
```

## Task 9: Build the FastMCP Adapter and 16-Tool Server

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp/gis_core.py`
- Create: `mcp_servers/gis_core_server.py`
- Test: `packages/ntl_toolkit/tests/test_mcp_gis_core.py`

- [ ] **Step 1: Write a failing server catalog test**

```python
from ntl_toolkit.adapters.mcp.gis_core import build_gis_core_mcp


EXPECTED_TOOLS = {
    "validate_environment",
    "inspect_vector",
    "inspect_raster",
    "filter_points_by_polygon",
    "spatial_join_points_to_admin",
    "buffer_points_aeqd",
    "dissolve_intersections",
    "clip_raster",
    "reproject_raster",
    "mosaic_rasters",
    "calculate_zonal_statistics",
    "calculate_ntl_metrics",
    "composite_ntl_rasters",
    "analyze_ntl_trend",
    "detect_ntl_anomaly",
    "validate_geodata",
}


def test_server_exposes_exact_v1_tool_catalog():
    mcp = build_gis_core_mcp()
    assert set(mcp._tool_manager._tools) == EXPECTED_TOOLS
```

- [ ] **Step 2: Verify the test fails**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_mcp_gis_core.py -v
```

Expected: FAIL because the MCP builder does not exist.

- [ ] **Step 3: Implement the MCP builder**

```python
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from ntl_toolkit.core import ntl, raster, vector
from ntl_toolkit.runtime.environment import load_runtime_environment, runtime_workdir
from ntl_toolkit.runtime.paths import resolve_local_path
from ntl_toolkit.schemas import ToolResult


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE_NEW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def build_gis_core_mcp() -> FastMCP:
    load_runtime_environment()
    workdir = runtime_workdir()
    mcp = FastMCP("ntl-gis-core", instructions="Atomic local GIS and NTL operations. Outputs never overwrite existing files.")

    @mcp.tool(annotations=READ_ONLY)
    def inspect_raster(path: str, mode: str = "full", sample_pixels: int = 0) -> dict:
        resolved = resolve_local_path(path, workdir)
        return raster.inspect_raster(resolved, mode=mode, sample_pixels=sample_pixels).model_dump(mode="json")

    @mcp.tool(annotations=WRITE_NEW)
    def clip_raster(raster_path: str, vector_path: str, output_path: str, all_touched: bool = False) -> dict:
        return raster.clip_raster(
            resolve_local_path(raster_path, workdir),
            resolve_local_path(vector_path, workdir),
            resolve_local_path(output_path, workdir),
            all_touched=all_touched,
        ).model_dump(mode="json")

    return mcp
```

Register these additional tools as explicit typed functions before `return mcp`: `validate_environment`, `inspect_vector`, `filter_points_by_polygon`, `spatial_join_points_to_admin`, `buffer_points_aeqd`, `dissolve_intersections`, `reproject_raster`, `mosaic_rasters`, `calculate_zonal_statistics`, `calculate_ntl_metrics`, `composite_ntl_rasters`, `analyze_ntl_trend`, `detect_ntl_anomaly`, and `validate_geodata`.

The MCP `calculate_ntl_metrics` signature is:

```python
    @mcp.tool(annotations=READ_ONLY)
    def calculate_ntl_metrics(
        raster_path: str,
        band: int = 1,
        selected_indices: list[str] | None = None,
    ) -> dict:
        return ntl.calculate_ntl_metrics_for_raster(
            resolve_local_path(raster_path, workdir),
            band=band,
            selected=selected_indices,
        ).model_dump(mode="json")
```

Every remaining MCP wrapper must resolve all input and output path strings through `resolve_local_path(value, workdir)` before calling Core. `validate_environment` imports `geopandas`, `rasterio`, `shapely`, `pyproj`, `numpy`, `pandas`, and `scipy`, records their versions under `metrics.versions`, and returns a failed `ToolResult` with code `DEPENDENCY_MISSING` when any import fails. Use `READ_ONLY` for inspection, validation, and raster metric calculation; use `WRITE_NEW` for every function that creates a file. Do not expose `**kwargs`, arbitrary code, delete, move, or shell execution. Each wrapper must return `ToolResult.model_dump(mode="json")`.

- [ ] **Step 4: Add the capability resources**

```python
    @mcp.resource("ntl://gis/capabilities")
    def gis_capabilities() -> str:
        return Path(__file__).with_name("gis_capabilities.json").read_text(encoding="utf-8")

    @mcp.resource("ntl://schemas/result-v1")
    def result_schema() -> str:
        return json.dumps(ToolResult.model_json_schema(), ensure_ascii=False, indent=2)
```

Create `gis_capabilities.json` beside the adapter with one entry per tool containing purpose, side effects, accepted formats, and common error codes.

- [ ] **Step 5: Add the stdio entrypoint**

```python
# mcp_servers/gis_core_server.py
from ntl_toolkit.adapters.mcp.gis_core import build_gis_core_mcp


def main() -> None:
    build_gis_core_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Test catalog, annotations, resources, and one read/write call**

Add tests asserting:

- exactly 16 tools are listed;
- inspection tools are read-only and idempotent;
- write tools are non-destructive and non-idempotent;
- both resources are listed;
- `inspect_raster` returns `ntl.tool.result.v1`;
- repeated `clip_raster` calls return distinct output paths.

Run:

```powershell
python -m pytest packages/ntl_toolkit/tests/test_mcp_gis_core.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit the MCP server**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/adapters/mcp mcp_servers/gis_core_server.py packages/ntl_toolkit/tests/test_mcp_gis_core.py
git commit -m "Add ntl-gis-core MCP server"
```

## Task 10: Add LangChain Adapters and Legacy Parity Tests

**Files:**
- Create: files under `packages/ntl_toolkit/src/ntl_toolkit/adapters/langchain/`
- Modify: `tools/geodata_inspector_tool.py`
- Modify: `tools/NTL_raster_stats.py`
- Modify: `tools/NTL_Composite.py`
- Modify: `tools/NTL_trend_detection_tool.py`
- Modify: `tools/NTL_anomaly_detection_tool.py`
- Test: `packages/ntl_toolkit/tests/test_langchain_parity.py`

- [ ] **Step 1: Write failing parity tests before modifying legacy wrappers**

```python
def test_raster_stats_adapter_matches_core(legacy_workspace, raster_fixture, admin_fixture, tmp_path):
    core_result = calculate_zonal_statistics(
        raster_paths=[raster_fixture],
        vector_path=admin_fixture,
        output_path=tmp_path / "core.csv",
        selected_indices=["TNTL", "ANTL"],
    )
    legacy_payload = NTL_raster_statistics(
        ntl_tif_path=raster_fixture.name,
        shapefile_path=admin_fixture.name,
        output_csv_path="legacy.csv",
        selected_indices=["TNTL", "ANTL"],
        config={"configurable": {"thread_id": legacy_workspace.thread_id}},
    )
    assert read_stats(core_result.outputs[0].path) == read_stats(legacy_workspace.outputs / "legacy.csv")
```

Add equivalent tests for local composite, trend, anomaly, local raster inspection, missing input, and duplicate output naming.

- [ ] **Step 2: Run parity tests against current legacy code**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_langchain_parity.py -v
```

Expected: baseline tests PASS or expose existing differences that must be recorded before adapter changes. Commit fixture corrections separately if required; do not change production code in this step.

- [ ] **Step 3: Implement explicit workspace-to-core adapters**

Each adapter must resolve current NTL-GPT virtual paths through `storage_manager`, then call the shared Core. Example:

```python
def run_raster_statistics_legacy(
    *,
    ntl_tif_path,
    ntl_tif_paths,
    shapefile_path,
    output_csv_path,
    selected_indices,
    only_global,
    thread_id,
):
    rasters = [storage_manager.resolve_input_path(path, thread_id) for path in collect_inputs(ntl_tif_path, ntl_tif_paths)]
    vector = storage_manager.resolve_input_path(shapefile_path, thread_id)
    output = storage_manager.resolve_output_path(output_csv_path, thread_id)
    return calculate_zonal_statistics(
        raster_paths=rasters,
        vector_path=vector,
        output_path=output,
        selected_indices=selected_indices,
        only_global=only_global,
    )
```

Keep the legacy Pydantic v1 input schemas and `StructuredTool.from_function` declarations unchanged.

- [ ] **Step 4: Replace legacy implementation bodies one module at a time**

Order:

1. `tools/geodata_inspector_tool.py` local raster/vector branches only; retain GEE asset inspection until the GEE plan.
2. `tools/NTL_raster_stats.py`.
3. `tools/NTL_Composite.py` local composite only; retain GEE composite.
4. `tools/NTL_trend_detection_tool.py`.
5. `tools/NTL_anomaly_detection_tool.py`.

After each file, run only the matching parity test before proceeding.

- [ ] **Step 5: Run all parity and existing repository tests**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_langchain_parity.py -v
python -m pytest packages/ntl_toolkit/tests -v
python -m pytest tests -v
python -m py_compile tools/geodata_inspector_tool.py tools/NTL_raster_stats.py tools/NTL_Composite.py tools/NTL_trend_detection_tool.py tools/NTL_anomaly_detection_tool.py
```

Expected: all tests PASS and all modules compile.

- [ ] **Step 6: Commit the adapters**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/adapters/langchain packages/ntl_toolkit/tests/test_langchain_parity.py tools/geodata_inspector_tool.py tools/NTL_raster_stats.py tools/NTL_Composite.py tools/NTL_trend_detection_tool.py tools/NTL_anomaly_detection_tool.py
git commit -m "Route NTL-GPT GIS tools through shared core"
```

## Task 11: Add the Migration Manifest, Documentation, and MCP Evaluations

**Files:**
- Create: `packages/ntl_toolkit/tool_migration_manifest.json`
- Create: `packages/ntl_toolkit/README.md`
- Create: `docs/mcp/ntl-gis-core.md`
- Create: `evaluations/ntl_gis_core.xml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `check_env.py`
- Modify: `.ntl-gpt/skills/conflict-ntl-workflow/SKILL.md`

- [ ] **Step 1: Create the migration manifest**

Include entries for the existing ConflictNTL vector operations and the five migrated NTL-GPT modules. Every entry must use one of:

```text
planned | extracting | parity_testing | migrated | deprecated
```

Mark only tools with passing parity tests as `migrated`.

- [ ] **Step 2: Add environment examples**

Add to `.env.example`:

```dotenv
NTL_MCP_ENV_FILE=
NTL_MCP_WORKDIR=
NTL_MCP_STATE_DIR=.ntl-mcp
```

Add these names to `check_env.py` optional variables without printing their secret values.

- [ ] **Step 3: Document local installation and client configuration**

`docs/mcp/ntl-gis-core.md` must contain these exact startup patterns:

```powershell
C:\ProgramData\Miniconda3\Scripts\conda.exe run -n NTL-GPT-Stable python D:\NTL-GPT-main\mcp_servers\gis_core_server.py
```

```toml
[mcp_servers.ntl-gis-core]
command = "C:/ProgramData/Miniconda3/Scripts/conda.exe"
args = ["run", "-n", "NTL-GPT-Stable", "python", "D:/NTL-GPT-main/mcp_servers/gis_core_server.py"]
```

Also include Claude Desktop and OpenClaw stdio examples, environment variables, supported formats, no-overwrite behavior, and troubleshooting for GDAL/PROJ imports.

- [ ] **Step 4: Create 10 read-only MCP evaluation questions**

Write `evaluations/ntl_gis_core.xml` with 10 independent questions covering raster metadata, vector metadata, CRS mismatch, bounds intersection, point/admin matching counts, NTL metric values, grid compatibility, nodata handling, chronological raster inspection, and invalid input diagnosis. Use committed fixtures so each answer is stable.

- [ ] **Step 5: Update the ConflictNTL skill after successful MCP parity**

Document `ntl-gis-core` as the preferred generic vector server and mark `conflictntl-gis-tools` as the compatibility server. Do not remove the old MCP config in this task.

- [ ] **Step 6: Validate documentation and commit**

Run:

```powershell
python -c "from pathlib import Path; [p.read_text(encoding='utf-8') for p in [Path('README.md'), Path('docs/mcp/ntl-gis-core.md'), Path('packages/ntl_toolkit/README.md')]]; print('utf8_ok')"
python check_env.py
```

Expected: `utf8_ok`; `check_env.py` reports optional MCP variables without exposing values.

```powershell
git add .env.example README.md check_env.py docs/mcp packages/ntl_toolkit/README.md packages/ntl_toolkit/tool_migration_manifest.json evaluations/ntl_gis_core.xml .ntl-gpt/skills/conflict-ntl-workflow/SKILL.md
git commit -m "Document ntl-gis-core MCP usage"
```

## Task 12: Run the Release Gate

**Files:**
- No new production files expected
- Update only failing tests or documentation uncovered by the gate

- [ ] **Step 1: Run package tests**

```powershell
python -m pytest packages/ntl_toolkit/tests -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run repository regression tests**

```powershell
python -m pytest tests -v
python -m py_compile graph_factory.py app_agents.py app_logic.py tools/__init__.py
```

Expected: all tests PASS and all modules compile.

- [ ] **Step 3: Verify dependency boundaries**

```powershell
rg -n "streamlit|langchain|fastmcp|mcp\.server" packages/ntl_toolkit/src/ntl_toolkit/core packages/ntl_toolkit/src/ntl_toolkit/schemas packages/ntl_toolkit/src/ntl_toolkit/runtime
```

Expected: no matches in `core`, `schemas`, or `runtime` except documentation strings that explicitly describe forbidden dependencies.

- [ ] **Step 4: Verify the exact tool catalog and no-overwrite behavior**

```powershell
python -m pytest packages/ntl_toolkit/tests/test_mcp_gis_core.py -v
```

Expected: exactly 16 tools, required resources present, annotations correct, repeated output calls use different paths.

- [ ] **Step 5: Run MCP Inspector manually**

```powershell
npx @modelcontextprotocol/inspector C:\ProgramData\Miniconda3\Scripts\conda.exe run -n NTL-GPT-Stable python D:\NTL-GPT-main\mcp_servers\gis_core_server.py
```

Verify `tools/list`, `resources/list`, one read-only call, one output-producing call, and one structured missing-input error.

- [ ] **Step 6: Record the release gate result**

Add a dated section to `docs/mcp/ntl-gis-core.md` containing commands run, test counts, Inspector result, known limitations, and the exact package version.

- [ ] **Step 7: Commit the verified release candidate**

```powershell
git add packages/ntl_toolkit docs/mcp/ntl-gis-core.md mcp_servers evaluations tools tests environment.yml
git commit -m "Verify ntl-gis-core release candidate"
```

Do not begin the `ntl-gee-tools` implementation until this release gate is green.
