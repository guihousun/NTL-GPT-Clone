# Case 201 paper-facing handoff

## Status and scope

Case 201 is complete as paper-case and supplementary workflow evidence. It is
not one of the formal 200 benchmark tasks, not a deployed NTL-GPT runtime trace,
and not Full-versus-Single performance evidence.

The case tests the scientific date chain for the 2025 Myanmar earthquake:

`event time → Asia/Yangon context → first post-event local night → UTC-indexed product date → exact-date QA eligibility → support-specific descriptive comparison`

## Accepted result

- USGS `us7000pn9s`: `2025-03-28T06:20:52Z` =
  `2025-03-28T12:50:52+06:30` in `Asia/Yangon`.
- First post-event local night: `2025-03-29`.
- Corresponding VNP46A2 UTC product date: `2025-03-28`.
- Auxiliary VNP46A1 `UTC_Time` at the containing event pixel:
  `2025-03-28T19:56:45Z` = `2025-03-29T02:26:45+06:30`; all valid
  `UTC_Time` pixels in the 25 km and 50 km supports mapped to local 29 March.
- Exact-date strict-QA support: `9,802/9,895` valid pixels at 25 km and
  `39,330/39,575` at 50 km.

| Support | Qualified baseline mean | First-night mean | Descriptive change |
|---:|---:|---:|---:|
| 25 km | 1.482538771460 | 1.043512511975 | −29.61% |
| 50 km | 0.833819996481 | 0.874851273979 | +4.92% |

Radiance units are nW cm⁻² sr⁻¹. The two supports are reported separately and
are not pooled.

## Evidence and validation

- Date-boundary contract and six passing unit tests: `implementation/`,
  `tests/`, and `validation/contract-test-result.json`.
- Event Tracker and Data Searcher acceptance: `role-outputs/event-tracker/`,
  `role-outputs/data-searcher/`, and `engineer/acceptance-log.md`.
- Analyst calculation and independent cross-check:
  `role-outputs/analyst-recovery/` and `role-outputs/analyst-crosscheck/`.
- Formal 25/50 km source package:
  `../paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/`.
- Official VNP46A1 timing verification:
  `../q18-vnp46a1-utc-time-verification-2026-08-20/`.

## Claim boundary

The evidence supports the local-night/UTC-product-date mapping, exact-date
eligibility, and two descriptive radiance comparisons. It does not establish
earthquake-caused outage, physical damage, recovery, causality, or statistical
significance. A later qualified observation must not be substituted and still
called the first post-event local night.
