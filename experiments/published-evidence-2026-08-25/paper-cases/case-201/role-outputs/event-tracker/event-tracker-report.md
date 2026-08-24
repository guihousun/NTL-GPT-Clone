# Case 201 Event Tracker report

## Outcome

Using the supplied generic implementation and the sole temporal authority
`2025-03-28T06:20:52Z`, the event normalizes to
`2025-03-28T12:50:52+06:30` in `Asia/Yangon`. The event is after the documented
local `00:30–02:30` candidate acquisition window, so the first post-event local
night is labelled **2025-03-29**. That candidate window maps to
`2025-03-28T18:00:00Z–20:00:00Z`; therefore the UTC-indexed VNP46A2 product date is
**2025-03-28**, with a one-day query end of `2025-03-29`.

The exact-date gate was run against the formal Q18 rows. The 25 km row has
9,802/9,895 strict-QA valid pixels and the 50 km row has 39,330/39,575; both
have non-null radiance means. The gate returned
`eligible_first_night_observation` for `2025-03-28`, and no later-date fallback
was used.

## Execution evidence

The local implementation was imported from
`implementation/gee_ntl_date_boundary_handling.py` and these functions were
actually executed:

- `determine_first_post_event_local_night`
- `utc_product_date_for_local_night`
- `exact_date_eligibility`
- `inclusive_end_to_exclusive`

The scoped contract tests were run with:

```text
python -m unittest discover -s experiments/paper-case-201-myanmar-first-local-night-2026-08-18/tests -p "test_*.py" -v
```

Result: **6 tests passed**. The tests cover UTC-to-Yangon normalization,
first-night rollover, UTC product-date mapping, exact-date terminal gating, an
eligible exact product, and the end-exclusive one-day boundary.

## Timezone conflict handling

The Case contract records a historical Q18 JSON local-field conflict involving
`+08:00`. The current supplied formal Q18 JSON and the checked legacy Q18 JSON
both contain the correct `2025-03-28T12:50:52+06:30` in `Asia/Yangon`; no
`+08:00` literal was present in the Q18 directory during this run. The conflict
is therefore preserved as a historical discrepancy declared by the contract,
not falsely attributed to the current supplied JSON. Neither old Q18 asset was
edited.

## Skill evidence and runtime boundary

The runtime Skill was manually read and hash-checked:

```text
runtime/.ntl-gpt/skills/gee-ntl-date-boundary-handling/SKILL.md
sha256 = 7f43d02a5db7b9cb3aa0381c26c0a96dfe5fd180fcf894384bf21e431ba0c8d9
```

The hash matches the Case version record. This run used the Skill rules as a
manually read, hash-bound contract and executed the Case-local companion
implementation. It was **not** a deployed NTL-GPT / Deep Agents runtime trace:
the deployed graph did not load the Skill for this Case, no runtime telemetry
exists, and no model call or benchmark result is claimed.

## Input hashes

| Input | SHA-256 |
|---|---|
| `case-201.contract.md` | `8e97e4a86a80e9fddd9d621686203020f9d2376408302b25a50551e08856c1b6` |
| `implementation/gee_ntl_date_boundary_handling.py` | `72a23d6cb0cf358d0548003fe423de4df62b3e325cd63d700ed6395788216b11` |
| runtime `SKILL.md` | `7f43d02a5db7b9cb3aa0381c26c0a96dfe5fd180fcf894384bf21e431ba0c8d9` |
| supplied formal `formal-event-context.json` | `d71a3bc8e5032a0be54dd827a491b741cc77029287f12beceed180feb9563364` |
| formal `formal-analysis-table.csv` | `6f51dff49017a286c380bc3489446639574924301b540cc9ca0970f103a07cff` |
| formal `formal-q18-validation.json` | `6dcd7afadcca92c80f5851777c6735c8f8f20d5fcad7e491d4dfd1b6d1c3fc0c` |

## Limitations

- The `00:30–02:30` interval is a candidate window, not an exact pixel
  acquisition timestamp.
- The generic implementation does not call GEE, download HDF5, inspect
  VNP46A1 `UTC_Time`, or recompute formal Q18 pixels.
- The eligibility result reuses the supplied formal Q18 QA rows; it is not a
  new observation acquisition.
- The event-time chain supports timing and exact-date eligibility only. It does
  not support outage, damage, recovery, causality, significance, deployed
  runtime, or benchmark claims.
