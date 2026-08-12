from __future__ import annotations

from pathlib import Path

import pytest

from storage_manager import current_thread_id
from tools import NTL_Code_generation as code_generation


SECRET_MARKER = "ntl-secret-marker-9f2d4f"


@pytest.fixture()
def isolated_code_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base_dir = tmp_path / "user_data"
    shared_dir = tmp_path / "base_data"
    base_dir.mkdir()
    shared_dir.mkdir()
    monkeypatch.setattr(code_generation.storage_manager, "base_dir", base_dir)
    monkeypatch.setattr(code_generation.storage_manager, "shared_dir", shared_dir)
    token = current_thread_id.set("code-isolation-test")
    try:
        yield code_generation.storage_manager.get_workspace("code-isolation-test")
    finally:
        current_thread_id.reset(token)


def _seed_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DEEPSEEK_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_API_KEY",
        "NTL_ACTIVE_GEE_ENCRYPTED_REFRESH_TOKEN",
        "NTL_ACTIVE_GEE_TOKEN_SCOPES",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "EARTHDATA_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    ):
        monkeypatch.setenv(key, f"{SECRET_MARKER}-{key.lower()}")


def test_sandbox_environment_is_allowlisted_and_credential_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_secret_environment(monkeypatch)
    monkeypatch.setenv("HOME", f"{SECRET_MARKER}-home")
    monkeypatch.setenv("USERPROFILE", f"{SECRET_MARKER}-profile")
    monkeypatch.setenv("APPDATA", f"{SECRET_MARKER}-appdata")
    monkeypatch.setenv("LOCALAPPDATA", f"{SECRET_MARKER}-localappdata")
    monkeypatch.setenv("PYTHONPATH", f"{SECRET_MARKER}-pythonpath")
    # A nominally allowed variable is also dropped if it embeds a value copied
    # from a secret-bearing source variable.
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET_MARKER)
    monkeypatch.setenv("PATH", f"safe-prefix;{SECRET_MARKER};safe-suffix")

    encrypted_token = code_generation.current_gee_encrypted_refresh_token.set(SECRET_MARKER)
    try:
        env = code_generation._build_sandbox_env("thread-1", tmp_path / "script.py")
    finally:
        code_generation.current_gee_encrypted_refresh_token.reset(encrypted_token)

    assert SECRET_MARKER not in "\n".join(f"{key}={value}" for key, value in env.items())
    assert "PATH" not in env
    assert env["PYTHONPATH"] == str(Path(code_generation.__file__).resolve().parent.parent)
    assert {
        "DEEPSEEK_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_API_KEY",
        "NTL_ACTIVE_GEE_ENCRYPTED_REFRESH_TOKEN",
        "NTL_ACTIVE_GEE_TOKEN_SCOPES",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "EARTHDATA_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    }.isdisjoint(env)
    sandbox_home = tmp_path / "sandbox_home"
    assert Path(env["HOME"]) == sandbox_home
    assert Path(env["USERPROFILE"]) == sandbox_home
    assert Path(env["APPDATA"]) == sandbox_home / "AppData" / "Roaming"
    assert Path(env["LOCALAPPDATA"]) == sandbox_home / "AppData" / "Local"


def test_user_code_cannot_disable_environment_scrubbing(
    isolated_code_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_secret_environment(monkeypatch)
    # The old opt-out must no longer return execution to the credential-bearing
    # application process.
    monkeypatch.setenv("NTL_EXEC_SANDBOX", "0")

    ok, logs, error_type, error_message, _traceback = code_generation._execute_code(
        "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))",
        timeout_seconds=30,
    )

    assert ok is True, (error_type, error_message, logs)
    assert SECRET_MARKER not in logs
    for forbidden_name in (
        "DEEPSEEK_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_API_KEY",
        "NTL_ACTIVE_GEE_ENCRYPTED_REFRESH_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "EARTHDATA_TOKEN",
    ):
        assert forbidden_name not in logs
