# NTL Persistent Job Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable SQLite-backed job runtime for long-running NTL-GPT MCP operations with durable status, progress, cancellation, recovery, logs, and output registration.

**Architecture:** Extend the existing framework-neutral `ntl_toolkit` package with job schemas, a SQLite repository, a cancellable subprocess executor, and an in-process worker runner. Business services register named handlers; MCP adapters expose job operations without the runtime importing FastMCP, LangChain, Streamlit, or Earthdata code.

**Tech Stack:** Python 3.11, Pydantic 2, SQLite 3 via `sqlite3`, `ThreadPoolExecutor`, `subprocess`, pytest 8, Windows process management.

## Global Constraints

- Keep `ntl.job.v1` backward-compatible with the existing `JobRecord` discriminator.
- Store job state at `NTL_MCP_JOB_DB` when set; otherwise use `<NTL_MCP_WORKDIR>/.ntl/jobs.sqlite3`.
- Never store credentials, authorization headers, `.env` contents, or complete subprocess environments in SQLite or logs.
- Do not delete or overwrite output artifacts; handlers must use existing path reservation helpers.
- Short atomic GIS tools remain synchronous and do not enter the job queue.
- A process restart marks orphaned `queued` or `running` jobs as `failed` with code `WORKER_RESTARTED`, and finalizes `cancel_requested` jobs as `cancelled`; it does not silently rerun network operations.
- Cancellation is cooperative first, then terminates the registered subprocess tree on Windows.
- Use `conda run -n NTL-GPT-Stable` for all validation commands.

---

## Target File Structure

```text
packages/ntl_toolkit/src/ntl_toolkit/
├── schemas/jobs.py                  # durable public job models
└── runtime/jobs/
    ├── __init__.py                  # exported runtime interfaces
    ├── store.py                     # SQLite schema and transactional repository
    ├── context.py                   # progress, cancellation, output registration
    ├── processes.py                 # cancellable subprocess execution
    └── runner.py                    # handler registry and thread worker lifecycle
packages/ntl_toolkit/tests/
├── test_job_schemas.py
├── test_job_store.py
├── test_job_processes.py
└── test_job_runner.py
```

### Task 1: Finalize Durable Job Schemas

**Files:**
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/schemas/jobs.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/schemas/__init__.py`
- Create: `packages/ntl_toolkit/tests/test_job_schemas.py`

**Interfaces:**
- Consumes: existing `JobRecord` and `OutputArtifact` conventions.
- Produces: `JobStatus`, `JobProgress`, `JobOutput`, `JobError`, and expanded `JobRecord` used by every later task.

- [ ] **Step 1: Write failing schema serialization tests**

```python
from datetime import UTC, datetime

from ntl_toolkit.schemas import JobProgress, JobRecord, JobStatus


def test_job_record_round_trips_as_ntl_job_v1() -> None:
    now = datetime.now(UTC)
    record = JobRecord(
        job_id="job-001",
        tool="submit_vnp46a2_country_mosaic",
        status=JobStatus.QUEUED,
        created_at=now,
        updated_at=now,
        request={"countries": ["ISR"]},
        progress=JobProgress(current=0, total=3, phase="queued", message="Queued"),
    )
    payload = record.model_dump(mode="json", by_alias=True)
    assert payload["schema"] == "ntl.job.v1"
    assert payload["status"] == "queued"
    assert payload["progress"]["total"] == 3


def test_job_record_rejects_secret_bearing_request_keys() -> None:
    now = datetime.now(UTC)
    try:
        JobRecord(
            job_id="job-002",
            tool="download",
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            request={"authorization": "Bearer secret"},
        )
    except ValueError as exc:
        assert "secret-bearing" in str(exc)
    else:
        raise AssertionError("secret-bearing request keys must be rejected")
```

- [ ] **Step 2: Run tests and confirm the missing models fail**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_schemas.py -q`

Expected: collection fails because `JobProgress` and `JobStatus` are not exported.

- [ ] **Step 3: Implement the schema contract**

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProgress(BaseModel):
    current: int = Field(default=0, ge=0)
    total: int | None = Field(default=None, ge=0)
    phase: str = "queued"
    message: str = ""


