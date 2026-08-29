# NTL Engineer task plan — CASE-201

## Route

1. Read and freeze the current `gee-ntl-date-boundary-handling` Skill content
   and hash.
2. Delegate Event Tracker a bounded source-time → local-night → UTC-product-date
   decision and inconsistency audit.
3. Delegate Data Searcher a bounded exact-date product/QA eligibility audit for
   both formal Q18 supports.
4. Validate both inputs, then delegate Analyst a bounded reuse of formal Q18
   baseline/first-night values; no raw-data retuning or causal inference.
5. Engineer synthesizes an evidence record, tests, manifest, and paper-facing
   boundary handoff.

## Acceptance gates

- `2025-03-28T06:20:52Z` must normalize to `2025-03-28T12:50:52+06:30`.
- The local first-night label must be `2025-03-29` and the UTC-indexed product
  date must be `2025-03-28` under the documented candidate window.
- The exact `2025-03-28` product must be tested for eligibility without using a
  later date as an implicit substitute.
- Formal Q18 values must remain 25 km −29.61% and 50 km +4.92%.
- Any role result must be stored as Codex-subagent simulation evidence, not
  runtime telemetry.
