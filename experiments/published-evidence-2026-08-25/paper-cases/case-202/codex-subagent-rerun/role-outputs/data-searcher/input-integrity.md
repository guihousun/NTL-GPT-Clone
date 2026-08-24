# Q19 input integrity audit

- **Case:** `Q19-tehran-city-longseries`
- **Role:** `NTL_Data_Searcher`
- **Execution context:** Codex-subagent simulation; independent local re-read; not deployed NTL-GPT telemetry.
- **Verdict:** **partial** — the supplied frozen package is internally consistent and analysis-ready for the declared baseline under its snapshot, but it is not a live/current re-query and it contains explicit coverage gaps and administrative-AOI limits.
- **Audit timestamp:** `2026-08-17T12:55:30Z`

## Source and provenance

The audit read the prior Q19 package at `vault/ntl-gpt/experiments\paper-case-multiagent-2026-08-13\Q19-tehran-city-longseries`. The package records an Earth Engine query timestamp of `2026-08-13T17:13:48Z` and an actual product-date cutoff of `2026-08-02`. This audit did not make a new GEE query or download. Exact bytes and SHA-256 values are in [input-manifest.csv](input-manifest.csv); the machine-readable cross-check is [daily-series-audit.json](daily-series-audit.json).

## AOI

The reopened GeoJSON contains one valid, non-empty `Polygon` feature named **City of Tehran**, shape ID `26516999B29761828880922`, `shapeType=ADM2`, CRS `EPSG:4326`. Independent Shapely/PROJ checks compute `628.22188034` km² in EPSG:6933 and `4051` vertices including ring closure, matching the metadata within the recorded precision. The source semantics are geoBoundaries ADM2 / canonical **Shahrestan**; it is not asserted to be a municipality or functional urban footprint. The package records no event buffer.

## Product, band, and reducer

- Collection: `NASA/VIIRS/002/VNP46A2` (version `002`), daily UTC product day.
- Band used: `DNB_BRDF_Corrected_NTL`; the gap-filled band is recorded as not used.
- Units: `nW cm^-2 sr^-1`; reducer scale: `500 m`; recorded native CRS: `EPSG:4326`.
- Per-image AOI statistics: mean, median, standard deviation, p25, p75, and count; monthly chunks are reopened locally.
- Product metadata and QA semantics are cross-checked against the local observation package, checkpoint, extractor, and the recorded official catalog URL. This role did not separately fetch the online catalog.

## QA and validity semantics

The local extractor evidence is `extract_tehran_daily_vnp46a2.py:249-278` and `extract_tehran_daily_vnp46a2.py:526-562`. The recorded strict mode combines the common night/cloud/shadow/cirrus/snow/radiance conditions with `Mandatory_Quality_Flag=0` and cloud-mask quality bits 4–5 ≥2. The permissive mode uses `Mandatory_Quality_Flag≤1` and bits 4–5 ≥1. A row is `qualified=true` only if an image exists and the selected QA-valid count is positive; statistics are null otherwise. `valid_fraction` is `valid_count / total_count` only for qualified rows, and no minimum coverage threshold is applied. No imputation or interpolation is recorded.

## Daily coverage

| Scope | Calendar days | Image available | Missing image | Strict qualified | Permissive qualified |
|---|---:|---:|---:|---:|---:|
| Full supplied series (2026-01-01–2026-08-02 UTC) | 214 | 200 | 14 | 161 | 164 |
| Required baseline (2026-01-01–2026-02-27 UTC) | 58 | 58 | 0 | 47 | 48 |

Full-series missing product dates are: `2026-03-10, 2026-03-11, 2026-03-12, 2026-04-28, 2026-04-29, 2026-04-30, 2026-06-01, 2026-06-02, 2026-07-11, 2026-07-12, 2026-07-13, 2026-07-14, 2026-07-15, 2026-07-16`. They are represented as `image_available=false`, not as zero radiance. Image-present but zero-qualified-pixel days are separately represented as `image_available=true`, `qualified=false`, with null statistics.

## Independent checks

- CSV rows: `428`; raw JSONL rows: `428`; semantic CSV↔JSONL mismatches: `0`.
- Eight monthly chunks contain `200` actual product dates and exactly match the CSV image-available date set: `True`.
- CSV covers every calendar day from `2026-01-01` to `2026-08-02` with both QA modes: `True` / `True`.
- Chunk-derived row reconstruction mismatches: `0`.
- Recorded artifact hash mismatches: `0`; AOI hashes in ObservationPackage match: `True`.
- Checkpoint counts match independent derivation: `True`.

The complete check object, source hashes, semantic digests, and mismatch samples are in [daily-series-audit.json](daily-series-audit.json).

## Handoff boundary

The Analyst may use the strict baseline rows under the selection rule in [q19-data-contract.json](q19-data-contract.json), retain null/unqualified days as gaps, and use permissive rows as a sensitivity input. This audit does not calculate or endorse event-window conclusions, rankings, causation, outage, damage, recovery, or continuous monitoring.