class JobOutput(BaseModel):
    path: str
    media_type: str = "application/octet-stream"
    role: str = "primary"


class JobError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
```

Expand `JobRecord` with `progress`, `error`, `started_at`, `finished_at`, `cancel_requested_at`, and `outputs: list[JobOutput]`. Add a model validator that recursively rejects case-insensitive secret-value keys `token`, `secret`, `password`, `authorization`, and `cookie`; allow names ending in `_env` because they contain only an environment-variable name such as `EARTHDATA_TOKEN`.

- [ ] **Step 4: Export the models and run schema tests**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_schemas.py packages/ntl_toolkit/tests/test_results.py -q`

Expected: all tests pass and existing `ToolResult` behavior remains unchanged.

- [ ] **Step 5: Commit the schema contract**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/schemas/jobs.py packages/ntl_toolkit/src/ntl_toolkit/schemas/__init__.py packages/ntl_toolkit/tests/test_job_schemas.py
git commit -m "feat: define durable job runtime schemas"
```

### Task 2: Add the Transactional SQLite Job Store

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/__init__.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/store.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/runtime/__init__.py`
- Create: `packages/ntl_toolkit/tests/test_job_store.py`

**Interfaces:**
- Consumes: `JobRecord`, `JobStatus`, `JobProgress`, `JobOutput`, `JobError`.
- Produces: `job_database_path(workdir) -> Path` and `SQLiteJobStore` methods `create`, `get`, `list`, `update_status`, `update_progress`, `request_cancel`, `add_output`, and `recover_interrupted`.

- [ ] **Step 1: Write failing persistence and recovery tests**

```python
def test_sqlite_store_persists_jobs_across_instances(tmp_path: Path) -> None:
    first = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    created = first.create(tool="download", request={"granule_ids": ["A"]})
    second = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    assert second.get(created.job_id).request == {"granule_ids": ["A"]}


def test_recover_interrupted_marks_running_jobs_failed(tmp_path: Path) -> None:
    store = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    job = store.create(tool="download", request={})
    store.update_status(job.job_id, JobStatus.RUNNING)
    recovered = store.recover_interrupted()
    assert recovered == 1
    record = store.get(job.job_id)
    assert record.status == JobStatus.FAILED
    assert record.error.code == "WORKER_RESTARTED"
```

- [ ] **Step 2: Run the store tests and confirm import failure**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_store.py -q`

Expected: collection fails because `SQLiteJobStore` does not exist.

- [ ] **Step 3: Implement SQLite schema and transactions**

Use one `jobs` table with `job_id TEXT PRIMARY KEY`, `tool`, `status`, timestamps, and one canonical JSON payload column. Enable `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and `PRAGMA busy_timeout=5000`. Serialize with `JobRecord.model_dump_json(by_alias=True)` and deserialize with `JobRecord.model_validate_json(payload)`. Wrap each mutation in `BEGIN IMMEDIATE` and return the updated record.

```python
def job_database_path(workdir: Path) -> Path:
    configured = os.getenv("NTL_MCP_JOB_DB", "").strip()
    path = Path(configured).expanduser() if configured else workdir / ".ntl" / "jobs.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


```

Implement these exact `SQLiteJobStore` signatures: `create(*, tool: str, request: dict[str, Any]) -> JobRecord`, `get(job_id: str) -> JobRecord`, `list(*, status: JobStatus | None = None, limit: int = 100) -> list[JobRecord]`, `update_status(job_id: str, status: JobStatus, *, error: JobError | None = None) -> JobRecord`, `update_progress(job_id: str, progress: JobProgress) -> JobRecord`, `request_cancel(job_id: str) -> JobRecord`, `add_output(job_id: str, output: JobOutput) -> JobRecord`, and `recover_interrupted() -> int`. `get` raises `KeyError(job_id)` for an unknown job; every mutating method reads and returns the committed row.

