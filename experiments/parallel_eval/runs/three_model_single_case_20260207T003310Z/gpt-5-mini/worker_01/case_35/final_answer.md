Result Summary:
- Task: Compute maximum NTL intensity per district in Shanghai for year 2020 using the NPP‑VIIRS‑Like annual product.
- Knowledge grounding: I consulted the NTL knowledge base for best-practices (product choice, preprocessing and zonal-statistics method).
- Temporal audit: The NPP‑VIIRS‑Like annual product covers 2000–2024, so 2020 is supported.
- Data used (already placed in workspace):
  - inputs/NTL_Shanghai_NPP-VIIRS-Like_2020.tif (annual NPP‑VIIRS‑Like for Shanghai, 2020)
  - inputs/shanghai_districts.shp (Shanghai district boundaries and associated shapefile files)
- Method & processing summary (CoT / steps performed)
  1. Verified product/time-range compatibility (annual NPP‑VIIRS‑Like, 2000–2024).
  2. Chose Scenario A (single annual composite → direct download / local raster zonal routine).
  3. Ensured inputs exist in inputs/ and have matching CRS (WGS84/EPSG:4326 for the provided shapefile).
  4. Ran the zonal-statistics routine (NTL_raster_statistics) to compute MaxNTL per district using the annual GeoTIFF:
     - Masked invalid/zero radiance pixels,
     - Computed per-polygon maximum (zonal max),
     - Saved per-district results to CSV.
- Key numeric finding (global summary from the run):
  - Global (entire Shanghai) MaxNTL = 391.8100 (radiance units consistent with VIIRS DNB ~ nW·cm⁻²·sr⁻¹)
- Per-district results:
  - Detailed per-district maximum values were written to the CSV below (16 districts processed).

Generated Files:
- outputs/ntl_max_per_district_2020.csv

Notes, caveats and recommendations:
- Units: VIIRS DNB radiance is typically reported in nW·cm⁻²·sr⁻¹; the NPP‑VIIRS‑Like product preserves radiance-like units. Use caution when comparing to other products.
- Saturation / ceilings: Very bright urban cores can saturate or be subject to non-linearities — max can underestimate true peak brightness in some pixels.
- Small polygons: Districts with very small area (few pixels) can produce unstable max values; consider a minimum-pixel threshold or smoothing if you need robust comparisons.
- Inter-product calibration: The “NPP‑VIIRS‑Like” product is a smoothed/gap-filled variant—good for annual statistics, but there are calibration differences versus raw official NPP‑VIIRS products. Avoid mixing products without cross-calibration.
- Preprocessing: The product already minimizes moonlight/cloud artifacts. We masked zero/no-data values during the zonal max calculation.
- If you need per-district maps (GeoTIFF or PNG), ranked lists, or visual summaries, I can:
  - (A) Preview the first/last rows or top-5 districts by MaxNTL from the CSV, or
  - (B) Produce a choropleth map (PNG) showing MaxNTL across districts, or
  - (C) Provide the Python snippet used to compute zonal max locally (rasterio + geopandas), or
  - (D) Re-run with alternative indices (e.g., mean, TNTL, ANTL).

Would you like me to:
- display the CSV contents (top 10 rows),
- generate a choropleth PNG of MaxNTL by district, or
- export the results as a shapefile with the MaxNTL attribute added?

If you want the CSV preview, I will load outputs/ntl_max_per_district_2020.csv and show the per-district maxima.