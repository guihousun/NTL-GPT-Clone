# Codex 变更记录

## [2026-02-26] v2026.02.26.09 Deep Agents Path Compatibility via StorageManager
### Scope
- Added Deep Agents virtual-path compatibility to `StorageManager` while preserving existing `inputs/outputs` behavior.
- Aligned `graph_factory.py` Deep Agents system prompt with actual workspace protocol.

### Files
- `storage_manager.py`
- `graph_factory.py`
- `tests/test_storage_manager_deepagents_paths.py`

### Changes
- `storage_manager.py`
  - Added `resolve_deepagents_path(...)`:
    - `/data/raw/<file>` -> `user_data/<thread_id>/inputs/<file>`
    - `/data/processed/<file>` -> `user_data/<thread_id>/outputs/<file>`
    - `/memories/<file>` -> `user_data/<thread_id>/memory/<file>`
    - `/shared/<file>` -> `base_data/<file>`
  - Added traversal-safe validation for virtual path tails (`..` rejected).
  - Extended workspace bootstrap to include `memory/` directory.
  - Kept legacy filename resolution path and shared-data fallback unchanged.
  - Added `list_workspace(...)` helper for `inputs/outputs/memory`.
- `graph_factory.py`
  - Replaced corrupted/misaligned Deep Agents prompt block.
  - Prompt now states canonical protocol (`inputs/outputs` + `storage_manager`) and documents `/data/*` as alias mapping.
  - Removed unsupported `write_todos`/hardcoded memory-file guidance from supervisor prompt text.

### Verification
- `conda run -n NTL-GPT pytest -q tests/test_storage_manager_deepagents_paths.py tests/test_code_read_workspace_file_tool.py tests/test_execute_output_thread_bound_write.py`
  - Result: `12 passed`
- `conda run -n NTL-GPT python -m py_compile storage_manager.py graph_factory.py tests/test_storage_manager_deepagents_paths.py`
  - Result: `exit 0`

