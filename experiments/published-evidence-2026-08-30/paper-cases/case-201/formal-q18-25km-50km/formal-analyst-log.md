# Q18 Formal NTL Analyst Log

- Completed (UTC): `2026-08-17T11:54:32.704305+00:00`
- Role: `NTL Analyst`
- Supervisor: `NTL Engineer`
- Status: `complete_descriptive_noncausal`
- Formal inputs only: yes
- Historical summaries, manuscript values, benchmark outputs/Gold, and legacy scripts read: no

## Fixed analysis

- Pre-event baseline: valid daily means from `2025-03-21` to `2025-03-27` UTC, equally weighted.
- A zero-valid-pixel day is missing and was not converted to zero radiance.
- First post-event local night: `2025-03-28` UTC product, interpreted as `2025-03-29` Asia/Yangon.
- AOIs: 25 km primary and 50 km spatial-sensitivity support.
- Late 2026-07 observations are listed separately and are not treated as recovery.

## Core results

- **25 km:** baseline mean `1.482539` (n=6, sample SD `0.271516`); first-night mean `1.043513`; difference `-0.439026` (`-29.61%`).
- **50 km:** baseline mean `0.833820` (n=7, sample SD `0.207723`); first-night mean `0.874851`; difference `+0.041031` (`+4.92%`).

Spatial-direction consistency: `False`.
The 25 km and 50 km AOIs show opposite first-night directions relative to their own pre-event baselines. Therefore the result is spatial-scale sensitive and does not support a scale-robust change claim.

These are descriptive nighttime-light observations. They do not establish outage, damage, earthquake causation, statistical significance, or recovery.

## Validation

- Reopened JSON, CSV, and PNG: passed.
- Recomputed both core differences from the formal input CSV: passed.
- JSON NaN/Inf protection (`allow_nan=False`): passed.
- Missing values use JSON `null` and blank CSV cells: passed.
- Mainshock/local-date semantics rechecked: passed.

## SHA-256

- `run_formal_q18_analysis.py`: `d7727b5cc61aa5ac8c276ae9106e11b516178bb5c9754b69b7a6a58cf60626b9`
- `formal-event-context.json`: `d71a3bc8e5032a0be54dd827a491b741cc77029287f12beceed180feb9563364`
- `formal-observation-package.json`: `7d9379dd8f066a37ac876a05ea346de797d2dfd40bc891a21592aa684255a804`
- `formal-q18-analysis-ready.csv`: `3c6777a41aa074a1357d25938120b026ab9cd7afa86bea3f419fbde64ce9d554`
- `formal-q18-validation.json`: `6dcd7afadcca92c80f5851777c6735c8f8f20d5fcad7e491d4dfd1b6d1c3fc0c`
- `formal-analysis-results.json`: `1d45e8d8c6bb03a4ac3aef03f5ee317419f79a2333bc949302fc81add5629cde`
- `formal-analysis-table.csv`: `6f51dff49017a286c380bc3489446639574924301b540cc9ca0970f103a07cff`
- `formal-analysis-preview.png`: `2f4c5fd207ead081b6da645bcc2a1e5d140ae05af5d33812f6b08e603df76b86`

## Interpretation limits

- The pre-event sample is small (six valid daily means at 25 km; seven at 50 km).
- QA coverage varies by date and is extremely unstable in the late follow-up subset.
- Season, lunar illumination, weather, land-cover/development change, and the long interval remain confounded.
- A strong subsequent earthquake was reported within minutes, but the supplied sources conflict on its magnitude; the conflict is preserved.
