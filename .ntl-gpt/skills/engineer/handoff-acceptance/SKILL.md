---
name: ntl-engineer-handoff-acceptance
description: Let NTL_Engineer validate a specialist's normal task result and typed scientific package against TaskPlan acceptance criteria.
---

# Handoff Acceptance

- Read the specialist's native task result for status, exact opaque package handle, evidence summary, validation verdict, limitations, and revision need or error.
- For a ready result, validate the opaque package handle and confirm the expected producer, package type, canonical SHA-256, and validation verdict. Runtime assignment/run/task identity and standardized handoff records are checked and written by the system, not read or authored by the model.
- Check the package against the exact TaskPlan acceptance criteria and prohibited-change list.
- Accept only evidence that is complete enough for the next dependency. Request one bounded, directed revision when it is repairable.
- Route every revision through NTL_Engineer; specialists do not call each other.
- Block when required evidence, scientific semantics, permissions, or budget cannot be resolved safely. Preserve the package and allow runtime telemetry to retain the native task/return trace; do not construct AssignmentEnvelope, HandoffEnvelope, or a handoff-decision JSON object.
