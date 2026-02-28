---
name: workflow-intent-router
description: Route tasks to intent-scoped workflow JSON files, then select concrete workflow steps with minimal token usage.
allowed-tools:
  - NTL_Solution_Knowledge
compatibility: "ntl-gpt>=1.0"
license: "Proprietary"
metadata:
  schema: "ntl.workflow.intent.router.v1"
  router_index: "/skills/workflow-intent-router/references/router_index.json"
  workflows_root: "/skills/workflow-intent-router/references/workflows"
  learning_mode: "posterior_only"
---

# Workflow Intent Router

## Purpose
Minimize workflow retrieval token cost and improve routing consistency by enforcing a two-stage read path:
1. Read router index for intent/category and target file path.
2. Read only mapped workflow JSON file to pick concrete workflow.

## Mandatory Execution Order
1. Read `/skills/workflow-intent-router/references/router_index.json`.
2. Classify the user request into one `intent_id`.
3. Read only the mapped file under `/skills/workflow-intent-router/references/workflows/*.json`.
4. Select one executable workflow task from that file.
5. Return workflow contract payload (task_id, task_name, category, description, steps, output).

Do not full-scan every workflow file in one pass unless router index is missing/corrupted.

## Intent IDs
- `data_retrieval_preprocessing`
- `statistical_analysis`
- `trend_change_detection`
- `regression_indicator_estimation`
- `event_impact_assessment`
- `urban_extraction_structure`
- `quality_validation_misc`

## Selection Rules
- Prefer exact task match by `task_id` when available.
- Else rank by lexical similarity on `task_name + description` against user query.
- If no match with confidence >= 0.45, mark `low_confidence_match`.

## Posterior Learning Rules (after task completion only)
- Run phase: read-only, no workflow mutation.
- Learn phase:
  - Formal writeback only when:
    - execution `status == success`, and
    - `artifact_audit.pass == true`.
  - Mutation is **agent-decision + agent-landing** only (no runtime auto-mutation).
  - Role split is mandatory:
    - `Code_Assistant`: proposal-only (`ntl.workflow.evolution.proposal.v1`), no direct file edits.
    - `NTL_Engineer`: only role allowed to decide and write formal workflow mutations.
  - Engineer directly edits:
    - `/skills/workflow-intent-router/references/workflows/<intent_id>.json`
    - `/skills/workflow-intent-router/references/evolution_log.jsonl`
  - Engineer must write `_evolution` note into the changed/added workflow item.
- Failure or interruption:
  - Engineer may write candidate evidence to
    `/skills/workflow-intent-router/references/evolution_candidates.jsonl`
  - do not mutate formal workflow files.
- Candidate-to-formal promotion:
  - when a later run reaches `success + artifact_audit.pass=true`,
    the agent may promote prior same-intent candidate evidence into formal workflow updates.

## Safety Boundaries
Allowed:
- Small step ordering refinement.
- Parameter default refinements.
- Description clarifications.
- New workflow append for genuinely new task type.

Forbidden:
- Unknown tool insertion.
- Goal-changing rewrites.
- Deleting key output definitions.

## Formal Logs
- Formal mutations: `/skills/workflow-intent-router/references/evolution_log.jsonl`
- Candidate-only records: `/skills/workflow-intent-router/references/evolution_candidates.jsonl`
