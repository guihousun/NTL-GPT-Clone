# AGENTS.md

## Project Addendum: Generalization-First Policy

This repository prefers robust, reusable capability upgrades over query-specific fixes.

### Mandatory Engineering Rules
- Avoid one-off hardcoded branches for a single case unless explicitly approved as a temporary hotfix.
- When fixing routing/workflow logic, abstract into intent/capability signals that can generalize to neighboring tasks.
- Any bugfix in a specific scenario must include at least one non-target variation test.
  Example: earthquake fix should also be validated on wildfire/conflict/flood style prompts.
- When adding heuristics, keep them centralized and documented; do not scatter ad-hoc keyword checks across files.
- Update both records after landing changes:
  - `docs/Codex_变更记录.md`
  - `docs/Skill_演进记录.md` (if a skill/process changed)

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
p = next(Path('docs').glob('Codex_*.md'))
b = p.read_bytes()
print('bom', b.startswith(b'\\xef\\xbb\\xbf'))
b.decode('utf-8')
print('utf8_ok', True)
PY

python - << 'PY'
from pathlib import Path
bad_points = [0x9359, 0x7481, 0x951b, 0x9286, 0x9225, 0x20ac]
text = next(Path('docs').glob('Codex_*.md')).read_text(encoding='utf-8')
hits = [(hex(cp), chr(cp)) for cp in bad_points if chr(cp) in text]
print('mojibake_hits', hits)
PY
```

### Recommended Quick Checklist
1. Is this fix capability-level or only case-level?
2. What neighboring tasks should also pass?
3. Do tests include at least one variation scenario?
4. Are change logs updated append-only?
5. Did we confirm encoding via Python UTF-8 parsing before declaring mojibake?

## Project Addendum: Result Bus Isolation Policy

### Mandatory Runtime Safety Rules
- If users request cross-device result notifications, use an independent Git result bus repo (example: `E:\codex-result-bus`).
- Never run result-sync `git push/pull` operations inside the active project workspace.
- Consumer machine (OpenClaw) should pull and notify only; do not push back.
- If remote is unavailable, persist local snapshot commit first and report the missing remote as an actionable item.

### Recommended Skill
- `.agents/skills/git-result-bus-sync/SKILL.md`
