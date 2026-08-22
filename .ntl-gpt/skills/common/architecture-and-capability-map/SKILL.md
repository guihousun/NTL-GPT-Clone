---
name: architecture-and-capability-map
description: Shared runtime memory for the four-role NTL-GPT routing and capability boundaries.
---

# Shared Runtime Architecture

This is a compact routing map reinforcing the versioned startup memory in
`.ntl-gpt/AGENTS.md`; it is not a replacement for the role prompts, typed
contracts, or domain methods in the role namespaces.

## Role boundaries

- `NTL_Engineer` owns task truth, planning, conditional routing, package
  acceptance, ordinary coding/execution, and final evidence synthesis.
- `NTL_Data_Searcher` owns product/date/AOI resolution, acquisition, standard
  preprocessing, QA, and observation provenance.
- `NTL_Analyst` owns nighttime-light-specific indices, thresholds, persistence,
  temporal/event analysis, NTL models, classification, figures, and scientific
  interpretation.
- `NTL_Event_Tracker` owns source-bounded event facts, timelines, as-of time,
  and source conflicts. It does not perform nighttime-light analysis.

## Routing rule

Route by scientific domain, not by apparent complexity. Complex but general
tabular statistics, generic GIS, deterministic file processing, plotting, and
report synthesis may remain with Engineer. Missing or time-sensitive
observations go to Data Searcher. Nighttime-light-specific methods or
interpretation go to Analyst. Event-source reconciliation goes to Event
Tracker. Specialists do not call one another; Engineer remains the supervisor.

Engineer and Analyst share the contract-checked local script runner. Engineer
may use it for ordinary deterministic work; Analyst uses it for assigned
nighttime-light science. A script still requires `ntl.script.contract.v2`, one
primary execution, and one final task-relevant validation. A package handle
means the save succeeded: reuse it, do not probe with new IDs or repeat an
unchanged validation.
