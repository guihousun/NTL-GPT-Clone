"""Tests for deterministic normalization of the 2017-2024 DEI workbook."""

from __future__ import annotations

import csv
import math
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prep_dei_labels  # noqa: E402


WORKBOOK = ROOT.parents[1] / "base_data" / "dei_2017-2023.xlsx"
EXPECTED_COUNTS = {
    2017: 40,
    2018: 100,
    2019: 113,
    2020: 220,
    2021: 242,
    2022: 242,
    2023: 257,
    2024: 260,
}
JIANGSU_13 = {
    "南京",
    "苏州",
    "无锡",
    "常州",
    "镇江",
    "扬州",
    "泰州",
    "南通",
    "盐城",
    "淮安",
    "连云港",
    "宿迁",
    "徐州",
}
EXPECTED_JIANGSU_BY_YEAR = {
    2017: {"南京", "苏州", "无锡"},
    2018: JIANGSU_13 - {"淮安", "连云港", "宿迁"},
    2019: JIANGSU_13,
    2020: JIANGSU_13,
    2021: JIANGSU_13,
    2022: JIANGSU_13,
    2023: JIANGSU_13,
    2024: JIANGSU_13,
}


class PrepDeiLabelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = prep_dei_labels.read_labels(WORKBOOK)

    def test_contract_is_literal_v2(self) -> None:
        contract = prep_dei_labels.NTL_SCRIPT_CONTRACT
        self.assertEqual(contract["schema"], "ntl.script.contract.v2")
        self.assertEqual(contract["execution"]["test_strategy"].split()[0], "unit")
        self.assertEqual(contract["execution"]["network_scope"], [])

    def test_actual_year_counts_and_total(self) -> None:
        counts = {
            year: sum(record.year == year for record in self.records)
            for year in EXPECTED_COUNTS
        }
        self.assertEqual(counts, EXPECTED_COUNTS)
        self.assertEqual(len(self.records), 1474)

    def test_unique_keys_nonempty_names_and_dei_range(self) -> None:
        keys = [(record.year, record.city_normalized) for record in self.records]
        self.assertEqual(len(keys), len(set(keys)))
        for record in self.records:
            self.assertTrue(record.city)
            self.assertTrue(record.city_normalized)
            value = float(record.dei)
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 100.0)

    def test_validator_fails_closed_on_duplicate_empty_and_out_of_range(self) -> None:
        valid = prep_dei_labels.LabelRecord(2017, "南京", "南京", Decimal("77"))
        duplicate = prep_dei_labels.LabelRecord(2017, "南京", "南京", Decimal("78"))
        empty = prep_dei_labels.LabelRecord(2017, "", "", Decimal("77"))
        out_of_range = prep_dei_labels.LabelRecord(
            2017, "南京", "南京", Decimal("101")
        )
        for rows in ([valid, duplicate], [empty], [out_of_range]):
            with self.subTest(rows=rows):
                with self.assertRaises(prep_dei_labels.LabelIntegrityError):
                    prep_dei_labels.validate_labels(rows)

    def test_conservative_city_normalization(self) -> None:
        self.assertEqual(prep_dei_labels.clean_city_name("  12 南\u3000京  "), "南京")
        self.assertEqual(prep_dei_labels.normalize_city_name("１２苏州"), "苏州")
        self.assertEqual(prep_dei_labels.normalize_city_name("吉林"), "吉林")

    def test_jiangsu_visibility_respects_observed_years(self) -> None:
        for year, expected in EXPECTED_JIANGSU_BY_YEAR.items():
            observed = {
                record.city_normalized
                for record in self.records
                if record.year == year and record.city_normalized in JIANGSU_13
            }
            with self.subTest(year=year):
                self.assertEqual(observed, expected)

    def test_csv_outputs_are_deterministic_utf8_sig_and_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            labels_a = folder / "labels-a.csv"
            inventory_a = folder / "inventory-a.csv"
            labels_b = folder / "labels-b.csv"
            inventory_b = folder / "inventory-b.csv"
            first = prep_dei_labels.prepare(WORKBOOK, labels_a, inventory_a)
            second = prep_dei_labels.prepare(WORKBOOK, labels_b, inventory_b)

            self.assertEqual(labels_a.read_bytes(), labels_b.read_bytes())
            self.assertEqual(inventory_a.read_bytes(), inventory_b.read_bytes())
            self.assertTrue(labels_a.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertTrue(inventory_a.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(first["labels_sha256"], second["labels_sha256"])
            self.assertEqual(first["inventory_sha256"], second["inventory_sha256"])

            with labels_a.open("r", encoding="utf-8-sig", newline="") as stream:
                labels = list(csv.DictReader(stream))
            with inventory_a.open("r", encoding="utf-8-sig", newline="") as stream:
                inventory = list(csv.DictReader(stream))
            self.assertEqual(len(labels), 1474)
            self.assertEqual(
                sum(int(row["ObservationCount"]) for row in inventory),
                len(labels),
            )
            self.assertEqual(
                list(labels[0]), ["Year", "City", "CityNormalized", "DEI"]
            )


if __name__ == "__main__":
    unittest.main()
