# CASE-201 scientific and execution contract

## Frozen inputs

- Event: USGS `us7000pn9s`; authoritative input time
  `2025-03-28T06:20:52Z`.
- Local context: `Asia/Yangon` (`UTC+06:30` on this date), therefore local
  event time `2025-03-28T12:50:52+06:30`.
- Product: VNP46A2 Collection 002,
  `DNB_BRDF-Corrected_NTL`, UTC-indexed official HDF granules.
- AOI: WGS84 geodesic, pixel-centre 25 km and 50 km buffers centred at
  `(95.936, 22.011)`.
- QA and formal values: reuse the formal Q18 25/50 km package; do not tune or
  recompute raw pixels solely to match an expected number.

## Decision rule

1. Normalize the source event time to UTC and derive its named local context.
2. Determine whether it occurs after the candidate local night-time acquisition
   window on the event date. For this case, the event is after the candidate
   00:30–02:30 local window, so the first post-event local night is
   `2025-03-29`.
3. Convert that local candidate acquisition window to UTC. It maps to
   `2025-03-28T18:00:00Z`–`20:00:00Z`, so the matching UTC-indexed product
   date is `2025-03-28`.
4. Check only `2025-03-28` against the formal Q18 eligible-observation rule.
   If it fails, return `no_eligible_first_night_observation`; do not move to a
   later product date under the same label.
5. If eligible, compare the pre-event qualified daily means for each support
   with the exact first-night row.

## Boundaries

- The 00:30–02:30 local interval is a documented candidate timing window, not
  a claimed exact pixel acquisition time.
- The current supplied Q18 JSON normalizes to `+06:30`. Any earlier
  `+08:00` working-copy discrepancy is treated only as historical audit
  context; the source UTC timestamp plus `ZoneInfo("Asia/Yangon")` remains the
  authority for this Case.
- This case supports a timing/eligibility chain and support-specific descriptive
  comparison only. It does not support causal outage, damage, recovery,
  significance, or deployed-runtime claims.
