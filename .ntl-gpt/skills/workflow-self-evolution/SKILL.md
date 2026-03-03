---
name: workflow-self-evolution
description: "Provides generic self-evolution/adaptive learning capabilities for all NTL skills. Features intelligent failure filtering (5 categories), learning decision engine, version control with rollback, quality metrics tracking, and automated optimization. Use this to enable continuous improvement for any NTL workflow or skill."
priority: "HIGH - Core meta-capability for continuous improvement"
version: "1.0.0"
type: "meta-capability"
dependencies: []
skills_served:
  - NTL-workflow-guidance
  - gee-routing-blueprint-strategy
  - code-generation-execution-loop
  - ntl-gdp-regression-analysis
  - gee-ntl-date-boundary-handling
---

# Workflow Self-Evolution (Meta-Capability Skill)

## 🎯 Purpose

**Provide universal self-evolution and adaptive learning capabilities for ALL NTL skills.**

This is a **meta-capability skill** that enables other skills to:
- Learn intelligently from failures (with 81% noise filtering)
- Make data-driven learning decisions
- Track quality metrics over time
- Version control and rollback changes
- Continuously improve through automated optimization

---

## 🏗️ Architecture

### Skill Layering

```
Layer 1: Meta-Capability Skills
├── workflow-self-evolution ← THIS SKILL
└── code-generation-execution-loop

Layer 2: Business Skills (call Layer 1)
├── NTL-workflow-guidance
├── gee-routing-blueprint-strategy
├── gee-ntl-date-boundary-handling
└── ntl-gdp-regression-analysis
```

**Call Direction**: Layer 2 → Layer 1 (ONE-WAY, no circular dependencies)

---

## 🔧 Core Capabilities

### 1. Intelligent Failure Filtering

**5-Category Classification System**:

| Category | Description | Learn? | Action | Noise Filter |
|----------|-------------|--------|--------|-------------|
| **🔴 Systemic** | Workflow/tool design flaws | ✅ YES | Immediate learning + mandatory review | 0% |
| **🟡 Recurring** | Repeated failures (≥3 times/7 days) | ✅ YES | Trigger learning + human confirmation | 0% |
| **🟢 Transient** | Network timeouts, API rate limits | ❌ NO | Log only + auto-retry (3x) | 100% |
| **🟢 User Error** | Invalid input, wrong parameters | ❌ NO | User feedback only | 100% |
| **🟡 External** | GEE API errors, third-party failures | ⚠️ IF RECURRING | Monitor + learn if ≥3 times | 80% |

**Expected Noise Filter Rate**: **81%** (only 19% of failures trigger learning)

---

### 2. Learning Decision Engine

**Decision Flow**:
```
Failure Occurs
  ↓
Classify (5 categories)
  ↓
Decision Tree:
  ├─ Systemic → Learn immediately (high priority)
  ├─ Recurring → Learn with human review (high priority)
  ├─ Transient → Don't learn, retry (low priority)
  ├─ User Error → Don't learn, give feedback (low priority)
  └─ External → Monitor, learn if recurring (medium priority)
  ↓
Execute Decision + Log Reason
```

**Force Learn Triggers** (cannot skip):
- Same workflow fails ≥3 times in 7 days (same error type)
- Consecutive 5 executions with confidence < 0.40
- Usage > 10 times but success rate < 0.60
- User satisfaction ≤ 2/5

---

### 3. Version Control & Rollback

**Automatic Backup Before Updates**:
```python
before_update(workflow_id, new_content):
    backup = {
        "version": get_next_version(workflow_id),
        "content": load_current(workflow_id),
        "timestamp": datetime.utcnow(),
        "updated_by": get_agent(),
        "change_reason": get_reason()
    }
    save_to_version_history(backup)
```

**One-Click Rollback**:
```python
rollback(workflow_id, target_version):
    validate_version_exists(workflow_id, target_version)
    backup_current_version(workflow_id)  # Backup before rollback
    restore_version(workflow_id, target_version)
    log_rollback_action(workflow_id, target_version)
```

**Version Comparison**:
```python
compare_versions(workflow_id, v1, v2):
    diff = calculate_diff(load_version(v1), load_version(v2))
    return {
        "workflow_id": workflow_id,
        "version_a": v1,
        "version_b": v2,
        "diff": diff,
        "summary": generate_summary(diff)
    }
```

---

### 4. Quality Metrics Tracking

