# Q19 Event-selection limitations

**Identity:** `NTL_Event_Tracker`, **Codex-subagent simulation**. These limitations apply to the local audit only; no deployment, Deep Agents execution, system telemetry, or live event monitoring is claimed.

## Verdict boundary

`City of Tehran is highest-ranked` is **indeterminate** if read as an exhaustive ranking of all attacks in the source period. It is **supported conditionally** for the reproducible subset defined here: named attack types, UTC dates 2026-02-28–2026-04-21, valid exact coordinates, and point-in-polygon allocation to the 20 supplied candidate ADM2 features. Under that subset, `City of Tehran` ranks first with **142** records versus **29** for `Tehran`.

## Data coverage and spatial support

- The ranking input is the frozen `2790`-row common-window CSV, derived from the 2026-05-13 per-layer StoryMap snapshots. The source metadata reports the common-window snapshot through 2026-04-27; no live refresh was attempted.
- The fixed ranking interval retains **2702** named attack records. Only **958** (35.455%) have valid exact coordinates. **1744** retained records have general town, general neighborhood, POV, blank, or other non-exact spatial support and cannot be assigned reliably to an ADM2 polygon from the available point fields.
- The 20-feature candidate set receives **248** exact records; **710** exact records lie outside the supplied candidate polygons. This is expected for an administrative context subset and is not a ranking of all 432 IRN ADM2 units in the historical full cache.
- The source `city` field is not a geometry. It matches candidate names for **467** retained rows, including **263** non-exact rows; these labels are diagnostic only. In particular, **237** non-exact records carry `city=Tehran`, enough to show why a complete city ranking cannot be inferred from exact points alone.
- The candidate file contains separate source features `Tehran` and `City of Tehran`, as well as `Shahriar` and `Shahariar`; this audit preserves their shape IDs and does not silently merge or correct them. The selected Q19 target is `City of Tehran`, whose geoBoundaries metadata describes ADM2 / canonical Shahrestan semantics, not a municipality or functional urban footprint.

## Source and classification limits

- `event_type` values are source classifications. This audit retains explicit attack/strike labels and excludes `unknown`, `Air Defense Activity`, `Evac Notice`, and `Other (see note)` from the primary count. Sensitivity checks show the top candidate remains `City of Tehran` for combined-force airstrike labels only (142 target records) and for all exact event types (143 target records), but this does not repair missing spatial support.
- `event_id` is not unique in the common-window CSV. The audit verifies uniqueness of `(event_family, objectid)` and uses that layer-local pair as identity. No arbitrary deduplication by event ID was performed.
- The nullable `time_utc` field is not converted to a fabricated timestamp. Calendar dates are used as source-reported UTC dates; date-only political markers remain date-only.
- The 200-point `tehran-isw-exact-airstrikes-v7.geojson` is a display/context derivative of the combined-force layer. It is recorded and hashed, but is not used as the complete ranking input.

## Window and event-date semantics

- The source's first record date, 2026-02-28, is a snapshot observation boundary and the fixed conflict-window start, not proof of when the conflict politically began.
- The rerun contract requires the pre-conflict baseline 2026-01-01–2026-02-27. The source snapshot starts on 2026-02-28, so baseline event absence cannot be assessed from this file.
- 2026-02-28–04-07 and 04-08–04-21 are analysis windows. The April 8 marker is a public UN reporting/background date for the initial two-week ceasefire announcement; the source context records the U.S. extension announcement on April 21 and the UN note on April 22.
- **April 22 must not be written as “the ceasefire ended.”** It is an institutional reporting/welcome date for the extension. April 22 onward is an extended monitoring span with intermittent fire and later anchors, not a single ceasefire/recovery/peace phase.

## Scientific interpretation boundary

The ranked event counts can justify a conditional administrative-selection statement only. They do not prove that Tehran received more physical attacks in an unobserved complete census, do not establish responsibility or damage, and do not establish that any nighttime-light change was caused by an event.
