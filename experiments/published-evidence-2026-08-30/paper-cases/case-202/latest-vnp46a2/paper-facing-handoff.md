# Case 202 — latest usable City of Tehran observation

## What changed

This paper-case evidence rerun retained the frozen City of Tehran ADM2 AOI,
VNP46A2 radiance band, strict QA mask, UTC basis, and three fixed comparison
windows. It extended only the neutral `extended monitoring` span.

At the live GEE refresh time, the collection contained VNP46A2 images through
**2026-08-19 UTC**. The direct August refresh recovered a valid City of Tehran
observation on **2026-08-12 UTC** under the frozen strict QA mask. Products on
2026-08-13–19 remained present but had no valid raw City pixels and are shown
as explicit gaps. NASA CMR, queried separately on 20 August, listed the Tehran
`h23v05` product through **2026-08-12 UTC**.

## Strict-QA descriptive results

| UTC period | Strict-qualified days | Mean ANTL (nW cm^-2^ sr^-1^) | Change from baseline |
|---|---:|---:|---:|
| Pre-conflict baseline, 2026-01-01–02-27 | 47 | 67.231835 | reference |
| Conflict evaluation, 2026-02-28–04-07 | 20 | 55.619916 | -17.271% |
| Ceasefire evaluation, 2026-04-08–04-21 | 11 | 61.358263 | -8.736% |
| Extended monitoring, 2026-04-22–08-19 | 90 | 59.254863 | -11.865% |

The first three values are unchanged from the complete-baseline rerun. The
extended-monitoring mean changes from 59.752430 through 2026-07-31 to
59.254863 through 2026-08-19, a difference of -0.497567 nW cm^-2^ sr^-1^.

## Safe paper-facing wording

> At the time of the live GEE refresh on 21 August 2026 UTC, the VNP46A2 collection contained images through 19 August 2026 UTC. The City of Tehran daily series retained a strict-QA-qualified value through 12 August; product dates from 13 to 19 August had no valid raw City pixels under the fixed product, band, and AOI contract and were shown as gaps. The fixed baseline, conflict-evaluation, and ceasefire-evaluation summaries were unchanged.

## Do not write

- Do not call 12 August the latest global VNP46A2 image, or treat the dashed
  13–19 August connector as observed ANTL.
- Do not turn the neutral post-21-April span into a recovery, peace, or uniform
  ceasefire period.
- Do not infer that observed radiance differences were caused by conflict,
  damage, outages, or recovery.
- Do not describe this Codex-subagent paper-case evidence as a deployment
  runtime trace or formal benchmark result.

## Deliverables

- New line chart: `outputs/case202-tehran-latest-timeseries.{svg,pdf,png,tiff}`
- Results and traceable availability: `outputs/analysis-results.json`,
  `qa/cmr-availability.json`, `observation-package.json`
- Independent and Engineer checks: `qa/independent-audit/`,
  `qa/engineer-validation.json`
