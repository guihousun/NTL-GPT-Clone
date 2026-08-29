# Q18 Formal NTL Data Searcher Log — 25 km / 50 km

- Completed: `2026-08-17`
- Role: `NTL Data Searcher`
- Supervisor: `NTL Engineer`
- Status: `analysis_ready_with_missing_quality_observations_and_temporal_coverage_limitation`

## Scope accepted from the Engineer

Prepare a VNP46A2 analysis-ready series for the USGS `us7000pn9s` event anchor
using 25 km and 50 km WGS84 geodesic supports. Do not change the event,
product, date semantics, quality mask or inference target.

## Data and spatial contract

- 16 official VNP46A2 Collection 2 HDF5 inputs were decoded independently.
- The selected band is `DNB_BRDF-Corrected_NTL` in nW cm⁻² sr⁻¹.
- AOI membership uses WGS84 ellipsoidal distance from `(95.936, 22.011)` to
  each pixel centre; 25 km contains 9,895 centres and 50 km contains 39,575.
- The strict QA contract is the logical AND of physical radiance validity,
  high mandatory quality, night / clear-cloud criteria, no cloud-mask flags,
  and snow-free pixels. It is unchanged from the superseded 25/100 km package.

## Coverage handoff

- 25 km has 11/16 dates with at least one strict-QA pixel; 2025-03-23 and four
  late-follow-up dates are explicit missing observations.
- 50 km has 15/16 dates with at least one strict-QA pixel; 2026-07-30 is an
  explicit missing observation.
- The pre-event window and first post-event product are qualified for both
  supports. No continuous official series is available between 2025-03-28 and
  2026-07-24 in this package.

## Handoff to the Analyst

Use only `formal-q18-analysis-ready.csv` with the accepted 25 km / 50 km
supports. Preserve missing dates as missing, compare the qualified pre-event
daily means with the first post-event product, and report the approximately
16-month temporal gap as a recovery-analysis limit.
