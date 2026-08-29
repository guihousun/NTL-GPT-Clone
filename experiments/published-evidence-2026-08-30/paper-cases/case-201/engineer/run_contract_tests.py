"""Run Case 201 contract tests and persist the exact local result."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    (root / "validation" / "contract-test-output.txt").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    payload = {
        "schema_version": "ntl.case201.contract-test-run.v1",
        "executed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "command": command,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "output_path": "validation/contract-test-output.txt",
    }
    (root / "validation" / "contract-test-result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
