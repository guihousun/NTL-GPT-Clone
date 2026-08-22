# NTL-GPT benchmark runtime

This package runs arbitrary NTL-GPT cases and prepares their outputs for an
independent Codex `luna_worker` evaluation. It deliberately contains no
benchmark-specific IDs, task counts, categories, gold answers, or scoring
logic.

## Boundary

The workflow has four separate stages:

1. `run` executes each case in a fresh NTL-GPT subprocess, thread, and
   workspace. At most four cases run concurrently.
2. `prepare-eval` verifies the recorded artifacts and creates one read-only
   evaluation packet per case, plus a checksum manifest and a full tested-
   workspace snapshot.
3. The parent Codex starts one fresh `luna_worker` for each packet. The worker
   may inspect normal Codex-accessible sources but may write only the packet's
   declared `result_path`.
4. `collect-eval` validates the Luna results, and `summarize` calculates the
   four formal metrics.

Evaluation is not a node in the tested LangGraph. Luna calls, tokens, and
evaluation time are therefore excluded from the tested-model metrics.

The runtime accepts any number of cases. A legacy set, a current set, and a
future expanded set use the same interface; their content remains outside this
package.

## Input contracts

Cases are UTF-8 JSONL records using `ntl-benchmark.case.v1`. `source_path`
must be relative and remain below the directory containing the case file;
absolute paths and traversal are rejected. Each `target_path` must be below
`inputs/` in the isolated task workspace.

```json
{
  "schema_version": "ntl-benchmark.case.v1",
  "case_id": "case-example",
  "prompt": "Complete the requested NTL analysis and save the result.",
  "inputs": [
    {
      "source_path": "fixtures/example.csv",
      "target_path": "inputs/example.csv",
      "sha256": "optional 64-character source checksum"
    }
  ],
  "metadata": {}
}
```

Evaluation specifications are separate UTF-8 JSONL records using
`ntl-benchmark.eval-spec.v1`. `gold_compare` checks a dated or static reference.
`live_verify` instructs Luna to resolve the reference independently at
evaluation time.

```json
{
  "schema_version": "ntl-benchmark.eval-spec.v1",
  "case_id": "case-example",
  "mode": "gold_compare",
  "mandatory_criteria": [
    {
      "criterion_id": "answer-correct",
      "description": "The final answer satisfies the required result."
    }
  ],
  "reference": {"expected": "case-owned reference"},
  "authoritative_sources": [],
  "notes": ""
}
```

Case IDs must be unique ignoring case, and the case,
evaluation-specification, run-record, packet, and result sets must join
exactly. The runtime binds the case file, individual case content, evaluation
specification, batch, model, Git state, packet, workspace, artifacts, and Luna
result through recorded identities and SHA-256 digests. It does not infer
missing records or silently discard extras.

## Commands

Run up to four cases concurrently:

```powershell
python batch_run.py run `
  --cases D:\path\to\cases.jsonl `
  --output-dir D:\path\to\runs\pilot-001 `
  --model deepseek-v4-flash `
  --max-workers 4
```

The output directory must not already exist. It contains the batch manifest,
one isolated workspace per case, and `task-runs.jsonl`. Wall-clock time is
measured by the parent from fresh subprocess start through worker exit, which
includes imports, workspace/input staging, graph execution, artifact inventory,
and worker record persistence.

A formal benchmark run must start from a clean Git worktree. The full Git
object ID and clean status are recorded with every task, and formal aggregation
rejects dirty-run provenance. Commit or otherwise freeze the intended runtime
changes before making paid production-model calls.

For a pilot selected from a larger JSONL, repeat `--case-id` on `run`,
`prepare-eval`, and `summarize`; no separate subset file is required.

Create evaluation packets outside all tested workspaces:

```powershell
python batch_run.py prepare-eval `
  --cases D:\path\to\cases.jsonl `
  --eval-specs D:\path\to\eval-specs.jsonl `
  --run-records D:\path\to\runs\pilot-001\task-runs.jsonl `
  --packet-dir D:\path\to\evaluation\packets `
  --result-dir D:\path\to\evaluation\luna-results
```

`packet-dir` and `result-dir` must be separate, non-nested, and either absent
or completely empty. Even when `--case-id` selects a subset, both directories
must remain outside every workspace recorded by the full input batch. That
full no-write set is carried in the packet manifest for collection and summary.

For every packet, the parent Codex substitutes its absolute path into
[`luna_eval_prompt.md`](luna_eval_prompt.md) and starts a fresh `luna_worker`
using `gpt-5.6-luna`.
Four evaluators may run concurrently when capacity permits. A valid completed
verdict is final; it is not voted or rerun. Only `status: "eval_error"` is
eligible for a replacement evaluator, with at most two replacements (attempts
1 through 3). Persistent evaluator failure blocks formal aggregation instead
of becoming an NTL-GPT failure.

Collect and validate all Luna results:

```powershell
python batch_run.py collect-eval `
  --packet-dir D:\path\to\evaluation\packets `
  --result-dir D:\path\to\evaluation\luna-results `
  --output D:\path\to\evaluation\eval-results.jsonl
```

Collection rechecks the packet manifest, packet hashes, complete workspace
snapshot, artifacts, declared source evidence, and the exact result-directory
inventory. The collected output must be a new file outside packet, result, and
tested-workspace roots.

Create the formal summary:

```powershell
python batch_run.py summarize `
  --run-records D:\path\to\runs\pilot-001\task-runs.jsonl `
  --eval-results D:\path\to\evaluation\eval-results.jsonl `
  --eval-specs D:\path\to\eval-specs.jsonl `
  --packet-dir D:\path\to\evaluation\packets `
  --output D:\path\to\evaluation\summary.json
```

Formal summarization re-verifies the packet manifest and every packet, then
joins each evaluation result to its packet by case, task run, batch, and
evaluation-specification digest before aggregation. It also rechecks that the
external run record and evaluation specification are the exact versions bound
into the packet. A hand-written JSONL therefore cannot bypass the packet-bound
artifact and source checks performed by `collect-eval`. Summary output must be
new and remain outside the packet directory, Luna result directories, and all
tested workspaces. With `--case-id`, those no-write boundaries are still
derived from the complete packet manifest, including unselected cases.

## Formal metrics

The summary reports:

1. Final Task Success Rate.
2. Mean Number of Large Language Model Calls per Task Run.
3. Mean Input, Output, and Total Token Consumption per Task Run.
4. Mean End-to-End Wall-Clock Execution Time per Task Run.

For every complete provider call and task aggregate,
`total_tokens = input_tokens + output_tokens`. Failed and timed-out NTL-GPT
runs remain in the denominator when at least one tested-model call was started
and every such call has complete provider usage and model identity. A failure
before the first tested-model call is an invalid formal attempt, not a zero-cost
task result. If a timeout or process failure interrupts an in-flight model
call, formal aggregation is blocked rather than recording unknown consumption
as zero. A missing or technically invalid evaluator result also blocks
aggregation.

## Verification status

The local test suite covers contracts, path isolation, input and artifact
checksums, subprocess timeout handling, four-worker scheduling, a real
provider-free DeepAgents main-agent/subagent/tool callback chain, external
evaluation packet/result joins, and provider-free CLI aggregation. It does not
prove that the selected production provider exposes complete usage metadata.
Run a small paid provider probe before the first formal benchmark and confirm
that `model_usage.usage_complete` is `true` and the recorded model identity is
the intended production model.
