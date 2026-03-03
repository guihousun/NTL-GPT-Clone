---
name: NTL-workflow-guidance
description: "PREFERRED alternative to Knowledge_Base_Searcher. Searches pre-defined workflow templates from local JSON files for faster, more accurate, and lower-token task planning. ALWAYS use this FIRST before considering Knowledge_Base_Searcher."
allowed-tools:
  - NTL_Solution_Knowledge
license: "Proprietary"
metadata:
  schema: "ntl.workflow.intent.router.v1"
  router_index: "/skills/NTL-workflow-guidance/references/router_index.json"
  workflows_root: "/skills/NTL-workflow-guidance/references/workflows"
  code_root: "/skills/NTL-workflow-guidance/references/code"
  learning_mode: "posterior_only"
  priority: "HIGH - Use before Knowledge_Base_Searcher"
---

# Workflow Intent Router (Preferred Workflow Search)

## 🎯 Primary Goal

**Replace Knowledge_Base_Searcher for most task planning scenarios.**

This skill is your **FIRST CHOICE** for task planning and workflow selection.

### Why This Skill is Better Than Knowledge_Base_Searcher

| Aspect | NTL-workflow-guidance | Knowledge_Base_Searcher |
|--------|------------------------|------------------------|
| **Speed** | ✅ Instant (local JSON files) | ❌ Slower (external API calls) |
| **Accuracy** | ✅ Pre-validated workflow templates | ⚠️ Variable (depends on search) |
| **Token Cost** | ✅ Very low (no external queries) | ❌ High (multiple API calls) |
| **Determinism** | ✅ Same input → same output | ⚠️ May vary by search results |
| **Tool Sequences** | ✅ Exact, tested sequences | ⚠️ May need validation |

### When to Use This Skill

**ALWAYS try this skill FIRST for:**
- Task planning and workflow selection
- Finding step-by-step procedures for NTL analysis
- Identifying appropriate tools and their parameters
- Standard analysis scenarios (retrieval, statistics, trend, event impact, etc.)

**Only fall back to Knowledge_Base_Searcher if:**
- No matching workflow found after fuzzy matching (confidence < 0.40)
- User request is completely novel (no pre-defined template exists)
- Workflow requires methodology research beyond template scope
- User explicitly asks for research/literature review

### Workflow Coverage

This skill covers 7 major intent categories with pre-defined templates:
1. **Data Retrieval & Preprocessing** - Download, calibration, destriping
2. **Statistical Analysis** - Zonal stats, point extraction, threshold analysis
3. **Trend & Change Detection** - Time-series, Mann-Kendall, anomaly detection
4. **Event Impact Assessment** - Disasters, conflicts, infrastructure damage
5. **Urban Extraction & Structure** - Built-up areas, urban centers, polycentric analysis
6. **Regression Indicator Estimation** - GDP, population, CO2, electrification
7. **Quality Validation & Misc** - Cross-sensor harmonization, validation

## 🚀 Priority Policy (MANDATORY)

**PRIORITY ORDER - FOLLOW STRICTLY:**

```
1. FIRST:  Try `NTL-workflow-guidance` (THIS SKILL)
           ↓ (if no match with confidence >= 0.40)
2. SECOND: Try `gee-routing-blueprint-strategy` (for GEE-specific routing only)
           ↓ (if still no match)
3. LAST:   Use `Knowledge_Base_Searcher` ONLY for:
           - Novel methodology research
           - Unprecedented task types
           - Workflow evolution proposals
```

**DO NOT:**
- ❌ Skip this skill and go directly to Knowledge_Base_Searcher
- ❌ Use Knowledge_Base_Searcher for tasks covered by existing workflows
- ❌ Escalate without first attempting fuzzy matching and multi-workflow composition

**ESCALATION CHECKLIST (before using Knowledge_Base_Searcher):**
- [ ] Tried exact match on `task_id` and `task_name`
- [ ] Tried fuzzy matching on `task_name + description + category`
- [ ] Checked if request can be composed from multiple existing workflows
- [ ] Verified confidence score < 0.40
- [ ] Documented why no existing workflow matches

---

## Mandatory Execution Order

### Stage 1: Intent Classification
1. Read `/skills/NTL-workflow-guidance/references/router_index.json`.
2. Classify the user request into one `intent_id` using:
   - **Primary**: Lexical similarity on `intent_name + source_categories`
   - **Secondary**: Keyword matching on user task description
   - **Tertiary**: Category hierarchy matching

