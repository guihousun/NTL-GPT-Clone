from __future__ import annotations

import unittest

import numpy as np

from experiments.official_daily_ntl_fastpath import gridded_pipeline


class TestGriddedPipelineQualityControl(unittest.TestCase):
    def test_require_qa_layers_rejects_missing_required_fields(self) -> None:
        with self.assertRaises(ValueError):
            gridded_pipeline.ensure_required_qa_layers_present(
                source="VJ146A1",
                qa_mode="balanced",
                qa_layers={"QF_Cloud_Mask": np.zeros((1, 1), dtype=np.uint16)},
                qa_variable_candidates={
                    "QF_Cloud_Mask": ("QF_Cloud_Mask",),
                    "QF_DNB": ("QF_DNB",),
                },
            )

    def test_require_qa_layers_allows_none_mode(self) -> None:
        gridded_pipeline.ensure_required_qa_layers_present(
            source="VJ146A1",
            qa_mode="none",
            qa_layers={},
            qa_variable_candidates={
                "QF_Cloud_Mask": ("QF_Cloud_Mask",),
                "QF_DNB": ("QF_DNB",),
            },
        )

    def test_balanced_vj146a1_masks_cloudy_and_bad_dnb_pixels(self) -> None:
        radiance = np.array(
            [
                [10.0, 20.0, 30.0],
                [40.0, 50.0, 60.0],
            ],
            dtype=np.float32,
        )
        qf_cloud_mask = np.array(
            [
                [0b00110000, 0b01010000, 0b10110000],
                [0b00000000, 0b11010000, 0b0011000000],
            ],
            dtype=np.uint16,
        )
        qf_dnb = np.array(
            [
                [0, 0, 0],
                [16, 512, 0],
            ],
            dtype=np.uint16,
        )

        masked, valid_mask, summary = gridded_pipeline.apply_quality_mask(
            source="VJ146A1",
            data=radiance,
            nodata=-9999.0,
            qa_mode="balanced",
            qa_layers={
                "QF_Cloud_Mask": qf_cloud_mask,
                "QF_DNB": qf_dnb,
            },
        )

        expected_mask = np.array(
            [
                [True, True, False],
                [False, False, False],
            ]
        )
        self.assertTrue(np.array_equal(valid_mask, expected_mask))
        self.assertEqual(masked[0, 0], 10.0)
        self.assertEqual(masked[0, 1], 20.0)
        self.assertEqual(masked[0, 2], -9999.0)
        self.assertEqual(masked[1, 0], -9999.0)
        self.assertEqual(masked[1, 1], -9999.0)
        self.assertEqual(masked[1, 2], -9999.0)
        self.assertEqual(summary["valid_pixel_count"], 2)
        self.assertEqual(summary["masked_pixel_count"], 4)

    def test_balanced_vj146a2_keeps_only_high_quality_main_retrievals(self) -> None:
        ntl = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        mandatory_quality_flag = np.array([[0, 1, 2, 255]], dtype=np.uint8)
        qf_cloud_mask = np.array([[0b00110000, 0b00110000, 0b00110000, 0b00110000]], dtype=np.uint16)

        masked, valid_mask, summary = gridded_pipeline.apply_quality_mask(
            source="VJ146A2",
            data=ntl,
            nodata=-9999.0,
            qa_mode="balanced",
            qa_layers={
                "Mandatory_Quality_Flag": mandatory_quality_flag,
                "QF_Cloud_Mask": qf_cloud_mask,
            },
        )

        expected_mask = np.array([[True, False, False, False]])
        self.assertTrue(np.array_equal(valid_mask, expected_mask))
        self.assertEqual(masked[0, 0], 1.0)
        self.assertEqual(masked[0, 1], -9999.0)
        self.assertEqual(masked[0, 2], -9999.0)
        self.assertEqual(masked[0, 3], -9999.0)
        self.assertEqual(summary["valid_pixel_count"], 1)
        self.assertEqual(summary["masked_pixel_count"], 3)

    def test_clear_only_vj146a1_requires_confident_clear_and_zero_dnb_flags(self) -> None:
        radiance = np.array([[10.0, 20.0, 30.0, 40.0]], dtype=np.float32)
        qf_cloud_mask = np.array(
            [[0b00110000, 0b00100000, 0b01110000, 0b11110000]],
            dtype=np.uint16,
        )
        qf_dnb = np.array([[0, 0, 0, 16]], dtype=np.uint16)

        masked, valid_mask, summary = gridded_pipeline.apply_quality_mask(
            source="VJ146A1",
            data=radiance,
            nodata=-9999.0,
            qa_mode="clear_only",
            qa_layers={
                "QF_Cloud_Mask": qf_cloud_mask,
                "QF_DNB": qf_dnb,
            },
        )

        expected_mask = np.array([[True, False, False, False]])
        self.assertTrue(np.array_equal(valid_mask, expected_mask))
        self.assertEqual(masked[0, 0], 10.0)
        self.assertEqual(masked[0, 1], -9999.0)
        self.assertEqual(masked[0, 2], -9999.0)
        self.assertEqual(masked[0, 3], -9999.0)
        self.assertEqual(summary["valid_pixel_count"], 1)

    def test_none_mode_preserves_input(self) -> None:
        data = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float32)
        masked, valid_mask, summary = gridded_pipeline.apply_quality_mask(
            source="VJ146A1",
            data=data,
            nodata=-9999.0,
            qa_mode="none",
            qa_layers={},
        )

        self.assertEqual(masked[0, 0], 1.0)
        self.assertEqual(masked[0, 1], -9999.0)
        self.assertTrue(np.array_equal(valid_mask, np.array([[True, False], [True, True]])))
        self.assertEqual(summary["valid_pixel_count"], 3)


if __name__ == "__main__":
    unittest.main()
