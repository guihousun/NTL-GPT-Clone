# Q18 Event Tracker review — formal 25 km / 50 km Myanmar case

> Codex-subagent simulation. This is a bounded evidence review, not a deployment-version NTL-GPT run, a Deep Agents run, or a benchmark result.

## Verdicts

| Check | Verdict | Evidence and boundary |
|---|---|---|
| Mainshock identity | `supported_with_source_boundary` | The formal context fixes USGS `us7000pn9s`, Mww 7.7, depth 10.0 km, WGS84 epicentre `(95.936, 22.011)`, and `2025-03-28T06:20:52Z`. The event role log states that the supplied USGS/ReliefWeb materials are official-domain search snapshots; `mww` and `reviewed` are supplemented by the project-derived verified reference. This supports the anchor but does not upgrade the snapshots into full downloaded source records. |
| UTC and local-date semantics | `supported` | Raw JSON records `2025-03-28T06:20:52Z` as `2025-03-28T12:50:52+06:30` in `Asia/Yangon`. The UTC-indexed product `2025-03-28` is explicitly interpreted as the first post-event local night, `2025-03-29`; exact pixel acquisition time is not exposed. This is a product-date convention, not an instantaneous observation at the earthquake time. |
| Formal spatial supports | `supported` | The package and validation fix WGS84 ellipsoidal geodesic pixel-centre supports of 25 km and 50 km, with 9,895 and 39,575 candidate pixel centres respectively. Validation reports both supports and the critical pre-event/first-post-event rows available. They must remain separate support-specific comparisons. |
| Sixteen HDF inputs | `independently_verified` | The observation package inventories 16 official VNP46A2 Collection 2 HDF5 granules dated 2025-03-21…28 and 2026-07-24…31. This review checked existence, byte count, and SHA-256 for all 16; every listed value matched. No file was downloaded or regenerated. |
| No continuous post-event sequence | `supported` | The package states that no raw product after 2025-03-28 and before 2026-07-24 is present. The late July 2026 records are sparse and QA-unstable, so the package does not contain a continuous immediate post-event series. |
| No recovery claim | `required_boundary` | The formal README, evidence report, and Analyst log explicitly prohibit a recovery trajectory or recovery rate. The roughly 16-month gap and unstable late-follow-up QA prevent that inference. |
| No causal/outage/damage claim | `required_boundary` | The accepted result is observational and descriptive only. Neither the event context nor the analysis establishes earthquake causation, outage, physical damage, or statistical significance. |
| Subsequent-earthquake conflict | `preserved` | The event context retains the source disagreement between a reported M6.4 event (with 06:32 UTC in some material) and an M6.7 event (minutes later, without an exact time in the supplied excerpt). It is not normalized here and remains a possible temporal confounder. |

## What is available for a paper-facing handoff

The strongest supported wording is: the case anchors an independently decoded,
strict-QA-filtered VNP46A2 comparison to the USGS-reviewed Mww 7.7 mainshock,
using separate 25 km and 50 km geodesic supports. The first post-event contrast
is `−29.61%` at 25 km (six valid pre-event daily means) and `+4.92%` at 50 km
(seven valid pre-event daily means), in nW cm⁻² sr⁻¹. These are descriptive,
support-sensitive observations, not an event-impact or recovery estimate.

The qualified temporal statement is: the baseline uses 2025-03-21–27 UTC
products, the 2025-03-28 UTC product is interpreted as the 2025-03-29 local
night, and no supplied product bridges 2025-03-28 to 2026-07-24. Missing
strict-QA dates remain missing; they were not converted to zero radiance.

## Read evidence

The detailed path/byte/SHA-256 inventory is in the sibling
`artifact-manifest.json`. Key evidence hashes are:

- `formal-event-context.json`: `d71a3bc8e5032a0be54dd827a491b741cc77029287f12beceed180feb9563364`
- `formal-event-tracker-log.md`: `0b35da79aeeabde22ff0b9fc3f0e8f47b220265f8880d341e239c0706cca3cd2`
- `formal-observation-package.json`: `7d9379dd8f066a37ac876a05ea346de797d2dfd40bc891a21592aa684255a804`
- `formal-q18-validation.json`: `6dcd7afadcca92c80f5851777c6735c8f8f20d5fcad7e491d4dfd1b6d1c3fc0c`
- `evidence-report.json`: `e6e76424c946579522acf5edc895e780f60358a9cf86b66561beda5ed0164318`
- `formal-analysis-results.json`: `1d45e8d8c6bb03a4ac3aef03f5ee317419f79a2333bc949302fc81add5629cde`

All statements above refer to the dated formal package only. They do not update
the active manuscript or any earlier 25 km / 100 km case assets.
