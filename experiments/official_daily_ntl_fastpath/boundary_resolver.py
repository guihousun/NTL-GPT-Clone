from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import geopandas as gpd
from shapely.geometry import shape

from storage_manager import current_thread_id, storage_manager
from tools.GaoDe_tool import get_administrative_division_data, get_administrative_division_osm

from .env_utils import get_env_or_dotenv
from .gee_baseline import DEFAULT_GEE_PROJECT


@dataclass(frozen=True)
class BoundaryResult:
    gdf: gpd.GeoDataFrame
    bbox: tuple[float, float, float, float]
    boundary_source: str
    boundary_path: Path


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def guess_is_in_china(study_area: str, is_in_china: bool | None = None) -> bool:
    if isinstance(is_in_china, bool):
        return is_in_china
    token = (study_area or "").strip().lower()
    if token in {"china", "prc", "people's republic of china", "中国", "中华人民共和国"}:
        return True
    return _contains_cjk(study_area)


def _copy_shapefile_bundle(src_shp: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    stem = src_shp.stem
    copied_shp = dst_dir / src_shp.name
    for file in src_shp.parent.glob(f"{stem}.*"):
        if file.suffix.lower() in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}:
            shutil.copy2(file, dst_dir / file.name)
    return copied_shp


def _load_gdf_and_bbox(boundary_path: Path) -> tuple[gpd.GeoDataFrame, tuple[float, float, float, float]]:
    gdf = gpd.read_file(boundary_path)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    minx, miny, maxx, maxy = gdf.total_bounds
    return gdf, (float(minx), float(miny), float(maxx), float(maxy))


def _safe_boundary_filename(study_area: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff]+", "_", study_area, flags=re.UNICODE).strip("_")
    if not stem:
        stem = f"area_{abs(hash(study_area)) & 0xFFFFFFFF:08x}"
    return f"boundary_{stem}.shp"


def _save_gdf_as_shp(gdf: gpd.GeoDataFrame, workspace: Path, boundary_filename: str) -> Path:
    local_shp = workspace / "boundaries" / boundary_filename
    local_shp.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(local_shp, encoding="utf-8")
    return local_shp


def _resolve_via_amap(study_area: str, workspace: Path, boundary_filename: str) -> BoundaryResult:
    thread_id = f"official_daily_fastpath_{workspace.name}"
    token = current_thread_id.set(thread_id)
    try:
        result = get_administrative_division_data(city=study_area, input_name=boundary_filename)
        if any(s in str(result).lower() for s in ("error", "failed")):
            raise RuntimeError(str(result))
        src_shp = Path(storage_manager.resolve_input_path(boundary_filename, thread_id=thread_id))
        if not src_shp.exists():
            raise FileNotFoundError(f"Boundary file not found after amap tool call: {src_shp}")

        local_shp = _copy_shapefile_bundle(src_shp, workspace / "boundaries")
        gdf, bbox = _load_gdf_and_bbox(local_shp)
        return BoundaryResult(gdf=gdf, bbox=bbox, boundary_source="amap", boundary_path=local_shp)
    finally:
        current_thread_id.reset(token)


def _resolve_via_osm(study_area: str, workspace: Path, boundary_filename: str) -> BoundaryResult:
    thread_id = f"official_daily_fastpath_{workspace.name}"
    token = current_thread_id.set(thread_id)
    try:
        result = get_administrative_division_osm(place_name=study_area, input_name=boundary_filename)
        if any(s in str(result).lower() for s in ("error", "failed")):
            raise RuntimeError(str(result))
        src_shp = Path(storage_manager.resolve_input_path(boundary_filename, thread_id=thread_id))
        if not src_shp.exists():
            raise FileNotFoundError(f"Boundary file not found after osm tool call: {src_shp}")

        local_shp = _copy_shapefile_bundle(src_shp, workspace / "boundaries")
        gdf, bbox = _load_gdf_and_bbox(local_shp)
        return BoundaryResult(gdf=gdf, bbox=bbox, boundary_source="osm", boundary_path=local_shp)
    finally:
        current_thread_id.reset(token)


def _resolve_via_gee(study_area: str, workspace: Path, boundary_filename: str) -> BoundaryResult:
    try:
        import ee
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"ee import failed: {exc}") from exc

    try:
        ee.Initialize(project=DEFAULT_GEE_PROJECT)
    except Exception:
        ee.Initialize()

    aliases = {
        "中国": "China",
        "中华人民共和国": "China",
        "美国": "United States",
        "日本": "Japan",
        "缅甸": "Myanmar",
    }

    text = (study_area or "").strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    primary = parts[0] if parts else text
    country_hint = parts[-1] if len(parts) > 1 else ""

    candidates = [
        text,
        primary,
        aliases.get(text, ""),
        aliases.get(primary, ""),
        country_hint,
        aliases.get(country_hint, ""),
    ]
    candidates = [c for c in candidates if c]

    def _query_geom(collection_id: str, field: str, values: list[str], country_filter: str | None = None) -> dict | None:
        fc = ee.FeatureCollection(collection_id)
        for v in values:
            filtered = fc.filter(ee.Filter.eq(field, v))
            if country_filter:
                filtered = filtered.filter(ee.Filter.eq("ADM0_NAME", country_filter))
            if int(filtered.size().getInfo()) > 0:
                return ee.Feature(filtered.first()).geometry().getInfo()
        return None

    country_filter = aliases.get(country_hint, country_hint) if country_hint else None

    geom = _query_geom("FAO/GAUL/2015/level0", "ADM0_NAME", candidates)
    if geom is None:
        geom = _query_geom("FAO/GAUL/2015/level1", "ADM1_NAME", candidates, country_filter=country_filter)
    if geom is None:
        geom = _query_geom("FAO/GAUL/2015/level2", "ADM2_NAME", candidates, country_filter=country_filter)
    if geom is None:
        raise RuntimeError(f"GEE GAUL boundary not found for: {study_area}")

    gdf = gpd.GeoDataFrame({"name": [study_area]}, geometry=[shape(geom)], crs="EPSG:4326")
    local_shp = _save_gdf_as_shp(gdf, workspace=workspace, boundary_filename=boundary_filename)
    gdf_loaded, bbox = _load_gdf_and_bbox(local_shp)
    return BoundaryResult(gdf=gdf_loaded, bbox=bbox, boundary_source="gee", boundary_path=local_shp)


def _resolver_chain(in_china: bool) -> list[tuple[str, Callable[[str, Path, str], BoundaryResult]]]:
    if in_china:
        return [("amap", _resolve_via_amap), ("osm", _resolve_via_osm), ("gee", _resolve_via_gee)]
    return [("osm", _resolve_via_osm), ("amap", _resolve_via_amap), ("gee", _resolve_via_gee)]


def resolve_boundary(
    study_area: str,
    workspace: Path,
    is_in_china: bool | None = None,
) -> BoundaryResult:
    _ = get_env_or_dotenv("amap_api_key")
    in_china = guess_is_in_china(study_area, is_in_china=is_in_china)
    boundary_filename = _safe_boundary_filename(study_area)

    errors: list[str] = []
    for source, resolver in _resolver_chain(in_china):
        try:
            return resolver(study_area, workspace, boundary_filename)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")

    raise RuntimeError(f"Boundary resolve failed for '{study_area}'. attempts={'; '.join(errors)}")
