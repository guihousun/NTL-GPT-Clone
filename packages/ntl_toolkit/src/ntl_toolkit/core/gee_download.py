from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ntl_toolkit.runtime.downloads import DownloadProgress, resolve_download_output, sanitize_download_text
from ntl_toolkit.schemas import OutputArtifact, ToolError, ToolResult


class GeeDownloadRequest(BaseModel):
    dataset_id: str
    band: str
    start_date: date
    end_date: date
    bbox: tuple[float, float, float, float]
    output: str
    reducer: Literal["first", "mean", "median", "mosaic"] = "first"
    scale: int = Field(default=500, ge=1, le=10000)
    crs: str = "EPSG:4326"
    project: str | None = None


def validate_gee_request(request: GeeDownloadRequest) -> None:
    if not request.dataset_id.strip():
        raise ValueError("dataset_id must not be empty")
    if not request.band.strip():
        raise ValueError("band must not be empty")
    if request.end_date < request.start_date:
        raise ValueError("end_date must be on or after start_date")
    minx, miny, maxx, maxy = request.bbox
    if not -180 <= minx < maxx <= 180:
        raise ValueError("bbox longitudes must satisfy -180 <= minx < maxx <= 180")
    if not -90 <= miny < maxy <= 90:
        raise ValueError("bbox latitude values must satisfy -90 <= miny < maxy <= 90")
    if not request.output.strip():
        raise ValueError("output must not be empty")
    if not request.crs.strip():
        raise ValueError("crs must not be empty")


def download_gee_raster(
    request: GeeDownloadRequest,
    *,
    progress: DownloadProgress | None = None,
) -> ToolResult:
    """Export one explicit GEE image or collection reduction without OAuth."""
    try:
        validate_gee_request(request)
    except ValueError as exc:
        return _failed("INVALID_PARAMETER", str(exc), "Correct the request and retry.")

    _report(progress, 0, 4, "initializing Earth Engine")
    try:
        ee = _initialize_ee(request.project)
    except Exception as exc:  # noqa: BLE001 - package the local setup failure
        return _failed(
            "GEE_NOT_INITIALIZED",
            sanitize_download_text(str(exc) or "Earth Engine initialization failed."),
            "Use EasyGEE to inspect the local Earth Engine setup and authorize it, then retry.",
        )

    try:
        _report(progress, 1, 4, "selecting imagery")
        image = _materialize_image(ee, request)
        output = resolve_download_output(request.output, Path.cwd())
        _report(progress, 2, 4, "exporting GeoTIFF")
        _export_image(image, request, output)
        _report(progress, 3, 4, "validating output")
        _validate_geotiff(output)
        _report(progress, 4, 4, "completed")
        return ToolResult.succeeded(
            tool="download_gee_raster",
            summary="Downloaded GEE raster.",
            outputs=[OutputArtifact(path=str(output), media_type="image/tiff")],
            metrics={
                "dataset_id": request.dataset_id,
                "band": request.band,
                "start_date": request.start_date.isoformat(),
                "end_date": request.end_date.isoformat(),
                "reducer": request.reducer,
            },
        )
    except Exception as exc:  # noqa: BLE001 - preserve a structured MCP error
        return _failed(
            "GEE_DOWNLOAD_FAILED",
            sanitize_download_text(str(exc) or type(exc).__name__),
            "Inspect the AOI, date window, output path, and GEE request-size limits before retrying.",
        )


def _initialize_ee(project: str | None):
    import ee

    if project:
        ee.Initialize(project=project)
    else:
        ee.Initialize()
    return ee


def _materialize_image(ee, request: GeeDownloadRequest):
    geometry = ee.Geometry.Rectangle(list(request.bbox))
    end_exclusive = request.end_date + timedelta(days=1)
    collection = (
        ee.ImageCollection(request.dataset_id)
        .filterDate(request.start_date.isoformat(), end_exclusive.isoformat())
        .filterBounds(geometry)
        .select(request.band)
    )
    if int(collection.size().getInfo()) <= 0:
        raise ValueError("No images found for the requested dataset, dates, and AOI.")
    if request.reducer == "first":
        return collection.first()
    return getattr(collection, request.reducer)()


def _export_image(image, request: GeeDownloadRequest, output: Path) -> Path:
    import ee
    import geemap

    geemap.ee_export_image(
        ee_object=image,
        filename=str(output),
        scale=request.scale,
        region=ee.Geometry.Rectangle(list(request.bbox)),
        crs=request.crs,
        file_per_band=False,
    )
    return output


def _validate_geotiff(path: Path) -> None:
    import rasterio

    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"GEE export did not create a non-empty GeoTIFF: {path}")
    with rasterio.open(path) as dataset:
        if dataset.count < 1 or dataset.width < 1 or dataset.height < 1 or dataset.crs is None:
            raise ValueError(f"GEE export is not a valid projected GeoTIFF: {path}")


def _report(progress: DownloadProgress | None, current: float, total: float, message: str) -> None:
    if progress is not None:
        progress(float(current), float(total), message)


def _failed(code: str, message: str, suggestion: str) -> ToolResult:
    return ToolResult.failed(
        tool="download_gee_raster",
        error=ToolError(code=code, message=message, suggestion=suggestion),
    )
