"""Download and freeze the Q70 Shanghai NTL and AOI inputs.

The source is public Earth Engine V1 monthly VNP/VIIRS data plus GADM 4.1.
This script does not generate urban-centre algorithms or use randomness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import numpy as np
import rasterio
from pyproj import CRS
from rasterio.crs import CRS as RasterioCRS
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import mapping


ROOT = Path(__file__).resolve().parent
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_CHN_1.json"
EE_COLLECTION = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"
EE_START = "2014-12-01"
EE_END = "2015-01-01"
TARGET_CRS_PROJ4 = (
    "+proj=aea +lat_1=30.5 +lat_2=32.0 +lat_0=31.25 "
    "+lon_0=121 +datum=WGS84 +units=m +no_defs"
)
TARGET_PIXEL_SIZE_M = 500.0
UNIT = "nW/cm^2/sr"
REQUIRED_BUFFER_KM = 10.0
EXPORT_BUFFER_KM = 12.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_bytes(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "NTL-GPT-Q70-fixture/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _select_shanghai(source_path: Path, destination: Path) -> gpd.GeoDataFrame:
    source = gpd.read_file(source_path)
    name_column = next((column for column in source.columns if column.upper() == "NAME_1"), None)
    if name_column is None:
        raise RuntimeError("GADM source does not contain NAME_1")
    selected = source[source[name_column].astype(str).str.casefold() == "shanghai"].copy()
    if len(selected) != 1:
        raise RuntimeError(f"Expected one Shanghai GADM feature, found {len(selected)}")
    selected = selected[[name_column, "geometry"]].rename(columns={name_column: "name"})
    selected = selected.to_crs("EPSG:4326")
    if selected.geometry.iloc[0] is None or selected.geometry.iloc[0].is_empty or not selected.geometry.iloc[0].is_valid:
        raise RuntimeError("Selected Shanghai boundary is empty or invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected.to_file(destination, driver="GeoJSON", index=False)
    return selected


def _download_ee_raster(boundary: gpd.GeoDataFrame, destination: Path, temporary: Path) -> dict[str, Any]:
    try:
        ee.Initialize()
    except Exception as exc:  # pragma: no cover - depends on local EE credentials
        raise RuntimeError("Earth Engine initialization failed; authenticate the local EE session first") from exc

    collection = ee.ImageCollection(EE_COLLECTION).filterDate(EE_START, EE_END)
    count = int(collection.size().getInfo())
    if count != 1:
        raise RuntimeError(f"Expected one December 2014 image, found {count}")
    image = ee.Image(collection.first())
    image_id = str(image.id().getInfo())
    system_index = str(image.get("system:index").getInfo())
    if system_index != "20141201":
        raise RuntimeError(f"Unexpected December 2014 image index: {system_index}")

    # Buffer in metres, then return to WGS84 for the Earth Engine region.
    projected = boundary.to_crs("EPSG:3857")
    # Export two extra kilometres so reprojection and pixel-grid rounding
    # cannot remove any part of the required 10 km AOI buffer.
    buffered = projected.geometry.union_all().buffer(EXPORT_BUFFER_KM * 1000.0)
    buffered_wgs84 = gpd.GeoSeries([buffered], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
    # Export the buffered polygon's bounding rectangle.  This retains a
    # complete raster envelope around the 10 km buffer instead of asking Earth
    # Engine to mask the four corner wedges outside the polygon.
    region = mapping(buffered_wgs84.envelope)
    download_url = image.select("avg_rad").getDownloadURL(
        {
            "region": region,
            "scale": 463.83,
            "crs": "EPSG:4326",
            "format": "GEO_TIFF",
            "filePerBand": False,
        }
    )
    archive_path = temporary / "earth_engine_export"
    _download_bytes(download_url, archive_path)
    raw_raster = temporary / "source.tif"
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            members = [member for member in archive.namelist() if member.lower().endswith((".tif", ".tiff"))]
            if len(members) != 1:
                raise RuntimeError(f"Expected one GeoTIFF in Earth Engine export, found {members}")
            with archive.open(members[0]) as source, raw_raster.open("wb") as target:
                shutil.copyfileobj(source, target)
    else:
        raw_raster = archive_path

    target_crs = RasterioCRS.from_user_input(TARGET_CRS_PROJ4)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(raw_raster) as source:
        if source.count != 1:
            raise RuntimeError(f"Earth Engine export has {source.count} bands, expected one")
        transform, width, height = calculate_default_transform(
            source.crs,
            target_crs,
            source.width,
            source.height,
            *source.bounds,
            resolution=(TARGET_PIXEL_SIZE_M, TARGET_PIXEL_SIZE_M),
        )
        profile = source.profile.copy()
        profile.update(
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            dtype="float32",
            crs=target_crs,
            transform=transform,
            nodata=-9999.0,
            compress="none",
            tiled=False,
        )
        with rasterio.open(destination, "w", **profile) as target:
            reproject(
                source=rasterio.band(source, 1),
                destination=rasterio.band(target, 1),
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs=target_crs,
                dst_nodata=-9999.0,
                resampling=Resampling.bilinear,
            )
            target.update_tags(
                units=UNIT,
                radiance_unit=UNIT,
                product="NPP-VIIRS Version 1 monthly composite",
                band="avg_rad",
                source_collection=EE_COLLECTION,
                source_image_id=image_id,
                source_system_index=system_index,
                source_date=EE_START,
                source_crs="EPSG:4326",
                source_export_scale_m="463.83",
                target_projection="local Albers Equal Area",
                target_pixel_size_m=str(TARGET_PIXEL_SIZE_M),
            )
        with rasterio.open(destination) as frozen:
            data = frozen.read(1, masked=True)
            if not np.any(~data.mask):
                raise RuntimeError("Reprojected NTL raster contains no valid pixels")
            if np.nanmax(data.filled(np.nan)) < 0:
                raise RuntimeError("Reprojected NTL raster has no non-negative radiance")

    return {
        "collection": EE_COLLECTION,
        "start": EE_START,
        "end": EE_END,
        "image_id": image_id,
        "system_index": system_index,
        "band": "avg_rad",
        "download_scale_m": 463.83,
        "download_crs": "EPSG:4326",
        "required_buffer_km": REQUIRED_BUFFER_KM,
        "export_buffer_km": EXPORT_BUFFER_KM,
        "target_crs": CRS.from_user_input(TARGET_CRS_PROJ4).to_string(),
        "target_pixel_size_m": TARGET_PIXEL_SIZE_M,
        "unit": UNIT,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    boundary_path = inputs / "shanghai_boundary.geojson"
    raster_path = inputs / "ntl_shanghai_2014_12_v1_albers_500m.tif"
    with tempfile.TemporaryDirectory(prefix="q70_download_") as temporary_dir:
        temporary = Path(temporary_dir)
        source_boundary = temporary / "gadm41_CHN_1.json"
        _download_bytes(GADM_URL, source_boundary)
        boundary = _select_shanghai(source_boundary, boundary_path)
        ee_metadata = _download_ee_raster(boundary, raster_path, temporary)

    source_manifest = {
        "schema": "ntl.q70.source_manifest.v1",
        "method_doi": "10.1109/TGRS.2017.2725917",
        "boundary": {
            "source_url": GADM_URL,
            "source_dataset": "GADM 4.1 China level-1 GeoJSON",
            "selected_name": "Shanghai",
            "frozen_path": "inputs/shanghai_boundary.geojson",
            "sha256": sha256(boundary_path),
        },
        "ntl": {
            **ee_metadata,
            "frozen_path": "inputs/ntl_shanghai_2014_12_v1_albers_500m.tif",
            "sha256": sha256(raster_path),
        },
    }
    with (root / "source_manifest.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(source_manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(source_manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
