# Q18 Data Review — formal Myanmar earthquake 25 km / 50 km package

## Review identity and verdict

- **Execution context:** **Codex-subagent simulation**, NTL Data Searcher review role. This is a read-only audit of the existing formal package; it is not a deployed NTL-GPT/Deep Agents run and is not a 200-task benchmark evaluation.
- **Case:** `Q18-myanmar-earthquake`, current formal package `formal-25km-50km-20260817`.
- **Verdict:** `partial / analysis-ready with explicit quality and temporal limits`. All 16 declared official HDF5 inputs are present, readable, and hash-consistent. The analysis-ready table preserves QA-empty observations as missing. The supplied files contain only the event-near product and a late July 2026 follow-up block, so they do not support a continuous recovery trajectory.
- **Mutation boundary:** no HDF5, analysis table, observation package, manifest, event record, manuscript, figure, Zotero item, benchmark asset, or runtime file was modified.

## Evidence reopened and source inventory

The formal package, manifest, validation object, CSV and builder were parsed:

- `.../Q18-myanmar-earthquake/formal-25km-50km-20260817/formal-observation-package.json` — SHA-256 `7d9379dd8f066a37ac876a05ea346de797d2dfd40bc891a21592aa684255a804`.
- `.../artifact-manifest.json` — SHA-256 `353c71f0c2501479b50f1964e7267ecdbef885056485d185981dad2b41c3cf9b`.
- `.../formal-q18-analysis-ready.csv` — SHA-256 `3c6777a41aa074a1357d25938120b026ab9cd7afa86bea3f419fbde64ce9d554`; reopened with 32 rows.
- `.../formal-q18-validation.json` — SHA-256 `6dcd7afadcca92c80f5851777c6735c8f8f20d5fcad7e491d4dfd1b6d1c3fc0c`.
- `build_formal_q18_timeseries.py` — SHA-256 `f43b600d1e76ec4f2056287c9f4fd1c55fe7bbfccf883a66c5c2837ae0ca353e`; its HDF paths, date parsing, geometry, QA mask and missing-row handling were read at lines 26–55, 89–212 and 245–365.

The 16 inventory paths are the existing frozen official-HDF inputs under `experiments/benchmark-v1/temporal-freeze/2026-08-11/.../official_hdf5/`. This physical provenance path is recorded as an input location only; this case review does not evaluate or modify the 200-task benchmark.

## HDF5 existence, hash and readability

All 16 input files were opened with `h5py`; their declared byte counts and SHA-256 values were recomputed and matched the package inventory. The date blocks are:

- 2025-03-21 through 2025-03-28 (8 granules);
- 2026-07-24 through 2026-07-31 (8 granules).

Each file exposed the four required datasets at the expected HDF-EOS paths and each dataset was read at least at one sample position:

| Dataset | Shape and dtype | Metadata read |
|---|---|---|
| `DNB_BRDF-Corrected_NTL` | 2400 × 2400, `float32` | `_FillValue=-999.9000244140625`, scale `1.0`, offset `0.0`, radiance units `nWatts/(cm^2 sr)` |
| `Mandatory_Quality_Flag` | 2400 × 2400, `uint8` | fill `255`, high-quality code `0` |
| `QF_Cloud_Mask` | 2400 × 2400, `uint16` | fill `65535`, bit-field description present |
| `Snow_Flag` | 2400 × 2400, `uint8` | fill `255`, snow-free code `0` |

`StructMetadata.0` was present in all 16 files. Independent root-attribute reads found the same tile/grid signature across all granules: `h27v06`, VersionID/collection `002`, WGS84 geographic bounds 90–100°E and 20–30°N, 2400 × 2400 cells. The first HDF describes `HE5_GCTP_GEO` and the package records 15 arc-second spacing.

## Product, band, spatial support and QA

The package selects official VNP46A2 Collection 2 HDF5, band `DNB_BRDF-Corrected_NTL`, in `nW cm⁻² sr⁻¹`; it does not substitute a different band. The event anchor is USGS `us7000pn9s`, `(95.936, 22.011)` WGS84.

