from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from experiments.official_daily_ntl_fastpath import download_official_ntl_by_bbox as mod


class TestDownloadOfficialNTLByBboxQAMode(unittest.TestCase):
    def test_download_clipped_for_source_passes_explicit_qa_mode(self) -> None:
        with (
            mock.patch.object(mod, "get_source_spec") as mock_spec,
            mock.patch.object(mod, "search_granules", return_value=["g1"]),
            mock.patch.object(mod, "group_granules_by_day", return_value={"2026-03-05": ["g1"]}),
            mock.patch.object(mod, "_build_roi_gdf_from_bbox", return_value="roi"),
            mock.patch.object(mod, "process_gridded_day") as mock_process,
        ):
            mock_spec.return_value = mock.Mock(
                processing_mode="gridded_tile_clip",
                short_name="VJ146A1",
                night_only=False,
                variable_candidates=("x",),
                qa_variable_candidates={"QF_Cloud_Mask": ("a",), "QF_DNB": ("b",)},
                default_qa_mode="balanced",
            )
            mock_process.return_value = {"status": "ok", "output_path": str(Path("out") / "a.tif")}

            row = mod._download_clipped_for_source(
                source="VJ146A1",
                start_date="2026-03-05",
                end_date="2026-03-05",
                bbox=(44.03, 25.08, 63.33, 39.77),
                workspace=Path("workspace"),
                token="token",
                qa_mode="strict",
            )

        self.assertEqual(row["status"], "ok")
        self.assertEqual(mock_process.call_args.kwargs["qa_mode"], "strict")


if __name__ == "__main__":
    unittest.main()
