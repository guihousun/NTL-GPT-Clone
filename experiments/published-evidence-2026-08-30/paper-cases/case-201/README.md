# Case 201 — Myanmar first post-event local night

## Scope

This directory is a **paper-case / supplementary workflow evidence** package.
It is explicitly outside the formal 200-task benchmark:

- `case_id`: `CASE-201`
- `formal_benchmark_member`: `false`
- It does not change the 200-task denominator, benchmark scores, model usage,
  or formal Full-versus-Single results.

The route is a native **Codex-subagent simulation** led by the NTL Engineer.
It is not a deployed NTL-GPT / Deep Agents runtime trace. The current runtime
Skill is recorded and its rules are applied in a versioned, local contract; no
claim is made that a deployed graph loaded the Skill for this case.

## Scientific question

For the 2025-03-28 Myanmar earthquake (USGS `us7000pn9s`), determine the
first post-event **local** night in `Asia/Yangon`, map it to the corresponding
UTC-indexed VNP46A2 product date, verify whether that exact observation is
eligible under the formal Q18 QA contract, and compare formal 25 km and 50 km
pre-event baselines with that exact first-night observation.

## Frozen semantic chain

`event source time → UTC normalization → local timezone context → first post-event local night → UTC-indexed product date → exact-date eligibility gate`

The local first-night label and UTC product date are separate fields. An
unqualified exact-date observation is reported as unavailable; it must not be
silently replaced by a later night while still called the first night.

## Completed result

- USGS event time: `2025-03-28T06:20:52Z`, or
  `2025-03-28T12:50:52+06:30` in `Asia/Yangon`.
- First post-event local night: `2025-03-29`; corresponding UTC-indexed
  VNP46A2 product date: `2025-03-28`.
- Auxiliary VNP46A1 `UTC_Time` verification placed the containing event pixel
  at `2025-03-28T19:56:45Z` / `2025-03-29T02:26:45+06:30`; all valid timing
  pixels in the 25 km and 50 km supports mapped to local 29 March.
- Under the frozen strict-QA contract, the exact VNP46A2 date retained
  `9,802/9,895` valid pixels at 25 km and `39,330/39,575` at 50 km.
- Relative to the qualified pre-event baseline, the exact first-night mean was
  `-29.61%` at 25 km and `+4.92%` at 50 km. These are support-specific
  descriptive comparisons, not causal, damage, outage, recovery, or
  significance estimates.

## Existing data reused

- Q18 formal 25/50 km package under
  `../paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/`.
- The source date skill at
  `runtime/.ntl-gpt/skills/gee-ntl-date-boundary-handling/SKILL.md`.

No original HDF5, formal Q18 result, manuscript, Zotero record, benchmark
record, or runtime code is overwritten.

## Required outputs

- `case-201.query.md` and `case-201.contract.md`
- `skill/` version record and implementation-diff note
- generic date-boundary contract implementation and tests
- bounded Event Tracker, Data Searcher, and Analyst role outputs
- Engineer acceptance, independent validation, artifact manifest, and one-page
  paper-facing handoff
