# Data Searcher review limitations

## Identity and scope

This file records the limitations of the **Codex-subagent case-evidence simulation** performed as the NTL Data Searcher review role on 2026-08-17. The review reopened existing packages and derived assets only. It did not rerun a remote query, download new data, regenerate a case table, rewrite an input raster, update a manuscript or figure, inspect Zotero, or evaluate the deployed NTL-GPT/Deep Agents runtime. It is not a 200-task benchmark result.

## Q17 — SDGSAT-1

- The original RGB and the preprocessed/calibrated analysis RGB are hash-identified and grid-consistent, but the analysis package treats the latter as user-supplied input. The full destriping, radiometric calibration and normalization chain was not recreated by this review.
- The calibration gains/biases and runtime source references in `formal-observation-package.json` document a contract; they do not prove that this review or this round applied those operations to the original raster.
- The RGB TIFF has no embedded band descriptions. R/G/B semantics rely on the package's runtime-contract evidence and user designation.
- RRLI/RBLI formula and NoData behavior were verified from the existing output metadata and finite spot checks, not by a full recomputation or a comparison against ground truth.
- Large ratio tails remain possible when the green denominator is small. This review does not choose thresholds, clip values, or validate mixed-light spectral purity.
- Existing classification/reference files were not used as evidence for this Data Searcher input review. This output therefore cannot claim classification accuracy.

## Q18 — Myanmar earthquake

- The 16 official HDF5 granules are a frozen supplied inventory. Full hash and readability checks establish integrity of those bytes, not current/live Earthdata availability or a new acquisition.
- The product date is a UTC-indexed granule date. Mapping `2025-03-28` to the first post-event local night `2025-03-29` is explicitly an interpretation; exact pixel acquisition time is not exposed in the HDF metadata.
- The 25 km and 50 km summaries use WGS84 geodesic pixel-centre inclusion and unweighted pixel means. They are not building-, population- or area-weighted measures.
- Strict QA yields zero-valid dates: five for 25 km and one for 50 km. These are preserved as missing; the review does not impute, interpolate or treat them as zero radiance.
- The supplied date set has a direct gap after the 2025-03-28 event product until 2026-07-24. The late follow-up block itself has very low qualified fractions on some dates. No recovery trajectory, recovery rate or continuous monitoring claim is supported.
- The separate 25 km and 50 km first-post contrasts are descriptive observations. They do not establish earthquake causation, power outage, physical damage, restoration, or statistical significance.

## Writing boundary for both cases

Allowed wording must stay at the level of verified input provenance, product/grid/QA semantics, analysis-ready artifact identity and bounded descriptive observations. The following are outside the writable scope of this review: deployed-system execution, role telemetry, Full-vs-Single performance, benchmark performance, causal event claims, and any preprocessing or recovery work not evidenced by the reopened assets.

