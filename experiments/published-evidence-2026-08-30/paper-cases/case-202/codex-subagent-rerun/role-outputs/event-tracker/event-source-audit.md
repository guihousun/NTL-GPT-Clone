# Q19 Event-source and city-selection audit

**Role and execution identity:** `NTL_Event_Tracker`, **Codex-subagent simulation**. This is a bounded local evidence audit, not a deployment run of NTL-GPT and not a claim about Deep Agents, system telemetry, or continuous monitoring. No live query was performed.

## Decision

- Claim under audit: `City of Tehran is highest-ranked`.
- Unqualified verdict: **indeterminate** as a complete event-census claim.
- Qualified result: **supported on the exact-coordinate retained attack subset**. `City of Tehran` has **142** assigned records and ranks 1st among the **20** candidate ADM2 features; the next candidate (`Tehran`) has **29**.
- The complete ranked table is [city-ranking.csv](city-ranking.csv); the machine-readable rule and verdict are [event-selection.json](event-selection.json).

The distinction is necessary: the source snapshot has **2702** retained attack records in the ranking window, but only **958** have a valid `coord_type=exact` coordinate. The geometry join assigns **248** of those exact records to the 20-feature candidate context; **710** exact records fall outside that candidate context. A source `city` string is retained as a diagnostic only and is never used to force a polygon assignment.

## Event source and snapshot

The ranking input is the frozen common-window CSV:

`vault/conflictntl/data/raw/events/source-events/ISW_storymap_events_2026-02-27_2026-04-27.csv`

- Rows: **2790**; SHA-256: `b469f0f073f7392f780604c2a1a9a9f933dddef1be99ba1f1efbb894a411cb13`.
- Companion metadata: `vault/conflictntl/data/raw/events/source-events/ISW_storymap_events_2026-02-27_2026-04-27_metadata.json`; SHA-256: `ed865ab0f327d0acb257d914e01a022bd6c711fe8891253ea0457c44f293b056`.
- The metadata records `records_all=2874`, `records_filtered_common_window=2790`, StoryMap item modified at `2026-05-12T20:59:59Z`, and pulls generated at `{'combined_force_pull': '2026-05-13T02:14:11.589050Z', 'iran_axis_retry_pull': '2026-05-13T02:15:37.476350Z'}`.
- The local common-window CSV is derived from two dated per-layer snapshots: combined-force `vault/conflictntl/data/raw/events/storymap-snapshots/2026-05-13/combined_force_isw_storymap_events.csv` (1384 rows; SHA-256 `7cf4065754dfbe5fec0fea7826df7666672a70b8e6888ec3c1f7c06d67170c88`) and Iran-axis `vault/conflictntl/data/raw/events/storymap-snapshots/2026-05-13/iran_axis_isw_storymap_events.csv` (1490 rows; SHA-256 `c7827e79ae1e2479c8c01ad50248700960b7fcc4de3a44b521a0c86f4022bcb1`). Their metadata and layer URLs are recorded in `event-selection.json` and `artifact-manifest.json`.
- The source event layer is the ArcGIS StoryMap/FeatureServer snapshot identified by the per-layer metadata, not a live query at audit time.

### Field semantics used

| Field | Use in this audit |
|---|---|
| `event_family` + `objectid` | Layer-local record identity and duplicate check; this pair is unique in the common-window CSV. |
| `event_id` | Source event identifier retained for provenance; not unique in this snapshot and therefore not used alone for deduplication. |
| `event_date_utc` | Source event calendar date. The nullable `time_utc` is not filled with a synthetic time. |
| `event_type` | Source classification used by the explicit retained attack-type allowlist below. |
| `latitude`, `longitude` | WGS84 point coordinates, read as `(longitude, latitude)` for GeoJSON/CRS84 geometry. |
| `coord_type` | Spatial-quality flag. Only normalized `exact` is assigned to ADM2 polygons. |
| `city`, `country` | Source labels for diagnostics; neither replaces point-in-polygon allocation. |
| `source_1`, `source_2`, `sources` | Source-link provenance carried through but not re-fetched. |

## Retention and spatial assignment

