# Hierarchical architecture smoke cases

These case and evaluator contracts exercise the new Deep Agents Full and
matched Single-Agent execution surfaces. They are engineering smoke tests, not
the formal 200-task release and not manuscript results.

- `SMOKE-FAST-001` checks the bounded Engineer fast path and typed evidence.
- `SMOKE-ANALYSIS-001` checks supplied-input scientific analysis and artifact
  generation on the verified BV1-091 synthetic city panel.
- `SMOKE-EVENT-001` checks the source-bounded event route using only two frozen
  raw official-domain search snapshots from the verified BV1-015 reference
  package. The tested workspace does not receive the resolved event, reference
  manifest, or benchmark Gold, and live retrieval is explicitly forbidden.
- `SMOKE-OBSERVATION-001` checks the Data Searcher route over a checksum-bound
  synthetic 2x2 GeoTIFF. It requires a full local inspection and ready
  ObservationPackage while forbidding all live retrieval and download tools.
  Its query timestamp is not model-authored: the runtime records the successful
  full inspector completion time and injects it when the package is saved.

Event fixture integrity anchors:

- `usgs_official_domain_search.json`: `e70612add1a878b8b7cf0e2975aef309f023465849defa83b73ba8e16f843dcb`
- `reliefweb_official_domain_search.json`: `7c087f14aedae780740f9c0faaee57aab12154296e5e987e7c2753d0ae830980`

## Compatibility preflight

The known-good Windows smoke environment is Python 3.11.15 with Deep Agents 0.7.5,
LangChain 1.3.15, langchain-core 1.5.4, LangGraph 1.2.11,
langchain-openai 1.1.7, Rasterio 1.4.4, pyproj 3.7.2, and Fiona 1.10.1. The
compatibility venv uses `--system-site-packages`: Rasterio, pyproj, and their
compatible PROJ/GDAL data directories come from the stable base environment
reported by `sys.base_prefix`, while Fiona is importable in the compatibility
venv. Set `PROJ_DATA` and `GDAL_DATA` in the same PowerShell process before any
test or provider run. Do not point PROJ at Fiona's bundled `proj_data`; its
database layout is not compatible with the inherited pyproj/Rasterio build.

Run this explicit preflight from the current repository checkout. It installs
`ntl-toolkit` editable from that checkout and rejects an import resolved from a
different worktree. No `.env`, secret-loading helper, or generated execution
script is created or sourced by this procedure.

```powershell
$repo = (Resolve-Path "D:\NTL-GPT-main\.worktrees\hierarchical-multiagent-experiments").Path
$py = "D:\NTL-GPT-smoke-runs\deepagents-075-compat\venv\Scripts\python.exe"
Set-Location $repo

$stablePrefix = (& $py -c "import sys; print(sys.base_prefix)").Trim()
$env:PROJ_DATA = Join-Path $stablePrefix "Library\share\proj"
$env:GDAL_DATA = Join-Path $stablePrefix "Library\share\gdal"
$env:LANGCHAIN_TRACING = "false"
$env:LANGCHAIN_TRACING_V2 = "false"
$env:LANGSMITH_TRACING = "false"
if (-not (Test-Path -LiteralPath (Join-Path $env:PROJ_DATA "proj.db"))) { throw "PROJ_DATA is invalid: $env:PROJ_DATA" }
if (-not (Test-Path -LiteralPath (Join-Path $env:GDAL_DATA "gdalvrt.xsd"))) { throw "GDAL_DATA is invalid: $env:GDAL_DATA" }

& $py -m pip install --no-deps -e ".\packages\ntl_toolkit"
& $py -c "import importlib.metadata as m, os, pathlib, sys; import fiona, ntl_toolkit, pyproj, rasterio; from rasterio.crs import CRS; expected={'deepagents':'0.7.5','langchain':'1.3.15','langchain-core':'1.5.4','langgraph':'1.2.11','langchain-openai':'1.1.7','rasterio':'1.4.4','pyproj':'3.7.2','fiona':'1.10.1'}; actual={name:m.version(name) for name in expected}; assert sys.version_info[:3] == (3,11,15), sys.version; assert actual == expected, (actual,expected); repo=pathlib.Path.cwd().resolve(); toolkit=pathlib.Path(ntl_toolkit.__file__).resolve(); assert toolkit.is_relative_to((repo/'packages'/'ntl_toolkit').resolve()), toolkit; assert pathlib.Path(os.environ['PROJ_DATA'],'proj.db').is_file(); assert pathlib.Path(os.environ['GDAL_DATA'],'gdalvrt.xsd').is_file(); assert pyproj.datadir.get_data_dir() == os.environ['PROJ_DATA']; assert CRS.from_epsg(4326).to_epsg() == 4326; print({'python':sys.version.split()[0],'versions':actual,'ntl_toolkit.__file__':str(toolkit),'PROJ_DATA':os.environ['PROJ_DATA'],'GDAL_DATA':os.environ['GDAL_DATA']})"
```

Run the same `cases.jsonl` once with `--architecture-mode full` and once with
`--architecture-mode single_agent`, then prepare independent Luna packets with
`eval-specs.jsonl`.

The Analysis, Event, and Observation evaluator contracts condition their architecture checks
on `run_record.environment.architecture_mode`: Full must show the named
specialist, persisted typed package, accepted handoff, and completed route;
matched Single-Agent must show no `task` delegation but the same ready typed
package and completed route.

Run the deterministic asset checks with:

```powershell
& $py -m pytest -q experiments/hierarchical_smoke/test_smoke_assets.py
```
