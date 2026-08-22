---
name: conflict-city-ntl-analysis
description: Use when a task asks NTL-GPT to retrieve an authorized structured conflict-event source, rank the cities with the most retrieved attack records in Iran and Israel (including all ties), and compare pre/post nighttime light. This workflow is source-gated, traceable, does not use QGIS MCP, and never treats NTL change as proof of damage or causation.
metadata:
  schema: "conflict_city_ntl.skill.v1"
  output_contract: "/skills/conflict-city-ntl-analysis/references/output_contract.json"
---

# Conflict City NTL Analysis

Use this narrow workflow to answer questions such as: retrieve the latest authorized Iran-Israel conflict-event records through an explicit cutoff, identify the city or tied cities with the highest record count in each country, and compare their pre/post VNP46A2 nighttime light.

This is not the full ConflictNTL agent system. Do not introduce QGIS MCP, infer physical attack counts from news, or attribute nighttime-light change to conflict damage.

## Required Inputs

Resolve these before execution:

- `start_date` and inclusive `end_date`, plus the timezone used to interpret relative dates such as “截至测试日”.
- Either an authorized structured event snapshot or explicit authorization to query the configured live source.
- The fixed attack-record event taxonomy and any versioned city-alias mapping.
- Pre-event and post-event NTL windows, product, band, QA rule, aggregation rule, scale, and output names.

If a relative date is used, report its resolved calendar date. Do not silently replace a missing date or source with a model guess.

## Source Authorization Gate

Apply this gate before event retrieval:

1. Prefer a user-provided, authorized CSV/JSON snapshot and call `conflict_city_event_ranking_tool` with its workspace-relative `events_path`.
2. The configured live ISW/CTP ArcGIS layers have a licensing gate. Publicly queryable data is not automatically licensed for reuse. Leave `events_path` empty for live retrieval only after the user or benchmark fixture explicitly acknowledges the applicable source terms by setting `source_terms_acknowledged=true`.
3. Without an authorized snapshot or explicit live-source acknowledgement, fail closed with `needs_source_authorization`. Do not produce a city ranking.
4. Search engines, GDELT, ReliefWeb, or prose reports may help discover or cross-check leads, but they must not be silently substituted for the structured ranking source.

The source snapshot, retrieval time, source-layer identifiers, date window, filters, exclusions, and hashes belong in provenance. Read `/skills/conflict-city-ntl-analysis/references/output_contract.json` before composing the final answer.

## Workflow

### 1. Retrieve, Normalize, and Rank Event Records

Delegate external-source work to Data_Searcher and call `conflict_city_event_ranking_tool`. Supply:

- `events_path` for an authorized local CSV/JSON snapshot, or an empty string for authorized live retrieval;
- `event_window_start` and inclusive `event_window_end`;
- `countries_csv="Iran,Israel"`;
- `city_aliases_json` and `eligible_event_types_json` from fixed JSON when the task provides them;
- `source_terms_acknowledged=true` only when live-source authorization is explicit;
- workspace-safe `output_root` and `run_label` values.

For direct development or audit use, the bundled thin CLI exposes the same core function:

```text
python .ntl-gpt/skills/conflict-city-ntl-analysis/scripts/fetch_and_rank_conflict_cities.py --input-events inputs/authorized_events.csv --start-date 2026-01-01 --end-date 2026-08-10 --thread-id <thread-id>
```

For live mode, add both `--live` and `--acknowledge-source-terms`; never add the acknowledgement on the user's behalf.

Use the tool's deterministic ranking. Do not have the LLM recount rows. The counting unit is **retrieved source attack records**, deduplicated by a source-namespaced record key. It is not a claim about independently verified physical attacks. Rank Iran and Israel separately, and retain every city tied for the maximum within each country.

Reject or report, rather than guess, records with unresolved country/city, invalid dates, excluded event types, or insufficient source identity. A stable source namespace must come from a preserved source layer URL, source ID, source layer, or event family; never merge missing-source records into a shared `unknown_source` namespace. Exclude them as `missing_source_identity`, expose `audit.missing_source_identity_record_count`, and require `status="partial"` whenever that count is nonzero. Preserve raw-row, distinct-record, eligible-record, duplicate, excluded, and unresolved counts.

### 2. Resolve City Boundaries

For every selected city, call `get_administrative_division_geoboundaries_tool` with the appropriate `country`, `level="city"`, canonical `place_name`, required workspace filename such as `input_name="iran_tehran_boundary.geojson"`, `output_format="geojson"`, and `convert_geojson_to_shp=false`.

Record the boundary source and administrative level. If an exact city boundary is unavailable, stop or explicitly label the accepted administrative unit as a city-level proxy; never silently substitute a province, point buffer, or differently named place. Include every tied top city.

### 3. Build Comparable NTL Inputs

Use the existing NTL data-selection and latest-availability capabilities to select and verify VNP46A2 observations for the fixed pre/post windows. Apply the same product version, `DNB_BRDF_Corrected_NTL` band, physical scaling, QA mask, spatial grid, compositing rule, and valid-pixel rule to both periods.

If the requested post-event window is not yet quality-complete, report the latency and stop or use only a predeclared fallback. Do not shift dates after seeing the result.

### 4. Calculate ANTL and TNTL

After the pre/post rasters and boundaries are in the workspace, call `NTL_raster_statistics` with:

- both pre/post raster inputs;
- the selected-city boundary layer;
- `selected_indices=["ANTL", "TNTL"]`;
- an auditable output CSV.

Report each city's pre/post ANTL and TNTL, absolute change, relative change when the denominator is valid, valid-pixel counts or coverage checks, and the exact observation/composite dates. Keep separately ranked countries and tied cities identifiable through the full analysis.

### 5. Report With Provenance and Guardrails

Return:

- source scope, authorization mode, as-of time, and immutable event snapshot metadata;
- normalized event records, city counts, exclusions, and all tied top cities;
- boundary provenance and administrative level;
- NTL product/band, QA and date windows;
- ANTL/TNTL table and maps;
- limitations and failures.

Use wording such as “the city with the most retrieved source attack records” rather than “the most attacked city” in analytical claims. State that detected NTL changes are candidate remote-sensing observations only and do not prove damage, outage cause, responsibility, or any other causal relationship.

## Fail-Closed Conditions

Do not emit a substantive ranking or NTL conclusion when any of these applies:

- source terms were not acknowledged for live retrieval;
- the authorized source cannot reconstruct records through the requested cutoff;
- either country has no eligible, city-resolved records;
- a partial source failure could change the maximum-city ranking;
- tied maxima were dropped;
- city boundaries or comparable quality-controlled NTL inputs are unavailable;
- output provenance is missing.

Return the concrete failure code and the missing requirement instead of improvising a result.
