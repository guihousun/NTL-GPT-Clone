# NTL-VLM Benchmark MVP

This package implements the executable pipeline for the 6-week `NTL-only` benchmark MVP:

- Scene manifest build (`scene_manifest.parquet`)
- Task generation for fixed `T1-T8`
- Quality gate checks (schema, leakage, duplicates, kappa-ready template)
- Submission evaluation (`overall`, `by_task`, `by_split`, `leaderboard`)
- NTL-GPT production job manifests for Data_Searcher and Code_Assistant

## Directory Contract

- `benchmarks/ntl_vlm_mvp/manifests/scene_manifest.parquet`
- `benchmarks/ntl_vlm_mvp/tasks/{task_id}.jsonl`
- `benchmarks/ntl_vlm_mvp/submissions/<track>/<model>/<task_id>.jsonl`
- `benchmarks/ntl_vlm_mvp/reports/{overall,by_task,by_split}.csv`
- `benchmarks/ntl_vlm_mvp/reports/leaderboard.csv`

## Core Schemas

- `SceneRecord`: `scene_id,event_id,hazard_type,aoi_wkt,pre_start,pre_end,post_start,post_end,quality_score,split,license_tag`
- `TaskSample`: `sample_id,scene_id,task_id,question,options,answer,source,confidence`
- `PredictionRecord`: `sample_id,prediction,model_id,track`

## Quick Start

From repo root:

```powershell
python -m benchmarks.ntl_vlm_mvp.run_mvp_pipeline --create-demo-submissions --evaluate
```

This will:

1. Build `scene_manifest.parquet` from `manifests/event_registry_template.csv`
2. Generate tasks `T1..T8`
3. Run QC and write `reports/qc_report.json`
4. Create demo submissions for `zero_shot` and `fine_tune`
5. Evaluate and write leaderboard/report CSVs

## Step-by-Step Commands

```powershell
# 0) Fetch real public event registry (natural + conflict)
python -m benchmarks.ntl_vlm_mvp.fetch_event_registry --root benchmarks/ntl_vlm_mvp

# 1) Build scene manifest
python -m benchmarks.ntl_vlm_mvp.build_dataset --root benchmarks/ntl_vlm_mvp --event-registry benchmarks/ntl_vlm_mvp/manifests/event_registry_clean.csv --no-dedup

# 2) Generate tasks
python -m benchmarks.ntl_vlm_mvp.generate_tasks --root benchmarks/ntl_vlm_mvp

# 3) Generate NTL-GPT job manifests
python -m benchmarks.ntl_vlm_mvp.generate_ntlgpt_jobs --root benchmarks/ntl_vlm_mvp --limit-scenes 200

# 4) Run quality gate
python -m benchmarks.ntl_vlm_mvp.qc --root benchmarks/ntl_vlm_mvp

# 5) Evaluate submissions
python -m benchmarks.ntl_vlm_mvp.evaluate_benchmark --root benchmarks/ntl_vlm_mvp
```

## Notes

- Default split is fixed to `2400/400/400/400`.
- Strict license filtering is enabled by default.
- Text tasks use BLEU-4, ROUGE-L, CIDEr-lite and cached LLM/heuristic score.
- If parquet engine is unavailable, CSV fallback is produced with a runtime warning.
- `build_dataset` and `run_mvp_pipeline` now auto-resolve event registry by priority:
  1) `manifests/event_registry_clean.csv`
  2) `manifests/event_registry_template.csv`
- `fetch_event_registry` currently uses:
  - GDACS RSS (`rss_7d`, `rss_24h`, `rss_fl_3m`, `rss_tc_3m`, `rss_eq_3m`)
  - UCDP GED API (`https://ucdpapi.pcr.uu.se/api/gedevents/25.1`)
