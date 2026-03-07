from __future__ import annotations

import unittest

from tools.official_vj_dnb_map_renderer import PALETTES


class TestOfficialVJDNBPalettePresets(unittest.TestCase):
    def test_white_viridis_palette_is_registered(self) -> None:
        self.assertIn("white_viridis", PALETTES)
        palette = PALETTES["white_viridis"]
        self.assertEqual(palette["cmap"], "viridis")
        self.assertEqual(palette["boundary_edge_color"], "#4b5563")


if __name__ == "__main__":
    unittest.main()