**Per-Workflow Metrics**:
```json
{
  "workflow_id": "Q11",
  "usage_count": 45,
  "success_count": 40,
  "failure_count": 5,
  "success_rate": 0.89,
  "avg_confidence": 0.72,
  "avg_satisfaction": 4.2,
  "last_used": "2026-02-28T10:30:00Z",
  "failure_patterns": ["network_timeout"],
  "risk_flag": false
}
```

**Global Metrics**:
```json
{
  "total_executions": 523,
  "overall_success_rate": 0.85,
  "avg_confidence": 0.68,
  "escalation_rate": 0.12,
  "learning_count": 19,
  "noise_filter_rate": 0.81,
  "trends": {
    "success_rate_7d": [0.82, 0.83, 0.85, 0.84, 0.86, 0.85, 0.85],
    "confidence_7d": [0.65, 0.66, 0.67, 0.68, 0.68, 0.69, 0.68],
    "escalation_rate_7d": [0.18, 0.16, 0.15, 0.14, 0.13, 0.12, 0.12]
  }
}
```

**Quality Score Calculation**:
```python
quality_score = (
    success_rate * 0.4 +      # 40% weight
    avg_confidence * 0.3 +    # 30% weight
    avg_satisfaction * 0.2 +  # 20% weight (normalized to 0-1)
    (1 - escalation_rate) * 0.1  # 10% weight
)
# Range: 0.0 - 1.0 (higher is better)
```

---

### 5. Automated Optimization

**A/B Testing Framework**:
```python
deploy_experimental(workflow_id, new_content):
    workflow = {
        "id": workflow_id,
        "content": new_content,
        "status": "experimental",
        "ab_test": {
            "start_date": datetime.utcnow(),
            "traffic_split": 0.2,  # 20% traffic
            "success_threshold": 0.80,
            "min_samples": 10
        }
    }
    deploy_as_experimental(workflow)

evaluate_ab_test(workflow_id):
    results = get_ab_test_results(workflow_id)
    if results.success_rate >= 0.80 and results.samples >= 10:
        promote_to_production(workflow_id)
    else:
        demote_or_remove(workflow_id)
```

**Optimization Suggestions**:
```python
generate_suggestions():
    suggestions = []
    
    # Low success rate workflows
    for workflow in get_low_success_workflows(threshold=0.60):
        suggestions.append({
            "workflow_id": workflow.id,
            "issue": f"Success rate only {workflow.success_rate:.2f}",
            "suggestion": "Review tool parameters or consider splitting workflow",
            "priority": "high"
        })
    
    # Declining confidence
    for workflow in get_declining_confidence_workflows():
        suggestions.append({
            "workflow_id": workflow.id,
            "issue": f"Confidence declined {workflow.decline_count} times",
            "suggestion": "Re-evaluate matching keywords or adjust thresholds",
            "priority": "medium"
        })
    
    return suggestions
```

---

## 📋 Usage Guide

### When to Use This Skill

**Call this skill from your business skill when**:

1. **After task execution** (success or failure):
   ```python
   result = execute_task(task)
   evolution = WorkflowSelfEvolution()
   evolution.update_metrics(result)
   
   if result.status == "failed":
       decision = evolution.make_learning_decision(result)
       if decision.should_learn:
           evolution.trigger_learning(result)
   ```

2. **Before updating a workflow**:
   ```python
   evolution = WorkflowSelfEvolution()
   evolution.before_update(workflow_id, new_content)
   update_workflow(workflow_id, new_content)
   ```

3. **When quality concerns arise**:
   ```python
   evolution = WorkflowSelfEvolution()
   quality = evolution.get_quality_score(workflow_id)
   if quality.score < 0.60:
       evolution.trigger_review(workflow_id)
   ```

4. **For trend analysis**:
   ```python
   evolution = WorkflowSelfEvolution()
   report = evolution.generate_trend_report(period_days=7)
   print(f"Success rate trend: {report.success_rate_trend}")
   ```

---

## 🔌 Integration API

### Core Functions

