from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from shutil import which

if __package__ in (None, ""):
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments.official_daily_ntl_fastpath.boundary_resolver import resolve_boundary
from experiments.official_daily_ntl_fastpath.gee_baseline import DEFAULT_GEE_DAILY_DATASET, DEFAULT_GEE_PROJECT


GEE_DATASET_PRESETS: dict[str, dict[str, str]] = {
    "daily": {
        "NASA/VIIRS/002/VNP46A2": "Gap_Filled_DNB_BRDF_Corrected_NTL",
        "NOAA/VIIRS/001/VNP46A1": "DNB_At_Sensor_Radiance_500m",
    },
    "monthly": {
        "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": "avg_rad",
    },
    "annual": {
        "NOAA/VIIRS/DNB/ANNUAL_V22": "average",
        "NOAA/VIIRS/DNB/ANNUAL_V21": "average",
        "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS": "avg_vis",
        "projects/sat-io/open-datasets/npp-viirs-ntl": "b1",
    },
}

DEFAULT_GEE_DATASET_BY_TEMPORAL = {
    "daily": DEFAULT_GEE_DAILY_DATASET,
    "monthly": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
    "annual": "NOAA/VIIRS/DNB/ANNUAL_V22",
}

DATASET_MIN_DATE: dict[str, str] = {
    "NASA/VIIRS/002/VNP46A2": "2014-01-01",
    "NOAA/VIIRS/001/VNP46A1": "2014-01-01",
    "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG": "2014-01-01",
}

ANNUAL_YEAR_RANGES: dict[str, tuple[int, int | None]] = {
    "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS": (1992, 2013),
    "NOAA/VIIRS/DNB/ANNUAL_V21": (2012, None),
    "NOAA/VIIRS/DNB/ANNUAL_V22": (2012, None),
    "projects/sat-io/open-datasets/npp-viirs-ntl": (2000, 2024),
}


def infer_temporal_resolution(dataset_id: str) -> str:
    for temporal, mapping in GEE_DATASET_PRESETS.items():
        if dataset_id in mapping:
            return temporal
    raise ValueError(f"Unsupported GEE dataset for temporal inference: {dataset_id}")


def periods_from_date_range(
    *,
    temporal_resolution: str,
    start_date: str,
    end_date: str,
) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("end_date must be >= start_date")

    temporal = temporal_resolution.strip().lower()
    if temporal == "daily":
        from datetime import timedelta

        periods: list[str] = []
        cur = start
        while cur <= end:
            periods.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return periods

    if temporal == "monthly":
        periods = []
        y, m = start.year, start.month
        while (y < end.year) or (y == end.year and m <= end.month):
            periods.append(f"{y:04d}-{m:02d}")
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
        return periods

    if temporal == "annual":
        return [str(y) for y in range(start.year, end.year + 1)]

    raise ValueError("temporal_resolution must be daily/monthly/annual")


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")
    vals = [float(p) for p in parts]
    minx, miny, maxx, maxy = vals
    if maxx < minx or maxy < miny:
        raise ValueError("bbox max must be >= min")
    return float(minx), float(miny), float(maxx), float(maxy)


def resolve_band(dataset_id: str, band: str | None) -> str:
    if band and band.strip():
        return band.strip()
    for _temporal, mapping in GEE_DATASET_PRESETS.items():
        if dataset_id in mapping:
            return mapping[dataset_id]
    raise ValueError(f"band is required for dataset: {dataset_id}")


def parse_period(temporal_resolution: str, period: str) -> tuple[str, str, str]:
    temporal = (temporal_resolution or "").strip().lower()
    token = (period or "").strip()

    if temporal == "daily":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
            raise ValueError("daily period must be YYYY-MM-DD")
        day = datetime.strptime(token, "%Y-%m-%d").date()
        end = day.replace(day=day.day)
        from datetime import timedelta

        return token, (day + timedelta(days=1)).strftime("%Y-%m-%d"), token

    if temporal == "monthly":
        if not re.fullmatch(r"\d{4}-\d{2}", token):
            raise ValueError("monthly period must be YYYY-MM")
        year, month = map(int, token.split("-"))
        if month < 1 or month > 12:
            raise ValueError("month must be 01-12")
        start = datetime(year, month, 1).date()
        if month == 12:
            end = datetime(year + 1, 1, 1).date()
        else:
            end = datetime(year, month + 1, 1).date()
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), token

    if temporal == "annual":
        if not re.fullmatch(r"\d{4}", token):
            raise ValueError("annual period must be YYYY")
        year = int(token)
        start = datetime(year, 1, 1).date()
        end = datetime(year + 1, 1, 1).date()
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), token

    raise ValueError("temporal_resolution must be daily/monthly/annual")


