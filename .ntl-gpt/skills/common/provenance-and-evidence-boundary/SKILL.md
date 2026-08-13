---
name: ntl-common-provenance-and-evidence-boundary
description: Preserve source provenance, temporal scope, uncertainty, and non-attribution boundaries across NTL-GPT roles.
---

# Provenance and Evidence Boundary

- Record the source/product identity, observation or publication time, retrieval `as_of`, and processing version.
- For each local input/output artifact, the model declares only its workspace-relative path, semantic role, and media type when known. The typed save layer binds its actual SHA-256 and byte count from the task workspace; the model must not compute, guess, copy, null-fill, or placeholder-fill those system-owned fields.
- Missing model-side checksum tooling is not missing scientific evidence and is never, by itself, a reason to block, fail, or request another delegation.
- Separate observed values from interpretation. Nighttime-light change is not by itself proof of cause, damage, outage, responsibility, or recovery.
- Preserve missing coverage, conflicts, quality limitations, fallback use, and alternative explanations.
- Do not read benchmark Gold or evaluator feedback during the tested run, and do not let post-run evaluation repair the result.
- State only what the recorded evidence and accepted parent contracts support.
