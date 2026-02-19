# GEE Workflow Integration (Data_Searcher + Code_Assistant)

The previous standalone `GEE_Specialist` role has been merged into `Data_Searcher`.

## Updated architecture

- `Data_Searcher`
  - Uses lightweight checker only: `geodata_quick_check_tool`
  - Validates dataset/time coverage with `GEE_dataset_router_tool`
  - Confirms administrative boundary via Amap/OSM + `geodata_quick_check_tool`
  - Chooses `direct_download` or `gee_server_side`
  - Returns structured GEE plan + optional Python blueprint/metadata validation
  - For non-built-in datasets, uses `GEE_catalog_discovery_tool` + `GEE_dataset_metadata_tool`
  - Supports optional quick cloud-side dataset availability check via `geodata_quick_check_tool(gee_assets=[...])`
- `NTL_Engineer`
  - Orchestrates and enforces boundary re-check before execution
- `Code_Assistant`
  - Uses full inspector: `geodata_inspector_tool`
  - Runs Geo-CodeCoT validation and execution
  - Restricted to analysis outputs; repository source/config edits are blocked

## Reference patterns adopted

- From `agentic-gee-assistant`:
  - Use a dedicated dataset-search/planning stage before execution.
  - Return structured, explainable routing decisions instead of implicit assumptions.
- From `gee-agents`:
  - Keep tool responsibilities explicit and composable.
  - Use schema-like metadata outputs (dataset, band, temporal range, execution mode).

## Accuracy guardrails

1. Named regions cannot be replaced by self-invented bbox.
2. Long daily series (>31 images) must use server-side processing plan.
3. Boundary metadata must include source, CRS, bounds, and validation status.
4. `GeoCode_COT_Validation_tool` now allows output-read verification without false blocking when `resolve_output_path()` is used.
