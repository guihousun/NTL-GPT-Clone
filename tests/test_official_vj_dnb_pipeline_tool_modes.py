from __future__ import annotations

import unittest

from tools import official_vj_dnb_pipeline_tool as mod


class TestOfficialVJDNBPipelineToolModes(unittest.TestCase):
    def test_resolve_source_mode_for_swath_sources(self) -> None:
        mode, sources = mod._resolve_pipeline_mode("VJ102DNB,VJ103DNB")
        self.assertEqual(mode, "swath_precise")
        self.assertEqual(sources, ["VJ102DNB", "VJ103DNB"])

    def test_resolve_source_mode_for_gridded_sources(self) -> None:
        mode, sources = mod._resolve_pipeline_mode("VJ146A1")
        self.assertEqual(mode, "gridded_tile_clip")
        self.assertEqual(sources, ["VJ146A1"])

    def test_resolve_source_mode_rejects_mixed_sources(self) -> None:
        with self.assertRaises(ValueError):
            mod._resolve_pipeline_mode("VJ102DNB,VJ146A1")


if __name__ == "__main__":
    unittest.main()