The two supports are predeclared and kept separate:

- 25 km: WGS84 ellipsoidal geodesic distance (`pyproj.Geod(ellps="WGS84")`) from pixel centre to the event point, inclusion `distance <= 25 km`, 9,895 pixel centres;
- 50 km: the same rule with `distance <= 50 km`, 39,575 pixel centres.

The reducer is an unweighted pixel mean (with median, population standard deviation and percentiles also retained). It is not a building-, population- or area-weighted estimate.

The strict QA mask is a logical AND of:

1. finite radiance, not radiance fill, and radiance ≥ 0 after scale/offset;
2. `Mandatory_Quality_Flag == 0`;
3. cloud-mask not fill, bit 0 = night, bits 4–5 ≥ 2, bits 6–7 ≤ 1;
4. cloud-mask bits 8, 9, 10, 12 and 13 equal zero (no shadow, cirrus, snow/ice, aurora or lunar-eclipse flag);
5. `Snow_Flag == 0` and not snow fill.

The logical-AND implementation is visible in `build_formal_q18_timeseries.py:167–212`, and the corresponding HDF paths are visible at lines 37–43.

## Dates, QA gaps and recovery boundary

- Event anchor: `2025-03-28T06:20:52Z` (12:50:52 Asia/Yangon).
- Pre-event UTC product dates: `2025-03-21`–`2025-03-27`.
- Event-day UTC product: `2025-03-28`, interpreted as the first post-event local night dated `2025-03-29`; this is a local-night interpretation, not an exact pixel acquisition timestamp.
- Later supplied dates: `2026-07-24`–`2026-07-31`.
- No raw product from `2025-03-29` through `2026-07-23` is present in this 16-file set. This is a coverage boundary of the supplied package, not a claim that the product was globally unavailable.

Independent CSV reread gives 16 rows per support, with the following QA-empty dates:

| Support | QA-valid dates | Explicit QA-empty dates | Pre-event valid days | First post-event valid |
|---:|---:|---|---:|---:|
| 25 km | 11/16 | 2025-03-23; 2026-07-24, 2026-07-27, 2026-07-29, 2026-07-30 | 6/7 | yes |
| 50 km | 15/16 | 2026-07-30 | 7/7 | yes |

Rows with zero QA-valid pixels retain blank radiance statistics and `qa_valid_fraction=0`; they are not encoded as zero radiance, imputed, or silently dropped. The reported pre-event means and first-post means reproduce from the CSV: 25 km `1.4825387715` → `1.0435125120` nW cm⁻² sr⁻¹ (−29.61%); 50 km `0.8338199965` → `0.8748512740` (+4.92%). These are separate descriptive support comparisons, not a pooled estimate.

The late follow-up block is also sparsely qualified (for example, on 2026-07-31 the table has 25/9,895 and 551/39,575 QA-valid pixels for 25/50 km). It cannot be treated as a recovery time series.

## What can be written from this audit

The following data/method statements are supported:

1. The formal case used 16 hash-identified official VNP46A2 Collection 2 HDF5 granules from two date blocks.
2. The selected band, grid/tile, radiance units, 25 km and 50 km geodesic pixel-centre supports, and strict logical-AND QA contract are traceable to the package, builder and reopened HDF metadata.
3. The 32-row analysis-ready table preserves product dates and QA-empty observations explicitly; the first post-event product is qualified for both supports and the two descriptive contrasts can be reported separately with their coverage limits.

## What cannot be written from this audit

Do **not** claim that the supplied files provide continuous post-event monitoring or a recovery trajectory/rate. Do not infer earthquake causation, outage, physical damage, restoration, or statistical significance from the two first-night contrasts. Exact pixel acquisition times, population/building-weighted effects, and current/live availability are not established by this frozen input review. The review also does not prove deployed NTL-GPT/Deep Agents execution, role telemetry, four-role performance, or benchmark performance.

