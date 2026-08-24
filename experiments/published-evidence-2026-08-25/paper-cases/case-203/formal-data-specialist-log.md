# Q17 NTL Data Specialist process log

## Handoff received

The NTL Engineer delegated real-scene source verification, fixed-formula RRLI/RBLI generation, and an analysis-ready observation package. Classification belongs to the NTL Analyst. The Engineer explicitly prohibited reading the user's existing `SDGSAT1_GLI_shanghai_RBLI.tif` and `SDGSAT1_GLI_shanghai_light_class1.tif` until the new result is complete and separately reviewed. Those files were not opened, hashed, listed for metadata, sampled, or visualized.

## Actual tools and evidence

- `rasterio` inspected only the user-provided original RGB and preprocessed radiance RGB.
- The active runtime files `tools/NTL_preprocess.py` and `tools/SDGSAT1_INDEX.py` were inspected to verify the R/G/B band order, calibration metadata, formulas, NoData propagation, and zero-denominator behavior.
- The source-linked Jia et al. (2024) contract at `data/benchmark-v1/fixtures/verified-reference/BV1-069/inputs/jia_2024_classification_contract.json` supplied only the formula and downstream threshold contract; no reference output or Gold answer was read.
- `compute_formal_indices.py` used block-window processing to calculate RRLI = R/G and RBLI = B/G as float32. It did not resample, reproject, classify, or inspect reference results.
- PowerShell `Get-FileHash` and the script's streaming SHA-256 checks recorded input, script, runtime-source, statistics, and output identities.

## Source and grid checks

- Original scene: 3-band uint16, NoData 0, EPSG:32651, 5674 × 9250, 40 m.
- Analysis input: 3-band float32, declared NoData -9999, same CRS, transform, extent, shape, and 40 m grid.
- Runtime band contract: band 1 = R, band 2 = G, band 3 = B.
- The calibrated raster contains finite zero-background values; division is valid only where G is nonzero. This yields 9,784,136 valid index pixels out of 52,484,500 (18.641953%).
- Both output rasters are single-band float32, NoData -9999, EPSG:32651, and exactly preserve the analysis-input grid.

## Validation result

Success for Data Specialist scope. Independently generated RRLI/RBLI GeoTIFFs and detailed statistics are ready for Analyst classification. The very high upper tails are mathematically attributable to small positive green denominators and are retained rather than silently clipped; the paper's ordered classification rules determine the downstream classes.

## Handoff

Downstream role: NTL Analyst.

- Typed package: `formal-observation-package.json`
- Reproduction script: `compute_formal_indices.py`
- RRLI: `formal-SDGSAT1-shanghai-RRLI.tif`
- RBLI: `formal-SDGSAT1-shanghai-RBLI.tif`
- Statistics: `formal-index-statistics.json`

The Analyst must perform the Jia et al. (2024) ordered threshold classification and its validation. It must not treat the Data Specialist's index statistics as a classification result.