def validate_dataset_period(
    *,
    dataset_id: str,
    temporal_resolution: str,
    start_date: str,
    period_label: str,
) -> None:
    temporal = temporal_resolution.strip().lower()

    min_start = DATASET_MIN_DATE.get(dataset_id)
    if min_start:
        if datetime.strptime(start_date, "%Y-%m-%d").date() < datetime.strptime(min_start, "%Y-%m-%d").date():
            raise ValueError(
                f"{dataset_id} is available from {min_start} for {temporal} requests."
            )

    if temporal == "annual":
        year_range = ANNUAL_YEAR_RANGES.get(dataset_id)
        if year_range:
            year = int(period_label)
            min_year, max_year = year_range
            if year < min_year:
                raise ValueError(f"{dataset_id} annual year must be >= {min_year}.")
            if max_year is not None and year > max_year:
                raise ValueError(f"{dataset_id} annual year must be <= {max_year}.")

    today = datetime.now(UTC).date()
    if temporal == "daily":
        if datetime.strptime(period_label, "%Y-%m-%d").date() > today:
            raise ValueError("daily period cannot be in the future.")
    elif temporal == "monthly":
        y, m = map(int, period_label.split("-"))
        p_start = date(y, m, 1)
        if p_start > date(today.year, today.month, 1):
            raise ValueError("monthly period cannot be in the future.")
    elif temporal == "annual":
        year = int(period_label)
        if year > today.year:
            raise ValueError("annual period cannot be in the future.")


def _bool_flag(raw: str | None) -> bool | None:
    if raw is None:
        return None
    v = raw.strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    raise ValueError("--is-in-china must be true/false")


