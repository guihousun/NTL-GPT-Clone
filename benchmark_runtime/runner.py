from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Iterable, Iterator
import uuid

from . import CASE_SCHEMA, RUN_SCHEMA
from .contracts import path_is_linklike
from .telemetry import BenchmarkTelemetryCallback, incomplete_model_usage, redact_text


BATCH_MANIFEST_SCHEMA = "ntl-benchmark.batch-manifest.v1"
MAX_BATCH_WORKERS = 4
REPO_ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json_atomic(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with target.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def load_case_records(path: str | Path) -> list[dict[str, Any]]:
    """Load and minimally normalize ``ntl-benchmark.case.v1`` JSONL records."""

    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    from .contracts import load_case_records as contract_loader

    records = contract_loader(source)
    if not isinstance(records, list) or not records:
        raise ValueError("case file must contain at least one case record")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(records, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"case {index} is not a JSON object")
        if raw.get("schema_version") != CASE_SCHEMA:
            raise ValueError(f"case {index} schema_version must be {CASE_SCHEMA}")
        case_id = str(raw.get("case_id") or "").strip()
        prompt = raw.get("prompt")
        inputs = raw.get("inputs", [])
        metadata = raw.get("metadata", {})
        if not case_id:
            raise ValueError(f"case {index} has no case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"case {case_id} has no prompt")
        if not isinstance(inputs, list) or any(not isinstance(item, dict) for item in inputs):
            raise ValueError(f"case {case_id} inputs must be a list of objects")
        if not isinstance(metadata, dict):
            raise ValueError(f"case {case_id} metadata must be an object")
        seen.add(case_id)
        normalized.append(
            {
                "schema_version": CASE_SCHEMA,
                "case_id": case_id,
                "prompt": prompt,
                "inputs": inputs,
                "metadata": metadata,
            }
        )
    return normalized


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(root.resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _resolve_input_source(source_path: Any, cases_base_dir: Path) -> Path:
    raw = str(source_path or "").strip()
    if not raw:
        raise ValueError("input source_path is required")
    logical = PurePosixPath(raw.replace("\\", "/"))
    if logical.is_absolute() or PureWindowsPath(raw).is_absolute() or ".." in logical.parts:
        raise ValueError(f"unsafe relative input source_path: {raw}")
    lexical_source = cases_base_dir / Path(*logical.parts)
    cursor = cases_base_dir
    for part in logical.parts:
        cursor = cursor / part
        if path_is_linklike(cursor):
            raise ValueError(f"input source_path must not traverse a link or junction: {raw}")
    source = lexical_source.resolve()
    if not _is_within(source, cases_base_dir):
        raise ValueError(f"input source_path escapes the case directory: {raw}")
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_nlink > 1:
        raise ValueError(f"input source_path must not be a hard-linked file: {raw}")
    return source


def _safe_input_target(target_path: Any, *, default_name: str) -> PurePosixPath:
    raw = str(target_path or default_name).strip().replace("\\", "/")
    logical = PurePosixPath(raw)
    if not raw or logical.is_absolute() or PureWindowsPath(raw).is_absolute() or ".." in logical.parts:
        raise ValueError(f"unsafe input target_path: {target_path}")
    parts = list(logical.parts)
    if parts and parts[0].casefold() == "inputs":
        parts = parts[1:]
    if not parts or any(part in {"", "."} for part in parts):
        raise ValueError(f"unsafe input target_path: {target_path}")
    if parts[0].casefold() in {"outputs", "memory", "shared"}:
        raise ValueError(f"input target_path must remain under inputs/: {target_path}")
    return PurePosixPath(*parts)


def stage_case_inputs(case: dict[str, Any], *, workspace: Path, cases_base_dir: Path) -> list[dict[str, Any]]:
    inputs_dir = workspace / "inputs"
    records: list[dict[str, Any]] = []
    claimed: set[str] = set()
    for index, item in enumerate(case.get("inputs") or [], 1):
        source = _resolve_input_source(item.get("source_path"), cases_base_dir.resolve())
        target_rel = _safe_input_target(item.get("target_path"), default_name=source.name)
        target_key = target_rel.as_posix().casefold()
        if target_key in claimed:
            raise ValueError(f"duplicate input target_path in case {case['case_id']}: {target_rel}")
        claimed.add(target_key)
        target = (inputs_dir / Path(*target_rel.parts)).resolve()
        if not _is_within(target, inputs_dir):
            raise ValueError(f"input target_path escapes inputs/: {target_rel}")
        expected = item.get("sha256")
        actual = sha256_file(source)
        if expected is not None:
            expected_text = str(expected).strip().casefold()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_text):
                raise ValueError(f"invalid sha256 for case {case['case_id']} input {index}")
            if actual != expected_text:
                raise ValueError(f"sha256 mismatch for case {case['case_id']} input {index}")
        if target.exists():
            raise FileExistsError(f"input target already exists: {target_rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_sha = sha256_file(target)
        if copied_sha != actual:
            raise IOError(f"staged input checksum changed: {target_rel}")
        records.append(
            {
                "relative_path": f"inputs/{target_rel.as_posix()}",
                "sha256": copied_sha,
                "bytes": target.stat().st_size,
            }
        )
    return records


def artifact_records(outputs_dir: Path) -> list[dict[str, Any]]:
    if path_is_linklike(outputs_dir):
        raise ValueError(f"output root must not be a symbolic link or junction: {outputs_dir}")
    if not outputs_dir.is_dir():
        return []
    resolved_root = outputs_dir.resolve(strict=True)
    records: list[dict[str, Any]] = []
    for path in sorted(outputs_dir.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path_is_linklike(path):
            raise ValueError(f"output artifacts must not be symbolic links or junctions: {path}")
        resolved = path.resolve(strict=True)
        if not _is_within(resolved, resolved_root):
            raise ValueError(f"output artifact escapes the task workspace: {path}")
        if path.is_file():
            if path.stat().st_nlink > 1:
                raise ValueError(f"output artifacts must not be hard links: {path}")
            records.append(
                {
                    "relative_path": f"outputs/{path.relative_to(outputs_dir).as_posix()}",
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return records


@contextmanager
def bind_thread_context(thread_id: str) -> Iterator[None]:
    """Bind and reliably reset the runtime thread ContextVar."""

    from storage_manager import current_thread_id

    normalized = str(thread_id or "").strip()
    if not normalized:
        raise ValueError("thread_id is required")
    token = current_thread_id.set(normalized)
    try:
        yield
    finally:
        current_thread_id.reset(token)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return str(content or "").strip()


def final_answer_from_result(result: Any) -> str | None:
    try:
        from langchain_core.messages import AIMessage
    except ImportError:
        return None
    messages = result.get("messages", []) if isinstance(result, dict) else []
    fallback: str | None = None
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or getattr(message, "tool_calls", None):
            continue
        text = _message_text(message)
        if not text:
            continue
        name = str(getattr(message, "name", "") or "").casefold()
        if name in {"ntl_engineer", "ntl-engineer"}:
            return text
        if fallback is None:
            fallback = text
    return fallback


def human_message_state(prompt: str) -> dict[str, list[Any]]:
    from langchain_core.messages import HumanMessage

    return {"messages": [HumanMessage(content=prompt)]}


def _invoke_ntl_graph(
    case: dict[str, Any],
    payload: dict[str, Any],
    telemetry: BenchmarkTelemetryCallback,
) -> Any:
    # NTL_USER_DATA_DIR is set by execute_worker_payload before these imports.
    from graph_factory import build_ntl_graph
    from model_config import get_api_model_name, get_env_api_key, missing_env_for_model

    model_name = str(payload["model"])
    missing = missing_env_for_model(model_name)
    if missing:
        raise RuntimeError(f"missing model runtime configuration: {', '.join(missing)}")
    expected_api_model = get_api_model_name(model_name)
    telemetry.allow_tested_models((model_name, expected_api_model))
    with bind_thread_context(payload["thread_id"]):
        graph = build_ntl_graph(
            model_name=model_name,
            api_key=get_env_api_key(model_name),
            request_timeout_s=int(payload["request_timeout_seconds"]),
            graph_name="NTL_Engineer",
        )
        return graph.invoke(
            human_message_state(case["prompt"]),
            config={
                "configurable": {"thread_id": payload["thread_id"]},
                "recursion_limit": int(payload["recursion_limit"]),
                "callbacks": [telemetry],
                "metadata": {
                    "benchmark_usage_scope": "tested_agent",
                    "agent_name": "NTL_Engineer",
                    "batch_run_id": payload["batch_run_id"],
                    "case_id": case["case_id"],
                },
            },
        )


def _environment_record(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    return {
        "workspace": str(workspace.resolve()),
        "model": str(payload.get("model") or ""),
        "request_timeout_seconds": int(payload.get("request_timeout_seconds") or 0),
        "task_timeout_seconds": float(payload.get("task_timeout_seconds") or 0),
        "recursion_limit": int(payload.get("recursion_limit") or 0),
        "system_git_sha": str(payload.get("system_git_sha") or "unknown"),
        "system_git_dirty": payload.get("system_git_dirty"),
        "system_git_status_sha256": payload.get("system_git_status_sha256"),
        "cases_sha256": payload.get("cases_sha256"),
        "case_sha256": payload.get("case_sha256"),
        "wall_clock_scope": str(
            payload.get("wall_clock_scope") or "worker_input_staging_to_artifact_inventory"
        ),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }


def execute_worker_payload(
    payload: dict[str, Any],
    *,
    graph_invoker: Callable[[dict[str, Any], dict[str, Any], BenchmarkTelemetryCallback], Any] | None = None,
) -> dict[str, Any]:
    """Execute one case in the current (already fresh) worker process."""

    workspace_root = Path(payload["workspace_root"]).resolve()
    thread_id = str(payload["thread_id"])
    workspace = (workspace_root / thread_id).resolve()
    if not _is_within(workspace, workspace_root):
        raise ValueError(f"thread workspace escapes workspace root: {thread_id}")
    if workspace.exists():
        raise FileExistsError(f"fresh task workspace already exists: {workspace}")

    # This must precede imports of storage_manager and graph_factory.
    os.environ["NTL_USER_DATA_DIR"] = str(workspace_root)
    workspace.mkdir(parents=True, exist_ok=False)
    for name in ("inputs", "outputs", "memory"):
        (workspace / name).mkdir()

    case = payload["case"]
    telemetry_path = workspace / ".benchmark-telemetry.json"
    telemetry = BenchmarkTelemetryCallback(
        telemetry_path,
        tested_model_ids=(str(payload.get("model") or ""),),
    )
    started_at = _utc_now()
    start_clock = time.perf_counter()
    terminal_state = "failed"
    final_answer: str | None = None
    errors: list[dict[str, str]] = []
    try:
        stage_case_inputs(
            case,
            workspace=workspace,
            cases_base_dir=Path(payload["cases_base_dir"]).resolve(),
        )
        result = (graph_invoker or _invoke_ntl_graph)(case, payload, telemetry)
        final_answer = final_answer_from_result(result)
        terminal_state = "succeeded" if final_answer else "no_final_answer"
        if not final_answer:
            errors.append({"code": "NO_FINAL_ANSWER", "message": "graph returned no final AI answer"})
        if terminal_state == "succeeded" and telemetry.model_usage_snapshot()["llm_call_count"] == 0:
            telemetry.mark_incomplete("succeeded run recorded no tested-model call")
            errors.append(
                {"code": "MISSING_MODEL_USAGE", "message": "succeeded run recorded no tested-model call"}
            )
    except BaseException as exc:  # noqa: BLE001 - the worker must always emit a run record
        errors.append({"code": type(exc).__name__, "message": redact_text(exc)})
        terminal_state = "failed"

    snapshot = telemetry.snapshot()
    try:
        artifacts = artifact_records(workspace / "outputs")
    except BaseException as exc:  # noqa: BLE001 - unsafe artifacts fail the task, not its record
        artifacts = []
        terminal_state = "failed"
        errors.append(
            {
                "code": "ARTIFACT_COLLECTION_FAILED",
                "message": redact_text(f"{type(exc).__name__}: {exc}"),
            }
        )
    ended_at = _utc_now()
    wall_clock_seconds = max(0.0, time.perf_counter() - start_clock)
    return {
        "schema_version": RUN_SCHEMA,
        "batch_run_id": str(payload["batch_run_id"]),
        "task_run_id": str(payload["task_run_id"]),
        "case_id": str(case["case_id"]),
        "thread_id": thread_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_clock_seconds": wall_clock_seconds,
        "terminal_state": terminal_state,
        "final_answer": final_answer,
        "artifacts": artifacts,
        "tool_trace": snapshot["tool_trace"],
        "model_usage": snapshot["model_usage"],
        "errors": errors,
        "environment": _environment_record(payload, workspace),
    }


def worker_main(payload_path: str | Path) -> int:
    path = Path(payload_path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = execute_worker_payload(payload)
    write_json_atomic(payload["result_path"], record)
    return 0


def _read_telemetry_journal(workspace: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    journal = workspace / ".benchmark-telemetry.json"
    if not journal.is_file():
        return incomplete_model_usage("telemetry journal was not created"), []
    try:
        payload = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return incomplete_model_usage(f"telemetry journal unreadable: {type(exc).__name__}"), []
    if isinstance(payload, dict) and isinstance(payload.get("model_usage"), dict):
        usage = payload["model_usage"]
        trace = payload.get("tool_trace") if isinstance(payload.get("tool_trace"), list) else []
    elif isinstance(payload, dict):
        usage = payload
        trace = []
    else:
        return incomplete_model_usage("telemetry journal has an invalid shape"), []
    calls = usage.get("calls") if isinstance(usage.get("calls"), list) else []
    usage["calls"] = calls
    usage["llm_call_count"] = len(calls)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if not isinstance(usage.get(key), int) or isinstance(usage.get(key), bool):
            usage[key] = sum(int(call.get(key) or 0) for call in calls if isinstance(call, dict))
    return usage, trace


def _force_usage_incomplete(usage: dict[str, Any], reason: str) -> dict[str, Any]:
    result = dict(usage)
    calls = list(result.get("calls") or [])
    result["calls"] = calls
    result["llm_call_count"] = len(calls)
    result["usage_complete"] = False
    reasons = [str(item) for item in (result.get("incomplete_reasons") or []) if str(item).strip()]
    if reason not in reasons:
        reasons.append(reason)
    result["incomplete_reasons"] = reasons
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if not isinstance(result.get(key), int) or isinstance(result.get(key), bool):
            result[key] = sum(int(call.get(key) or 0) for call in calls if isinstance(call, dict))
    return result


def _provider_usage_is_complete(usage: dict[str, Any]) -> bool:
    """Return true only when every started provider call is fully journaled."""

    calls = usage.get("calls")
    if usage.get("usage_complete") is not True or not isinstance(calls, list) or not calls:
        return False
    for call in calls:
        if not isinstance(call, dict):
            return False
        if call.get("status") != "completed" or call.get("usage_complete") is not True:
            return False
        if call.get("model_identity_matches_tested") is not True:
            return False
        for key in ("provider_reported_model_id", "provider_request_id"):
            if not isinstance(call.get(key), str) or not call[key].strip():
                return False
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = call.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
    return True


def abnormal_run_record(
    payload: dict[str, Any],
    *,
    terminal_state: str,
    elapsed: float,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    workspace = (Path(payload["workspace_root"]).resolve() / str(payload["thread_id"])).resolve()
    usage, trace = _read_telemetry_journal(workspace)
    # A process timeout/failure does not itself make already-finished provider
    # calls unobservable. Preserve a complete journal (for example, a timeout
    # in a long-running tool after the last model response). If a request was
    # in flight, errored without usage, or no journal exists, fail closed so a
    # formal token mean cannot silently undercount consumption.
    if not _provider_usage_is_complete(usage):
        usage = _force_usage_incomplete(usage, error_code)
    errors = [{"code": error_code, "message": redact_text(error_message)[-4000:]}]
    try:
        artifacts = artifact_records(workspace / "outputs")
    except BaseException as exc:  # noqa: BLE001 - preserve the abnormal run record
        artifacts = []
        errors.append(
            {
                "code": "ARTIFACT_COLLECTION_FAILED",
                "message": redact_text(f"{type(exc).__name__}: {exc}")[-4000:],
            }
        )
    ended_at = _utc_now()
    return {
        "schema_version": RUN_SCHEMA,
        "batch_run_id": str(payload["batch_run_id"]),
        "task_run_id": str(payload["task_run_id"]),
        "case_id": str(payload["case"]["case_id"]),
        "thread_id": str(payload["thread_id"]),
        "started_at": str(payload["submitted_at"]),
        "ended_at": ended_at,
        "wall_clock_seconds": max(0.0, float(elapsed)),
        "terminal_state": terminal_state,
        "final_answer": None,
        "artifacts": artifacts,
        "tool_trace": trace,
        "model_usage": usage,
        "errors": errors,
        "environment": _environment_record(payload, workspace),
    }


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        process.kill()


def _launch_worker(payload_path: Path, payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    command = [sys.executable, "-X", "utf8", "-m", "benchmark_runtime.cli", "_worker", str(payload_path)]
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["LANGCHAIN_TRACING"] = "false"
    environment["LANGCHAIN_TRACING_V2"] = "false"
    environment["LANGSMITH_TRACING"] = "false"
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    launch_started_at = _utc_now()
    started = time.perf_counter()
    abnormal_payload = dict(payload)
    abnormal_payload["submitted_at"] = launch_started_at
    abnormal_payload["wall_clock_scope"] = "parent_process_start_to_worker_exit"
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **popen_kwargs,
    )
    try:
        stdout, stderr = process.communicate(timeout=float(payload["task_timeout_seconds"]))
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return abnormal_run_record(
            abnormal_payload,
            terminal_state="timed_out",
            elapsed=time.perf_counter() - started,
            error_code="TASK_TIMEOUT",
            error_message=f"task exceeded {payload['task_timeout_seconds']} seconds",
        )
    worker_ended_at = _utc_now()
    worker_elapsed = max(0.0, time.perf_counter() - started)
    result_path = Path(payload["result_path"])
    if process.returncode != 0 or not result_path.is_file():
        detail = stderr or stdout or f"worker exited with code {process.returncode}"
        return abnormal_run_record(
            abnormal_payload,
            terminal_state="failed",
            elapsed=worker_elapsed,
            error_code="WORKER_PROCESS_FAILED",
            error_message=detail,
        )
    try:
        record = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return abnormal_run_record(
            abnormal_payload,
            terminal_state="failed",
            elapsed=worker_elapsed,
            error_code="INVALID_WORKER_RECORD",
            error_message=str(exc),
        )
    if not isinstance(record, dict) or record.get("schema_version") != RUN_SCHEMA:
        return abnormal_run_record(
            abnormal_payload,
            terminal_state="failed",
            elapsed=worker_elapsed,
            error_code="INVALID_WORKER_RECORD",
            error_message="worker record has the wrong schema",
        )
    try:
        from .contracts import validate_run_record

        record = validate_run_record(record)
        expected_workspace = (
            Path(payload["workspace_root"]).resolve() / str(payload["thread_id"])
        ).resolve()
        expected_fields = {
            "batch_run_id": str(payload["batch_run_id"]),
            "task_run_id": str(payload["task_run_id"]),
            "case_id": str(payload["case"]["case_id"]),
            "thread_id": str(payload["thread_id"]),
        }
        mismatches = [
            field for field, expected in expected_fields.items() if record.get(field) != expected
        ]
        declared_workspace = Path(record["environment"]["workspace"]).resolve(strict=False)
        if declared_workspace != expected_workspace:
            mismatches.append("environment.workspace")
        if mismatches:
            raise ValueError("worker record does not match its payload: " + ", ".join(mismatches))
        record["started_at"] = launch_started_at
        record["ended_at"] = worker_ended_at
        record["wall_clock_seconds"] = worker_elapsed
        record["environment"] = dict(record["environment"])
        record["environment"]["wall_clock_scope"] = "parent_process_start_to_worker_exit"
        record = validate_run_record(record)
    except (TypeError, ValueError, OSError) as exc:
        return abnormal_run_record(
            abnormal_payload,
            terminal_state="failed",
            elapsed=worker_elapsed,
            error_code="INVALID_WORKER_RECORD",
            error_message=str(exc),
        )
    return record


def _git_sha(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _git_state(repo_root: Path) -> dict[str, Any]:
    """Capture a compact pre-run code identity without persisting changed paths."""

    sha = _git_sha(repo_root)
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {
            "system_git_sha": sha,
            "system_git_dirty": None,
            "system_git_status_sha256": None,
        }
    status_bytes = completed.stdout
    return {
        "system_git_sha": sha,
        "system_git_dirty": bool(status_bytes),
        "system_git_status_sha256": hashlib.sha256(status_bytes).hexdigest(),
    }


def _safe_component(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip(".-")
    return (normalized or fallback)[:80]


def _select_cases(cases: list[dict[str, Any]], requested: Iterable[str] | None) -> list[dict[str, Any]]:
    requested_ids = [str(value) for value in (requested or [])]
    if not requested_ids:
        return cases
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("duplicate --case-id")
    by_id = {case["case_id"]: case for case in cases}
    unknown = [case_id for case_id in requested_ids if case_id not in by_id]
    if unknown:
        raise ValueError(f"unknown case IDs: {unknown}")
    return [by_id[case_id] for case_id in requested_ids]


def _positive_number(value: Any, *, name: str, integer: bool = False) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be positive")
    result = int(value) if integer else float(value)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def run_batch(
    args: Any,
    *,
    launcher: Callable[[Path, dict[str, Any], Path], dict[str, Any]] | None = None,
) -> int:
    cases_path = Path(args.cases).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists; resume/overwrite is disabled: {output_dir}")
    cases = _select_cases(load_case_records(cases_path), getattr(args, "case_id", None))
    max_workers = int(_positive_number(args.max_workers, name="max_workers", integer=True))
    if max_workers > MAX_BATCH_WORKERS:
        raise ValueError(f"max_workers cannot exceed {MAX_BATCH_WORKERS}")
    task_timeout = float(_positive_number(args.task_timeout_seconds, name="task_timeout_seconds"))
    request_timeout = int(_positive_number(args.request_timeout_seconds, name="request_timeout_seconds", integer=True))
    recursion_limit = int(_positive_number(args.recursion_limit, name="recursion_limit", integer=True))
    model = str(args.model or "").strip()
    if not model:
        raise ValueError("model is required")

    repo_root = REPO_ROOT
    git_state = _git_state(repo_root)

    batch_run_id = f"ntl-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
    output_dir.mkdir(parents=True, exist_ok=False)
    control_dir = output_dir / "control"
    task_records_dir = output_dir / "task-records"
    workspace_root = output_dir / "workspaces"
    for directory in (control_dir, task_records_dir, workspace_root):
        directory.mkdir()

    system_git_sha = str(git_state["system_git_sha"])
    manifest_path = output_dir / "batch-manifest.json"
    cases_sha256 = sha256_file(cases_path)
    manifest: dict[str, Any] = {
        "schema_version": BATCH_MANIFEST_SCHEMA,
        "batch_run_id": batch_run_id,
        "created_at": _utc_now(),
        "ended_at": None,
        "status": "running",
        "cases_path": str(cases_path),
        "cases_sha256": cases_sha256,
        "case_ids": [case["case_id"] for case in cases],
        "task_count": len(cases),
        "model": model,
        "configured_concurrency": max_workers,
        "execution": {
            "fresh_subprocess_per_task": True,
            "fresh_thread_per_task": True,
            "isolated_workspace_per_task": True,
            "resume_allowed": False,
            "task_timeout_seconds": task_timeout,
            "request_timeout_seconds": request_timeout,
            "recursion_limit": recursion_limit,
            "wall_clock_scope": "parent_process_start_to_worker_exit",
        },
        "environment": dict(git_state),
    }
    write_json_atomic(manifest_path, manifest)

    launch = launcher or _launch_worker
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for index, case in enumerate(cases, 1):
        task_run_id = str(uuid.uuid4())
        case_component = _safe_component(case["case_id"], fallback=f"case-{index:04d}")
        thread_id = f"{_safe_component(batch_run_id, fallback='batch')}-{case_component}-{task_run_id[:8]}"
        record_name = f"{index:04d}-{case_component}.json"
        result_path = task_records_dir / record_name
        payload = {
            "case": case,
            "cases_base_dir": str(cases_path.parent),
            "workspace_root": str(workspace_root),
            "result_path": str(result_path),
            "batch_run_id": batch_run_id,
            "task_run_id": task_run_id,
            "thread_id": thread_id,
            "model": model,
            "request_timeout_seconds": request_timeout,
            "task_timeout_seconds": task_timeout,
            "recursion_limit": recursion_limit,
            "system_git_sha": system_git_sha,
            "system_git_dirty": git_state["system_git_dirty"],
            "system_git_status_sha256": git_state["system_git_status_sha256"],
            "cases_sha256": cases_sha256,
            "case_sha256": sha256_json(case),
            "submitted_at": _utc_now(),
        }
        payload_path = control_dir / f"{index:04d}-{case_component}.json"
        write_json_atomic(payload_path, payload)
        payloads.append((payload_path, payload))

    records: list[dict[str, Any] | None] = [None] * len(payloads)
    def launch_one(
        payload_path: Path,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        launch_started_at = _utc_now()
        launch_clock = time.perf_counter()
        try:
            return launch(payload_path, payload, repo_root)
        except BaseException as exc:  # noqa: BLE001 - preserve every task in the batch
            abnormal_payload = dict(payload)
            abnormal_payload["submitted_at"] = launch_started_at
            abnormal_payload["wall_clock_scope"] = "parent_process_start_to_worker_exit"
            return abnormal_run_record(
                abnormal_payload,
                terminal_state="failed",
                elapsed=time.perf_counter() - launch_clock,
                error_code="PARENT_LAUNCHER_FAILED",
                error_message=f"{type(exc).__name__}: {exc}",
            )

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ntl-benchmark") as executor:
        future_to_index = {}
        for index, (payload_path, payload) in enumerate(payloads):
            future = executor.submit(launch_one, payload_path, payload)
            future_to_index[future] = index
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            payload_path, payload = payloads[index]
            del payload_path
            record = future.result()
            write_json_atomic(payload["result_path"], record)
            records[index] = record

    run_jsonl = output_dir / "task-runs.jsonl"
    completed_records = [record for record in records if record is not None]
    for record in completed_records:
        append_jsonl(run_jsonl, record)
    counts = Counter(str(record.get("terminal_state") or "unknown") for record in completed_records)
    manifest.update(
        {
            "ended_at": _utc_now(),
            "status": "completed",
            "terminal_counts": dict(sorted(counts.items())),
            "task_record_count": len(completed_records),
        }
    )
    write_json_atomic(manifest_path, manifest)
    print(
        json.dumps(
            {
                "batch_run_id": batch_run_id,
                "output_dir": str(output_dir),
                "task_count": len(completed_records),
                "configured_concurrency": max_workers,
                "terminal_counts": manifest["terminal_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
