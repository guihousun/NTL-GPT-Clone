# NTL-GPT Runtime Memory

This file is the small, versioned startup memory for the Deep Agents runtime.
It is reference context, not a replacement for the active role prompts,
typed contracts, or role-scoped Skills.

## Four-role routing

- `NTL_Engineer` owns task truth, planning, conditional routing, ordinary
  coding/execution, package acceptance, and final EvidenceReport synthesis.
- `NTL_Data_Searcher` owns product/date/AOI resolution, acquisition, standard
  preprocessing, QA, and observation provenance.
- `NTL_Analyst` owns nighttime-light-specific indices, thresholds, persistence,
  NTL temporal/event analysis, models, classification, figures, and scientific
  interpretation.
- `NTL_Event_Tracker` owns source-bounded event facts, timelines, as-of time,
  and source conflicts; it does not perform nighttime-light analysis.

Route by domain rather than apparent complexity. Complex but general-purpose
tabular statistics, generic GIS, deterministic file processing, plotting, and
report synthesis may remain with Engineer. Missing observations go to Data
Searcher; nighttime-light-specific methods go to Analyst; event-source work
goes to Event Tracker. Specialists do not call one another.

Engineer and Analyst share a contract-checked local script runner. Engineer
may use it for ordinary deterministic work; Analyst uses it for assigned
nighttime-light science. Scripts require `ntl.script.contract.v2`, one primary
execution, and one final task-relevant validation. A persisted package handle
is authoritative: reuse it and do not probe with new IDs or repeat unchanged
validation. This startup memory is read-only during benchmark runs; workflow
changes belong in versioned prompts, Skills, and code.
