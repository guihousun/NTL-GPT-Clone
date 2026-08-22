"""Tests for recoverable annual LongNTL model deployment."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import deploy_longntl_candidate  # noqa: E402


class LongNtlDeploymentTests(unittest.TestCase):
    def test_contract_is_v2_and_requires_recoverable_backup(self) -> None:
        contract = deploy_longntl_candidate.NTL_SCRIPT_CONTRACT
        self.assertEqual(contract["schema"], "ntl.script.contract.v2")
        self.assertEqual(contract["execution"]["overwrite_policy"], "replace")
        self.assertIn("backup", " ".join(contract["failure_gates"]))

    def test_deploy_is_recoverable_and_idempotent(self) -> None:
        candidate = ROOT / "results" / "yearly_dei_models_longntl_candidate.json"
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            record = base / "record.json"
            target = base / "Model" / "yearly_dei_models.json"
            backup = base / "backup.json"
            manifest = base / "manifest.json"
            target.parent.mkdir(parents=True)
            original = b'{"artifact_type":"reconstructed-from-paper"}\n'
            target.write_bytes(original)

            first = deploy_longntl_candidate.deploy(
                candidate, record, target, backup, manifest
            )
            second = deploy_longntl_candidate.deploy(
                candidate, record, target, backup, manifest
            )

            self.assertEqual(backup.read_bytes(), original)
            self.assertEqual(record.read_bytes(), target.read_bytes())
            self.assertEqual(first["runtime_target"]["sha256"], second["runtime_target"]["sha256"])
            artifact = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(artifact["status"], "deployed-local-default")
            self.assertTrue(artifact["deployment"]["deployed"])
            self.assertNotIn(
                "Runtime parser compatibility tested, but artifact not copied to base_data/Model.",
                artifact["limitations"],
            )
            checked = deploy_longntl_candidate.check(record, target, manifest)
            self.assertEqual(checked["status"], "deployed-local-default")

    def test_candidate_semantics_fail_closed(self) -> None:
        candidate = json.loads(
            (ROOT / "results" / "yearly_dei_models_longntl_candidate.json").read_text(
                encoding="utf-8"
            )
        )
        candidate["feature"]["name"] = "ANTL"
        with self.assertRaises(deploy_longntl_candidate.DeploymentError):
            deploy_longntl_candidate.validate_candidate(candidate)


if __name__ == "__main__":
    unittest.main()