### Stage 2: Workflow Selection
3. Read only the mapped file under `/skills/NTL-workflow-guidance/references/workflows/<intent_id>.json`.
4. Select one executable workflow task using multi-stage matching:
   - **Stage 2a**: Exact match on `task_id` (if user provides specific ID)
   - **Stage 2b**: Fuzzy match on `task_name` (threshold: 0.60)
   - **Stage 2c**: Combined similarity on `task_name + description` (threshold: 0.40)
   - **Stage 2d**: If no match, check composability from multiple workflows

### Stage 3: Output Generation
5. Return workflow contract payload:
   ```json
   {
     "task_id": "...",
     "task_name": "...",
     "category": "...",
     "description": "...",
     "steps": [...],
     "output": "...",
     "confidence": 0.xx,
     "match_type": "exact|fuzzy|composed",
     "source_workflow_file": "..."
   }
   ```

**IMPORTANT**: Do not full-scan every workflow file in one pass unless router index is missing/corrupted.

## Intent IDs (Coverage Map)

### Current Intent Coverage (7 categories, 50+ pre-defined workflows)

| Intent ID | Intent Name | Coverage | Example Tasks |
|-----------|-------------|----------|---------------|
| `data_retrieval_preprocessing` | Data Retrieval & Preprocessing | ✅ Complete | Download NTL, destriping, calibration, geocoding |
| `statistical_analysis` | Statistical Analysis | ✅ Complete | Zonal stats, point extraction, threshold analysis |
| `trend_change_detection` | Trend & Change Detection | ✅ Complete | Time-series, Mann-Kendall, anomaly detection |
| `regression_indicator_estimation` | Regression Indicator Estimation | ✅ Complete | GDP, population, CO2, DEI estimation |
| `event_impact_assessment` | Event Impact Assessment | ✅ Complete | Earthquake, flood, conflict, blackout analysis |
| `urban_extraction_structure` | Urban Extraction & Structure | ✅ Complete | Built-up area, urban centers, polycentric analysis |
| `quality_validation_misc` | Quality Validation & Misc | ✅ Complete | Cross-sensor harmonization, validation |

### Intent Expansion Roadmap (Planned)

| Intent ID | Intent Name | Status | Target Coverage |
|-----------|-------------|--------|-----------------|
| `road_infrastructure_extraction` | Road & Infrastructure Extraction | 🔶 Planned | Road networks, settlement mapping |
| `electrification_monitoring` | Electrification Monitoring | 🔶 Planned | SDG 7.1.1 indicators, grid access |
| `conflict_humanitarian` | Conflict & Humanitarian Monitoring | 🔶 Planned | Conflict damage, refugee camps |
| `seasonal_temporal_analysis` | Seasonal & Temporal Analysis | 🔶 Planned | Monthly composites, seasonal patterns |

**Note**: If user request matches a planned intent, return closest existing match + note about future coverage.

## 🎯 Selection Rules (Enhanced)

### Multi-Stage Matching Strategy

**Stage 1: Exact Match (Priority: HIGHEST)**
- Match on `task_id` if user provides specific ID (e.g., "Q11", "Q20")
- Match on exact `task_name` string
- Confidence: 1.0 (guaranteed match)

**Stage 2: Fuzzy Match on Task Name (Priority: HIGH)**
- Use fuzzy string matching (Levenshtein/Jaro-Winkler) on `task_name`
- Threshold: `similarity >= 0.60`
- Confidence: `0.70 - 0.95` (based on similarity score)
- Example: "Calculate average NTL" matches "Calculate mean nighttime light"

**Stage 3: Combined Similarity (Priority: MEDIUM)**
- Combined scoring on `task_name + description + category`
- Use TF-IDF + cosine similarity or BM25
- Threshold: `similarity >= 0.40`
- Confidence: `0.40 - 0.70` (based on similarity score)
- Example: "Find brightest district" matches "Identify district with highest average NTL"

**Stage 4: Workflow Composition (Priority: LOW)**
- If no single workflow matches, check if request can be composed from multiple workflows
- Example: "Download NTL and calculate trend" = `data_retrieval` + `trend_detection`
- Confidence: `0.30 - 0.50` (based on composition complexity)
- Return composed workflow with clear step sequencing

