# Q17 Data Review — SDGSAT-1 light classification

## Review identity and verdict

- **Execution context:** **Codex-subagent simulation**, NTL Data Searcher review role. This is an independent read-only audit of an existing case package; it is not a deployed NTL-GPT/Deep Agents run and is not part of the 200-task benchmark.
- **Case:** `Q17-sdgsat-light-classification`.
- **Verdict:** `partial / analysis-ready inputs verified`. The declared source and derived RRLI/RBLI rasters are readable, hash-consistent, and grid-consistent. The supplied preprocessed/calibrated RGB is accepted as the analysis input; the preceding destriping/calibration chain was **not** rerun or independently reconstructed in this review.
- **Mutation boundary:** no source raster, index raster, classification raster, package, manifest, manuscript, figure, Zotero item, benchmark asset, or runtime file was modified.

## Evidence reopened

The formal package and source manifest were parsed:

- `experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/formal-observation-package.json` — SHA-256 `ae36cc77d17dcb99900596c1ebd54dc10cb8685388bb8b949b39b3e5c51def09`; the full file was parsed.
- `experiments/paper-case-multiagent-2026-08-13/Q17-sdgsat-light-classification/artifact-manifest.json` — SHA-256 `9415ff94da5fc5a767f15e7893dcbff52c4b8cdf10ea18c2b39f063b9c4aee26`; the artifact list was parsed.
- `compute_formal_indices.py` — SHA-256 `6c824bd4321d3e3fe5b39111c7d9c9c847d1de3686767e5a58f106e8e65d338`; the source path, validity mask, ratio formulas, output profile and non-classification tags were read at lines 18–27, 94–156.

The package's exact source hashes were recomputed. Both declared source files and both formal index outputs reopened successfully with `rasterio`.

## Input lineage, grid and band/NoData checks

| Asset | Reopened metadata | Hash result |
|---|---|---|
| Original RGB: `user-provided-local-data/SGDSAT-1/KX10_GIU_20220304_E121.82_N31.56_202200100146_L4A_A_RGB.tif` | 3 bands; `uint16`; NoData `0`; EPSG:32651; 5674 × 9250; 40 × 40 m; transform and bounds match the analysis raster | SHA-256 `8b78a2bc10b6d836ffa49e0595b07ed6f79b36f66e764b47caccd28cfea98ec0` — **matches package** |
| Analysis RGB: `user-provided-local-data/NTL-GPT/SDGSAT_1/SDGSAT1_GLI_shanghai_radiance_rgb.tif` | 3 bands; `float32`; NoData `-9999`; EPSG:32651; 5674 × 9250; 40 × 40 m; bounds `[194936.5543, 3299270.7544, 421896.5543, 3669270.7544]` | SHA-256 `a69a3a4f778031e6adf12aef83e4429cd9a44c04b68f7442ab9f50f8e9b7ef9f` — **matches package** |
| Formal RRLI: `formal-SDGSAT1-shanghai-RRLI.tif` | 1 band; `float32`; NoData `-9999`; same EPSG:32651, 40 m transform, shape and bounds; band description `RRLI (Red / Green)` | SHA-256 `dccd7c22988cb0d0b71debe952a06f3c466cf8446aa9662b34966c0a302d4423` — **matches package** |
| Formal RBLI: `formal-SDGSAT1-shanghai-RBLI.tif` | 1 band; `float32`; NoData `-9999`; same EPSG:32651, 40 m transform, shape and bounds; band description `RBLI (Blue / Green)` | SHA-256 `50fb93f7bedd9fc1ff74722a852354f28618790f1092f47a0ed8c4bc8f2080b1` — **matches package** |

The source RGB files have no embedded band descriptions. The package resolves band order as band 1 = R, band 2 = G, band 3 = B from the active runtime contract; this is a provenance dependency, not an independently embedded TIFF label. The formal outputs retain the same spatial grid and are tiled DEFLATE GeoTIFFs.

## RRLI/RBLI provenance and spot check

`compute_formal_indices.py` reads only the declared analysis RGB (`SOURCE`, lines 18–20), checks a three-band float32 input (lines 94–99), uses the shared finite/non-NoData mask and `G != 0` (lines 133–154), then writes:

- `RRLI = R / G` (`Band1 / Band2`);
- `RBLI = B / G` (`Band3 / Band2`);
- output NoData `-9999` when the shared source mask is invalid, non-finite, or the green denominator is zero.

The output tags explicitly state `role="analysis-ready index; no classification applied"` (lines 118–130). Four valid pixel positions were sampled after reopening the source and outputs. At `(row, col) = (540,1080), (540,1100), (540,1120), (560,1280)` (zero-based), output-vs-direct-division absolute errors were at float32 round-off scale: maximum RRLI error `2.1e-7`, maximum RBLI error `8.3e-9`. Zero-background positions returned output NoData, consistent with the zero-denominator rule.

These checks verify the existing index artifacts' source and formula contract; they do not rerun the full index computation or inspect the user's pre-existing RBLI/classification files.

## What can be written from this audit

The following input/method statements are supported with qualification:

1. The case used the user-supplied, preprocessed/calibrated SDGSAT-1 RGB raster as its analysis input; its declared hash, grid and metadata are reproducible from the package.
2. Formal RRLI and RBLI are derived from that raster as `R/G` and `B/G`, with shared validity masking and NoData propagation; the existing outputs are readable and hash-consistent.
3. The derived index rasters preserve the source CRS, extent, 40 m grid and array dimensions, and are analysis-ready inputs for a downstream classification step.

## What cannot be written from this audit

Do **not** state that this round completed, reran, or independently validated the full SDGSAT-1 preprocessing chain (destriping, radiometric calibration, or normalization). The package explicitly says the calibrated raster was supplied by the user and that the preceding chain was not recreated. Do not infer physical calibration correctness from the matching file hash alone. Also do not turn these input checks into ground-truth classification accuracy, deployment/runtime performance, or benchmark evidence; those are outside this Data Searcher review.
