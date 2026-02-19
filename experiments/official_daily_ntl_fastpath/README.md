# Official Daily NTL Fastpath (Independent Experiment)

This workspace is isolated from the main project chain.

## 1) Fast availability and clipping workflow

Run with NRT-first source profile (default):

```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/run_fast_daily_ntl.py \
  --study-area "上海市" \
  --workspace experiments/official_daily_ntl_fastpath/workspace_validation/shanghai_nrt_priority
```

Key outputs:

- `outputs/availability_report.json`
- `outputs/availability_report.csv`
- `outputs/<SOURCE>/<DATE>/*_clipped.tif` (when download and clipping succeed)

## 2) Live web monitor (availability + global render)

Start local monitor service:

```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/monitor_server.py \
  --host 127.0.0.1 \
  --port 8765
```

Open in browser:

- `http://127.0.0.1:8765`

Features:

- `/api/latest`: latest available date per source (global / bbox).
- `/api/latest`: also returns GEE baseline latest date (`NASA/VIIRS/002/VNP46A2`) for the same bbox.
- Auto-refresh table for NRT-priority sources.
- Global render using NASA GIBS VIIRS DayNightBand layers.

## 3) Token

Set `EARTHDATA_TOKEN` in `.env` or environment before running download/clipping.
Without a valid token, metadata querying still works but downloads can fail.

## 4) Download daily NTL from GEE (GeoTIFF)

```bash
conda run --no-capture-output -n NTL-GPT python experiments/official_daily_ntl_fastpath/download_gee_daily_ntl.py \
  --study-area "上海市" \
  --date 2026-02-10 \
  --dataset NASA/VIIRS/002/VNP46A2 \
  --workspace experiments/official_daily_ntl_fastpath/workspace_gee_download
```

Outputs:
- `outputs/gee_daily/<dataset>/<date>/*.tif`
- `outputs/gee_daily/<dataset>/<date>/download_meta.json`
