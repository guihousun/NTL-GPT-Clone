---
name: ntl-engineer-handoff-acceptance
description: Let NTL_Engineer accept, revise, reject, or block typed specialist handoffs using the TaskPlan acceptance criteria.
---

# Handoff Acceptance

- Confirm the expected producer, opaque package reference, package type, SHA-256, status, and validation verdict. Runtime assignment/run/task identity is checked and injected by the system, not read or authored by the model.
- Check the package against the exact TaskPlan acceptance criteria and prohibited-change list.
- Accept only evidence that is complete enough for the next dependency. Request one bounded, directed revision when it is repairable.
- Route every revision through NTL_Engineer; specialists do not call each other.
- Block when required evidence, scientific semantics, permissions, or budget cannot be resolved safely. Preserve the rejected package and decision trace.
