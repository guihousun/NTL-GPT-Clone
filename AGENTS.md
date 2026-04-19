# AGENTS.md

## Project Snapshot

This repository is a local Streamlit application for nighttime light analysis. The current codebase is organized around a UI shell, a long-running multi-agent runtime, and a large geospatial tool layer.

### Current Repository Map
- Entry/UI:
  - `Streamlit.py` is the main app entry.
  - `app_ui.py` renders the interface.
  - `app_state.py` initializes session-level defaults and config.
- Runtime orchestration:
  - `app_logic.py` manages run lifecycle, event streaming, stale-run recovery, and chat/result persistence.
  - `app_agents.py` exposes the cached graph builder used by Streamlit.
  - `graph_factory.py` builds the Deep Agents / LangGraph-style supervisor graph.
- Agent definitions:
  - `agents/NTL_Engineer.py`
  - `agents/NTL_Data_Searcher.py`
  - `agents/NTL_Code_Assistant.py`
  - `agents/NTL_Knowledge_Subagent.py`
- Data/context/persistence:
  - `storage_manager.py`
  - `history_store.py`
  - `file_context_service.py`
- Domain tooling:
  - `tools/` contains the geospatial, retrieval, preprocessing, rendering, and knowledge-base tools.
- Environment/bootstrap:
  - `environment.yml`
  - `.env.example`
  - `check_env.py`

### Current Working Assumptions
- Do not assume `.git` metadata is present in the workspace snapshot. Check before using git-based workflows.
- Do not assume `docs/` exists. In the current snapshot it may be absent; avoid creating placeholder docs unless the task actually needs milestone documentation.
- Do not assume the app is currently startup-clean. Validate touched runtime files before claiming boot success.

## Project Addendum: Runtime and Workspace Discipline

### Mandatory Runtime Rules
- Preserve the current thread-workspace model:
  - read user inputs from the thread workspace input area
  - write generated artifacts to the thread workspace output area
  - use `storage_manager` path helpers instead of hardcoded absolute local paths
- Treat shared/base data as read-only unless the user explicitly asks for data curation work.
- When changing agent routing or workflow logic, keep `graph_factory.py`, agent prompts under `agents/`, and tool registration under `tools/__init__.py` logically aligned.
- Keep long-running Streamlit session-state keys backward compatible when possible. `app_logic.py` contains the runtime heartbeat, stop/cancel, and event consumption contract; do not casually rename keys used across reruns.
- Centralize heuristics in orchestration or dedicated helper modules. Do not scatter ad hoc prompt keyword checks across UI, agent, and tool files.

### Recommended Validation Baseline
- For touched Python files, run `python -m py_compile` on the changed modules before finishing.
- For environment/bootstrap changes, run `python check_env.py`.
- For routing/workflow fixes, verify at least one neighboring prompt variation, not only the exact failing prompt.
- For file encoding concerns, verify with Python UTF-8 reads before declaring corruption.

## Project Addendum: Generalization-First Policy

This repository prefers robust, reusable capability upgrades over query-specific fixes.

### Mandatory Engineering Rules
- Avoid one-off hardcoded branches for a single case unless explicitly approved as a temporary hotfix.
- When fixing routing/workflow logic, abstract into intent/capability signals that can generalize to neighboring tasks.
- Any bugfix in a specific scenario must include at least one non-target variation test.
  Example: earthquake fix should also be validated on wildfire/conflict/flood style prompts.
- When adding heuristics, keep them centralized and documented; do not scatter ad hoc keyword checks across files.
- For complex tasks, prioritize the `using-superpowers` skill first to choose the right process/implementation skills before coding.
- Keep documentation lightweight but consistent:
  - `CHANGELOG.md` (high-impact engineering changes; batch minor tweaks)
  - `docs/NTL-GPT*.md` (product capability/version summary; milestone-level updates)
  - `docs/Skill_*.md` (optional; update only when process/skill norms materially change)
  - the legacy Codex Chinese change-log file under `docs/` is no longer a required maintenance target
- If `docs/` is absent for the current task, do not create empty placeholder files just to satisfy process language; update the closest real artifact instead.

## Project Addendum: Encoding Integrity

### Mandatory Text Rules
- Markdown/JSON/Python source files must be saved as UTF-8; prefer UTF-8 without BOM for docs.
- Do not paste or commit mojibake text in Chinese docs.
- If any encoding issue is discovered, fix encoding first, then continue feature changes.
- When deciding whether text is mojibake, prioritize Python UTF-8 parse results over terminal rendering.
- Terminal display artifacts (code page/font issues) are not sufficient evidence of file corruption.
- For suspected encoding issues, run UTF-8 parse checks first, then decide whether a fix is needed.

### Encoding Check Commands
```bash
python - << 'PY'
from pathlib import Path
p = next(Path('docs').glob('NTL-GPT*.md'))
b = p.read_bytes()
print('bom', b.startswith(b'\xef\xbb\xbf'))
b.decode('utf-8')
print('utf8_ok', True)
PY

python - << 'PY'
from pathlib import Path
bad_points = [0x9359, 0x7481, 0x951b, 0x9286, 0x9225, 0x20ac]
text = next(Path('docs').glob('NTL-GPT*.md')).read_text(encoding='utf-8')
hits = [(hex(cp), chr(cp)) for cp in bad_points if chr(cp) in text]
print('mojibake_hits', hits)
PY
```

### Recommended Quick Checklist
1. Is this fix capability-level or only case-level?
2. What neighboring tasks should also pass?
3. Do tests include at least one variation scenario?
4. Are version docs/release notes updated?
5. Did we confirm encoding via Python UTF-8 parsing before declaring mojibake?

## Project Addendum: Result Bus Isolation Policy

### Mandatory Runtime Safety Rules
- If users request cross-device result notifications, use an independent Git result bus repo (example: `E:\codex-result-bus`).
- Never run result-sync `git push/pull` operations inside the active project workspace.
- Consumer machine (OpenClaw) should pull and notify only; do not push back.
- If remote is unavailable, persist local snapshot commit first and report the missing remote as an actionable item.

### Recommended Skill
- `.agents/skills/git-result-bus-sync/SKILL.md`
