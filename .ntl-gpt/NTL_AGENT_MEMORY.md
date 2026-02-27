# NTL Agent Memory

This file is dedicated to NTL-GPT runtime memory and must not be mixed with Codex workspace policies.

## Scope
- Domain: nighttime light (NTL) geospatial workflows.
- Runtime roles: `NTL_Engineer`, `Data_Searcher`, `Code_Assistant`.

## Workspace Protocol
- Read inputs from `/inputs/` (thread-scoped workspace).
- Write artifacts to `/outputs/` (thread-scoped workspace).
- Use `storage_manager.resolve_input_path(...)` and `storage_manager.resolve_output_path(...)`.
- Never use hardcoded absolute local paths.
- `/shared/...` is read-only: it can be used as input via `resolve_input_path`, but all generated outputs must go to thread `/outputs/`.

## Execution Policy
- Prefer built-in tools when they fully satisfy intent.
- Delegate retrieval/metadata tasks to `Data_Searcher`.
- Delegate code validation/execution tasks to `Code_Assistant`.
- Keep handoff sequential and avoid unnecessary loops.

## Safety
- Keep all artifacts thread-scoped.
- Do not emit host absolute paths in user-facing UI.
- On file mismatch, report actionable recovery steps with logical paths.
