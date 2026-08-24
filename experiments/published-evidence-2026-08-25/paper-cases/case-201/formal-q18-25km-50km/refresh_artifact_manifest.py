"""Write a self-contained SHA-256 inventory for the formal Q18 25/50 package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifact-manifest.json"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    artifacts = []
    for path in sorted(ROOT.iterdir()):
        if path.is_file() and path != OUT:
            artifacts.append(
                {
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                }
            )
    manifest = {
        "schema": "ntl.paper-case.artifact-manifest.v2",
        "case_id": "Q18-myanmar-earthquake",
        "status": "current_formal_25km_50km",
        "supersedes_for_paper_use": "../formal 25 km / 100 km root-level artifacts",
        "artifacts": artifacts,
    }
    OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest entries={len(artifacts)}")


if __name__ == "__main__":
    main()
