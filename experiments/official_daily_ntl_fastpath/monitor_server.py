from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

WEB_ROOT = Path(__file__).resolve().parent / "web_ui"
DEFAULT_WORKSPACE = Path(__file__).resolve().parent / "workspace_monitor"

GIBS_LAYERS = [
    {
        "id": "VIIRS_NOAA20_DayNightBand",
        "label": "NOAA20 DayNightBand (NRT)",
        "matrix_set": "GoogleMapsCompatible_Level7",
        "format": "jpg",
    },
    {
        "id": "VIIRS_SNPP_DayNightBand",
        "label": "SNPP DayNightBand (NRT)",
        "matrix_set": "GoogleMapsCompatible_Level7",
        "format": "jpg",
    },
    {
        "id": "VIIRS_NOAA21_DayNightBand",
        "label": "NOAA21 DayNightBand",
        "matrix_set": "GoogleMapsCompatible_Level7",
        "format": "jpg",
    },
]


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minx,miny,maxx,maxy")
    values = [float(p) for p in parts]
    minx, miny, maxx, maxy = values
    if maxx < minx or maxy < miny:
        raise ValueError("bbox max must be >= min")
    return float(minx), float(miny), float(maxx), float(maxy)


def _lag_days(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        day = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.now(UTC).date() - day).days


