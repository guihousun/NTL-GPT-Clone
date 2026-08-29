# Case 202 — Tehran latest-available VNP46A2 extension

## Purpose

This versioned paper-case rerun extends the existing City of Tehran ADM2 daily
VNP46A2 series from its prior 2026-07-31 display cutoff to the latest GEE
collection product date returned at execution time. Its latest live refresh
reached 2026-08-19 UTC. The City-level strict-QA series contains an additional
valid 2026-08-12 observation; 2026-08-13 through 2026-08-19 remain explicit
City-AOI gaps: direct checks found no valid raw radiance pixels, so they are
not filled values. It recomputes the same fixed
descriptive windows and creates a new standalone line chart.

It is a paper-case / supplementary workflow-evidence asset. It is not part of
the formal 200-task benchmark, not a deployment-runtime trace, and does not
replace or modify prior Q19 or Case 202 assets.

## Frozen scientific contract

- AOI: the existing geoBoundaries `City of Tehran` ADM2 / canonical Shahrestan
  polygon; no event-point buffer and no Draw.io update.
- Product: `NASA/VIIRS/002/VNP46A2`, `DNB_BRDF_Corrected_NTL`, Collection 2.
- Primary time basis: UTC product day.
- Primary QA: the existing strict VNP46A2 mask; permissive QA is retained only
  as a descriptive sensitivity check.
- Fixed windows: baseline 2026-01-01–02-27, conflict 2026-02-28–04-07, and
  ceasefire evaluation 2026-04-08–04-21, all UTC and inclusive.
- The post-2026-04-21 span is named `extended monitoring`; it is not presented
  as a homogeneous ceasefire, recovery, or peace period.
- The visual and descriptive extension endpoint is the live GEE collection
  date. All observed statistics use only strict-QA-qualified City of Tehran
  values; a later unavailable product day remains a gap, not an estimated or
  gap-filled observation.
- The line chart uses actual strict-qualified daily values and a trailing
  14-calendar-day mean emitted only when its window contains at least three
  actual observations. A horizontal dashed continuation reaches the live GEE
  endpoint solely to mark the subsequent quality gap; missing values are
  neither interpolated nor imputed.

## Outputs

- `daily-vnp46a2.csv` and `gee-chunk-*.json`: live observation extraction.
- `outputs/analysis-window-summary.csv`: strict and permissive descriptive
  summaries.
- `outputs/analysis-results.json`: calculated values, comparison with the
  2026-08-17 evidence record, and claim limits.
- `outputs/case202-tehran-latest-timeseries.{svg,pdf,png,tiff}`: standalone
  line chart only; no Draw.io or manuscript attachment is altered.
- `qa/`: source, numerical, export, and visual-QA records.

## Claim boundary

The chart and summaries describe quality-screened nighttime-light observations.
They do not establish conflict causation, outage, damage, recovery, or a
complete event census. The retained source-reported timeline remains in the
evidence record but is intentionally not rendered in this standalone chart.
