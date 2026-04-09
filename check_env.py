from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOTENV_PATH = ROOT / ".env"

REQUIRED_ENV = [
    "DASHSCOPE_Qwen_plus_KEY",
    "DASHSCOPE_Qwen_plus_URL",
    "DASHSCOPE_Coding_URL",
]

OPTIONAL_ENV = [
    "GEE_DEFAULT_PROJECT_ID",
    "EARTHDATA_TOKEN",
    "NTL_TOOL_PROFILE",
    "NTL_CONTEXTILY_TMP",
]

CORE_IMPORTS = {
    "streamlit": "streamlit",
    "deepagents": "deepagents",
    "geopandas": "geopandas",
    "rasterio": "rasterio",
}


def _print(title: str, lines: list[str]) -> None:
    print(title)
    for line in lines:
        print(f"  - {line}")


def _load_dotenv_snapshot() -> dict[str, str]:
    values: dict[str, str] = {}
    if not DOTENV_PATH.exists():
        return values
    for raw_line in DOTENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _check_env() -> tuple[list[str], list[str]]:
    env_snapshot = _load_dotenv_snapshot()

    def _value(name: str) -> str:
        runtime = str(os.getenv(name, "") or "").strip()
        if runtime:
            return runtime
        return str(env_snapshot.get(name, "") or "").strip()

    missing = [name for name in REQUIRED_ENV if not _value(name)]
    optional = [name for name in OPTIONAL_ENV if _value(name)]
    return missing, optional


def _check_files() -> list[str]:
    missing = []
    for rel in ("environment.yml", ".env.example", "Streamlit.py", "app_ui.py", "graph_factory.py"):
        if not (ROOT / rel).exists():
            missing.append(rel)
    return missing


def _check_imports() -> tuple[list[str], list[str]]:
    ok = []
    failed = []
    for label, module_name in CORE_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            ok.append(label)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{label}: {exc}")
    return ok, failed


def main() -> int:
    print("NTL-GPT stable environment check")
    print(f"Repository: {ROOT}")
    print(f"Python: {sys.executable}")

    missing_env, optional_present = _check_env()
    missing_files = _check_files()
    ok_imports, failed_imports = _check_imports()

    _print("Required env vars", [f"{name}: {'OK' if name not in missing_env else 'MISSING'}" for name in REQUIRED_ENV])
    _print("Optional env vars", [f"{name}: {'SET' if name in optional_present else 'EMPTY'}" for name in OPTIONAL_ENV])
    _print("Core imports", [f"{name}: OK" for name in ok_imports] + [f"{msg}" for msg in failed_imports])

    if missing_files:
        _print("Missing files", missing_files)

    print("")
    if missing_env or missing_files or failed_imports:
        print("Result: NOT READY")
        if missing_env:
            print("Action: fill required values in .env before starting the app.")
        if failed_imports:
            print("Action: recreate the conda environment with `conda env create -f environment.yml`.")
        return 1

    print("Result: READY")
    print("Next: streamlit run Streamlit.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