def _get_param(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = params.get(key)
    if not values:
        return default
    return values[0]


def _build_gibs_snapshot_url(
    layer_id: str,
    date_str: str,
    bbox: tuple[float, float, float, float],
    snapshot_px: int,
) -> str:
    minx, miny, maxx, maxy = bbox
    bbox_wms = f"{miny},{minx},{maxy},{maxx}"
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetMap",
        "VERSION": "1.3.0",
        "LAYERS": layer_id,
        "STYLES": "",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
        "HEIGHT": str(snapshot_px),
        "WIDTH": str(snapshot_px),
        "CRS": "EPSG:4326",
        "BBOX": bbox_wms,
        "TIME": date_str,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?{query}"


def _validate_snapshot_request(query: dict[str, list[str]]) -> tuple[str, str, tuple[float, float, float, float], int]:
    allowed_layers = {x["id"] for x in GIBS_LAYERS}
    layer_id = _get_param(query, "layer", "") or ""
    if layer_id not in allowed_layers:
        raise ValueError(f"unsupported layer: {layer_id}")

    date_str = _get_param(query, "date", "") or ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise ValueError("date must be YYYY-MM-DD")

    bbox = _parse_bbox(_get_param(query, "bbox"))
    if bbox is None:
        raise ValueError("bbox required as minx,miny,maxx,maxy")

    snapshot_raw = _get_param(query, "snapshot_px", "2048") or "2048"
    snapshot_px = int(snapshot_raw)
    snapshot_px = max(256, min(4096, snapshot_px))
    return layer_id, date_str, bbox, snapshot_px


def _fetch_snapshot_png(layer_id: str, date_str: str, bbox: tuple[float, float, float, float], snapshot_px: int) -> bytes:
    url = _build_gibs_snapshot_url(layer_id=layer_id, date_str=date_str, bbox=bbox, snapshot_px=snapshot_px)
    req = Request(url, headers={"User-Agent": "NTL-Fast-Monitor/1.0"})
    with urlopen(req, timeout=90) as resp:  # noqa: S310
        data = resp.read()
        content_type = str(resp.headers.get("Content-Type", ""))
    if not data:
        raise ValueError("empty snapshot response from GIBS")
    if "image" not in content_type.lower():
        raise ValueError(f"unexpected content-type: {content_type}")
    return data


def _latest_window_dates(days: int) -> tuple[str, str]:
    now_utc = datetime.now(UTC)
    start_date = (now_utc.date() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = now_utc.date().strftime("%Y-%m-%d")
    return start_date, end_date


def _parse_iso_date(value: str, *, field: str) -> str:
    raw = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    return raw


def _parse_download_date_range(query: dict[str, list[str]]) -> tuple[str, str]:
    legacy_date = (_get_param(query, "date", "") or "").strip()
    start_raw = (_get_param(query, "start_date", "") or "").strip()
    end_raw = (_get_param(query, "end_date", "") or "").strip()

    if legacy_date and not start_raw and not end_raw:
        day = _parse_iso_date(legacy_date, field="date")
        return day, day

    if start_raw and not end_raw:
        day = _parse_iso_date(start_raw, field="start_date")
        return day, day
    if end_raw and not start_raw:
        day = _parse_iso_date(end_raw, field="end_date")
        return day, day
    if not start_raw and not end_raw:
        today = datetime.now(UTC).date().strftime("%Y-%m-%d")
        return today, today

    start_date = _parse_iso_date(start_raw, field="start_date")
    end_date = _parse_iso_date(end_raw, field="end_date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    return start_date, end_date


def _read_file_bytes(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_bytes()


def _zip_files(file_paths: list[Path], out_zip: Path) -> Path:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in file_paths:
            zf.write(p, arcname=p.name)
    return out_zip


def build_latest_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from experiments.official_daily_ntl_fastpath.boundary_resolver import resolve_boundary
    from experiments.official_daily_ntl_fastpath.cmr_client import (
        build_cmr_query_url,
        latest_granule_day,
        search_granules,
    )
    from experiments.official_daily_ntl_fastpath.source_registry import (
        get_nrt_priority_sources,
        get_source_spec,
        parse_sources_arg,
    )
    from experiments.official_daily_ntl_fastpath.gee_baseline import (
        DEFAULT_GEE_DAILY_DATASET,
        query_gee_products_latest,
    )

    now_utc = datetime.now(UTC)
    days = int(_get_param(query, "days", "10") or "10")
    start_date = (now_utc.date() - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = now_utc.date().strftime("%Y-%m-%d")

    study_area = _get_param(query, "study_area")
    sources_raw = _get_param(query, "sources", "nrt_priority")
    sources = parse_sources_arg(sources_raw)

    bbox = _parse_bbox(_get_param(query, "bbox"))
    boundary_source = None
    if study_area and not bbox:
        boundary = resolve_boundary(study_area=study_area, workspace=DEFAULT_WORKSPACE)
        bbox = boundary.bbox
        boundary_source = boundary.boundary_source

    gee_rows, gee_query_error = query_gee_products_latest(bbox=bbox)
    default_gee_row = next((x for x in gee_rows if x.get("dataset_id") == DEFAULT_GEE_DAILY_DATASET), None)
    gee_latest_date = (
        (default_gee_row.get("latest_bbox_date") or default_gee_row.get("latest_global_date"))
        if default_gee_row
        else None
    )
    gee_error = default_gee_row.get("error") if default_gee_row else gee_query_error

    rows: list[dict[str, Any]] = []
    for source in sources:
        spec = get_source_spec(source)
        try:
            g_global = search_granules(
                short_name=spec.short_name,
                start_date=start_date,
                end_date=end_date,
                bbox=None,
                page_size=200,
            )
            latest_global = latest_granule_day(g_global, night_only=spec.night_only)
            count_global = len(g_global)
        except Exception as exc:  # noqa: BLE001
            latest_global = None
            count_global = 0
            rows.append(
                {
                    "source": source,
                    "error": str(exc),
                    "latest_global_date": None,
                    "latest_bbox_date": None,
                }
            )
            continue

        latest_bbox = None
        count_bbox = None
        if bbox is not None:
            g_bbox = search_granules(
                short_name=spec.short_name,
                start_date=start_date,
                end_date=end_date,
                bbox=bbox,
                page_size=200,
            )
            latest_bbox = latest_granule_day(g_bbox, night_only=spec.night_only)
            count_bbox = len(g_bbox)

        rows.append(
            {
                "source": source,
                "processing_mode": spec.processing_mode,
                "night_only": spec.night_only,
                "latest_global_date": latest_global,
                "latest_global_lag_days": _lag_days(latest_global),
                "latest_bbox_date": latest_bbox,
                "latest_bbox_lag_days": _lag_days(latest_bbox),
                "granule_count_global": count_global,
                "granule_count_bbox": count_bbox,
                "cmr_query_global": build_cmr_query_url(
                    short_name=spec.short_name,
                    start_date=start_date,
                    end_date=end_date,
                    bbox=None,
                    page_size=200,
                    descending=True,
                ),
                "cmr_query_bbox": (
                    build_cmr_query_url(
                        short_name=spec.short_name,
                        start_date=start_date,
                        end_date=end_date,
                        bbox=bbox,
                        page_size=200,
                        descending=True,
                    )
                    if bbox is not None
                    else None
                ),
            }
        )

    return {
        "generated_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "start_date": start_date,
        "end_date": end_date,
        "study_area": study_area,
        "boundary_source": boundary_source,
        "bbox": bbox,
        "sources_requested": sources,
        "sources_default_nrt_priority": get_nrt_priority_sources(),
        "gee_dataset": DEFAULT_GEE_DAILY_DATASET,
        "gee_latest_date": gee_latest_date,
        "gee_latest_lag_days": _lag_days(gee_latest_date),
        "gee_error": gee_error,
        "gee_rows": [
            {
                **x,
                "latest_global_lag_days": _lag_days(x.get("latest_global_date")),
                "latest_bbox_lag_days": _lag_days(x.get("latest_bbox_date")),
            }
            for x in gee_rows
        ],
        "rows": rows,
        "gibs_layers": GIBS_LAYERS,
    }


def build_orbit_feed_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from experiments.official_daily_ntl_fastpath.orbit_service import build_orbit_feed

    force_raw = (_get_param(query, "force_refresh", "0") or "0").strip().lower()
    ttl_raw = (_get_param(query, "ttl_minutes", "180") or "180").strip()
    force_refresh = force_raw in {"1", "true", "yes", "y"}
    ttl_minutes = max(10, min(1440, int(ttl_raw)))
    return build_orbit_feed(
        workspace=DEFAULT_WORKSPACE,
        force_refresh=force_refresh,
        ttl_minutes=ttl_minutes,
    )


def build_download_data(
    query: dict[str, list[str]],
) -> tuple[bytes, str, str]:
    from experiments.official_daily_ntl_fastpath.boundary_resolver import resolve_boundary

    provider = (_get_param(query, "provider", "gee") or "gee").strip().lower()
    study_area = _get_param(query, "study_area")
    bbox = _parse_bbox(_get_param(query, "bbox"))
    boundary_source = None
    if study_area and not bbox:
        boundary = resolve_boundary(study_area=study_area, workspace=DEFAULT_WORKSPACE)
        bbox = boundary.bbox
        boundary_source = boundary.boundary_source
    if bbox is None:
        raise ValueError("study_area or bbox is required")

    if provider == "gee":
        from experiments.official_daily_ntl_fastpath.download_gee_daily_ntl import (
            DEFAULT_GEE_DATASET_BY_TEMPORAL,
            download_gee_ntl,
            infer_temporal_resolution,
            periods_from_date_range,
        )
        from experiments.official_daily_ntl_fastpath.gee_baseline import DEFAULT_GEE_PROJECT

        start_date, end_date = _parse_download_date_range(query)
        default_dataset = DEFAULT_GEE_DATASET_BY_TEMPORAL["daily"]
        dataset = (_get_param(query, "source", default_dataset) or default_dataset).strip()
        temporal = infer_temporal_resolution(dataset)
        periods = periods_from_date_range(
            temporal_resolution=temporal,
            start_date=start_date,
            end_date=end_date,
        )
        if len(periods) > 90:
            raise ValueError("GEE download range is too large (> 90 periods). Please narrow the date range.")
        band = (_get_param(query, "band") or "").strip() or None
        scale_raw = _get_param(query, "scale", "500") or "500"
        scale = max(30, min(5000, int(scale_raw)))

        tif_paths: list[Path] = []
        for period in periods:
            result = download_gee_ntl(
                bbox=bbox,
                dataset=dataset,
                temporal_resolution=temporal,
                period=period,
                workspace=DEFAULT_WORKSPACE,
                gee_project=DEFAULT_GEE_PROJECT,
                band=band,
                scale=scale,
                region_name=study_area or "bbox",
            )
            tif_paths.append(Path(str(result["output_tif"])))

        if len(tif_paths) == 1:
            tif_path = tif_paths[0]
            return _read_file_bytes(tif_path), "image/tiff", tif_path.name

        safe_dataset = dataset.replace("/", "_")
        zip_name = f"{safe_dataset}_{start_date}_to_{end_date}.zip"
        zip_path = _zip_files(
            tif_paths,
            out_zip=DEFAULT_WORKSPACE / "downloads" / "gee" / safe_dataset / zip_name,
        )
        return _read_file_bytes(zip_path), "application/zip", zip_path.name

    if provider != "official":
        raise ValueError("provider must be gee or official")

    from experiments.official_daily_ntl_fastpath.cmr_client import (
        download_file_with_curl,
        extract_download_link,
        group_granules_by_day,
        resolve_token,
        search_granules,
    )
    from experiments.official_daily_ntl_fastpath.gridded_pipeline import process_gridded_day
    from experiments.official_daily_ntl_fastpath.source_registry import get_source_spec

    source = (_get_param(query, "source", "") or "").strip().upper()
    output_format = (_get_param(query, "format", "raw_h5") or "raw_h5").strip().lower()
    if output_format not in {"raw_h5", "clipped_tif"}:
        raise ValueError("format must be raw_h5 or clipped_tif")
    if not source:
        raise ValueError("source is required")

    start_date, end_date = _parse_download_date_range(query)

    spec = get_source_spec(source)
    granules = search_granules(
        short_name=spec.short_name,
        start_date=start_date,
        end_date=end_date,
        bbox=bbox,
        page_size=200,
    )
    groups = group_granules_by_day(granules, night_only=spec.night_only)
    selected_days = sorted(groups.keys())
    if not selected_days:
        raise ValueError(f"no granules found for {source} in {start_date}..{end_date}")
    if len(selected_days) > 31:
        raise ValueError("Official source range is too large (> 31 days). Please narrow the date range.")

    token = resolve_token("EARTHDATA_TOKEN")
    if not token:
        raise ValueError("EARTHDATA_TOKEN missing")

    if output_format == "raw_h5":
        downloaded: list[Path] = []
        failed: list[str] = []
        for day in selected_days:
            entries = groups.get(day, [])
            raw_dir = DEFAULT_WORKSPACE / "downloads" / "raw" / source / day
            for idx, entry in enumerate(entries, start=1):
                link = extract_download_link(entry.links)
                if not link:
                    failed.append(f"{day}#{idx}:missing_download_link")
                    continue
                filename = Path(link.split("?")[0]).name or f"{source}_{day}_{idx}.h5"
                dst = raw_dir / filename
                ok, err = download_file_with_curl(link, dst, earthdata_token=token)
                if not ok:
                    failed.append(f"{day}#{idx}:{err}")
                    continue
                downloaded.append(dst)
        if not downloaded:
            preview = " | ".join(failed[:3]) if failed else "no downloadable file in selected granules range"
            raise RuntimeError(
                f"no downloadable file in selected granules range; failed={len(failed)}; detail={preview}"
            )

        if len(downloaded) == 1:
            data = _read_file_bytes(downloaded[0])
            return data, "application/octet-stream", downloaded[0].name

        zip_path = _zip_files(
            downloaded,
            out_zip=DEFAULT_WORKSPACE
            / "downloads"
            / "raw"
            / source
            / f"{source}_{selected_days[0]}_to_{selected_days[-1]}_raw.zip",
        )
        return _read_file_bytes(zip_path), "application/zip", zip_path.name

    if spec.processing_mode != "gridded_tile_clip":
        raise ValueError(f"{source} is feasibility_only and cannot export clipped_tif in this round")

    boundary = resolve_boundary(study_area=study_area or "", workspace=DEFAULT_WORKSPACE) if boundary_source else None
    if boundary is None:
        from types import SimpleNamespace

        from shapely.geometry import box
        import geopandas as gpd

        minx, miny, maxx, maxy = bbox
        gdf = gpd.GeoDataFrame(geometry=[box(minx, miny, maxx, maxy)], crs="EPSG:4326")
        boundary = SimpleNamespace(gdf=gdf)

    tif_paths: list[Path] = []
    failed_days: list[str] = []
    for day in selected_days:
        entries = groups.get(day, [])
        result = process_gridded_day(
            source=source,
            day=day,
            entries=entries,
            variable_candidates=spec.variable_candidates,
            roi_gdf=boundary.gdf,
            workspace=DEFAULT_WORKSPACE,
            earthdata_token=token,
        )
        if result.get("status") == "ok" and result.get("output_path"):
            tif_paths.append(Path(str(result["output_path"])))
        else:
            failed_days.append(day)

    if not tif_paths:
        raise RuntimeError(f"clipped_tif failed for all requested days: {', '.join(failed_days)}")
    if len(tif_paths) == 1:
        tif_path = tif_paths[0]
        return _read_file_bytes(tif_path), "image/tiff", tif_path.name

    zip_path = _zip_files(
        tif_paths,
        out_zip=DEFAULT_WORKSPACE
        / "downloads"
        / "clipped"
        / source
        / f"{source}_{selected_days[0]}_to_{selected_days[-1]}_clipped.zip",
    )
    return _read_file_bytes(zip_path), "application/zip", zip_path.name


class MonitorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        filename: str | None = None,
        status: int = 200,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "ts_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})
            return
        if parsed.path == "/api/study_areas":
            try:
                query = parse_qs(parsed.query)
                country = (_get_param(query, "country", "") or "").strip() or None
                province = (_get_param(query, "province", "") or "").strip() or None
                limit_raw = _get_param(query, "limit", "2000") or "2000"
                limit = max(10, min(10000, int(limit_raw)))
                from experiments.official_daily_ntl_fastpath.study_area_catalog import get_study_area_catalog

                payload = get_study_area_catalog(country=country, province=province, limit=limit)
                self._send_json(payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/latest":
            try:
                payload = build_latest_payload(parse_qs(parsed.query))
                self._send_json(payload)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/orbit_feed":
            try:
                payload = build_orbit_feed_payload(parse_qs(parsed.query))
                self._send_json(payload)
            except RuntimeError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/download_snapshot":
            try:
                layer_id, date_str, bbox, snapshot_px = _validate_snapshot_request(parse_qs(parsed.query))
                png = _fetch_snapshot_png(layer_id=layer_id, date_str=date_str, bbox=bbox, snapshot_px=snapshot_px)
                filename = f"{layer_id}_{date_str}_{snapshot_px}px.png"
                self._send_bytes(png, content_type="image/png", filename=filename)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/download_data":
            try:
                payload, content_type, filename = build_download_data(parse_qs(parsed.query))
                self._send_bytes(payload, content_type=content_type, filename=filename)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve NTL fastpath monitoring UI and API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), MonitorHandler)
    print(f"http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
