---
name: ntl-engineer-task-planning-and-routing
description: Let NTL_Engineer create a typed TaskPlan and choose direct, observation, analysis, or event-context routes without over-delegation.
---

# Task Planning and Routing

Normalize the objective, AOI, time, product requirements, outputs, scientific boundaries, acceptance checks, risks, and budget into a `TaskPlan`.

Use the direct fast path only when inputs are ready, all semantics are resolved, the operation is bounded and mature, no multi-temporal/event/modeling analysis is involved, and validation is immediate. Otherwise route sequentially through the required specialists:

- observations or acquisition → NTL_Data_Searcher;
- task-specific scientific analysis → NTL_Analyst;
- requested evolving-event context → NTL_Event_Tracker.

Record why every specialist was invoked or skipped.

Delegate with the native `task` tool using a self-contained natural-language
description. Include the objective, scientific scope, known inputs or opaque
parent package handles, requested typed scientific package, acceptance checks,
and limitations. Do not serialize AssignmentEnvelope or HandoffEnvelope JSON;
the runtime records task calls and returns as standardized process telemetry.
