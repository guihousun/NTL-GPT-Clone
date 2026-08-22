# DEI model rebuild experiment

This directory contains two deliberately separate model assets:

1. `yearly_dei_models.json` is a **reconstructed-from-paper** record of the
   rounded 2017--2020 formulas printed by Chen et al. (2022). It is retained as
   historical evidence and is not used with LongNTL inputs.
2. `results/yearly_dei_models_longntl_candidate.json` is the frozen
   **newly retrained candidate** for 2017--2024. After explicit user approval,
   a deployed-status copy was installed as the local runtime default and is
   preserved at `results/yearly_dei_models_longntl_deployed.json`.

The two TNTL definitions and their coefficients are not interchangeable. The
LongNTL candidate does not use a monthly extraction path.

## Annual LongNTL experiment contract

- DEI labels: `base_data/dei_2017-2023.xlsx`, whose actual columns are treated
  exactly as model years 2017--2024 under the user's explicit instruction.
- NTL source: Earth Engine community asset
  `projects/sat-io/open-datasets/npp-viirs-ntl`, annual band `b1`; upstream is
  Harvard Dataverse `10.7910/DVN/YGIVCD`, Version 6.0 / Version 1, CC0 1.0.
- Feature: `TNTL`, the sum of positive annual `b1` native-grid pixels inside a
  matched city boundary. ANTL is never accepted.
- Grid: the source image's native EPSG:4326 nominal 500 m grid.
- Boundaries: `projects/empyrean-caster-430308-m2/assets/city`, 375 features.
  Its source, licence, reference year, and historical consistency remain
  unresolved, so the artifact remains a candidate.
- Upstream LongNTL sidecars establish a corrected yearly VIIRS median times a
  fixed 2013 mask for 2019--2024. The exact monthly inventory and correction
  implementation are not public; this experiment consumes the released annual
  images directly and does not recreate that upstream pipeline.
- City matching: deterministic exact/unique-prefix matching plus one explicit
  alias. The conflicting 2023 `毫州=47.4` row is quarantined; the separately
  listed `亳州=42.7` row is retained.
- Candidate forms: linear, logarithmic, exponential, and quadratic.
- Selection: minimum deterministic shuffled five-fold out-of-fold RMSE for
  each model year, seed `202208`.

Eligible sample counts are 40, 100, 113, 220, 242, 242, 256, and 260 for
2017--2024. The selected form is logarithmic in 2017 and quadratic in
2018--2024.

## Reproduce the annual pipeline

Use the repository's `NTL-GPT-Stable` environment. Earth Engine extraction
requires existing non-interactive credentials and an authorized quota
project; the script never starts OAuth.

```powershell
$py = 'C:\Users\27334\miniconda3\envs\NTL-GPT-Stable\python.exe'

& $py prep_dei_labels.py
& $py extract_city_tntl_longntl_gee.py --gee-project $env:GEE_DEFAULT_PROJECT_ID

# Expected to fail because one source row requires quarantine.
& $py match_dei_longntl.py

# Explicitly build the eligible subset while preserving the quarantine CSV.
& $py match_dei_longntl.py --allow-quarantine

& $py train_dei_models.py data/dei_longntl_matched_2017_2024.csv `
  --selection-rule cv_rmse `
  --output results/longntl_retraining_cv_rmse.json
& $py train_dei_models.py data/dei_longntl_matched_2017_2024.csv `
  --selection-rule paper_logarithmic `
  --output results/longntl_retraining_logarithmic.json
& $py build_retrained_artifact.py
& $py predict_jiangsu_2020.py
& $py -m unittest discover -s tests -v

# Run only after explicit deployment approval.
& $py deploy_longntl_candidate.py
& $py deploy_longntl_candidate.py --check
```

## Main outputs

- `data/city_tntl_longntl_2017_2024.csv` and its extraction manifest: 3000
  city-boundary-year rows.
- `data/dei_longntl_matched_2017_2024.csv`: 1473 eligible training rows.
- `data/dei_longntl_city_match.csv`: full row-level city match audit.
- `data/dei_longntl_quarantine.csv`: one unresolved 2023 source-label row.
- `results/longntl_retraining_cv_rmse.json`: all four fitted candidates and
  in-sample plus five-fold metrics.
- `results/longntl_retraining_logarithmic.json`: paper-form sensitivity report
  on the annual LongNTL inputs.
- `results/yearly_dei_models_longntl_candidate.json`: transparent mixed-form
  runtime-compatible candidate with training TNTL range gates.
- `results/longntl_model_metrics.csv`: compact 32-row candidate comparison.
- `results/jiangsu_2020_predictions_longntl.csv`: 13 fitted values. All 13
  cities occur in the 2020 training cohort, so this is not external validation.
- `results/yearly_dei_models_longntl_deployed.json`: byte-identical record of
  the local default deployed artifact.
- `results/yearly_dei_models_default_before_longntl_20260809.json`: recoverable
  backup of the previous paper-formula default.
- `results/longntl_deployment_manifest.json`: deployment approval, paths, and
  checksums.

## Deployment status

The annual v2 model is deployed at
`base_data/Model/yearly_dei_models.json` with status
`deployed-local-default`, following explicit user acceptance of the documented
minor limitations. The runtime supports 2017--2024 and still fails closed on
ANTL, an omitted/unsupported year, invalid TNTL, and extrapolation beyond each
year's observed TNTL range. The original paper-formula default remains
recoverable from the versioned backup in `results/`.
