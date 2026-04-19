"""Download OSM administrative boundaries for Iran and Israel.

The workflow uses Geofabrik .osm.pbf extracts plus osmium-tool to preserve OSM
tags such as admin_level. Israel is extracted from Geofabrik's
israel-and-palestine region and then spatially filtered with the previously
downloaded geoBoundaries ADM0 mask when available.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "osm_admin_boundaries_irn_isr"
DEFAULT_MASK_DIR = REPO_ROOT / "docs" / "geoboundaries_irn_isr_all_levels"

SOURCES = {
    "IRN": {
        "country": "Iran",
        "region_slug": "iran",
        "url": "https://download.geofabrik.de/asia/iran-latest.osm.pbf",
    },
    "ISR": {
        "country": "Israel",
        "region_slug": "israel-and-palestine",
        "url": "https://download.geofabrik.de/asia/israel-and-palestine-latest.osm.pbf",
    },
}


def download_file(url: str, output_path: Path, timeout: int) -> int:
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path.stat().st_size
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        with output_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    return output_path.stat().st_size


def run_command(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} failed: {message}")


def extract_admin_boundaries(pbf_path: Path, work_dir: Path, slug: str) -> Path:
    filtered_pbf = work_dir / f"{slug}_admin_boundaries.osm.pbf"
    exported_geojson = work_dir / f"{slug}_admin_boundaries_raw.geojson"
    run_command(
        ["osmium", "tags-filter", str(pbf_path), "r/boundary=administrative", "-o", str(filtered_pbf), "-O"],
        work_dir,
    )
    run_command(
        [
            "osmium",
            "export",
            str(filtered_pbf),
            "-o",
            str(exported_geojson),
            "-O",
            "--geometry-types=polygon",
            "--add-unique-id=type_id",
            "--attributes=type,id",
        ],
        work_dir,
    )
    return exported_geojson


def normalize_admin_level(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() else ""


def apply_country_mask(gdf: gpd.GeoDataFrame, iso3: str, mask_dir: Path) -> tuple[gpd.GeoDataFrame, str]:
    mask_path = mask_dir / f"{iso3.lower()}_geoboundaries_adm0.geojson"
    if not mask_path.exists() or gdf.empty:
        return gdf, ""
    mask = gpd.read_file(mask_path)
    if mask.crs is not None and gdf.crs is not None and str(mask.crs) != str(gdf.crs):
        mask = mask.to_crs(gdf.crs)
    mask_union = mask.geometry.union_all() if hasattr(mask.geometry, "union_all") else mask.geometry.unary_union
    points = gdf.geometry.representative_point()
    filtered = gdf[points.within(mask_union)].copy()
    return filtered, str(mask_path)


def load_and_clean_boundaries(raw_geojson: Path, iso3: str, mask_dir: Path) -> tuple[gpd.GeoDataFrame, str]:
    gdf = gpd.read_file(raw_geojson)
    if "boundary" in gdf.columns:
        gdf = gdf[gdf["boundary"].astype(str).str.lower() == "administrative"].copy()
    if "admin_level" not in gdf.columns:
        gdf["admin_level"] = ""
    gdf["admin_level"] = gdf["admin_level"].map(normalize_admin_level)
    gdf = gdf[gdf["admin_level"] != ""].copy()
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif str(gdf.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
        gdf = gdf.to_crs("EPSG:4326")
    gdf, mask_used = apply_country_mask(gdf, iso3, mask_dir)
    return gdf, mask_used


def write_outputs(gdf: gpd.GeoDataFrame, iso3: str, country: str, output_dir: Path, source_url: str, mask_used: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stale in output_dir.glob(f"{iso3.lower()}_osm_admin_boundaries*.geojson"):
        stale.unlink()
    all_path = output_dir / f"{iso3.lower()}_osm_admin_boundaries_all.geojson"
    gdf.to_file(all_path, driver="GeoJSON")

    for level in sorted(gdf["admin_level"].dropna().unique(), key=lambda v: int(v) if str(v).isdigit() else 999):
        level_gdf = gdf[gdf["admin_level"] == level].copy()
        output_path = output_dir / f"{iso3.lower()}_osm_admin_boundaries_admin_level_{level}.geojson"
        level_gdf.to_file(output_path, driver="GeoJSON")
        rows.append(
            {
                "iso3": iso3,
                "country": country,
                "admin_level": level,
                "feature_count": int(len(level_gdf)),
                "output_geojson": str(output_path),
                "all_levels_geojson": str(all_path),
                "source": "OpenStreetMap via Geofabrik PBF",
                "source_url": source_url,
                "country_mask": mask_used,
                "status": "exported",
                "error_message": "",
            }
        )
    if not rows:
        rows.append(
            {
                "iso3": iso3,
                "country": country,
                "admin_level": "",
                "feature_count": 0,
                "output_geojson": "",
                "all_levels_geojson": str(all_path),
                "source": "OpenStreetMap via Geofabrik PBF",
                "source_url": source_url,
                "country_mask": mask_used,
                "status": "no_admin_levels_found",
                "error_message": "",
            }
        )
    return rows


def process_source(iso3: str, cfg: dict[str, str], output_dir: Path, mask_dir: Path, timeout: int) -> list[dict[str, Any]]:
    raw_dir = output_dir / "raw"
    work_dir = output_dir / "work"
    raw_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    pbf_path = raw_dir / f"{cfg['region_slug']}-latest.osm.pbf"
    rows: list[dict[str, Any]] = []
    try:
        download_file(cfg["url"], pbf_path, timeout)
        raw_geojson = extract_admin_boundaries(pbf_path, work_dir, cfg["region_slug"])
        gdf, mask_used = load_and_clean_boundaries(raw_geojson, iso3, mask_dir)
        rows.extend(write_outputs(gdf, iso3, cfg["country"], output_dir, cfg["url"], mask_used))
    except Exception as exc:
        rows.append(
            {
                "iso3": iso3,
                "country": cfg["country"],
                "admin_level": "",
                "feature_count": "",
                "output_geojson": "",
                "all_levels_geojson": "",
                "source": "OpenStreetMap via Geofabrik PBF",
                "source_url": cfg["url"],
                "country_mask": "",
                "status": "failed",
                "error_message": str(exc),
            }
        )
    return rows


def write_manifest(rows: list[dict[str, Any]], output_dir: Path) -> None:
    fieldnames = [
        "iso3",
        "country",
        "admin_level",
        "feature_count",
        "output_geojson",
        "all_levels_geojson",
        "source",
        "source_url",
        "country_mask",
        "status",
        "error_message",
    ]
    csv_path = output_dir / "osm_admin_boundaries_manifest.csv"
    json_path = output_dir / "osm_admin_boundaries_manifest.json"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for OSM boundary outputs.")
    parser.add_argument("--mask-dir", default=str(DEFAULT_MASK_DIR), help="Directory with geoBoundaries ADM0 masks.")
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    if shutil.which("osmium") is None:
        raise RuntimeError("osmium executable not found. Install osmium-tool in the active conda environment.")
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mask_dir = Path(args.mask_dir).resolve()
    rows: list[dict[str, Any]] = []

    for iso3, cfg in SOURCES.items():
        rows.extend(process_source(iso3, cfg, output_dir, mask_dir, args.timeout))

    write_manifest(rows, output_dir)
    exported = sum(1 for row in rows if row["status"] == "exported")
    failed = sum(1 for row in rows if row["status"] == "failed")
    print(json.dumps({"output_dir": str(output_dir), "exported_levels": exported, "failed_sources": failed}, ensure_ascii=False))
    return 0 if exported else 1


if __name__ == "__main__":
    raise SystemExit(main())