def _curl_download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    curl_bin = which("curl.exe") or which("curl")
    if not curl_bin:
        raise RuntimeError("curl executable is required but not found in PATH.")
    cmd = [curl_bin, "--silent", "--show-error", "--location", "--fail", url, "--output", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl failed: {proc.returncode}")
    if not out_path.exists() or out_path.stat().st_size <= 0:
        raise RuntimeError("Downloaded file is missing or empty.")


def _maybe_unpack_tif(path: Path) -> Path:
    if path.suffix.lower() != ".zip":
        return path
    with zipfile.ZipFile(path, "r") as zf:
        tif_names = [n for n in zf.namelist() if n.lower().endswith(".tif") or n.lower().endswith(".tiff")]
        if not tif_names:
            raise RuntimeError("zip downloaded from GEE has no tif file.")
        name = tif_names[0]
        out_path = path.with_suffix(".tif")
        with zf.open(name) as src, out_path.open("wb") as dst:
            dst.write(src.read())
    return out_path


def _serialize_region_for_download(geom: object) -> str:
    try:
        return str(geom.toGeoJSONString())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        info = geom.getInfo()  # type: ignore[attr-defined]
        return json.dumps(info, ensure_ascii=False)


def download_gee_ntl(
    *,
    bbox: tuple[float, float, float, float],
    dataset: str,
    temporal_resolution: str,
    period: str,
    workspace: Path,
    gee_project: str = DEFAULT_GEE_PROJECT,
    band: str | None = None,
    scale: int = 500,
    output_name: str | None = None,
    region_name: str = "bbox",
) -> dict[str, str | int]:
    temporal = (temporal_resolution or "daily").strip().lower()
    dataset_id = (dataset or DEFAULT_GEE_DATASET_BY_TEMPORAL[temporal]).strip()
    band_name = resolve_band(dataset_id, band)

    start_date, end_date_exclusive, period_label = parse_period(temporal, period)
    validate_dataset_period(
        dataset_id=dataset_id,
        temporal_resolution=temporal,
        start_date=start_date,
        period_label=period_label,
    )

    import ee

    try:
        ee.Initialize(project=gee_project)
    except Exception:
        ee.Initialize()

    minx, miny, maxx, maxy = bbox
    geom = ee.Geometry.Rectangle([minx, miny, maxx, maxy], proj="EPSG:4326", geodesic=False)

    collection = ee.ImageCollection(dataset_id).filterDate(start_date, end_date_exclusive).filterBounds(geom)
    image_count = int(collection.size().getInfo())
    if image_count <= 0:
        raise RuntimeError(
            f"No image in {dataset_id} for period {period_label} ({start_date} to {end_date_exclusive})."
        )

    if temporal == "daily":
        image = ee.Image(collection.sort("system:time_start").first()).select(band_name)
    else:
        image = collection.select(band_name).mean()
    image = image.clip(geom)

    download_url = image.getDownloadURL(
        {
            "name": f"gee_ntl_{period_label.replace('-', '')}",
            "region": _serialize_region_for_download(geom),
            "scale": int(scale),
            "crs": "EPSG:4326",
            "format": "GEO_TIFF",
            "filePerBand": False,
        }
    )

    safe_dataset = dataset_id.replace("/", "_")
    out_dir = workspace / "outputs" / f"gee_{temporal}" / safe_dataset / period_label
    out_dir.mkdir(parents=True, exist_ok=True)

    out_name = output_name or f"{safe_dataset}_{period_label}.tif"
    out_path = out_dir / out_name
    tmp_path = out_path.with_suffix(".zip")

    _curl_download(download_url, tmp_path)
    final_path = _maybe_unpack_tif(tmp_path)
    if final_path != out_path:
        final_path.replace(out_path)
    tmp_path.unlink(missing_ok=True)

    meta = {
        "temporal_resolution": temporal,
        "period": period_label,
        "start_date": start_date,
        "end_date_exclusive": end_date_exclusive,
        "dataset": dataset_id,
        "band": band_name,
        "gee_project": gee_project,
        "region": region_name,
        "bbox": [minx, miny, maxx, maxy],
        "image_count": image_count,
        "scale": int(scale),
        "output_tif": str(out_path),
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta_path = out_dir / "download_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_tif": str(out_path), "meta_json": str(meta_path), "image_count": image_count}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download GEE NTL image (daily/monthly/annual) for area/bbox.")
    parser.add_argument("--temporal-resolution", default="daily", choices=["daily", "monthly", "annual"])
    parser.add_argument("--period", default=None, help="daily: YYYY-MM-DD; monthly: YYYY-MM; annual: YYYY")
    parser.add_argument("--date", default=None, help="Backward-compat alias of --period for daily")
    parser.add_argument("--study-area", default=None, help="Administrative area name")
    parser.add_argument("--bbox", default=None, help="minx,miny,maxx,maxy")
    parser.add_argument("--dataset", default=None, help="GEE dataset id")
    parser.add_argument("--band", default=None, help="Band name (optional if dataset has preset)")
    parser.add_argument("--scale", type=int, default=500, help="Export scale in meters")
    parser.add_argument("--workspace", default="experiments/official_daily_ntl_fastpath/workspace_gee_download")
    parser.add_argument("--output-name", default=None, help="Output tif filename")
    parser.add_argument("--gee-project", default=DEFAULT_GEE_PROJECT, help="GEE project id")
    parser.add_argument("--is-in-china", default=None, choices=["true", "false"])
    return parser.parse_args()


def run() -> dict[str, str | int]:
    args = _parse_args()

    temporal = str(args.temporal_resolution).strip().lower()
    period = (args.period or "").strip() or (args.date or "").strip()
    if not period:
        raise ValueError("--period is required (or use --date for daily compatibility)")

    dataset = (args.dataset or DEFAULT_GEE_DATASET_BY_TEMPORAL[temporal]).strip()
    bbox = parse_bbox(args.bbox)
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    in_china = _bool_flag(args.is_in_china)
    if bbox is None:
        if not args.study_area:
            raise ValueError("Either --study-area or --bbox is required.")
        boundary = resolve_boundary(study_area=args.study_area, workspace=workspace, is_in_china=in_china)
        bbox = boundary.bbox
        region_name = args.study_area
    else:
        region_name = "bbox"

    result = download_gee_ntl(
        bbox=bbox,
        dataset=dataset,
        temporal_resolution=temporal,
        period=period,
        workspace=workspace,
        gee_project=args.gee_project,
        band=args.band,
        scale=int(args.scale),
        output_name=args.output_name,
        region_name=region_name,
    )

    print(str(result["output_tif"]))
    print(str(result["meta_json"]))
    return result


if __name__ == "__main__":
    run()
