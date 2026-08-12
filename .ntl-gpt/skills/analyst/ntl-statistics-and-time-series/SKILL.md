---
name: ntl-analyst-statistics-and-time-series
description: Execute task-specific nighttime-light statistics, time-series, trend, anomaly, and comparison workflows on accepted observations.
---

# NTL Statistics and Time Series

- Consume either accepted ObservationPackage artifacts with explicit product, units, dates, QA, grid, and valid-pixel semantics, or checksum-bound staged inputs explicitly authorized by an accepted TaskPlan with `observation_required=false`. Never reinterpret a staged fixture as a live observation.
- Define the assigned statistic, temporal aggregation, baseline, comparison, missing-data rule, and uncertainty before execution.
- Check sample support, NoData, edge effects, numerical range, and sensitivity to low baselines.
- Save machine-readable tables and plots with parameters and checksums.
- Report association and observation; do not infer causal mechanisms from radiance alone.
