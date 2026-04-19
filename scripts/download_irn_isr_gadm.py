"""Download GADM administrative boundaries for Iran and Israel.

GADM publishes one country shapefile ZIP containing all available ADM levels.
This script stores the original ZIP and exports each available ADM layer to
GeoJSON for downstream ConflictNTL AOI processing.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "gadm_irn_isr_all_levels"
GADM_VERSION = "4.1"
GADM_URL_TEMPLATE = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_{iso3}_shp.zip"
COUNTRIES = {
    "IRN": "Iran",
    "ISR": "Israel",
}


def download_file(url: str, output_path: Path, timeout: int) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        with output_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    return output_path.stat().st_size


def extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)


def shapefile_adm_level(path: Path, iso3: str) -> int | None:
    match = re.fullmatch(rf"gadm41_{re.escape(iso3)}_(\d+)", path.stem, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def convert_layer(shp_path: Path, output_path: Path) -> dict[str, Any]:
    gdf = gpd.read_file(shp_path)
    if gdf.crs is not None and str(gdf.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
        gdf = gdf.to_crs("EPSG:4326")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")
    return {
        "feature_count": int(len(gdf)),
        "crs": "" if gdf.crs is None else str(gdf.crs),
        "bounds": list(map(float, gdf.total_bounds)) if len(gdf) else [],
        "file_size_bytes": output_path.stat().st_size,
    }


def process_country(iso3: str, country: str, output_dir: Path, timeout: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_dir = output_dir / "raw"
    extract_dir = output_dir / "extracted" / iso3
    url = GADM_URL_TEMPLATE.format(iso3=iso3)
    zip_path = raw_dir / f"gadm41_{iso3}_shp.zip"

    try:
        zip_size = download_file(url, zip_path, timeout)
        extract_zip(zip_path, extract_dir)
    except Exception as exc:
        rows.append(
            {
                "iso3": iso3,
                "country": country,
                "adm_level": "",
                "status": "download_failed",
                "feature_count": "",
                "file_size_bytes": "",
                "crs": "",
                "bounds": "",
                "output_geojson": "",
                "source_zip": str(zip_path),
                "source_zip_size_bytes": "",
                "source_url": url,
                "error_message": str(exc),
            }
        )
        return rows

    shp_files = sorted(
        (p for p in extract_dir.glob(f"gadm41_{iso3}_*.shp") if shapefile_adm_level(p, iso3) is not None),
        key=lambda p: shapefile_adm_level(p, iso3) or -1,
    )
    if not shp_files:
        rows.append(
            {
                "iso3": iso3,
                "country": country,
                "adm_level": "",
                "status": "no_layers_found",
                "feature_count": "",
                "file_size_bytes": "",
                "crs": "",
                "bounds": "",
                "output_geojson": "",
                "source_zip": str(zip_path),
                "source_zip_size_bytes": zip_size,
                "source_url": url,
                "error_message": "No GADM shapefiles found after extraction.",
            }
        )
        return rows

    for shp_path in shp_files:
        adm_level = shapefile_adm_level(shp_path, iso3)
        output_geojson = output_dir / f"{iso3.lower()}_gadm41_adm{adm_level}.geojson"
        row: dict[str, Any] = {
            "iso3": iso3,
            "country": country,
            "adm_level": adm_level,
            "status": "pending",
            "feature_count": "",
            "file_size_bytes": "",
            "crs": "",
            "bounds": "",
            "output_geojson": str(output_geojson),
            "source_zip": str(zip_path),
            "source_zip_size_bytes": zip_size,
            "source_url": url,
            "error_message": "",
        }
        try:
            stats = convert_layer(shp_path, output_geojson)
            row.update(
                {
                    "status": "converted",
                    "feature_count": stats["feature_count"],
                    "file_size_bytes": stats["file_size_bytes"],
                    "crs": stats["crs"],
                    "bounds": json.dumps(stats["bounds"], ensure_ascii=False),
                }
            )
        except Exception as exc:
            row.update({"status": "convert_failed", "error_message": str(exc)})
        rows.append(row)
    return rows


def write_manifest(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "iso3",
        "country",
        "adm_level",
        "status",
        "feature_count",
        "file_size_bytes",
        "crs",
        "bounds",
        "output_geojson",
        "source_zip",
        "source_zip_size_bytes",
        "source_url",
        "error_message",
    ]
    csv_path = output_dir / "gadm_download_manifest.csv"
    json_path = output_dir / "gadm_download_manifest.json"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for GeoJSON and manifests.")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for iso3, country in COUNTRIES.items():
        rows.extend(process_country(iso3, country, output_dir, args.timeout))

    write_manifest(rows, output_dir)
    converted = sum(1 for row in rows if row["status"] == "converted")
    failed = len(rows) - converted
    print(
        json.dumps(
            {
                "gadm_version": GADM_VERSION,
                "output_dir": str(output_dir),
                "converted": converted,
                "failed": failed,
            },
            ensure_ascii=False,
        )
    )
    return 0 if converted else 1


if __name__ == "__main__":
    raise SystemExit(main())
