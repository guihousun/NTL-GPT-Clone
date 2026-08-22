"""Offline integrity tests for the annual LongNTL DEI retraining pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import extract_city_tntl_longntl_gee  # noqa: E402
import match_dei_longntl  # noqa: E402


DATA = ROOT / "data"
RESULTS = ROOT / "results"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class AnnualLongNtlPipelineTests(unittest.TestCase):
    def test_scripts_have_v2_contracts_and_annual_only_sources(self) -> None:
        for module in (extract_city_tntl_longntl_gee, match_dei_longntl):
            with self.subTest(module=module.__name__):
                self.assertEqual(
                    module.NTL_SCRIPT_CONTRACT["schema"], "ntl.script.contract.v2"
                )
        contract_text = json.dumps(
            extract_city_tntl_longntl_gee.NTL_SCRIPT_CONTRACT, ensure_ascii=False
        ).lower()
        self.assertIn("annual", contract_text)
        self.assertNotIn("monthly_v1", contract_text)
        self.assertEqual(extract_city_tntl_longntl_gee.BAND, "b1")

    def test_extraction_manifest_and_csv_reconcile(self) -> None:
        csv_path = DATA / "city_tntl_longntl_2017_2024.csv"
        manifest = json.loads(
            (DATA / "city_tntl_longntl_2017_2024_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        rows = read_csv(csv_path)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["output"]["row_count"], 3000)
        self.assertEqual(manifest["output"]["sha256"], sha256_file(csv_path))
        self.assertEqual(len(rows), 3000)
        self.assertEqual(
            Counter(int(row["Year"]) for row in rows),
            Counter({year: 375 for year in range(2017, 2025)}),
        )
        self.assertEqual(
            len({(row["Year"], row["BoundaryGB"]) for row in rows}), 3000
        )
        for row in rows:
            tntl = float(row["TNTL"])
            self.assertTrue(math.isfinite(tntl))
            self.assertGreaterEqual(tntl, 0)
            if tntl == 0:
                self.assertEqual(row["ValidPixelCount"], "0")
                self.assertEqual(row["HasPositivePixels"], "false")

    def test_matching_manifest_preserves_one_quarantine(self) -> None:
        manifest_path = DATA / "dei_longntl_matching_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        training = read_csv(DATA / "dei_longntl_matched_2017_2024.csv")
        quarantine = read_csv(DATA / "dei_longntl_quarantine.csv")
        self.assertEqual(manifest["matching"]["input_label_rows"], 1474)
        self.assertEqual(manifest["matching"]["matched_training_rows"], 1473)
        self.assertEqual(manifest["matching"]["quarantined_rows"], 1)
        self.assertEqual(len(training), 1473)
        self.assertEqual(len(quarantine), 1)
        self.assertEqual(quarantine[0]["Year"], "2023")
        self.assertEqual(quarantine[0]["CityNormalized"], "毫州")
        self.assertIn("亳州=42.7", quarantine[0]["Reason"])
        self.assertEqual(
            manifest["outputs"]["training"]["sha256"],
            sha256_file(DATA / "dei_longntl_matched_2017_2024.csv"),
        )

    def test_training_report_covers_exact_eligible_counts(self) -> None:
        report = json.loads(
            (RESULTS / "longntl_retraining_cv_rmse.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["artifact_type"], "retrained")
        self.assertEqual(report["data_integrity_gate"], "passed")
        self.assertEqual(report["input"]["row_count"], 1473)
        self.assertEqual(
            report["input"]["sha256"],
            sha256_file(DATA / "dei_longntl_matched_2017_2024.csv"),
        )
        expected = {2017: 40, 2018: 100, 2019: 113, 2020: 220,
                    2021: 242, 2022: 242, 2023: 256, 2024: 260}
        for year, count in expected.items():
            result = report["yearly_results"][str(year)]
            self.assertEqual(result["sample_size"], count)
            self.assertIn(
                result["selected_model"],
                {"linear", "logarithmic", "exponential", "quadratic"},
            )
            metrics = result["candidates"][result["selected_model"]]
            for scope in ("in_sample_metrics", "five_fold_out_of_fold_metrics"):
                self.assertTrue(math.isfinite(metrics[scope]["r2"]))
                self.assertTrue(math.isfinite(metrics[scope]["mae"]))
                self.assertGreater(metrics[scope]["rmse"], 0)


if __name__ == "__main__":
    unittest.main()
