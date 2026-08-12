---
name: ntl-common-workspace-and-artifact-contract
description: Enforce the isolated NTL-GPT workspace, artifact paths, manifests, and checksum rules shared by all four roles.
---

# Workspace and Artifact Contract

- Read assigned inputs from `/inputs/` or accepted package paths; write new artifacts only under `/outputs/`.
- Distinguish filesystem-tool paths from typed-contract paths: filesystem calls use virtual `/inputs/...` and `/outputs/...`, while `ArtifactRecord.path`, `artifact_manifest_path`, and other typed contract artifact fields must use workspace-relative `inputs/...` or `outputs/...` with no leading slash.
- Treat `/shared/` as read-only. Never write outside the current run workspace or invent an artifact path.
- A successful artifact must exist, be non-empty when applicable, have its actual path, byte size, media type, and SHA-256 recorded.
- Preserve failed scripts, logs, checks, and partial outputs for audit. A submitted job or zero exit code is not artifact validation.
- Return compact references in messages; keep large tables, logs, and binaries in files.
