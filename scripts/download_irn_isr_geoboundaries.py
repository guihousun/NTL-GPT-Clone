"""Download geoBoundaries Open administrative boundaries for Iran and Israel.

This script intentionally uses the geoBoundaries API directly instead of the
project's GADM-first helper, because the experiment needs source-specific
geoBoundaries layers.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "geoboundaries_irn_isr_all_levels"
META_URL_TEMPLATE = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM{adm}/"
COUNTRIES = {
    "IRN": "Iran",
    "ISR": "Israel",
}


def request_json(url: str, timeout: int) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    return response.json()


def download_file(url: str, output_path: Path, timeout: int) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        if response.status_code != 200:
            raise RuntimeError(f"download HTTP {response.status_code}")
        with output_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    return output_path.stat().st_size


def count_features(path: Path) -> tuple[int | None, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        features = data.get("features")
        if isinstance(features, list):
            return len(features), str(data.get("crs", {}).get("properties", {}).get("name", "EPSG:4326"))
        return None, ""
    except Exception:
        return None, ""


def download_level(iso3: str, country: str, adm: int, output_dir: Path, timeout: int) -> dict[str, Any]:
    meta_url = META_URL_TEMPLATE.format(iso3=iso3, adm=adm)
    row: dict[str, Any] = {
        "iso3": iso3,
        "country": country,
        "adm_level": adm,
        "status": "pending",
        "feature_count": "",
        "file_size_bytes": "",
        "crs": "",
        "output_geojson": "",
        "meta_url": meta_url,
        "download_url": "",
        "boundary_id": "",
        "boundary_name": "",
        "boundary_type": "",
        "license": "",
        "error_message": "",
    }
    try:
        meta = request_json(meta_url, timeout)
        gj_url = str(meta.get("gjDownloadURL") or "").strip()
        if not gj_url:
            raise RuntimeError("missing gjDownloadURL")

        output_path = output_dir / f"{iso3.lower()}_geoboundaries_adm{adm}.geojson"
        file_size = download_file(gj_url, output_path, timeout)
        feature_count, crs = count_features(output_path)

        row.update(
            {
                "status": "downloaded",
                "feature_count": "" if feature_count is None else feature_count,
                "file_size_bytes": file_size,
                "crs": crs,
                "output_geojson": str(output_path),
                "download_url": gj_url,
                "boundary_id": meta.get("boundaryID", ""),
                "boundary_name": meta.get("boundaryName", ""),
                "boundary_type": meta.get("boundaryType", ""),
                "license": meta.get("licenseDetail", ""),
            }
        )
    except Exception as exc:
        row.update({"status": "unavailable_or_failed", "error_message": str(exc)})
    return row


def write_manifest(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "geoboundaries_download_manifest.csv"
    json_path = output_dir / "geoboundaries_download_manifest.json"
    fieldnames = [
        "iso3",
        "country",
        "adm_level",
        "status",
        "feature_count",
        "file_size_bytes",
        "crs",
        "output_geojson",
        "meta_url",
        "download_url",
        "boundary_id",
        "boundary_name",
        "boundary_type",
        "license",
        "error_message",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for GeoJSON and manifests.")
    parser.add_argument("--min-adm", type=int, default=0, help="Minimum ADM level to query.")
    parser.add_argument("--max-adm", type=int, default=5, help="Maximum ADM level to query.")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    rows: list[dict[str, Any]] = []

    for iso3, country in COUNTRIES.items():
        for adm in range(args.min_adm, args.max_adm + 1):
            rows.append(download_level(iso3, country, adm, output_dir, args.timeout))

    write_manifest(rows, output_dir)
    downloaded = sum(1 for row in rows if row["status"] == "downloaded")
    failed = len(rows) - downloaded
    print(json.dumps({"output_dir": str(output_dir), "downloaded": downloaded, "failed": failed}, ensure_ascii=False))
    return 0 if downloaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
