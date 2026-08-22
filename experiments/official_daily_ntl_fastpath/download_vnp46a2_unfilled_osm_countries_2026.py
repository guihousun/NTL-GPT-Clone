from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import ee
import geemap
import geopandas as gpd
import osmnx as ox
from dotenv import load_dotenv
from shapely.geometry import mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ID = "NASA/VIIRS/002/VNP46A2"
BAND = "DNB_BRDF_Corrected_NTL"
SCALE_M = 500
SIMPLIFY_TOLERANCE_DEG = 0.001
DEFAULT_START = "2026-01-27"
DEFAULT_OUTPUT_ROOT = Path(r"F:\专业数据\夜间灯光")


@dataclass(frozen=True)
class CountrySpec:
    iso3: str
    slug: str
    name: str
    osm_query: str


COUNTRIES: list[CountrySpec] = [
    CountrySpec("PAK", "pakistan", "Pakistan", "Pakistan"),
    CountrySpec("AUS", "australia", "Australia", "Australia"),
    CountrySpec("NZL", "new_zealand", "New Zealand", "New Zealand"),
    CountrySpec("THA", "thailand", "Thailand", "Thailand"),
    CountrySpec("VNM", "vietnam", "Vietnam", "Vietnam"),
    CountrySpec("MYS", "malaysia", "Malaysia", "Malaysia"),
    CountrySpec("IDN", "indonesia", "Indonesia", "Indonesia"),
    CountrySpec("MMR", "myanmar", "Myanmar", "Myanmar"),
    CountrySpec("PHL", "philippines", "Philippines", "Philippines"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download VNP46A2 unfilled DNB_BRDF_Corrected_NTL GeoTIFFs for OSM "
            "country boundaries simplified at 0.001 degrees."
        )
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument(
        "--end",
        default=date.today().strftime("%Y-%m-%d"),
        help="Inclusive end date, YYYY-MM-DD. Clamped to the latest GEE product date.",
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--countries", nargs="*", default=None, help="Optional ISO3/slug/name subset.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare boundaries and date lists without downloading.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing GeoTIFFs.")
    parser.add_argument("--limit-days", type=int, default=0, help="Optional smoke-test day limit per country.")
    parser.add_argument("--retries", type=int, default=1)
    return parser.parse_args()


def iter_dates(start: str, end: str) -> list[str]:
    current = datetime.strptime(start, "%Y-%m-%d").date()
    end_day = datetime.strptime(end, "%Y-%m-%d").date()
    out: list[str] = []
    while current <= end_day:
        out.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return out


def end_exclusive(day: str) -> str:
    return (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def selected_countries(tokens: Iterable[str] | None) -> list[CountrySpec]:
    if not tokens:
        return COUNTRIES
    wanted = {str(token).strip().lower() for token in tokens if str(token).strip()}
    out = [
        country
        for country in COUNTRIES
        if country.iso3.lower() in wanted
        or country.slug.lower() in wanted
        or country.name.lower() in wanted
    ]
    found = {item.iso3.lower() for item in out} | {item.slug.lower() for item in out} | {item.name.lower() for item in out}
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"Unknown country selectors: {', '.join(missing)}")
    return out


def init_ee() -> str:
    load_dotenv(REPO_ROOT / ".env")
    project = os.getenv("GEE_DEFAULT_PROJECT_ID") or "empyrean-caster-430308-m2"
    ee.Initialize(project=project)
    return project


def gee_latest_day() -> str:
    millis = ee.ImageCollection(DATASET_ID).aggregate_max("system:time_start").getInfo()
    if millis is None:
        raise RuntimeError(f"No images found in {DATASET_ID}.")
    return datetime.fromtimestamp(float(millis) / 1000, tz=UTC).strftime("%Y-%m-%d")


def clamp_end_day(requested_end: str, latest_day: str) -> str:
    requested = datetime.strptime(requested_end, "%Y-%m-%d").date()
    latest = datetime.strptime(latest_day, "%Y-%m-%d").date()
    return min(requested, latest).strftime("%Y-%m-%d")


def run_dir(output_root: Path, start: str, end: str) -> Path:
    return output_root / f"VNP46A2_unfilled_osm_0p001_{start}_to_{end}"


def fetch_osm_boundary(country: CountrySpec, boundary_dir: Path) -> gpd.GeoDataFrame:
    path = boundary_dir / f"osm_admin0_{country.iso3}_{country.slug}.geojson"
    if path.exists() and path.stat().st_size > 1000:
        return gpd.read_file(path).to_crs("EPSG:4326")

    ox.settings.use_cache = True
    ox.settings.log_console = False
    gdf = ox.geocode_to_gdf(country.osm_query, which_result=1).to_crs("EPSG:4326")
    if gdf.empty:
        raise RuntimeError(f"OSM/Nominatim returned no boundary for {country.name}.")
    gdf = gdf.copy()
    gdf["download_source"] = "OSM Nominatim via osmnx.geocode_to_gdf"
    gdf["requested_place"] = country.osm_query
    gdf["iso3"] = country.iso3
    gdf["slug"] = country.slug
    boundary_dir.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")
    return gdf


def simplified_boundary(gdf: gpd.GeoDataFrame, country: CountrySpec, simplified_dir: Path) -> gpd.GeoDataFrame:
    out = simplified_dir / f"osm_admin0_{country.iso3}_{country.slug}_simplified_0p001.geojson"
    if out.exists() and out.stat().st_size > 1000:
        return gpd.read_file(out).to_crs("EPSG:4326")
    simplified = gdf.copy()
    simplified["geometry"] = simplified.geometry.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
    simplified = simplified[~simplified.geometry.is_empty & simplified.geometry.notna()].copy()
    simplified_dir.mkdir(parents=True, exist_ok=True)
    simplified.to_file(out, driver="GeoJSON")
    return simplified


def area_km2(gdf: gpd.GeoDataFrame) -> float:
    return float(gdf.to_crs("EPSG:6933").geometry.area.sum() / 1_000_000.0)


def ee_geometry(gdf: gpd.GeoDataFrame) -> ee.Geometry:
    geom = gdf.geometry.union_all() if hasattr(gdf.geometry, "union_all") else gdf.geometry.unary_union
    return ee.Geometry(mapping(geom), proj="EPSG:4326", geodesic=False)


def collection_for_region(start: str, end: str, region: ee.Geometry) -> ee.ImageCollection:
    def prep(img):
        date_text = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")
        return img.select(BAND).rename("ntl").set("date", date_text).clip(region)

    return (
        ee.ImageCollection(DATASET_ID)
        .filterDate(start, end_exclusive(end))
        .filterBounds(region)
        .select(BAND)
        .sort("system:time_start")
        .map(prep)
    )


def available_dates(collection: ee.ImageCollection) -> list[str]:
    keys = collection.aggregate_array("date").getInfo()
    return sorted({str(k) for k in keys if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(k))})


def too_large_or_quota_error(message: str) -> bool:
    low = str(message or "").lower()
    markers = (
        "total request size",
        "request payload size exceeds",
        "user memory limit",
        "computed value is too large",
        "too many pixels",
        "download is too large",
        "pixel grid dimensions",
        "50331648",
    )
    return any(marker in low for marker in markers)


def export_image(image: ee.Image, region: ee.Geometry, output_path: Path) -> tuple[bool, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            geemap.ee_export_image(
                ee_object=image,
                filename=str(output_path),
                scale=SCALE_M,
                region=region,
                crs="EPSG:4326",
                file_per_band=False,
            )
    except Exception as exc:  # noqa: BLE001
        output_path.unlink(missing_ok=True)
        message = "\n".join(
            part.strip()
            for part in [repr(exc), stdout_buf.getvalue(), stderr_buf.getvalue()]
            if part and part.strip()
        )
        return False, message

    message = "\n".join(
        part.strip() for part in [stdout_buf.getvalue(), stderr_buf.getvalue()] if part and part.strip()
    )
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return False, message or "No output file created."
    if too_large_or_quota_error(message) or "an error occurred while downloading" in message.lower():
        output_path.unlink(missing_ok=True)
        return False, message
    return True, message


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "country",
        "iso3",
        "date",
        "dataset",
        "band",
        "boundary_source",
        "simplify_tolerance_deg",
        "gee_boundary_mode",
        "status",
        "output_file",
        "file_size_mb",
        "note",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    project = init_ee()
    latest_day = gee_latest_day()
    effective_end = clamp_end_day(args.end, latest_day)
    dates = iter_dates(args.start, effective_end)
    if args.limit_days > 0:
        dates = dates[: args.limit_days]

    output_root = Path(args.output_root)
    base_dir = run_dir(output_root, args.start, effective_end)
    boundary_dir = base_dir / "osm_boundaries"
    simplified_dir = base_dir / "osm_boundaries_simplified_0p001"
    image_dir = base_dir / "gee_direct_country"
    manifest_path = base_dir / "vnp46a2_unfilled_osm_0p001_manifest.csv"
    log_path = base_dir / "logs" / "download_events.jsonl"
    summary_path = base_dir / "vnp46a2_unfilled_osm_0p001_summary.json"

    rows: list[dict[str, object]] = []
    countries = selected_countries(args.countries)
    asset_roots = ee.data.getAssetRoots()
    gee_boundary_mode = "inline_ee_geometry"
    if asset_roots:
        gee_boundary_mode = "inline_ee_geometry_asset_root_available_not_used"

    for country in countries:
        try:
            raw = fetch_osm_boundary(country, boundary_dir)
            simple = simplified_boundary(raw, country, simplified_dir)
            raw_area = area_km2(raw)
            simple_area = area_km2(simple)
            region = ee_geometry(simple)
            collection = collection_for_region(args.start, effective_end, region)
            present_dates = available_dates(collection)
            selected_dates = [day for day in dates if day in set(present_dates)]
            print(
                f"[{country.iso3}] available={len(present_dates)} selected={len(selected_dates)} "
                f"raw_area={raw_area:.1f}km2 simplified_area={simple_area:.1f}km2"
            )
        except Exception as exc:  # noqa: BLE001
            record = {
                "country": country.name,
                "iso3": country.iso3,
                "date": "",
                "dataset": DATASET_ID,
                "band": BAND,
                "boundary_source": "OSM Nominatim boundary simplified with preserve_topology=True",
                "simplify_tolerance_deg": SIMPLIFY_TOLERANCE_DEG,
                "gee_boundary_mode": gee_boundary_mode,
                "status": "boundary_or_collection_failed",
                "output_file": "",
                "file_size_mb": "",
                "note": repr(exc)[:500],
            }
            rows.append(record)
            write_jsonl(log_path, record)
            write_manifest(manifest_path, rows)
            print(f"[{country.iso3}] boundary_or_collection_failed {exc!r}")
            continue

        if args.dry_run:
            record = {
                "country": country.name,
                "iso3": country.iso3,
                "date": "",
                "dataset": DATASET_ID,
                "band": BAND,
                "boundary_source": "OSM Nominatim boundary simplified with preserve_topology=True",
                "simplify_tolerance_deg": SIMPLIFY_TOLERANCE_DEG,
                "gee_boundary_mode": gee_boundary_mode,
                "status": "dry_run_ready",
                "output_file": str(image_dir / country.iso3),
                "file_size_mb": "",
                "note": f"selected_dates={len(selected_dates)} latest_gee_day={latest_day}",
            }
            rows.append(record)
            write_jsonl(log_path, record)
            write_manifest(manifest_path, rows)
            continue

        for day in selected_dates:
            image = ee.Image(collection.filter(ee.Filter.eq("date", day)).first())
            output = image_dir / country.iso3 / f"VNP46A2_{BAND}_{country.iso3}_{country.slug}_osm0p001_{day}.tif"
            record = {
                "country": country.name,
                "iso3": country.iso3,
                "date": day,
                "dataset": DATASET_ID,
                "band": BAND,
                "boundary_source": "OSM Nominatim boundary simplified with preserve_topology=True",
                "simplify_tolerance_deg": SIMPLIFY_TOLERANCE_DEG,
                "gee_boundary_mode": gee_boundary_mode,
                "status": "started",
                "output_file": str(output),
                "file_size_mb": "",
                "note": "",
            }
            if output.exists() and output.stat().st_size > 0 and not args.force:
                record["status"] = "downloaded"
                record["file_size_mb"] = round(output.stat().st_size / 1024 / 1024, 3)
                record["note"] = "Existing GeoTIFF reused."
                rows.append(record)
                write_jsonl(log_path, record)
                write_manifest(manifest_path, rows)
                continue

            ok = False
            message = ""
            for attempt in range(max(0, int(args.retries)) + 1):
                ok, message = export_image(image, region, output)
                if ok:
                    break
                if too_large_or_quota_error(message):
                    break
                time.sleep(1.5 * (attempt + 1))
            if ok:
                record["status"] = "downloaded"
                record["file_size_mb"] = round(output.stat().st_size / 1024 / 1024, 3)
            elif too_large_or_quota_error(message):
                record["status"] = "gee_country_too_large_skip_for_province_mosaic"
            else:
                record["status"] = "gee_download_failed"
            record["note"] = str(message or "")[:500]
            rows.append(record)
            write_jsonl(log_path, record)
            write_manifest(manifest_path, rows)
            print(f"[{country.iso3} {day}] {record['status']}")

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "gee_project": project,
        "dataset": DATASET_ID,
        "band": BAND,
        "requested_start": args.start,
        "requested_end": args.end,
        "latest_gee_day": latest_day,
        "effective_end": effective_end,
        "countries": [country.iso3 for country in countries],
        "output_root": str(output_root),
        "run_dir": str(base_dir),
        "manifest": str(manifest_path),
        "boundary_dir": str(boundary_dir),
        "simplified_boundary_dir": str(simplified_dir),
        "gee_boundary_mode": gee_boundary_mode,
        "asset_roots_visible": [r.get("id") for r in asset_roots],
        "rows": len(rows),
        "downloaded": sum(1 for r in rows if r.get("status") == "downloaded"),
        "too_large": sum(1 for r in rows if r.get("status") == "gee_country_too_large_skip_for_province_mosaic"),
        "failed": sum(
            1
            for r in rows
            if r.get("status") not in {"downloaded", "dry_run_ready", "gee_country_too_large_skip_for_province_mosaic"}
        ),
        "dry_run": bool(args.dry_run),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
