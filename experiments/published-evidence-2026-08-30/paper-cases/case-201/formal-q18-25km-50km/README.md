---
type: paper-case-formal-artifact
project_id: ntl-gpt
case_id: Q18-myanmar-earthquake
status: current-formal-case
created: 2026-08-17
---

# Q18 formal 25 km / 50 km Myanmar earthquake case

This is the current formal Q18 spatial-support package. It supersedes the
earlier root-level 25 km / 100 km formal package for paper-facing use, while
leaving those prior artifacts intact for reproducibility and audit.

## Fixed contract

- **Event anchor:** USGS `us7000pn9s`, Mww 7.7, 2025-03-28 06:20:52 UTC;
  `(95.936, 22.011)` WGS84.
- **Product:** official VNP46A2 Collection 2 HDF5, `DNB_BRDF-Corrected_NTL`.
- **Inputs:** the same 16 official HDF5 granules as the superseded package.
- **Spatial support:** WGS84 ellipsoidal geodesic 25 km and 50 km radii;
  pixel-centre inclusion and unweighted daily AOI means.
- **Temporal semantics:** qualified 2025-03-21–27 UTC pre-event daily means;
  first post-event product 2025-03-28 UTC, interpreted as the 29 March local
  night in Asia/Yangon.
- **Quality:** unchanged strict logical-AND Mandatory / cloud / snow QA mask.

## Formal result

| Support | Valid pre-event daily means | Pre-event mean | First post-event mean | Difference |
|---|---:|---:|---:|---:|
| 25 km | 6 | 1.482539 | 1.043513 | −29.61% |
| 50 km | 7 | 0.833820 | 0.874851 | +4.92% |

Units are nW cm⁻² sr⁻¹. The two support-specific comparisons are reported
separately; they are not pooled into a single change estimate.

## Interpretation boundary

The case can evidence a source-anchored, quality-qualified NTL workflow and a
transparent sensitivity comparison. It cannot establish earthquake causation,
power outage, physical damage, recovery, or statistical significance. Only the
first post-event local night is available near the event; the next observations
are about 16 months later and do not form a recovery trajectory.

## Files

- `formal-event-context.json` and `formal-event-tracker-log.md` — source-bounded
  event anchor.
- `build_formal_q18_timeseries.py`, `formal-observation-package.json`,
  `formal-q18-analysis-ready.csv`, and `formal-q18-validation.json` — data and
  QA contract.
- `run_formal_q18_analysis.py`, `formal-analysis-results.json`,
  `formal-analysis-table.csv`, `formal-analysis-preview.png`, and
  `formal-analyst-log.md` — descriptive comparison and its reproducible
  outputs.
- `formal-data-searcher-log.md` and `evidence-report.*` — role handoff and
  paper-facing boundary.
- `artifact-manifest.json` — reproducibility inventory and hashes.

The package is the current formal case evidence. It does not by itself update
the active manuscript; manuscript wording and figure replacement are handled
through the paper-writing handoff.
