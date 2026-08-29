# Q17 Evidence Report — SDGSAT-1 Light-Type Classification

## Decision

**Status: success.** The formal Engineer → Data Specialist → Engineer →
Analyst → Engineer chain processed the user-provided full-size SDGSAT-1 scene,
generated independent RRLI/RBLI rasters and a fixed-threshold light-type map,
then performed a post-lock blind implementation comparison.

## Route and evidence

- Data Specialist verified the real 5674×9250, 40 m, EPSG:32651 input grid and
  generated RRLI=`R/G` and RBLI=`B/G` without reading the existing RBLI or class
  files.
- Engineer reopened both index GeoTIFFs, verified their hashes/grid/NoData, and
  independently spot-checked index formula values.
- Analyst applied the fixed ordered rules: `RRLI>9 → RLED`; otherwise
  `RBLI>0.57 → WLED`; otherwise `Other`; invalid indices remained NoData=255.
- The classification was locked by SHA-256 before the existing files were
  opened. The later comparison did not change thresholds, masks, order, or the
  result hash.

## Result

Of 9,784,136 valid index pixels, 4,211,496 (43.04%) were WLED, 244,523
(2.50%) RLED, and 5,328,117 (54.46%) Other. An independent 5,000-position
Engineer check found zero classification mismatches among 965 valid samples.

The earlier RBLI had a narrower valid mask. On 2,200,100 commonly valid pixels,
new and earlier RBLI values were exactly equal (MAE/RMSE/max absolute
difference all 0). Classification agreement over 9,782,275 common semantic
pixels was 88.78%; IoU was 0.896 for WLED, 0.204 for RLED, and 0.853 for Other.
This is implementation consistency, not ground-truth accuracy.

## Supported claim

The architecture executed a real, full-resolution procedural workflow in
which data verification and deterministic feature construction were separated
from scientific classification and validation, with a blind post-result check.

## Main limitations

The user-approved preprocessed RGB was accepted rather than recreating the
destriping/calibration chain; small green denominators create large ratios;
fixed thresholds cannot resolve every mixed-light spectrum; no field labels
were available.

