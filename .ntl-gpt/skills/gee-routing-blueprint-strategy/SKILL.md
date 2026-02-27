---
name: gee-routing-blueprint-strategy
description: Use when deciding Data_Searcher GEE retrieval path (direct_download vs gee_server_side), boundary strategy, metadata/discovery calls, and completion checks.
---

# GEE Routing / Blueprint / Metadata Strategy

## Purpose
Centralize reusable routing rules from `tools/GEE_specialist_toolkit.py` and `agents/NTL_Data_Searcher.py` into one execution policy.

## When To Use
- Any request that includes GEE retrieval, temporal range planning, dataset choice, or execution mode decision.
- Any request that might require `GEE_dataset_router_tool`, `GEE_script_blueprint_tool`, `GEE_dataset_metadata_tool`, or `GEE_catalog_discovery_tool`.

## Core Decision Order
1. Read upstream `task_level` (`L1|L2|L3`) from NTL_Engineer handoff.
2. If task is pure local-file inspection with explicit existing filenames and no GEE retrieval, skip router.
3. Otherwise call `GEE_dataset_router_tool` first.
4. Route to:
- `direct_download` for lightweight retrieval (`daily <=14` OR `monthly <=12` OR `annual <=12`) and file-focused intent.
- `gee_server_side` for larger ranges or explicit analysis-first intent (`GEE Python API`, ANTL statistics, event impact windows).
5. For unknown dataset mapping, call discovery then metadata:
- `GEE_catalog_discovery_tool` -> `GEE_dataset_metadata_tool`.
- Check `official_candidates` and `candidates` even when `known_matches` is empty.

## Boundary Strategy
- Default: no global pre-boundary check.
- Retrieve/verify boundary only when needed:
  - user explicitly asks boundary file/metadata,
  - analysis/clip/zonal workflow required,
  - download reports ambiguity/not-found region,
  - outside-China task requiring explicit boundary (`get_administrative_division_osm_tool`).

## Direct Download Short-Circuit
- After successful `NTL_download_tool` with non-empty `output_files` and no ambiguity/error flags:
  - skip extra metadata/discovery calls,
  - optional `geodata_quick_check_tool`,
  - set `GEE_execution_plan.metadata_validation = not_required_local_analysis`.

## Completion Gate
- Use router `estimated_image_count` as expected count.
- Ensure returned `output_files` coverage matches expected count before `status=complete`.
- Return one final structured payload only; do not loop repeated completion messages.

## Guardrails
- Do not replace named regions with invented bbox.
- Do not perform bulk local download for long daily ranges.
- Keep rules capability-level, not query-specific.
