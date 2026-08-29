"""Create a reproducible source-path index and package manifest for this experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


VAULT = Path(r"local-path/Research_vault")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def vault_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(VAULT).as_posix()
    except ValueError:
        return str(path)


def file_record(path: Path, label: str, purpose: str) -> dict[str, object]:
    record: dict[str, object] = {
        "label": label,
        "path": vault_relative(path),
        "purpose": purpose,
        "exists": path.is_file(),
    }
    if path.is_file():
        record.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.experiment_root.resolve()

    sources = [
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q19-tehran-city-longseries/daily-vnp46a2.csv",
            "Q19 daily statistics",
            "Analyst full-baseline recomputation",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q19-tehran-city-longseries/tehran-boundary.geojson",
            "Q19 administrative AOI",
            "City of Tehran ADM2/Shahrestan identity",
        ),
        file_record(
            VAULT / "work/projects/conflictntl/data/raw/events/source-events/ISW_storymap_events_2026-02-27_2026-04-27.csv",
            "Q19 dated event snapshot",
            "Exact-coordinate retained-event subset ranking",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-observation-package.json",
            "Q17 observation package",
            "SDGSAT-1 lineage and index contract review",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-class-statistics.json",
            "Q17 class statistics",
            "Independent pixel-count review",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/formal-observation-package.json",
            "Q18 observation package",
            "VNP46A2/HDF/QA/support review",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/experiments/paper-case-multiagent-2026-08-13/Q18-myanmar-earthquake/formal-25km-50km-20260817/formal-analysis-results.json",
            "Q18 formal analysis",
            "25/50 km table/JSON consistency review",
        ),
        file_record(
            VAULT / "work/projects/ntl-gpt/decisions/2026-08-17-q18-formal-25km-50km-supports.md",
            "Q18 support decision",
            "Formal paper-facing spatial-support pair",
        ),
    ]

    source_csv = root / "input-manifests/source-data-paths.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["label", "path", "purpose", "exists", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(sources)

    output_path = root / "artifact-manifest.json"
    generated = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == output_path or "__pycache__" in path.parts or path.name == ".gitkeep":
            continue
        generated.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    payload = {
        "schema_version": "codex-subagent-case-evidence-package-manifest.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "execution_identity": {
            "kind": "Codex-subagent case-evidence simulation",
            "not_deployed_ntl_gpt_runtime": True,
            "not_deep_agents_trace": True,
            "not_benchmark_evidence": True,
        },
        "source_data": sources,
        "generated_artifacts": generated,
        "manifest_self_hash": {
            "included": False,
            "reason": "The manifest omits its own hash to avoid recursive self-reference.",
        },
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
