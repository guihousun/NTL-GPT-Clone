---
name: ntl-common-structured-handoff
description: Persist typed NTL-GPT scientific packages and return concise native task results between Engineer and one specialist.
---

# Structured Handoff

- Only NTL_Engineer assigns specialist work. Specialists never dispatch one another.
- Read the Engineer's self-contained natural-language task for its objective, scientific scope, known inputs or parent package handles, requested typed package, acceptance checks, and limitations. Ask for a bounded clarification when a scientifically necessary item is unresolved. Do not require or construct AssignmentEnvelope or HandoffEnvelope JSON.
- Persist the full typed scientific package first, then return a concise normal task result using only the opaque package handle returned by the typed save tool.
- State status, exact package handle when saved, an evidence-based summary, validation verdict, limitations, and any revision need or structured error. Use `ready` only for a package whose validation passed; otherwise use `needs_revision`, `blocked`, or `failed` with an explicit reason.
- Runtime identity, timestamps, and standardized assignment/handoff process records are system-owned. Never discover, invent, or serialize them.
- A revision returns to NTL_Engineer; never create a hidden direct specialist-to-specialist control edge.