### Confidence Thresholds and Actions

| Confidence Range | Match Quality | Action |
|-----------------|---------------|--------|
| **0.80 - 1.00** | Excellent | Return workflow with high confidence |
| **0.60 - 0.79** | Good | Return workflow, note minor differences |
| **0.40 - 0.59** | Fair | Return best match with uncertainty note |
| **0.30 - 0.39** | Poor | Attempt workflow composition |
| **< 0.30** | No Match | Escalate to Knowledge_Base_Searcher |

### Escalation Protocol

**BEFORE escalating to Knowledge_Base_Searcher:**

1. ✅ Verify all 4 matching stages completed
2. ✅ Document which stages failed and why
3. ✅ Check if request is novel or just poorly phrased
4. ✅ Suggest rephrasing if query is ambiguous

**Escalation Payload Format:**
```json
{
  "status": "no_match",
  "attempted_stages": ["exact", "fuzzy", "combined", "composition"],
  "best_confidence": 0.25,
  "best_match_task_id": "Q11",
  "escalation_reason": "novel_methodology_required",
  "suggested_kb_query": "methodology for NTL-based poverty estimation",
  "recommendation": "Use Knowledge_Base_Searcher for methodology research"
}
```

## Integration with Other Skills

### Meta-Capability Skills (Call These)
- **workflow-self-evolution**: **USER-GATED** - Provides intelligent failure filtering, learning decisions, version control, and quality metrics. Ask user after task execution whether to apply evolution updates.
  - This is a SKILL protocol, NOT a Python import/module.
  - Integration method: file I/O + tool calls (`read_file`, `write_file`, `edit_file`).
  - When: After task execution, only if user confirms.
  - Why: Enable continuous improvement with 81% noise filtering
  - See: `/skills/workflow-self-evolution/INTEGRATION_EXAMPLE.md`

### Business Skills (Collaborate)
- **gee-routing-blueprint-strategy**: Handles GEE retrieval path decisions and task_level classification.
- **code-generation-execution-loop**: Handles script execution after workflow selection.
- **gee-ntl-date-boundary-handling**: Provides date/boundary handling for event impact workflows.
- **ntl-gdp-regression-analysis**: Provides regression modeling for indicator estimation workflows.

### Integration Pattern

```text
1) Execute workflow task and collect execution result.
2) Ask user whether to run self-evolution for this completed run.
3) If user confirms:
   - update `/skills/workflow-self-evolution/references/metrics.json`
   - on failure append `/skills/workflow-self-evolution/references/failure_log.jsonl`
   - if learning is needed, backup/patch target workflow JSON and append:
     - `/skills/workflow-self-evolution/references/learning_log.jsonl`
     - `/skills/NTL-workflow-guidance/references/evolution_log.jsonl`
4) Formal workflow improvement must directly modify:
   - `/skills/NTL-workflow-guidance/references/workflows/<intent_id>.json`
   and include `_evolution` annotations in changed/new items.
5) Never use fake imports like `from skills.workflow_self_evolution import ...`.
```

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
    - `/skills/NTL-workflow-guidance/references/workflows/<intent_id>.json`
    - `/skills/NTL-workflow-guidance/references/evolution_log.jsonl`
  - Engineer must write `_evolution` note into the changed/added workflow item.
  - Writing only `workflow-self-evolution` logs is insufficient; target workflow JSON must be updated for persistent guidance fixes.
- Failure or interruption:
  - Engineer may write candidate evidence to
    `/skills/NTL-workflow-guidance/references/evolution_candidates.jsonl`
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
- Formal mutations: `/skills/NTL-workflow-guidance/references/evolution_log.jsonl`
- Candidate-only records: `/skills/NTL-workflow-guidance/references/evolution_candidates.jsonl`

## Successful Code Case Library
- Store successful runnable scripts under:
  - `/skills/NTL-workflow-guidance/references/code/<intent_id>/`
- Maintain index:
  - `/skills/NTL-workflow-guidance/references/code/code_index.json`
- For each curated case, link it from the corresponding workflow task with fields like:
  - `code_examples[]` (path, status, quality notes)
- Use curated code as implementation guidance, not blind copy:
  - validate inputs/outputs, CRS, dataset/band, and boundary/date constraints before reuse.
