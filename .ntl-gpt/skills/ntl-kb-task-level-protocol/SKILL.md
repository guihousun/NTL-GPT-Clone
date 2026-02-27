---
name: ntl-kb-task-level-protocol
description: Use when applying task-level proposal and retrieval contract protocol from NTL_Knowledge_Base_Searcher to Engineer/Data_Searcher handoff.
---

# NTL KB Task-Level Protocol

## Purpose
Extract only protocol logic from `tools/NTL_Knowledge_Base_Searcher.py`:
- `proposed_task_level`
- `task_level_reason_codes`
- `task_level_confidence`
- handoff contract consistency

## Scope
- This skill governs decision protocol and schema consistency.
- This skill does NOT replace runtime retrieval/generation code.

## Leveling Rules
1. Produce preliminary level proposal (`L1|L2|L3`) from KB intent.
2. Attach reason codes from shared set:
- `built_in_tool_matched`
- `download_only`
- `analysis_with_tool`
- `no_tool_custom_code`
- `algorithm_gap`
- `low_confidence_match`
3. Keep confidence numeric in `[0,1]`.
4. Engineer remains final authority and may upgrade level with justification.

## Contract Rules
- Preserve envelope consistency with retrieval contracts (for downstream handoff).
- Keep level and reason codes consistent across:
  - KB output intent block,
  - Engineer handoff packet,
  - Data_Searcher final contract.

## Guardrails
- No per-query hardcoded shortcuts.
- If confidence is low, prefer explicit uncertainty + recommended escalation.
- Do not remove runtime tools just because protocol is documented as a skill.