- [ ] **Step 4: Run persistence tests including two concurrent writers**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_store.py -q`

Expected: persistence, WAL concurrency, cancellation request, output registration, and restart recovery tests pass. Recovery marks queued/running rows failed and cancel-requested rows cancelled.

- [ ] **Step 5: Commit the job store**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs packages/ntl_toolkit/src/ntl_toolkit/runtime/__init__.py packages/ntl_toolkit/tests/test_job_store.py
git commit -m "feat: add SQLite job store"
```

### Task 3: Add Cancellable Subprocess Execution

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/context.py`
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/processes.py`
- Create: `packages/ntl_toolkit/tests/test_job_processes.py`

**Interfaces:**
- Consumes: `SQLiteJobStore`, job schemas.
- Produces: `JobCancelled`, `JobContext`, `SubprocessResult`, and `run_cancellable_subprocess(context, command, cwd, env, timeout) -> SubprocessResult`.

- [ ] **Step 1: Write failing cancellation and redaction tests**

```python
def test_subprocess_can_be_cancelled_without_leaving_child_alive(tmp_path: Path) -> None:
    store, context = make_context(tmp_path)
    thread = Thread(target=lambda: run_cancellable_subprocess(
        context,
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=60,
    ))
    thread.start()
    wait_until(lambda: context.has_process)
    store.request_cancel(context.job_id)
    context.cancel_registered_process()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_subprocess_result_redacts_bearer_tokens(tmp_path: Path) -> None:
    _, context = make_context(tmp_path)
    result = run_cancellable_subprocess(
        context,
        [sys.executable, "-c", "print('Authorization: Bearer abc.def.ghi')"],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=10,
    )
    assert "abc.def.ghi" not in result.stdout_tail
    assert "<REDACTED>" in result.stdout_tail
```

- [ ] **Step 2: Run tests and confirm missing process APIs**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_processes.py -q`

Expected: collection fails because `JobContext` and `run_cancellable_subprocess` are absent.

- [ ] **Step 3: Implement cooperative cancellation and process-tree termination**

`JobContext` polls the store for `cancel_requested`, updates progress, registers outputs, and holds one active `Popen`. On Windows launch with `CREATE_NEW_PROCESS_GROUP`; cancellation first sends `CTRL_BREAK_EVENT`, waits two seconds, then invokes `taskkill /PID <pid> /T /F`. On other platforms terminate the process group, then kill after two seconds.

```python
@dataclass(frozen=True)
class SubprocessResult:
    returncode: int
    stdout_tail: str
    stderr_tail: str
    duration_sec: float


class JobContext:
    """Bind one job id to store-backed progress, cancellation, and outputs."""
```

Implement these exact methods on `JobContext`: `update_progress(*, current: int, total: int | None, phase: str, message: str) -> None`, `raise_if_cancelled() -> None`, `add_output(path: Path, *, media_type: str, role: str = "primary") -> None`, `register_process(process: subprocess.Popen[str]) -> None`, and `cancel_registered_process() -> None`. Guard the active process with a `threading.Lock`; `raise_if_cancelled` raises `JobCancelled(job_id)` when the stored status is `cancel_requested`.

- [ ] **Step 4: Run subprocess tests and verify no child remains**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_processes.py -q`

Expected: cancellation completes within five seconds, token text is redacted, and timeout returns error code `PROCESS_TIMEOUT`.

- [ ] **Step 5: Commit subprocess control**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/context.py packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/processes.py packages/ntl_toolkit/tests/test_job_processes.py
git commit -m "feat: add cancellable job subprocesses"
```

### Task 4: Add the Persistent Job Runner

**Files:**
- Create: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/runner.py`
- Modify: `packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/__init__.py`
- Create: `packages/ntl_toolkit/tests/test_job_runner.py`

**Interfaces:**
- Consumes: `SQLiteJobStore`, `JobContext`, `ToolResult`.
- Produces: `JobHandler = Callable[[JobContext, dict[str, Any]], ToolResult]` and `PersistentJobRunner.submit/get/list/cancel/shutdown`.

- [ ] **Step 1: Write failing success, failure, cancellation, and restart tests**

