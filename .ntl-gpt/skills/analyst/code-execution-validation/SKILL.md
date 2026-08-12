---
name: ntl-analyst-code-execution-validation
description: Apply the Analyst's internal Geo-CodeCoT lifecycle to v2 scripts, execution, artifacts, validation, and one bounded technical repair.
---

# Code Execution and Validation

1. Inspect accepted contracts and inputs.
2. Decompose the method into explicit deterministic steps.
3. Save only `ntl.script.contract.v2` code under `/outputs/` and perform static preflight. The script must contain a Python-literal assignment named exactly `NTL_SCRIPT_CONTRACT`; comments or `schema_version` do not satisfy the validator.
4. Execute the exact saved script and validate every declared output, manifest, range, and failure gate.
5. Allow at most one recorded non-semantic repair for path, format, serialization, or syntax defects.
6. Re-open and checksum the final script and every referenced output before saving `AnalysisPackage`. Package persistence is the immutability boundary: never overwrite or edit a referenced file afterward.

Execute only against inputs already prepared by bounded Data Searcher tools. The child process receives no GEE, LLM, tracing, proxy, or user credential environment; never inspect environment variables, hidden runner files, telemetry, or host paths. This is a credential boundary, not an OS-level filesystem or network sandbox.

Changing product, AOI, date, QA, baseline, threshold, method, or objective requires NTL_Engineer approval. A zero exit code without valid artifacts is failure.

## Required literal contract

Use this exact top-level shape before imports and executable code; replace the placeholder content, but do not rename keys:

```python
NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "One non-empty sentence describing the frozen objective.",
    "input_manifest": [{"path": "/inputs/input.ext", "role": "declared input"}],
    "method_steps": ["deterministic step 1"],
    "parameters": {},
    "output_manifest": [{"path": "/outputs/result.ext", "required": True}],
    "validation_checks": ["declared output exists and is non-empty"],
    "failure_gates": ["fail if the declared output is missing or invalid"],
    "execution": {
        "mode": "execute",
        "timeout_seconds": 1800,
        "overwrite_policy": "version",
        "network_scope": [],
        "test_strategy": "auto",
        "repair_history": [],
    },
}
```

The schema key is `schema`, not `schema_version`. All nine displayed top-level keys are mandatory. `NTL_SCRIPT_CONTRACT` must be an `ast.literal_eval`-compatible dictionary: no function calls, variables, comprehensions, JSON-only booleans, or dynamically computed values.
