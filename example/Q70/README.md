# Q70 frozen fixture: Chen et al. (2017) Shanghai urban centres

This fixture is a reproducible, local copy of the inputs used for the legacy
70-question case. It is kept separate from the active manuscript, benchmark
workbooks, Zotero storage, and runtime workspaces.

## Source chain

- Method: Chen et al. (2017), “A New Approach for Detecting Urban Centers and
  Their Spatial Structure With Nighttime Light Remote Sensing,” DOI
  [10.1109/TGRS.2017.2725917](https://doi.org/10.1109/TGRS.2017.2725917).
- NTL product: the public Earth Engine collection
  [`NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMCFG),
  band `avg_rad`, image date `2014-12-01` to `2015-01-01` (system index
  `20141201`). This is Version 1 monthly NPP-VIIRS radiance in
  nW·cm⁻²·sr⁻¹. The download script records the exact collection, image, and
  export parameters in `source_manifest.json`.
- AOI: the Shanghai level-1 administrative polygon selected from
  [GADM 4.1 China level-1 GeoJSON](https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_CHN_1.json),
  with the selected geometry frozen locally as
  `inputs/shanghai_boundary.geojson`.
- Export and preparation: the Earth Engine image is exported over the AOI
  plus a 12 km metric margin, which guarantees the required 10 km buffer after
  reprojection and 500 m pixel-grid rounding. It is then resampled
  deterministically to a 500 m local Albers Equal Area raster. The target
  raster stores the radiance unit tag and `-9999` nodata value. The target CRS
  and all hashes are recorded in `source_manifest.json` and `SHA256SUMS.txt`.

## Files

- `download_fixture.py`: authenticated Earth Engine export, boundary download,
  reprojection, validation, and input provenance generation.
- `generate_reference_output.py`: runs the checked-in deterministic core in a
  separate output directory and writes a reference vector, CSV, metadata, and
  hash manifest.
- `inputs/`: frozen boundary and NTL GeoTIFF.
- `reference_output/`: independently generated reference output for regression
  checking.
- `source_manifest.json`: source identifiers, export parameters, raster
  properties, and input SHA-256 values.
- `SHA256SUMS.txt`: SHA-256 values for the fixture files (excluding the
  manifest itself to avoid a self-reference).

The paper's reported 33 centres is a review target only. It is deliberately
not encoded as a parameter, fixture assertion, or algorithm branch. A count
difference must be investigated through product version, AOI, projection,
contour implementation, and tree rules.

## Regeneration

From `D:\NTL-GPT-main` with an authenticated Earth Engine Python session:

```powershell
python -X utf8 example/Q70/download_fixture.py
python -X utf8 example/Q70/generate_reference_output.py
```

The scripts are deterministic after the source services return the same
source bytes. The final frozen files, rather than a future live download, are
the regression-test inputs.
