# 运行与验证日志

## 运行身份

- Execution type: Codex-subagent case-evidence simulation.
- Excluded evidence classes: deployed NTL-GPT runtime trace, Deep Agents trace,
  benchmark run, Full-vs-Single outcome, and benchmark resource accounting.
- All source case files were read only. No active manuscript, figure attachment,
  Zotero record, benchmark record, or runtime-repository file was changed.

## Q19 route

1. **Event Tracker** wrote a dated-source and exact-coordinate ADM2 ranking
   audit. It found a conditional first rank for City of Tehran, but an
   `indeterminate` complete overall rank because most retained records lack
   exact coordinates.
2. **Data Searcher** verified the existing daily VNP46A2 table/JSONL and AOI.
   It found a source cutoff of 2026-08-02 and 47/48 strict/permissive qualified
   days in the required complete UTC baseline.
3. The first **Analyst** attempt was interrupted before writing an artifact and
   is not treated as a completed role output.
4. An **Analyst recovery** ran only a local CSV aggregation and generated the
   eight window/QA results and future figure-input tables. A separate Analyst
   crosscheck independently reproduced all eight values.
5. **Engineer** ran `validate_q19_recompute.py`, which compared the original
   CSV, recovery summary, crosscheck summary, event-selection verdict and
   figure-input constraints. All 11 checks passed.

## Q17/Q18 review route

- Event Tracker review: event anchor/temporal boundary for Q18, conditional
  Event Tracker skip for Q17.
- Data Searcher review: Q17 image/index lineage and Q18 HDF/product/QA inputs.
- Analyst review: Q17 pixel statistics/agreement and Q18 table/JSON contrasts.

Each review role wrote only under its own `role-outputs/review-*` directory and
did not regenerate existing assets.

## Local validation commands

```text
python -m py_compile engineer/verify_q19_inputs.py
python -m py_compile engineer/build_q19_figure_inputs.py
python -m py_compile engineer/validate_q19_recompute.py
python -m py_compile engineer/build_package_manifest.py
python engineer/verify_q19_inputs.py ...
python engineer/build_q19_figure_inputs.py ...
python engineer/validate_q19_recompute.py ...
python engineer/build_package_manifest.py ...
```

The exact file identities and resulting checks are persisted in
`engineer/q19-input-verification.json`, `validation/engineer-q19-validation.json`,
the role manifests, and the top-level `artifact-manifest.json`.
