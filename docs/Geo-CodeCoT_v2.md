# Geo-CodeCoT v2 for NTL-GPT

Last updated: 2026-02-06

## Objective
Strengthen NTL-GPT Code Assistant for geospatial programming reliability, especially GEE Python and local geospatial stacks (rasterio, geopandas, shapely), while preserving your existing multi-agent architecture.

## What Changed

### 1) Geo-CodeCoT v2: preflight + execution + remediation
File: `tools/NTL_Code_generation.py`

- Added **domain-aware preflight checks** before code execution:
  - syntax validity
  - workspace path protocol (`storage_manager.resolve_input_path/resolve_output_path`)
  - absolute path rejection
  - GEE initialization checks (`ee.Initialize(project=...)`)
  - GEE dataset/band consistency checks for NTL datasets
  - reduction safety checks (`scale`, `maxPixels`, `bestEffort/tileScale`)
  - CRS-risk heuristics for geopandas/rasterio workflows
- Added **structured fix suggestions** for common failures (FileNotFound, EEException, projection mismatch, memory/pixel limit issues).
- Kept tool names unchanged (`GeoCode_COT_Validation_tool`, `final_geospatial_code_execution_tool`) for compatibility.

### 2) Knowledge-first coding via recipe retrieval
Files:
- `tools/geocode_knowledge_tool.py`
- `tools/__init__.py`

- Added a new tool: `GeoCode_Knowledge_Recipes_tool`
- Provides retrieval of project-aligned, runnable templates for:
  - GEE annual zonal stats (ANTL/TNTL)
  - GEE long daily series server-side statistics
  - rasterio + geopandas zonal statistics
  - raster reprojection/alignment
  - geopandas spatial join
  - shapely geometry repair
- Integrated into `Code_tools`, so the Code Assistant can retrieve templates before generating code.

### 3) Code Assistant strategy update
File: `agents/NTL_Code_Assistant.py`

- Upgraded prompt to enforce a strict sequence:
  1. inspect data
  2. retrieve canonical recipe
  3. build mini-test blocks
  4. run validator
  5. execute final workflow
- Added explicit best-practice constraints for GEE/rasterio/geopandas/shapely.
- Updated temporal constraints with explicit dataset IDs and end dates.

## Earth Engine Date Audit (verified on 2026-02-06)

- `NASA/VIIRS/002/VNP46A2`: availability listed as 2012-01-19 to 2026-01-05.
- `NOAA/VIIRS/001/VNP46A1`: availability listed as 2012-01-19 to 2024-11-03.
- `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG`: availability listed as 2014-01-01 to 2025-03-01.
- `NOAA/VIIRS/DNB/ANNUAL_V21`: availability listed as 2012-04-01 to 2021-01-01.
- `NOAA/VIIRS/DNB/ANNUAL_V22`: availability listed as 2012-04-01 to 2024-01-01.

## Innovation Points (Compared with Generic Code Agents)

1. **Geospatial protocol-aware static checks**
- Checks geospatial-specific mistakes before runtime (CRS, reduction parameters, asset-band mismatch), not just syntax.

2. **Server-side-first strategy for long NTL daily series**
- Explicitly pushes heavy daily statistics to GEE server-side map/reduce to avoid local download bottlenecks.

3. **Hybrid reliability loop (recipe retrieval + mini-tests + final execution)**
- Reduces hallucinated code by constraining generation with domain templates and progressive validation.

4. **Thread-safe workspace semantics baked into code generation**
- Enforces `storage_manager` path resolution to support multi-session isolation and reproducibility.

## Recommended Next Extension

1. Add retrieval from an external code corpus (real successful runs from `user_data/*/outputs` + scripts) to build a run-proven RAG index.
2. Add property-based regression tests for tool outputs (schema checks + numerical sanity checks).
3. Add benchmark tasks for GEE/rasterio/geopandas separately and track pass@1 / pass@k.

## References

- Google Earth Engine client vs server model:
  - https://developers.google.com/earth-engine/guides/client_server
- Google Earth Engine `reduceRegion`/`reduceRegions`:
  - https://developers.google.com/earth-engine/guides/reducers_reduce_region
  - https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions
- Earth Engine dataset catalogs:
  - NASA VNP46A2: https://developers.google.com/earth-engine/datasets/catalog/NASA_VIIRS_002_VNP46A2
  - NOAA VNP46A1: https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_001_VNP46A1
  - NOAA Monthly VCMSLCFG: https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG
  - NOAA Annual V21: https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V21
  - NOAA Annual V22: https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V22
- Rasterio docs:
  - https://rasterio.readthedocs.io/en/stable/topics/reproject.html
  - https://rasterio.readthedocs.io/en/stable/topics/features.html
- GeoPandas docs:
  - https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_crs.html
  - https://geopandas.org/en/stable/docs/reference/api/geopandas.sjoin.html
- Shapely docs:
  - https://shapely.readthedocs.io/en/2.1.1/reference/shapely.make_valid.html
