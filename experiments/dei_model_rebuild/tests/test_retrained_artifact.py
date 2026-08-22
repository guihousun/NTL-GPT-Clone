"""Tests for the LongNTL retrained candidate artifact and Jiangsu fitted values."""

from __future__ import annotations

import csv
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_retrained_artifact as builder  # noqa: E402
import predict_jiangsu_2020 as jiangsu  # noqa: E402


ARTIFACT_PATH = ROOT / "results" / "yearly_dei_models_longntl_candidate.json"
METRICS_PATH = ROOT / "results" / "longntl_model_metrics.csv"
PREDICTIONS_PATH = ROOT / "results" / "jiangsu_2020_predictions_longntl.csv"


class RetrainedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifact = builder.build_artifact()

    def test_scripts_declare_literal_v2_contract(self) -> None:
        for module in (builder, jiangsu):
            with self.subTest(module=module.__name__):
                contract = module.NTL_SCRIPT_CONTRACT
                self.assertEqual(contract["schema"], "ntl.script.contract.v2")
                self.assertEqual(contract["execution"]["network_scope"], [])
                self.assertIn("test_strategy", contract["execution"])

    def test_committed_artifact_is_deterministic_and_exact(self) -> None:
        self.assertEqual(
            json.loads(ARTIFACT_PATH.read_text(encoding="utf-8")), self.artifact
        )
        with tempfile.TemporaryDirectory() as folder:
            first_json = Path(folder) / "first.json"
            first_csv = Path(folder) / "first.csv"
            second_json = Path(folder) / "second.json"
            second_csv = Path(folder) / "second.csv"
            builder.write_outputs(self.artifact, first_json, first_csv)
            builder.write_outputs(builder.build_artifact(), second_json, second_csv)
            self.assertEqual(first_json.read_bytes(), second_json.read_bytes())
            self.assertEqual(first_csv.read_bytes(), second_csv.read_bytes())
            self.assertEqual(first_json.read_bytes(), ARTIFACT_PATH.read_bytes())
            self.assertEqual(first_csv.read_bytes(), METRICS_PATH.read_bytes())

    def test_each_winner_is_recomputed_from_cv_rmse(self) -> None:
        report = json.loads(builder.DEFAULT_REPORT.read_text(encoding="utf-8"))
        for year, model in self.artifact["models"].items():
            candidates = report["yearly_results"][year]["candidates"]
            expected = min(
                builder.MODEL_ORDER,
                key=lambda name: candidates[name]["five_fold_out_of_fold_metrics"][
                    "rmse"
                ],
            )
            with self.subTest(year=year):
                self.assertEqual(model["model_type"], expected)
                self.assertEqual(
                    model["selection"]["selected_cv_rmse"],
                    candidates[expected]["five_fold_out_of_fold_metrics"]["rmse"],
                )

    def test_all_four_formula_families_are_supported(self) -> None:
        x = 10.0
        cases = {
            "linear": ({"a": 2.0, "b": 3.0}, 23.0),
            "logarithmic": ({"a": 2.0, "b": 3.0}, 2.0 * math.log(x) + 3.0),
            "exponential": ({"a": 0.1, "b": 3.0}, 3.0 * math.exp(1.0)),
            "quadratic": ({"a": 2.0, "b": 3.0, "c": 4.0}, 234.0),
        }
        for model_type, (parameters, expected) in cases.items():
            with self.subTest(model_type=model_type):
                self.assertAlmostEqual(
                    builder.evaluate_model(model_type, parameters, x), expected
                )

    def test_input_hashes_and_candidate_not_deployed_status(self) -> None:
        inputs = self.artifact["inputs"]
        for value in inputs.values():
            if isinstance(value, dict) and value.get("path") and value.get("sha256"):
                with self.subTest(path=value["path"]):
                    self.assertEqual(
                        builder.sha256_file(Path(value["path"])), value["sha256"]
                    )
        self.assertEqual(self.artifact["artifact_type"], "retrained")
        self.assertEqual(self.artifact["status"], "candidate-not-deployed")
        self.assertFalse(self.artifact["deployment"]["deployed"])
        self.assertIsNone(self.artifact["deployment"]["runtime_model_path"])
        self.assertTrue(
            self.artifact["deployment"]["runtime_schema_compatibility_tested"]
        )
        self.assertNotIn("runtime_tool_modified", self.artifact["deployment"])
        self.assertNotIn("base_data\\Model", str(ARTIFACT_PATH))

    def test_metrics_have_32_rows_and_one_selected_per_year(self) -> None:
        with METRICS_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 8 * 4)
        for year in self.artifact["models"]:
            annual = [row for row in rows if row["year"] == year]
            self.assertEqual(sum(row["selected"] == "true" for row in annual), 1)

    def test_jiangsu_has_13_in_sample_fitted_values_with_exact_residuals(self) -> None:
        generated = jiangsu.generate_rows(ARTIFACT_PATH, builder.DEFAULT_MATCHED)
        self.assertEqual([row["city"] for row in generated], list(jiangsu.JIANGSU_13))
        self.assertEqual(len(generated), 13)
        for row in generated:
            self.assertEqual(
                row["evaluation_scope"],
                "in-sample fitted value; not external validation",
            )
            observed = float(row["observed_dei"])
            predicted = float(row["predicted_dei"])
            residual = float(row["residual_observed_minus_predicted"])
            self.assertAlmostEqual(residual, observed - predicted, places=10)
        with PREDICTIONS_PATH.open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            committed = list(csv.DictReader(stream))
        self.assertEqual(committed, generated)


if __name__ == "__main__":
    unittest.main()