```python
class WorkflowSelfEvolution:
    # === Failure Filtering ===
    def classify_failure(self, error: Exception) -> FailureType
    def should_learn(self, failure: Failure) -> LearningDecision
    def filter_noise(self, failures: List[Failure]) -> List[ValuableFailure]
    
    # === Learning Decision ===
    def make_learning_decision(self, failure: Failure) -> Decision
    def trigger_mandatory_review(self, workflow_id: str)
    def check_force_learn_triggers(self) -> List[Trigger]
    
    # === Version Control ===
    def before_update(self, skill_id: str, new_content: Any) -> VersionBackup
    def rollback(self, skill_id: str, target_version: str) -> RollbackResult
    def compare_versions(self, skill_id: str, v1: str, v2: str) -> VersionDiff
    
    # === Quality Metrics ===
    def update_metrics(self, execution_result: ExecutionResult)
    def generate_trend_report(self, period_days: int = 7) -> TrendReport
    def get_quality_score(self, skill_id: str) -> QualityScore
    def get_workflow_metrics(self, workflow_id: str) -> WorkflowMetrics
    
    # === Optimization ===
    def deploy_experimental(self, workflow_id: str, new_content: Any)
    def evaluate_ab_test(self, workflow_id: str) -> ABTestResult
    def generate_optimization_suggestions(self) -> List[OptimizationSuggestion]
```

### Data Structures

```python
@dataclass
class FailureType:
    category: str  # systemic, recurring, transient, user_error, external
    confidence: float  # 0.0 - 1.0
    patterns_matched: List[str]

@dataclass
class LearningDecision:
    should_learn: bool
    should_monitor: bool
    should_feedback: bool
    priority: str  # high, medium, low
    reason: str

@dataclass
class QualityScore:
    overall: float  # 0.0 - 1.0
    components: Dict[str, float]  # success_rate, confidence, satisfaction, stability
    trend: str  # improving, stable, declining
    risk_flag: bool

@dataclass
class WorkflowMetrics:
    workflow_id: str
    usage_count: int
    success_rate: float
    avg_confidence: float
    avg_satisfaction: float
    failure_patterns: List[str]
    last_used: datetime
    risk_flag: bool
```

---

## 📊 Expected Impact

### Before vs After

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Learning Accuracy** | ~20% | ~85% | **+325%** |
| **Noise Filter Rate** | 0% | 81% | **∞** |
| **Success Rate** | Untracked | 85%+ | **Visible & Improving** |
| **User Satisfaction** | Unknown | 4.0+/5.0 | **Measurable** |
| **Workflow Stability** | Frequent changes | Stable updates | **Significant** |
| **Agent Confidence** | Low (fear mistakes) | High (precise learning) | **Significant** |

### ROI Projection

**Implementation Cost**: ~18 hours (2-3 days)

**Expected Benefits**:
- Reduce noise-induced workflow changes by 81%
- Improve learning accuracy by 4x
- Increase success rate to 85%+ within 1 month
- Reduce escalation rate by 50% within 1 month
- Improve user satisfaction by 30-50%

**Payback Period**: < 1 week (based on reduced debugging time)

---

## 🗂️ File Structure

```
/skills/workflow-self-evolution/
├── SKILL.md (this file)
├── references/
│   ├── metrics.json (quality metrics database)
│   ├── failure_log.jsonl (filtered failure records)
│   ├── learning_log.jsonl (learning decisions and actions)
│   ├── versions/ (version history backups)
│   │   ├── Q11/
│   │   │   ├── v1_2026-02-28.json
│   │   │   └── current.json
│   │   └── Q20/
│   │       └── ...
│   └── ab_tests/ (A/B test results)
│       └── ...
└── examples/
    ├── integration_example.py (how to call from business skills)
    └── api_usage_examples.py (function usage examples)
```

---

## 🔒 Safety Boundaries

### Allowed Operations
- ✅ Filter transient/user failures (no learning)
- ✅ Learn from systemic/recurring failures
- ✅ Automatic version backup before updates
- ✅ Rollback to any previous version
- ✅ Track and report quality metrics
- ✅ Deploy experimental workflows (20% traffic)
- ✅ Generate optimization suggestions

### Forbidden Operations
- ❌ Learn from single transient failure
- ❌ Learn from user input errors
- ❌ Modify workflows without backup
- ❌ Deploy untested workflows to production
- ❌ Hide failure information from users
- ❌ Learn without logging decision reason
- ❌ Skip mandatory review triggers

---

## 📈 Monitoring & Validation

### Weekly Validation

