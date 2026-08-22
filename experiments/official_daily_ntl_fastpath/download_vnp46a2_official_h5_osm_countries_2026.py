from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import h5py
from shapely.geometry import box

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from experiments.official_daily_ntl_fastpath.cmr_client import (  # noqa: E402
    download_file_with_curl,
    extract_download_link,
    group_granules_by_day,
    resolve_token,
    search_granules,
)
from experiments.official_daily_ntl_fastpath.download_vnp46a2_unfilled_osm_countries_2026 import (  # noqa: E402
    DATASET_ID,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_START,
    SIMPLIFY_TOLERANCE_DEG,
    clamp_end_day,
    gee_latest_day,
    init_ee,
    iter_dates,
    run_dir,
    selected_countries,
)

SHORT_NAME = "VNP46A2"
BAND = "DNB_BRDF_Corrected_NTL"


def redact_secrets(text: object) -> str:
    value = str(text or "")
    value = re.sub(r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._-]+", r"\1<REDACTED>", value)
    value = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer <REDACTED>", value)
    value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "<REDACTED_JWT>", value)
    return value


def validate_h5_band(path: Path) -> tuple[bool, str]:
    try:
        with h5py.File(path, "r") as h5:
            hits: list[str] = []

            def walk(name, obj):
                normalized = name.replace("-", "_")
                if isinstance(obj, h5py.Dataset) and normalized.endswith(BAND) and "Gap_Filled" not in normalized:
                    hits.append(name)

            h5.visititems(walk)
            if not hits:
                return False, f"{BAND} dataset missing"
            ds = h5[hits[0]]
            if len(ds.shape) != 2 or min(ds.shape) <= 0:
                return False, f"invalid dataset shape: {ds.shape}"
            # Force a tiny read so truncated files fail before they are accepted.
            _ = ds[0, 0]
    except Exception as exc:  # noqa: BLE001
        return False, repr(exc)
    return True, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official NASA Earthdata VNP46A2 H5 granules for OSM 0.001 country boundaries."
    )
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", required=True, help="Inclusive end date. Clamped to latest GEE product date.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument("--targets", nargs="+", default=None, help="Optional ISO3:YYYY-MM-DD values to retry specific country-days.")
    parser.add_argument("--limit-days", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8, help="Parallel curl workers per country-day.")
    parser.add_argument("--download-timeout", type=int, default=240, help="Per-HDF curl timeout in seconds.")
    parser.add_argument("--run-label", default="", help="Optional suffix for manifest/summary files.")
    parser.add_argument("--token-env", default="EARTHDATA_TOKEN")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parse_targets(values: list[str]) -> dict[str, list[str]]:
    targets: dict[str, list[str]] = {}
    for value in values:
        iso3, day = value.split(":", 1)
        targets.setdefault(iso3.strip().upper(), []).append(day.strip())
    return {iso3: sorted(set(days)) for iso3, days in targets.items()}


def safe_filename_from_url(url: str, fallback: str) -> str:
    name = Path(url.split("?", 1)[0]).name
    return name if name else fallback


def boundary_bbox(path: Path) -> tuple[float, float, float, float]:
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    return tuple(round(float(x), 6) for x in gdf.total_bounds)


def tile_box_from_granule_id(granule_id: str):
    import re

    match = re.search(r"\.h(\d{2})v(\d{2})\.", str(granule_id or ""))
    if not match:
        return None
    h = int(match.group(1))
    v = int(match.group(2))
    xmin = -180.0 + h * 10.0
    xmax = xmin + 10.0
    ymax = 90.0 - v * 10.0
    ymin = ymax - 10.0
    return box(xmin, ymin, xmax, ymax)


def country_geometries(path: Path) -> list:
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    return [geom for geom in gdf.geometry if geom is not None and not geom.is_empty]


