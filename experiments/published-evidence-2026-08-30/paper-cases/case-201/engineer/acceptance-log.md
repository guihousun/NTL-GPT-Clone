# CASE-201 NTL Engineer acceptance log

## Event Tracker acceptance

Accepted with an explicit runtime boundary.

- Source event time: `2025-03-28T06:20:52Z`.
- Recomputed local context: `2025-03-28T12:50:52+06:30` (`Asia/Yangon`).
- First post-event local night: `2025-03-29`.
- Candidate local acquisition interval: 00:30–02:30 Asia/Yangon, mapping to
  `2025-03-28T18:00:00Z`–`20:00:00Z` and therefore UTC product day
  `2025-03-28`.
- The Event Tracker manually read the hashed runtime Skill but did not invoke a
  deployed graph; this is a Codex-subagent simulation.

## Data Searcher acceptance

Accepted for the exact-date gate.

- Formal product: VNP46A2 Collection 002,
  `DNB_BRDF-Corrected_NTL`, UTC product date `2025-03-28`.
- The exact product is eligible for both supports under the existing formal
  strict-QA contract: 25 km `9802/9895` valid pixels and 50 km `39330/39575`.
- No later-date fallback, new GEE call, LAADS/CMR call, download, or raw-data
  rewrite occurred.

## Analyst authorization

The Analyst may now reuse the accepted Q18 formal table only to calculate and
verify support-specific pre-event baseline versus exact first-night comparison.
It must retain 25 km/50 km results separately and make no causal, outage,
damage, recovery, significance, runtime, or benchmark claim.
