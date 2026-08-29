"""Build the sanitized public NTL-GPT experiment-evidence bundle.

The source Vault remains authoritative.  This script only copies selected,
non-sensitive derived evidence into a GitHub-ready release directory.  It
does not copy raw HDF5 inputs, large intermediate rasters, caches, or Python
bytecode.  Text files are rewritten to remove known local absolute paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".ndjson",
    ".py",
    ".svg",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class CopySpec:
    source: Path
    target: str
    omit_names: frozenset[str] = frozenset()
    omit_prefixes: tuple[str, ...] = ()
    omit_suffixes: frozenset[str] = frozenset({".pyc"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_copy(relative: Path, spec: CopySpec) -> bool:
    text = relative.as_posix()
    if relative.name == "artifact-manifest.json":
        return False
    if relative.name in spec.omit_names:
        return False
    if relative.suffix.lower() in spec.omit_suffixes:
        return False
    if "__pycache__" in relative.parts or relative.name == ".gitkeep":
        return False
    return not any(text == prefix or text.startswith(prefix + "/") for prefix in spec.omit_prefixes)


PLAIN_WINDOWS_PATH = re.compile(r'''[A-Za-z]:(?:\\\\|\\|/)[^"'`\r\n]*''')
JSON_WINDOWS_PATH = re.compile(
    r'''[A-Za-z]:(?:\\\\|/)(?:(?!(?<!\\)\\(?:["/bfnrtu]))[^"'`\r\n])*'''
)


def sanitize_text(text: str, *, suffix: str = "") -> str:
    """Replace local Windows paths while preserving JSON string escapes."""

    def redact(match: re.Match[str]) -> str:
        normalized = match.group(0).replace("\\\\", "/").replace("\\", "/")
        for marker, replacement in (
            ("/Research_vault/work/projects/ntl-gpt/", "vault/ntl-gpt/"),
            ("/Research_vault/work/projects/conflictntl/", "vault/conflictntl/"),
            ("/NTL-GPT-main/.worktrees/hierarchical-multiagent-experiments/", "runtime/"),
            ("/NTL-GPT-main/", "runtime/"),
            ("/NTL-CHAT/", "user-provided-local-data/"),
            ("/NTL-GPT-smoke-runs/", "local-runtime/"),
        ):
            if marker in normalized:
                return replacement + normalized.split(marker, 1)[1]
        if "/Users/" in normalized:
            after_users = normalized.split("/Users/", 1)[1].split("/", 1)
            return "local-user/" + (after_users[1] if len(after_users) == 2 else "")
        return "local-path/" + normalized.rsplit("/", 1)[-1]

    pattern = JSON_WINDOWS_PATH if suffix in {".json", ".jsonl", ".ndjson"} else PLAIN_WINDOWS_PATH
    sanitized = pattern.sub(redact, text)
    return sanitized.replace("\r\n", "\n").replace("\r", "\n")


def refresh_manifest(output: Path, source_records: Iterable[dict[str, object]] = ()) -> None:
    """Sanitize all published text files and rebuild the derived integrity manifest."""

    source_roles = {
        str(record["path"]): str(record["source_role"])
        for record in source_records
    }
    manifest_path = output / "public-artifact-manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        for record in existing.get("files", []):
            source_roles.setdefault(str(record["path"]), str(record.get("source_role", "derived-public-bundle")))

    records: list[dict[str, object]] = []
    for path in sorted(candidate for candidate in output.rglob("*") if candidate.is_file()):
        relative = path.relative_to(output)
        if relative.name == "public-artifact-manifest.json" or "__pycache__" in relative.parts or relative.suffix == ".pyc":
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            original = path.read_text(encoding="utf-8")
            sanitized = sanitize_text(original, suffix=path.suffix.lower())
            if sanitized != original:
                path.write_text(sanitized, encoding="utf-8", newline="")
        relative_text = relative.as_posix()
        records.append(
            {
                "path": relative_text,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "source_role": source_roles.get(relative_text, "derived-public-bundle"),
            }
        )

    manifest = {
        "schema_version": "ntl-gpt.published-evidence.v1",
        "scope": "Public derived experimental evidence; raw source data, credentials, caches, local paths, and selected large intermediates are excluded.",
        "source_runtime_commit": "14b95a2379d7d2a53e6df3adf1f1d6a51b086dec",
        "published_bundle_date": "2026-08-30",
        "file_count": len(records),
        "files": records,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_spec(spec: CopySpec, destination: Path, records: list[dict[str, object]]) -> None:
    if not spec.source.is_dir():
        raise FileNotFoundError(spec.source)
    for source in sorted(path for path in spec.source.rglob("*") if path.is_file()):
        relative = source.relative_to(spec.source)
        if not should_copy(relative, spec):
            continue
        target = destination / spec.target / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in TEXT_SUFFIXES:
            target.write_text(
                sanitize_text(source.read_text(encoding="utf-8"), suffix=source.suffix.lower()),
                encoding="utf-8",
                newline="",
            )
        else:
            shutil.copy2(source, target)
        records.append(
            {
                "path": target.relative_to(destination).as_posix(),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
                "source_role": spec.target,
            }
        )


def build_specs(vault_project: Path) -> tuple[CopySpec, ...]:
    experiments = vault_project / "experiments"
    return (
        CopySpec(experiments / "benchmark-v1" / "final-record-20260822", "benchmark/final-record-20260822"),
        CopySpec(
            vault_project / "manuscript" / "supplementary-data" / "ntl-gpt-current-supplement-2026-08-22",
            "benchmark/supplementary-data-20260822",
        ),
        CopySpec(experiments / "paper-case-201-myanmar-first-local-night-2026-08-18", "paper-cases/case-201"),
        CopySpec(
            experiments / "paper-case-multiagent-2026-08-13" / "Q18-myanmar-earthquake" / "formal-25km-50km-20260817",
            "paper-cases/case-201/formal-q18-25km-50km",
        ),
        CopySpec(
            experiments / "q18-vnp46a1-utc-time-verification-2026-08-20",
            "paper-cases/case-201/vnp46a1-utc-time-verification",
            omit_prefixes=("source",),
        ),
        CopySpec(
            experiments / "paper-case-codex-subagent-rerun-2026-08-17",
            "paper-cases/case-202/codex-subagent-rerun",
        ),
        CopySpec(
            experiments / "case-202-tehran-latest-vnp46a2-2026-08-21",
            "paper-cases/case-202/latest-vnp46a2",
            omit_names=frozenset({"artifact-manifest.json", "case202-tehran-latest-timeseries.tiff"}),
            omit_prefixes=("history", "qa/independent-audit"),
        ),
        CopySpec(
            experiments / "paper-case-multiagent-2026-08-13" / "Q17-sdgsat-light-classification",
            "paper-cases/case-203",
            omit_names=frozenset(
                {
                    "artifact-manifest.json",
                    "formal-SDGSAT1-shanghai-RRLI.tif",
                    "formal-SDGSAT1-shanghai-RBLI.tif",
                }
            ),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true", help="sanitize an existing bundle and rebuild its manifest")
    args = parser.parse_args()

    output = args.output.resolve()
    if args.refresh:
        if not output.is_dir():
            raise FileNotFoundError(output)
        refresh_manifest(output)
        return 0
    allowed_existing = {"build_public_bundle.py", "__pycache__"}
    if any(path.name not in allowed_existing for path in output.iterdir()):
        raise RuntimeError(f"Output directory must be empty: {output}")

    records: list[dict[str, object]] = []
    for spec in build_specs(args.vault_project.resolve()):
        copy_spec(spec, output, records)

    registry = args.vault_project / "experiments" / "paper-case-registry.json"
    registry_target = output / "paper-cases" / "paper-case-registry.json"
    registry_target.parent.mkdir(parents=True, exist_ok=True)
    registry_target.write_text(
        sanitize_text(registry.read_text(encoding="utf-8"), suffix=".json"),
        encoding="utf-8",
        newline="",
    )
    records.append(
        {
            "path": registry_target.relative_to(output).as_posix(),
            "bytes": registry_target.stat().st_size,
            "sha256": sha256(registry_target),
            "source_role": "paper-case-registry",
        }
    )

    readme = output / "README.md"
    readme.write_text(
        "# NTL-GPT published experiment evidence\n\n"
        "This directory is a GitHub-ready, derived evidence bundle generated "
        "from the active Research Vault experiment records on 2026-08-30. "
        "It is not a new runtime execution.\n\n"
        "## Included evidence\n\n"
        "- `benchmark/`: the current 200-task reconciled final record (Full "
        "176/200; matched Single-Agent 170/200), per-task result tables, and "
        "resource summaries. The record is a dirty-runtime dated reconciliation, "
        "not a clean-release reproducibility claim.\n"
        "- `paper-cases/case-201/`: Myanmar first post-event local-night timing, "
        "formal 25/50 km descriptive comparison, and VNP46A1 `UTC_Time` timing "
        "verification.\n"
        "- `paper-cases/case-202/`: Tehran event-selection evidence, the Codex "
        "subagent reconstruction, and the latest VNP46A2 extension through the "
        "GEE collection endpoint of 2026-08-19 UTC.\n"
        "- `paper-cases/case-203/`: SDGSAT-1 classification scripts, statistics, "
        "preview, and final classification GeoTIFF.\n\n"
        "## Deliberate exclusions\n\n"
        "Raw HDF5 inputs, RRLI/RBLI intermediate GeoTIFFs, the 32 MB Tehran TIFF, "
        "caches, Python bytecode, credentials, and local absolute paths are not "
        "published. `public-artifact-manifest.json` is the integrity manifest for "
        "this sanitized bundle; it replaces upstream manifests whose hashes bind "
        "to omitted or path-redacted local artifacts.\n\n"
        "## Evidence boundary\n\n"
        "Case 201–203 are paper-case/supplementary workflow evidence and are not "
        "members of the formal 200-task benchmark. They are Codex-subagent "
        "workflow reconstructions, not deployed NTL-GPT runtime telemetry or "
        "Full-versus-Single performance evidence.\n\n"
        "Source runtime commit recorded by the source experiment package: "
        "`14b95a2379d7d2a53e6df3adf1f1d6a51b086dec`.\n",
        encoding="utf-8",
        newline="",
    )
    records.extend(
        [
            {
                "path": "build_public_bundle.py",
                "bytes": (output / "build_public_bundle.py").stat().st_size,
                "sha256": sha256(output / "build_public_bundle.py"),
                "source_role": "bundle-builder",
            },
            {
                "path": "README.md",
                "bytes": readme.stat().st_size,
                "sha256": sha256(readme),
                "source_role": "bundle-readme",
            },
        ]
    )

    refresh_manifest(output, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