```python
def test_runner_executes_registered_handler_and_records_output(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    runner.register("write-result", write_result_handler)
    record = runner.submit("write-result", {"name": "result.txt"})
    completed = wait_for_terminal(runner, record.job_id)
    assert completed.status == JobStatus.SUCCEEDED
    assert completed.outputs[0].path.endswith("result.txt")


def test_runner_rejects_unknown_handler(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(KeyError, match="unregistered job handler"):
        runner.submit("missing", {})
```

- [ ] **Step 2: Run tests and confirm runner import failure**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_runner.py -q`

Expected: collection fails because `PersistentJobRunner` is undefined.

- [ ] **Step 3: Implement bounded worker lifecycle**

```python
JobHandler = Callable[[JobContext, dict[str, Any]], ToolResult]


```

Implement these exact `PersistentJobRunner` signatures: `__init__(store: SQLiteJobStore, *, max_workers: int = 2) -> None`, `register(name: str, handler: JobHandler) -> None`, `submit(name: str, request: dict[str, Any]) -> JobRecord`, `get(job_id: str) -> JobRecord`, `list(*, status: JobStatus | None = None, limit: int = 100) -> list[JobRecord]`, `cancel(job_id: str) -> JobRecord`, and `shutdown(*, wait: bool = True) -> None`. Duplicate handler names raise `ValueError`; unknown submit names raise `KeyError`; submit creates the row before scheduling the future.

The worker sets `running`, invokes the handler, maps `ToolResult.status` to a terminal job status, catches `JobCancelled` as `cancelled`, and stores sanitized `JobError` for other exceptions. Constructor calls `recover_interrupted()` before accepting new jobs. `max_workers` defaults from `NTL_MCP_JOB_WORKERS` with range 1-8.

- [ ] **Step 4: Run all Job Runtime tests**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests/test_job_*.py -q`

Expected: schema, SQLite, subprocess, runner, restart, and cancellation tests all pass.

- [ ] **Step 5: Commit the runner**

```powershell
git add packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/runner.py packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/__init__.py packages/ntl_toolkit/tests/test_job_runner.py
git commit -m "feat: add persistent job runner"
```

### Task 5: Package and Regression Validation

**Files:**
- Modify: `packages/ntl_toolkit/README.md`
- Modify: `packages/ntl_toolkit/tests/test_package_import.py`

**Interfaces:**
- Consumes: all Job Runtime public APIs.
- Produces: documented environment variables and import guarantees for the Earthdata implementation plan.

- [ ] **Step 1: Add a failing package import assertion**

```python
def test_job_runtime_is_publicly_importable() -> None:
    from ntl_toolkit.runtime.jobs import PersistentJobRunner, SQLiteJobStore
    assert PersistentJobRunner.__name__ == "PersistentJobRunner"
    assert SQLiteJobStore.__name__ == "SQLiteJobStore"
```

- [ ] **Step 2: Run full package tests before documentation changes**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests -q`

Expected: the new import assertion fails until exports are complete; no GIS regression should fail.

- [ ] **Step 3: Export APIs and document runtime configuration**

Document `NTL_MCP_JOB_DB`, `NTL_MCP_JOB_WORKERS`, SQLite WAL behavior, restart semantics, cancellation semantics, and the explicit rule that job requests and logs never contain secrets.

- [ ] **Step 4: Build the wheel and run complete package tests**

Run: `conda run -n NTL-GPT-Stable python -m pytest packages/ntl_toolkit/tests -q`

Run: `conda run -n NTL-GPT-Stable python -m pip wheel --no-deps --wheel-dir .tmp-wheel packages/ntl_toolkit`

Expected: all package tests pass and one `ntl_toolkit-*.whl` is built. Remove `.tmp-wheel` after inspecting the wheel contents; do not commit it.

- [ ] **Step 5: Commit Job Runtime documentation and package gate**

```powershell
git add packages/ntl_toolkit/README.md packages/ntl_toolkit/tests/test_package_import.py packages/ntl_toolkit/src/ntl_toolkit/runtime/jobs/__init__.py
git commit -m "docs: document persistent job runtime"
```
