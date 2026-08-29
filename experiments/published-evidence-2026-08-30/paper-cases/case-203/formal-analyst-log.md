# Q17 formal NTL Analyst log

## Blind analysis phase

- Status: completed and locked before reference comparison.
- Formal inputs: accepted RRLI/RBLI rasters and frozen Jia et al. (2024) method contract.
- Ordered classification: RRLI > 9 → RLED; otherwise RBLI > 0.57 → WLED; otherwise Other.
- NoData: 255; invalid index pixels were not relabelled as Other.
- Threshold tuning: none.
- Full raster reopened: yes.
- Independent threshold sample: 4,964 pixels; mismatches: 0.
- New-result SHA-256: `2a086016653569b5f6c73a40f2f9a6b64a0cc0f6568bce230383f9d49c327e7d`.
- Reference files opened in this phase: no.

The result decisions above are locked. The comparison phase may quantify agreement or difference but may not modify thresholds, masking, class order, or the new result.


## Post-lock blind reference comparison

- Lock verified before opening references: yes.
- New-result hash remained `2a086016653569b5f6c73a40f2f9a6b64a0cc0f6568bce230383f9d49c327e7d`.
- Existing RBLI SHA-256: `ee939cb4fb2cbbde1936065da66b56f9e1d290de8bfddf9ce45458848bc7bb62`.
- Existing classification SHA-256: `2eb124b7488a8356203ab224e8ac0b5fb424a54b6b60bab99b7ac190fd0fec19`.
- Existing RBLI has only 2,200,100 common-valid pixels; its valid mask is narrower than the new result.
- RBLI MAE: 0.0.
- RBLI RMSE: 0.0.
- RBLI values in the common-valid region are exactly identical: 1.0.
- Classification common semantic pixels: 9,782,275.
- Classification overall agreement: 0.8878253780434511.
- Post-comparison threshold, mask, class-order, or raster modification: none.

The 88.78% classification agreement describes consistency with an earlier implementation. It is not ground-truth accuracy. No Gold output was opened at any stage.

## Analytical limitations

- Large ratios can occur where the green denominator is small.
- Fixed thresholds cannot fully resolve mixed light sources or spectral mixtures.
- The preceding preprocessing chain was accepted from the user and not rerun in this case.
- No field-validated labels were available.