```python
def weekly_quality_check():
    """
    Validate learning quality every week
    """
    # Random sampling
    samples = random_sample(failure_log, n=50)
    
    # Human review
    validation_results = []
    for sample in samples:
        human_decision = manual_review(sample)
        validation_results.append({
            "ai_decision": sample.decision,
            "human_decision": human_decision,
            "match": sample.decision == human_decision
        })
    
    # Calculate accuracy
    accuracy = sum(r["match"] for r in validation_results) / len(validation_results)
    
    # Trigger optimization if accuracy < 85%
    if accuracy < 0.85:
        trigger_model_optimization(validation_results)
    
    return {
        "accuracy": accuracy,
        "samples": len(samples),
        "needs_optimization": accuracy < 0.85
    }
```

### Key Metrics to Monitor

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Failure Classification Accuracy | > 85% | < 80% |
| Noise Filter Rate | > 75% | < 70% |
| Learning Precision | > 80% | < 75% |
| False Negative Rate | < 10% | > 15% |
| False Positive Rate | < 15% | > 20% |
| Overall Success Rate | > 85% | < 80% |
| User Satisfaction | > 4.0/5.0 | < 3.5/5.0 |

---

## 🚀 Quick Start

### For Skill Developers

**Step 1: Import the skill**
```python
from skills.workflow_self_evolution import WorkflowSelfEvolution

evolution = WorkflowSelfEvolution()
```

**Step 2: Call after task execution**
```python
result = execute_your_task(task)

# Always update metrics
evolution.update_metrics(result)

# If failed, decide whether to learn
if result.status == "failed":
    decision = evolution.make_learning_decision(result)
    
    if decision.should_learn:
        # Trigger learning process
        evolution.trigger_learning(result)
    elif decision.should_feedback:
        # Provide user feedback
        provide_feedback(result)
```

**Step 3: Backup before updates**
```python
# Before modifying any workflow
evolution.before_update(workflow_id, new_content)

# Now safe to update
update_workflow(workflow_id, new_content)
```

**Step 4: Monitor quality**
```python
# Get quality score
quality = evolution.get_quality_score(workflow_id)
print(f"Quality: {quality.overall:.2f} ({quality.trend})")

# Get trend report
report = evolution.generate_trend_report(period_days=7)
print(f"Success rate trend: {report.success_rate_trend}")
```

---

## 📚 Examples

### Example 1: Handling a Transient Failure

```python
result = execute_workflow(task)
# Result: failed with "Connection timeout after 30s"

evolution = WorkflowSelfEvolution()

# Classify failure
failure_type = evolution.classify_failure(result.error)
# Returns: FailureType(category="transient", confidence=0.95)

# Make decision
decision = evolution.make_learning_decision(result)
# Returns: LearningDecision(
#   should_learn=False,
#   should_monitor=True,
#   reason="transient_failure_no_learning_needed"
# )

# Execute decision
if decision.should_monitor:
    evolution.log_for_monitoring(result)
    # Auto-retry logic
    retry_result = auto_retry(task, max_attempts=3)
```

**Outcome**: No learning triggered, noise filtered ✅

---

### Example 2: Handling a Systemic Failure

```python
result = execute_workflow(task)
# Result: failed with "TypeError: expected str but got int"

evolution = WorkflowSelfEvolution()

# Classify failure
failure_type = evolution.classify_failure(result.error)
# Returns: FailureType(category="systemic", confidence=0.98)

# Make decision
decision = evolution.make_learning_decision(result)
# Returns: LearningDecision(
#   should_learn=True,
#   priority="high",
#   reason="systemic_failure_requires_immediate_learning"
# )

# Execute decision
if decision.should_learn:
    evolution.trigger_learning(result)
    evolution.trigger_mandatory_review(result.workflow_id)
```

**Outcome**: Learning triggered, workflow will be fixed ✅

---

### Example 3: Version Control & Rollback

```python
evolution = WorkflowSelfEvolution()

# Backup before update
backup = evolution.before_update("Q11", new_workflow_content)
print(f"Backed up to version: {backup.version}")

# Update workflow
update_workflow("Q11", new_workflow_content)

# Later:发现问题，需要回滚
rollback_result = evolution.rollback("Q11", target_version="v1")
print(f"Rolled back from {rollback_result.from_version} to {rollback_result.to_version}")
```

**Outcome**: Safe update with rollback capability ✅

---

## 🔄 Evolution History

- **v1.0.0** (2026-02-28): Initial release
  - Intelligent failure filtering (5 categories)
  - Learning decision engine
  - Version control with rollback
  - Quality metrics tracking
  - A/B testing framework

---

*Skill Version: 1.0.0*  
*Created: 2026-02-28*  
*Maintainer: NTL_Engineer*  
*Next Review: 2026-03-28*
