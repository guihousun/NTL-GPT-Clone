"""Unit and integration tests for reconstructed and retraining DEI assets."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


NTL_SCRIPT_CONTRACT = {
    "schema": "ntl.script.contract.v2",
    "objective": "Test the DEI paper reconstruction and fail-closed retraining gate.",
    "input_manifest": [
        {
            "kind": "experiment_assets",
            "path": "D:/NTL-GPT-main/experiments/dei_model_rebuild",
            "required": True,
        }
    ],
    "method_steps": ["run unit tests", "run command-line reconstruction and validation checks"],
    "parameters": {"framework": "unittest"},
    "output_manifest": [
        {"kind": "unittest_report", "path": "stdout/stderr", "required": True}
    ],
    "validation_checks": ["formula arithmetic", "schema", "failure gates", "four candidate fits"],
    "failure_gates": ["any failed assertion or non-zero integration command"],
    "execution": {
        "mode": "local",
        "timeout_seconds": 120,
        "overwrite_policy": "temporary-directory writes only",
        "network_scope": [],
        "test_strategy": "unittest unit and subprocess integration checks",
    },
}


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import reconstruct_from_paper  # noqa: E402
import train_dei_models  # noqa: E402
import validate_reconstruction  # noqa: E402
import verify_h3c_workbook  # noqa: E402
from reconstruct_from_paper import build_artifact, predict  # noqa: E402
from train_dei_models import (  # noqa: E402
    DataIntegrityError,
    MODEL_NAMES,
    load_and_validate,
    train,
)
from validate_reconstruction import validate  # noqa: E402


MODEL_PATH = ROOT / "yearly_dei_models.json"
FIELDS = [
    "city",
    "year",
    "dei",
    "tntl",
    "dei_source",
    "boundary_source",
    "ntl_product",
    "preprocessing_id",
]


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def complete_rows(count: int = 10, year: int = 2020) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        tntl = 1000.0 * (index + 1) ** 1.7
        rows.append(
            {
                "city": f"City-{index + 1}",
                "year": year,
                "dei": 12.619 * math.log(tntl) - 81.687 + (index % 3 - 1) * 0.4,
                "tntl": tntl,
                "dei_source": "source:edition:2020",
                "boundary_source": "boundary:version:2020",
                "ntl_product": "SNPP-VIIRS-vcm-v1",
                "preprocessing_id": "pipeline:v1",
            }
        )
    return rows


class ReconstructionTests(unittest.TestCase):
    def test_all_experiment_scripts_declare_v2_contract(self) -> None:
        required = {
            "mode",
            "timeout_seconds",
            "overwrite_policy",
            "network_scope",
            "test_strategy",
        }
        for module in (
            reconstruct_from_paper,
            validate_reconstruction,
            train_dei_models,
            verify_h3c_workbook,
        ):
            with self.subTest(module=module.__name__):
                contract = module.NTL_SCRIPT_CONTRACT
                self.assertEqual(contract["schema"], "ntl.script.contract.v2")
                for key in (
                    "objective",
                    "input_manifest",
                    "method_steps",
                    "parameters",
                    "output_manifest",
                    "validation_checks",
                    "failure_gates",
                    "execution",
                ):
                    self.assertIn(key, contract)
                for manifest_name in ("input_manifest", "output_manifest"):
                    for item in contract[manifest_name]:
                        self.assertIsInstance(item, dict)
                        self.assertTrue({"kind", "path", "required"}.issubset(item))
                self.assertTrue(required.issubset(contract["execution"]))
                if module is verify_h3c_workbook:
                    self.assertEqual(
                        contract["execution"]["network_scope"][0]["host"],
                        "deindex.h3c.com",
                    )
                else:
                    self.assertEqual(contract["execution"]["network_scope"], [])

    def test_offline_workbook_parser_matches_recorded_edition_counts(self) -> None:
        workbook = Path(r"D:\NTL-GPT-main\base_data\dei_2017-2023.xlsx")
        if not workbook.exists():
            self.skipTest("user-supplied DEI workbook is not present")
        self.assertEqual(verify_h3c_workbook.sha256_file(workbook), verify_h3c_workbook.EXPECTED_SHA256)
        pairs = verify_h3c_workbook.read_workbook_pairs(workbook)
        self.assertEqual(
            {year: len(values) for year, values in pairs.items()},
            {2017: 40, 2018: 100, 2019: 113, 2020: 220, 2021: 242, 2022: 242, 2023: 257, 2024: 260},
        )

    def test_committed_json_exactly_matches_builder(self) -> None:
        committed = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(committed, build_artifact())
        self.assertEqual(validate(committed), [])

    def test_exact_supported_year_arithmetic(self) -> None:
        artifact = build_artifact()
        tntl = 100000.0
        expected = {
            2017: 62.285533199556454,
            2018: 61.774734621735234,
            2019: 64.05293879989195,
            2020: 63.59460644245932,
        }
        for year, value in expected.items():
            self.assertAlmostEqual(predict(artifact, year, tntl), value, places=12)

    def test_invalid_feature_and_year_fail(self) -> None:
        artifact = build_artifact()
        for value in (0.0, -1.0, math.nan, math.inf, -math.inf):
            with self.subTest(tntl=value), self.assertRaisesRegex(
                ValueError, "finite and strictly positive"
            ):
                predict(artifact, 2020, value)
        with self.assertRaisesRegex(ValueError, "unsupported model year"):
            predict(artifact, 2021, 100000.0)

    def test_corrupt_artifact_is_rejected(self) -> None:
        artifact = build_artifact()
        artifact["models"]["2020"]["coefficient"] = 0
        self.assertTrue(any("2020: coefficient" in error for error in validate(artifact)))

    def test_command_line_checks(self) -> None:
        for command in (
            [sys.executable, str(ROOT / "reconstruct_from_paper.py"), "--check", str(MODEL_PATH)],
            [sys.executable, str(ROOT / "validate_reconstruction.py"), str(MODEL_PATH)],
        ):
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TrainingGateTests(unittest.TestCase):
    def test_antl_is_not_accepted_as_tntl(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "antl.csv"
            fields = ["antl" if field == "tntl" else field for field in FIELDS]
            rows = complete_rows(5)
            for row in rows:
                row["antl"] = row.pop("tntl")
            write_csv(path, rows, fields)
            with self.assertRaisesRegex(DataIntegrityError, "ANTL.*not interchangeable"):
                load_and_validate(path)

    def test_missing_provenance_nonpositive_tntl_and_duplicate_fail_together(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.csv"
            rows = complete_rows(6)
            rows[0]["boundary_source"] = "unknown"
            rows[1]["tntl"] = 0
            rows[3]["city"] = rows[2]["city"]
            write_csv(path, rows)
            with self.assertRaises(DataIntegrityError) as caught:
                load_and_validate(path)
            message = str(caught.exception)
            self.assertIn("boundary_source must contain explicit provenance", message)
            self.assertIn("tntl must be strictly positive", message)
            self.assertIn("duplicate (city, year)", message)

    def test_dei_only_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dei_only.csv"
            write_csv(
                path,
                [{"city": "A", "year": 2020, "dei": 80}],
                ["city", "year", "dei"],
            )
            with self.assertRaisesRegex(DataIntegrityError, "missing required fields"):
                load_and_validate(path)

    def test_complete_rows_fit_all_four_candidates_and_cv_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "complete.csv"
            write_csv(path, complete_rows())
            records = load_and_validate(path)
            report = train(records, input_path=path)
            self.assertEqual(report["artifact_type"], "retrained")
            result = report["yearly_results"]["2020"]
            self.assertEqual(set(result["candidates"]), set(MODEL_NAMES))
            self.assertEqual(result["selected_model"], "logarithmic")
            for candidate in result["candidates"].values():
                for scope in ("in_sample_metrics", "five_fold_out_of_fold_metrics"):
                    self.assertEqual(set(candidate[scope]), {"r2", "mae", "rmse"})
                    self.assertTrue(math.isfinite(candidate[scope]["mae"]))
                    self.assertTrue(math.isfinite(candidate[scope]["rmse"]))


if __name__ == "__main__":
    unittest.main()
