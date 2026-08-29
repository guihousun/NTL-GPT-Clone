# NTL-GPT published experiment evidence

This directory is a GitHub-ready, derived evidence bundle generated from the active Research Vault experiment records on 2026-08-30. It is not a new runtime execution.

## Included evidence

- `benchmark/`: the current 200-task reconciled final record (Full 176/200; matched Single-Agent 170/200), per-task result tables, and resource summaries. The record is a dirty-runtime dated reconciliation, not a clean-release reproducibility claim.
- `paper-cases/case-201/`: Myanmar first post-event local-night timing, formal 25/50 km descriptive comparison, and VNP46A1 `UTC_Time` timing verification.
- `paper-cases/case-202/`: Tehran event-selection evidence, the Codex subagent reconstruction, and the latest VNP46A2 extension through the GEE collection endpoint of 2026-08-19 UTC.
- `paper-cases/case-203/`: SDGSAT-1 classification scripts, statistics, preview, and final classification GeoTIFF.

## Deliberate exclusions

Raw HDF5 inputs, RRLI/RBLI intermediate GeoTIFFs, the 32 MB Tehran TIFF, caches, Python bytecode, credentials, and local absolute paths are not published. `public-artifact-manifest.json` is the integrity manifest for this sanitized bundle; it replaces upstream manifests whose hashes bind to omitted or path-redacted local artifacts.

## Evidence boundary

Case 201–203 are paper-case/supplementary workflow evidence and are not members of the formal 200-task benchmark. They are Codex-subagent workflow reconstructions, not deployed NTL-GPT runtime telemetry or Full-versus-Single performance evidence.

Source runtime commit recorded by the source experiment package: `14b95a2379d7d2a53e6df3adf1f1d6a51b086dec`.