def filter_entries_to_country_tiles(entries, geometries: list) -> list:
    filtered = []
    for entry in entries:
        tile_geom = tile_box_from_granule_id(entry.producer_granule_id)
        if tile_geom is None:
            filtered.append(entry)
            continue
        if any(geom.intersects(tile_geom) for geom in geometries):
            filtered.append(entry)
    return filtered


def valid_h5_files(day_dir: Path, geometries: list | None = None) -> list[Path]:
    files = sorted(path for path in day_dir.glob("*.h5") if path.exists() and path.stat().st_size > 512)
    if geometries is None:
        return files
    out: list[Path] = []
    for path in files:
        tile_geom = tile_box_from_granule_id(path.name)
        if tile_geom is None or any(geom.intersects(tile_geom) for geom in geometries):
            out.append(path)
    return out


def download_one(
    entry,
    idx: int,
    day_dir: Path,
    iso3: str,
    day: str,
    token: str,
    timeout: int,
) -> tuple[bool, Path | None, str]:
    link = extract_download_link(entry.links)
    if not link:
        return False, None, f"{idx}:missing_link:{entry.producer_granule_id}"
    filename = safe_filename_from_url(link, f"VNP46A2_{iso3}_{day}_{idx}.h5")
    dst = day_dir / filename
    if dst.exists() and dst.stat().st_size > 512:
        valid, reason = validate_h5_band(dst)
        if valid:
            return True, dst, "existing"
        dst.unlink(missing_ok=True)
        # Continue into a fresh download below; the failed validation will be
        # reported only if the replacement download also fails.
    try:
        ok, err = download_file_with_curl(link, dst, earthdata_token=token, timeout=max(60, int(timeout)))
    except Exception as exc:  # noqa: BLE001
        dst.unlink(missing_ok=True)
        return False, None, redact_secrets(f"{idx}:{entry.producer_granule_id}:exception:{exc!r}")
    if ok:
        valid, reason = validate_h5_band(dst)
        if valid:
            return True, dst, ""
        dst.unlink(missing_ok=True)
        return False, None, redact_secrets(f"{idx}:{entry.producer_granule_id}:invalid_download:{reason}")
    dst.unlink(missing_ok=True)
    return False, None, redact_secrets(f"{idx}:{entry.producer_granule_id}:{err}")


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "country",
        "iso3",
        "date",
        "source",
        "gee_dataset",
        "band",
        "boundary_source",
        "simplify_tolerance_deg",
        "bbox",
        "status",
        "granules_found",
        "downloaded_count",
        "failed_count",
        "output_dir",
        "file_size_mb",
        "files",
        "note",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    token = resolve_token(args.token_env)
    if not token:
        raise RuntimeError(f"{args.token_env} missing")
    init_ee()
    effective_end = clamp_end_day(args.end, gee_latest_day())
    dates = iter_dates(args.start, effective_end)
    if args.limit_days > 0:
        dates = dates[: args.limit_days]
    target_dates_by_iso = parse_targets(args.targets) if args.targets else None

    base_dir = run_dir(Path(args.output_root), args.start, effective_end)
    simplified_dir = base_dir / "osm_boundaries_simplified_0p001"
    out_root = base_dir / "official_raw_h5"
    label = f"_{args.run_label.strip()}" if str(args.run_label or "").strip() else ""
    manifest = base_dir / f"vnp46a2_official_h5_osm_0p001{label}_manifest.csv"
    rows: list[dict[str, object]] = []

    country_tokens = sorted(target_dates_by_iso) if target_dates_by_iso else args.countries
    for country in selected_countries(country_tokens):
        matches = sorted(simplified_dir.glob(f"osm_admin0_{country.iso3}_*_simplified_0p001.geojson"))
        if not matches:
            rows.append(
                {
                    "country": country.name,
                    "iso3": country.iso3,
                    "date": "",
                    "source": "NASA CMR/Earthdata official H5",
                    "gee_dataset": DATASET_ID,
                    "band": BAND,
                    "boundary_source": str(simplified_dir),
                    "simplify_tolerance_deg": SIMPLIFY_TOLERANCE_DEG,
                    "bbox": "",
                    "status": "missing_simplified_boundary",
                    "granules_found": 0,
                    "downloaded_count": 0,
                    "failed_count": 0,
                    "output_dir": "",
                    "file_size_mb": "",
                    "files": "",
                    "note": "Run the country script dry-run first to build simplified OSM boundaries.",
                }
            )
            write_manifest(manifest, rows)
            continue
        boundary_path = matches[0]
        bbox = boundary_bbox(boundary_path)
        geometries = country_geometries(boundary_path)
        bbox_text = ",".join(str(x) for x in bbox)
        country_dates = target_dates_by_iso.get(country.iso3, []) if target_dates_by_iso else dates
        for day in country_dates:
            day_dir = out_root / country.iso3 / day
            record: dict[str, object] = {
                "country": country.name,
                "iso3": country.iso3,
                "date": day,
                "source": "NASA CMR/Earthdata official H5",
                "gee_dataset": DATASET_ID,
                "band": BAND,
                "boundary_source": str(boundary_path),
                "simplify_tolerance_deg": SIMPLIFY_TOLERANCE_DEG,
                "bbox": bbox_text,
                "status": "started",
                "granules_found": 0,
                "downloaded_count": 0,
                "failed_count": 0,
                "output_dir": str(day_dir),
                "file_size_mb": "",
                "files": "",
                "note": "",
            }
            try:
                granules = search_granules(SHORT_NAME, day, day, bbox=bbox, page_size=200)
                raw_entries = group_granules_by_day(granules).get(day, [])
                entries = filter_entries_to_country_tiles(raw_entries, geometries)
                record["granules_found"] = len(entries)
                if not entries:
                    record["status"] = "no_granules"
                    record["note"] = (
                        f"CMR returned {len(raw_entries)} bbox granules but none intersected the OSM country geometry."
                    )
                    rows.append(record)
                    write_manifest(manifest, rows)
                    print(f"[{country.iso3} {day}] no_granules")
                    continue

                downloaded: list[Path] = []
                failures: list[str] = []
                with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
                    futures = [
                        executor.submit(download_one, entry, idx, day_dir, country.iso3, day, token, args.download_timeout)
                        for idx, entry in enumerate(entries, start=1)
                    ]
                    for future in as_completed(futures):
                        ok, path, note = future.result()
                        if ok and path is not None:
                            downloaded.append(path)
                        elif note:
                            failures.append(note)
                record["downloaded_count"] = len(downloaded)
                record["failed_count"] = len(failures)
                record["file_size_mb"] = round(sum(p.stat().st_size for p in downloaded) / 1024 / 1024, 3)
                record["files"] = ";".join(str(p) for p in sorted(downloaded))
                record["status"] = (
                    "official_h5_downloaded"
                    if downloaded and not failures
                    else "official_h5_partial"
                    if downloaded
                    else "official_h5_failed"
                )
                record["note"] = redact_secrets(" | ".join(failures[:5]))
                print(
                    f"[{country.iso3} {day}] {record['status']} "
                    f"granules={len(entries)} downloaded={len(downloaded)} failed={len(failures)}"
                )
            except Exception as exc:  # noqa: BLE001
                record["status"] = "official_h5_exception"
                record["note"] = redact_secrets(repr(exc))
                print(f"[{country.iso3} {day}] official_h5_exception {redact_secrets(repr(exc))}")
            rows.append(record)
            write_manifest(manifest, rows)
            time.sleep(0.1)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "countries": args.countries or "ALL",
        "start": args.start,
        "end": effective_end,
        "rows": len(rows),
        "downloaded_rows": sum(1 for r in rows if r.get("status") == "official_h5_downloaded"),
        "failed_rows": sum(1 for r in rows if r.get("status") not in {"official_h5_downloaded"}),
        "manifest": str(manifest),
    }
    summary_path = base_dir / f"vnp46a2_official_h5_osm_0p001{label}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_rows"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