1. Date filter: `event_date_utc` in the inclusive UTC calendar interval **2026-02-28 through 2026-04-21**, equivalent to `[2026-02-28T00:00:00Z, 2026-04-22T00:00:00Z)`. This is the union of the fixed conflict and ceasefire-evaluation windows.
2. Event filter: retain the named attack/strike labels `Anti-Tank Fire, Confirmed Airstrike, Direct Engagement, Drone & Missile Attack, Drone & Rocket Attack, Drone Attack, Missile Attack, Mortar Attack, Report of Explosion with Footage, Reported Airstrike, Rocket Attack`. Labels such as `unknown`, `Air Defense Activity`, `Evac Notice`, and `Other (see note)` are not silently treated as attacks.
3. Coordinate filter: require `coord_type=exact` (case-insensitive), finite latitude/longitude, and valid WGS84 bounds. General town, general neighborhood, POV, blank, and other non-exact records remain in the denominator but are not allocated.
4. Boundary input: `vault/ntl-gpt/deliverables/figure-drafts/ntl-gpt-case-figures-unified-2026-08-17-v9-formal-25km-50km/assets/map-sources/tehran-adm2-neighbours-v7.geojson` (20 valid non-empty ADM2 polygons; SHA-256 `98386cd2ae02fed9f0c8d1f539b62ec3d020c056e2597218c5f2861742f88403`). The Q19 target is the exact source feature `City of Tehran`, shape ID `26516999B29761828880922`, from `vault/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q19-tehran-city-longseries/tehran-boundary.geojson`; its metadata identifies canonical semantics as geoBoundaries ADM2 / Shahrestan, not a municipality.
5. Assignment predicate: `polygon.covers(Point(longitude, latitude))`; boundary points are included, no nearest-city fallback or event buffer is used. The candidate polygons had no positive-area overlaps in the audit.

## Candidate ranking (top 10)

| Rank | Source `shapeName` | Assigned exact attack records | Q19 target |
|---:|---|---:|:---:|
| 1 | City of Tehran | 142 | yes |
| 2 | Tehran | 29 | no |
| 3 | Karaj | 18 | no |
| 4 | Pakdasht | 11 | no |
| 5 | Rey | 10 | no |
| 6 | Malard | 6 | no |
| 6 | Paveh | 6 | no |
| 8 | Savojbolagh | 5 | no |
| 9 | Shahriar | 4 | no |
| 9 | Qods | 4 | no |

The CSV preserves all 20 features, including zero-count features and source-name distinctions such as `Tehran`, `City of Tehran`, `Shahriar`, and `Shahariar`; no spelling or administrative-unit merge was applied.

## Conflict start and window semantics

- The source snapshot's first event date is **2026-02-28**. That is the first date present in this snapshot and the fixed conflict-window start; it is **not independently established here as the political conflict onset**.
- The rerun contract baseline is **2026-01-01 through 2026-02-27 UTC**. The source snapshot contains no records before 2026-02-28, so it cannot demonstrate no pre-conflict attacks. An older Q19 context artifact used 2026-02-14 as its preconflict start; that historical choice is not used to override the rerun contract.
- **2026-02-28–2026-04-07** and **2026-04-08–2026-04-21** are statistical analysis windows, not a complete political chronology.
- The dated context sources record an initial ceasefire background on April 8, a U.S. extension announcement on April 21, and a UN note welcoming/reporting that extension on April 22. **April 22 is not treated as a ceasefire end date.** April 22 onward is an extended monitoring span with intermittent or later hostilities, not a homogeneous ceasefire, recovery, or peace phase.

## Non-causal boundary

Event points and source markers contextualize observation windows only. They do not prove attribution, damage, outage, causation, recovery, or a nighttime-light response to any particular event.

## Audit files

- [event-selection.json](event-selection.json): structured rule, counts, verdict, timeline semantics, and hashes.
- [city-ranking.csv](city-ranking.csv): 20-candidate ranking.
- [limitations.md](limitations.md): exact limitations and interpretation boundary.
- [artifact-manifest.json](artifact-manifest.json): input/output hashes and row/feature counts.
