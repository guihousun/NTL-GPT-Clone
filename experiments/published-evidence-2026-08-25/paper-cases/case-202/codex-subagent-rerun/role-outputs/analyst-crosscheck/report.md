# Q19 analyst cross-check

Codex-subagent simulation only; this is an independent recomputation from the specified daily CSV.

Input: `vault/ntl-gpt/experiments\paper-case-multiagent-2026-08-13\Q19-tehran-city-longseries\daily-vnp46a2.csv`

Qualified rows are filtered by `qualified=true`; windows are inclusive UTC date ranges. `relative_to_first_pct` is 100 × (window mean − w1 mean) / w1 mean, within the same QA mode.

## Baseline checks

| QA mode | expected n | recomputed n | status |
|---|---:|---:|---|
| strict | 47 | 47 | PASS |
| permissive | 48 | 48 | PASS |

## Window results

| QA mode | window | n | mean(mean) | relative to w1 (%) |
|---|---|---:|---:|---:|
| strict | w1 (2026-01-01..2026-02-27) | 47 | 67.231835 | 0.000000 |
| strict | w2 (2026-02-28..2026-04-07) | 20 | 55.619916 | -17.271460 |
| strict | w3 (2026-04-08..2026-04-21) | 11 | 61.358263 | -8.736296 |
| strict | w4 (2026-04-22..2026-07-31) | 83 | 59.752430 | -11.124796 |
| permissive | w1 (2026-01-01..2026-02-27) | 48 | 65.202541 | 0.000000 |
| permissive | w2 (2026-02-28..2026-04-07) | 20 | 54.722792 | -16.072609 |
| permissive | w3 (2026-04-08..2026-04-21) | 12 | 58.574162 | -10.165830 |
| permissive | w4 (2026-04-22..2026-07-31) | 84 | 59.863432 | -8.188500 |
