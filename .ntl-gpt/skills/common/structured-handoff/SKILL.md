---
name: ntl-common-structured-handoff
description: Create and return typed NTL-GPT packages and compact handoff envelopes between Engineer and one specialist.
---

# Structured Handoff

- Only NTL_Engineer assigns specialist work. Specialists never dispatch one another.
- Validate the model-facing `ntl.assignment.v1` target, accepted parent references, output type, acceptance checks, prohibited changes, and budget before acting. Runtime identity and timestamps are intentionally absent and system-injected; never discover or invent them.
- Persist the full typed package first, then return a compact `ntl.handoff.v1` draft using only the opaque package reference returned by the typed save tool.
- Use `ready` only for a package whose validation passed. Use `needs_revision`, `blocked`, or `failed` with an explicit reason and standard error code otherwise.
- A revision returns to NTL_Engineer; never create a hidden direct specialist-to-specialist control edge.
