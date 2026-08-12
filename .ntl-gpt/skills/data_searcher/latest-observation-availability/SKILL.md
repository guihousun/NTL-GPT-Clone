---
name: ntl-data-searcher-latest-observation-availability
description: Resolve the latest quality-eligible observation as of the benchmark or task cutoff without using future information.
---

# Latest Observation Availability

- Treat `as_of`, timezone, publication latency, and quality eligibility as part of the data contract.
- Query live availability with the allowlisted metadata/availability tools; do not infer a current date from nominal product cadence.
- Record query time, latest published period, latest quality-eligible observation, selected product/band, evidence source, and any allowed fallback.
- Distinguish unavailable, unpublished, uncovered, and quality-insufficient observations.
- Never refresh a frozen benchmark temporal answer inside the tested run or access evaluator Gold.
