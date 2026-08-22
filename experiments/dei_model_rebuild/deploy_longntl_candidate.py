"""Deploy the validated annual LongNTL DEI candidate as the local default.

Deployment is deterministic and recoverable: the current default artifact is
preserved once, a deployed copy is written under experiment results, and the
same bytes are atomically installed at ``base_data/Model/yearly_dei_models.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
DEFAULT_CANDIDATE = ROOT / "results" / "yearly_dei_models_longntl_candidate.json"
DEFAULT_DEPLOYED_RECORD = ROOT / "results" / "yearly_dei_models_longntl_deployed.json"
DEFAULT_TARGET = REPO / "base_data" / "Model" / "yearly_dei_models.json"
DEFAULT_BACKUP = ROOT / "results" / "yearly_dei_models_default_before_longntl_20260809.json"
DEFAULT_MANIFEST = ROOT / "results" / "longntl_deployment_manifest.json"
DEPLOYMENT_DATE = "2026-08-09"


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Install the validated annual LongNTL DEI v2 artifact as the recoverable local runtime default.",
    "input_manifest": [
        {"kind": "validated_candidate_json", "path": "results/yearly_dei_models_longntl_candidate.json", "required": True},
        {"kind": "current_default_json", "path": "base_data/Model/yearly_dei_models.json", "required": False},
    ],
    "method_steps": [
        "validate candidate identity, provenance class, feature semantics, and supported years",
        "preserve the previous default artifact in experiment results",
        "derive a deterministic deployed-status artifact",
        "atomically write identical bytes to the deployed record and runtime default",
        "write a deployment manifest with all SHA-256 values",
    ],
    "parameters": {
        "deployment_date": DEPLOYMENT_DATE,
        "approval": "explicit user confirmation in the active task",
        "overwrite_policy": "replace exact runtime default after recoverable backup",
    },
    "output_manifest": [
        {"kind": "deployed_model_record", "path": "results/yearly_dei_models_longntl_deployed.json", "required": True},
        {"kind": "runtime_default_model", "path": "base_data/Model/yearly_dei_models.json", "required": True},
        {"kind": "previous_default_backup", "path": "results/yearly_dei_models_default_before_longntl_20260809.json", "required": False},
        {"kind": "deployment_manifest", "path": "results/longntl_deployment_manifest.json", "required": True},
    ],
    "validation_checks": [
        "candidate is retrained v2 TNTL-only and covers exactly 2017-2024",
        "candidate is not already marked deployed",
        "backup preserves the pre-deployment default bytes",
        "deployed record and runtime target are byte-identical",
        "manifest hashes match all material artifacts",
    ],
    "failure_gates": [
        "candidate schema, provenance, feature, or year set changed",
        "existing backup conflicts with the current pre-deployment default",
        "atomic write or post-write checksum verification fails",
    ],
    "execution": {
        "mode": "execute",
        "timeout_seconds": 120,
        "overwrite_policy": "replace",
        "network_scope": [],
        "test_strategy": "required unit tests, check mode, and default-runtime direct invocation",
    },
}


class DeploymentError(RuntimeError):
    """Raised when a deployment invariant is not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_unique_json(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DeploymentError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream, object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"cannot read candidate {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeploymentError("candidate root must be an object")
    return value


def validate_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("schema_version") != "ntl-gpt.dei.yearly-formula.v2":
        raise DeploymentError("candidate must use yearly-formula.v2")
    if candidate.get("artifact_type") != "retrained":
        raise DeploymentError("candidate must be classified as retrained")
    if candidate.get("status") != "candidate-not-deployed":
        raise DeploymentError("candidate status must be candidate-not-deployed")
    feature = candidate.get("feature")
    if not isinstance(feature, dict) or feature.get("name") != "TNTL":
        raise DeploymentError("candidate feature must be TNTL")
    if feature.get("antl_is_accepted") is not False:
        raise DeploymentError("candidate must explicitly reject ANTL")
    if set(candidate.get("models", {})) != {str(year) for year in range(2017, 2025)}:
        raise DeploymentError("candidate must cover exactly model years 2017-2024")
    deployment = candidate.get("deployment")
    if not isinstance(deployment, dict) or deployment.get("deployed") is not False:
        raise DeploymentError("candidate deployment.deployed must be false")


def deployed_artifact(candidate: dict[str, Any], candidate_sha: str, target: Path) -> dict[str, Any]:
    artifact = deepcopy(candidate)
    artifact["status"] = "deployed-local-default"
    artifact["deployment"] = {
        **artifact.get("deployment", {}),
        "deployed": True,
        "runtime_model_path": str(target.resolve()),
        "deployed_at": DEPLOYMENT_DATE,
        "deployed_from_candidate_sha256": candidate_sha,
        "approval": "explicit user confirmation in active task",
    }
    obsolete = "Runtime parser compatibility tested, but artifact not copied to base_data/Model."
    artifact["limitations"] = [
        item for item in artifact.get("limitations", []) if item != obsolete
    ]
    return artifact


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def deploy(
    candidate_path: Path,
    deployed_record: Path,
    target: Path,
    backup: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    candidate = load_unique_json(candidate_path)
    validate_candidate(candidate)
    candidate_sha = sha256_file(candidate_path)
    artifact = deployed_artifact(candidate, candidate_sha, target)
    content = json_bytes(artifact)

    previous_default: dict[str, Any] | None = None
    if target.is_file():
        target_sha = sha256_file(target)
        if backup.exists():
            if sha256_file(backup) != target_sha:
                # Idempotent redeployment is allowed when the target already
                # contains the derived deployed artifact and the backup holds
                # the original default.
                if target.read_bytes() != content:
                    raise DeploymentError(
                        "existing backup differs from the current default; refusing overwrite"
                    )
                previous_default = {
                    "path": str(backup.resolve()),
                    "sha256": sha256_file(backup),
                }
            else:
                previous_default = {
                    "path": str(backup.resolve()),
                    "sha256": sha256_file(backup),
                }
        else:
            atomic_write(backup, target.read_bytes())
            previous_default = {
                "path": str(backup.resolve()),
                "sha256": sha256_file(backup),
            }
    elif backup.exists():
        previous_default = {
            "path": str(backup.resolve()),
            "sha256": sha256_file(backup),
        }

    atomic_write(deployed_record, content)
    atomic_write(target, content)
    if deployed_record.read_bytes() != target.read_bytes():
        raise DeploymentError("deployed record and runtime target are not byte-identical")

    manifest = {
        "schema_version": "ntl-gpt.dei.deployment.v1",
        "status": "deployed-local-default",
        "deployed_at": DEPLOYMENT_DATE,
        "approval": "explicit user confirmation in active task",
        "candidate": {
            "path": str(candidate_path.resolve()),
            "sha256": candidate_sha,
        },
        "previous_default": previous_default,
        "deployed_record": {
            "path": str(deployed_record.resolve()),
            "sha256": sha256_file(deployed_record),
        },
        "runtime_target": {
            "path": str(target.resolve()),
            "sha256": sha256_file(target),
        },
        "supported_years": list(range(2017, 2025)),
        "feature": "TNTL",
        "antl_is_accepted": False,
    }
    atomic_write(manifest_path, json_bytes(manifest))
    return manifest


def check(deployed_record: Path, target: Path, manifest_path: Path) -> dict[str, Any]:
    if not deployed_record.is_file() or not target.is_file() or not manifest_path.is_file():
        raise DeploymentError("deployed record, runtime target, or manifest is missing")
    manifest = load_unique_json(manifest_path)
    if manifest.get("status") != "deployed-local-default":
        raise DeploymentError("deployment manifest status is not deployed-local-default")
    if deployed_record.read_bytes() != target.read_bytes():
        raise DeploymentError("deployed record and runtime target differ")
    expected = manifest.get("runtime_target", {}).get("sha256")
    if sha256_file(target) != expected:
        raise DeploymentError("runtime target checksum differs from deployment manifest")
    artifact = load_unique_json(target)
    if artifact.get("status") != "deployed-local-default":
        raise DeploymentError("runtime artifact status is not deployed-local-default")
    if artifact.get("deployment", {}).get("deployed") is not True:
        raise DeploymentError("runtime artifact does not declare deployment")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--deployed-record", type=Path, default=DEFAULT_DEPLOYED_RECORD)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = (
        check(args.deployed_record, args.target, args.manifest)
        if args.check
        else deploy(
            args.candidate,
            args.deployed_record,
            args.target,
            args.backup,
            args.manifest,
        )
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
