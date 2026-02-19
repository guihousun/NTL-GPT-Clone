Plan and actions — computing per-district maximum NTL (NPP‑VIIRS‑Like, 2020) for Shanghai

Summary of steps I followed
- Queried NTL knowledge base for best-practice preprocessing and zonal-statistics workflow.
- Checked temporal availability: annual NPP‑VIIRS‑Like supports 2000–2024 — 2020 is supported.
- Located/ downloaded required data and administrative boundaries to workspace inputs/:
  - inputs/NTL_Shanghai_NPP-VIIRS-Like_2020.tif (annual NPP‑VIIRS‑Like, 2020)
  - inputs/shanghai_districts.shp (district boundaries, EPSG:4326)
- Executed zonal statistics (MaxNTL per district) using the NTL_raster_statistics tool.
- Result CSV saved to outputs/.

Findings / Results
- Per-district maximum NTL (MaxNTL) values for Shanghai (NPP‑VIIRS‑Like, 2020) were computed and saved.
- Global (whole-Shanghai) MaxNTL: 391.8100 (units: radiance, see notes below — typical units are nW/cm²/sr).
- Detailed per-district values: see generated CSV.

Generated files (workspace)
- outputs/shanghai_districts_maxNTL_2020.csv

Methodology (concise)
- Data: annual NPP‑VIIRS‑Like 2020 composite (supported 2000–2024).
- Metric: MaxNTL = pixel-wise maximum radiance within each district polygon.
- Preprocessing steps applied/checked:
  - CRS harmonization (vector reprojected to raster CRS if needed).
  - NoData handling (nodata used from raster metadata).
  - No resampling required since district polygons overlay directly on raster grid.
- Tools: raster zonal statistics (server-side tool invoked in workspace).

Quality notes and caveats
- Units/scale: NPP‑VIIRS‑Like annual composites are radiance-like values commonly reported in nW/cm²/sr. Typical maximums vary by city — our global max = 391.81 (unusually high; see caveat).
- Caveat: The reported global MaxNTL (391.81) is unexpectedly large for standard VIIRS radiance (normally <100). Possible causes:
  - The NPP‑VIIRS‑Like product here may be scaled (e.g., multiplied, different units), or include outliers/artefacts. Recommend inspecting raster metadata and histogram.
  - Saturation, stray light, or data processing differences in "Like" products can create high values.
- Recommended QA:
  - Open the raster in a GIS and inspect the bright pixels (locations) against known urban cores.
  - Check raster metadata (scale, units, valid range) in inputs/NTL_Shanghai_NPP-VIIRS-Like_2020.tif.
  - Visualize a map of MaxNTL or the input raster and compare with known landmarks.
  - If values look implausible, consider thresholding extreme values or using an alternative VIIRS annual product (native NPP‑VIIRS 2012–2023) or the monthly/daily composites for cross-checking.

If you want (next steps — choose one)
1) I can open and show the top 5 districts by MaxNTL (name + value) now.
2) I can produce a map (PNG) of MaxNTL across districts and save to outputs/ (e.g., outputs/shanghai_MaxNTL_map_2020.png).
3) I can run a quick metadata and histogram report on the input raster to confirm units/scale and identify outliers.
4) I can re-run using a masked approach (exclude water and very small islands) if you want tighter urban-only metrics.

Which of these would you like me to do?