# Q19 Tehran：Engineer paper-facing evidence record

## Identity

This is a **Codex-subagent case-evidence simulation**. It records real local
role outputs produced in this experiment directory, but is not a deployed
NTL-GPT or Deep Agents runtime trace and is not evidence for the 200-task
benchmark or Full-vs-Single comparison.

## Accepted inputs and scope

- AOI: the geoBoundaries `City of Tehran` ADM2 / canonical Shahrestan polygon
  (about 628.22 km²). It is an administrative unit, not a claimed municipality
  or functional urban footprint.
- Product table: existing VNP46A2 daily city statistics, with strict QA as the
  primary result and permissive QA as sensitivity.
- Time basis: UTC. The source table reaches 2026-08-02; this analysis and its
  figure-input tables deliberately stop at 2026-07-31.
- Analysis design: qualified daily city means are aggregated descriptively;
  missing or unqualified dates are not imputed.

## Recomputed descriptive results

| Window | Strict QA qualified days | Strict mean (nW cm⁻² sr⁻¹) | Change vs. full baseline | Permissive QA change |
|---|---:|---:|---:|---:|
| Baseline: 2026-01-01—02-27 | 47 | 67.231835 | 0.000% | 0.000% (n=48; mean 65.202541) |
| Conflict evaluation: 02-28—04-07 | 20 | 55.619916 | −17.271% | −16.073% (n=20) |
| Fixed ceasefire evaluation: 04-08—04-21 | 11 | 61.358263 | −8.736% | −10.166% (n=12) |
| Extended monitoring: 04-22—07-31 | 83 | 59.752430 | −11.125% | −8.188% (n=84) |

The comparison uses the complete 2026-01-01—2026-02-27 baseline, not the
former 2026-02-14—2026-02-27 short window. No significance test or causal
analysis was performed.

## Event-selection finding

The Event Tracker can support a **qualified** spatial-selection statement only:
within the exact-coordinate, retained-attack subset for 2026-02-28—2026-04-21,
City of Tehran is first among 20 candidate ADM2 areas (142 of 248 assigned
records). The overall ranking is **indeterminate**, because only 958 of 2702
retained attack records have exact coordinates. Therefore this package does not
support calling City of Tehran the highest-ranked city without the qualifier.

`2026-04-22` is an institutional reporting date for a ceasefire extension; it
is not evidence that the ceasefire ended. The 2026-04-22—07-31 span is a
neutral extended-monitoring period, not a uniform ceasefire, recovery, or
peace phase.

## What the active manuscript may use after writing-task review

- The administrative-AOI identity, UTC date range, VNP46A2 daily-series
  provenance, and the newly recomputed descriptive values above.
- A qualified selection statement such as: “City of Tehran was selected as the
  first-ranked ADM2 within the retained exact-coordinate event subset; the
  event source does not establish a complete overall city ranking.”
- A caption can state that the blue line is a centred 14-day visual summary
  derived only from actual strict-QA observations (minimum three samples), with
  no interpolation; event dates are date-only markers.

## What remains unusable

- “City of Tehran, the highest-ranked city” without qualification.
- A claim that this rerun was a deployed NTL-GPT/Deep Agents execution or that
  it validates benchmark performance.
- Any causal statement that the conflict, ceasefire, outage, damage, or a
  specific event produced the radiance changes.
- A recovery or continuous-monitoring claim. The rerun performs no new live
  source query or new GEE extraction; it audits a dated existing series.

## Evidence paths

- Event audit: `role-outputs/event-tracker/event-selection.json`
- Data audit: `role-outputs/data-searcher/q19-data-contract.json`
- Analyst recovery: `role-outputs/analyst-recovery/q19-analysis-results.json`
- Independent Analyst crosscheck: `role-outputs/analyst-crosscheck/crosscheck.json`
- Engineer verification: `validation/engineer-q19-validation.json`
- Analyst future figure inputs: `role-outputs/analyst-recovery/q19-figure-input-daily.csv`
  and `role-outputs/analyst-recovery/q19-figure-input-events.csv`; Engineer's
  independently packaged schema-rich copies are in `derived/`.
