"""Create a self-contained manifest for the Q18 UTC_Time audit package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
Q18 = ROOT.parent / "paper-case-multiagent-2026-08-13" / "Q18-myanmar-earthquake" / "formal-25km-50km-20260817"


def identity(path: Path, *, relative_to: Path) -> dict[str, object]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": path.relative_to(relative_to).as_posix(), "bytes": path.stat().st_size, "sha256": digest}


def main() -> None:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.name not in {"artifact-manifest.json", "session"} and "__pycache__" not in path.parts:
            files.append(identity(path, relative_to=ROOT))
    external = [
        {"label": "formal Q18 validation", **identity(Q18 / "formal-q18-validation.json", relative_to=Q18.parent)},
        {"label": "formal Q18 analysis CSV", **identity(Q18 / "formal-q18-analysis-ready.csv", relative_to=Q18.parent)},
        {"label": "formal Q18 observation package", **identity(Q18 / "formal-observation-package.json", relative_to=Q18.parent)},
    ]
    payload = {
        "schema_version": "ntl.q18.vnp46a1-utc-time-artifact-manifest.v1",
        "status": "completed_source_backed_utc_time_verification",
        "files": files,
        "external_referenced_inputs": external,
        "exclusions": ["Earthdata bearer tokens", "Earthdata cookies", "VNP46A2 radiance recomputation", "deployment-runtime or benchmark telemetry"],
    }
    (ROOT / "artifact-manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
