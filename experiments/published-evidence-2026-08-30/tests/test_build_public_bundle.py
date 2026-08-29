from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


BUNDLE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_bundle", BUNDLE_ROOT / "build_public_bundle.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_json_path_sanitization_preserves_later_escaped_quotes() -> None:
    source = json.dumps(
        {
            "stdout": (
                "Earth Engine review: "
                r"vault/ntl-gpt/run.py"
                "\n  ee.Dictionary({\"times_ms\": [1, 2]})"
            )
        }
    )

    sanitized = MODULE.sanitize_text(source, suffix=".json")
    parsed = json.loads(sanitized)

    assert "vault/ntl-gpt/run.py" in parsed["stdout"]
    assert 'ee.Dictionary({"times_ms": [1, 2]})' in parsed["stdout"]


def test_plain_text_path_sanitization_remains_portable() -> None:
    source = r"Input: runtime/outputs/result.csv"
    assert MODULE.sanitize_text(source, suffix=".md") == "Input: runtime/outputs/result.csv"
