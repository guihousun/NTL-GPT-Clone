from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.transform import from_origin
from shapely.geometry import mapping

from ntl_toolkit.schemas import ToolError, ToolResult

NODATA = -9999.0
_DATE_FORMAT = "%Y-%m-%d"
_RADIANCE_DATASET = "DNB_At_Sensor_Radiance_500m"
_UTC_TIME_DATASET = "UTC_Time"


@dataclass(frozen=True)
class Vnp46a1DownloadRequest:
    start_date: str
    end_date: str
    output_root: str
    countries: list[str] = field(default_factory=list)
    bbox: list[float] | tuple[float, float, float, float] | None = None
    include_utc_time: bool = False
    phase: Literal["full", "prepare", "download", "mosaic", "audit"] = "full"
    execution_mode: Literal["plan", "run"] = "plan"
    targets: list[str] = field(default_factory=list)
    workers: int = 4
    download_timeout: int = 600
    token_env: str = "EARTHDATA_TOKEN"
    force: bool = False

    def __post_init__(self) -> None:
        _parse_date(self.start_date, "start_date")
        _parse_date(self.end_date, "end_date")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        countries = sorted({str(value).strip().upper() for value in self.countries if str(value).strip()})
        normalized_bbox = _normalize_bbox(self.bbox) if self.bbox is not None else None
        if bool(countries) == bool(normalized_bbox):
            raise ValueError("exactly one of countries or bbox must be provided")
        if countries and any(len(value) != 3 or not value.isalpha() for value in countries):
            raise ValueError("countries must contain ISO3 codes")
        if not str(self.output_root).strip():
            raise ValueError("output_root must not be empty")
        if not 1 <= self.workers <= 8:
            raise ValueError("workers must be between 1 and 8")
        if not 60 <= self.download_timeout <= 1800:
            raise ValueError("download_timeout must be between 60 and 1800 seconds")
        if not self.token_env.isidentifier():
            raise ValueError("token_env must be an environment variable name")
        object.__setattr__(self, "countries", countries)
        object.__setattr__(self, "bbox", normalized_bbox)
        targets = sorted({str(value).strip().upper() for value in self.targets if str(value).strip()})
        for target in targets:
            self.validate_target(target)
        object.__setattr__(self, "targets", targets)

    @property
    def target_id(self) -> str:
        if self.countries:
            if len(self.countries) != 1:
                raise ValueError("VNP46A1 country mode currently accepts exactly one ISO3 country per run")
            return self.countries[0]
        assert self.bbox is not None
        encoded = ",".join(f"{value:.6f}" for value in self.bbox).encode("ascii")
        return f"BBOX_{hashlib.sha256(encoded).hexdigest()[:12].upper()}"

    @property
    def output_path(self) -> Path:
        return Path(self.output_root).expanduser().resolve(strict=False)

    @property
    def run_root(self) -> Path:
        return self.output_path / f"VNP46A1_at_sensor_{self.target_id}_{self.start_date}_to_{self.end_date}"

    @property
    def target_mode(self) -> str:
        return "country" if self.countries else "bbox"

    @property
    def phase_list(self) -> list[str]:
        return ["prepare", "download", "mosaic", "audit"] if self.phase == "full" else [self.phase]

    def validate_target(self, target: str) -> tuple[str, str]:
        try:
            target_id, day = target.rsplit(":", 1)
        except ValueError as exc:
            raise ValueError("targets must use TARGET_ID:YYYY-MM-DD") from exc
        if target_id != self.target_id:
            raise ValueError("retry target does not belong to the current request")
        _parse_date(day, "target date")
        return target_id, day


def h5_to_target_tifs(
    h5_path: str | Path,
    radiance_path: str | Path,
    *,
    target_geometry: Any,
    include_utc_time: bool,
) -> tuple[Path, Path | None]:
    """Convert one official VNP46A1 HDF5 file into clipped radiance and UTC rasters."""
    source = Path(h5_path)
    output = Path(radiance_path)
    with h5py.File(source, "r") as handle:
        root_attrs = {name: _as_scalar(value) for name, value in handle.attrs.items()}
        radiance_dataset_path, radiance_dataset = _find_dataset(handle, _RADIANCE_DATASET)
        transform = _geographic_transform(root_attrs, radiance_dataset.shape)
        radiance = _scaled_values(radiance_dataset)
        _write_clipped_tif(
            output,
            radiance,
            transform,
            target_geometry,
            tags={
                "source_h5": str(source),
                "source_dataset": radiance_dataset_path,
                "product": "VNP46A1",
                "semantic_role": "at_sensor_dnb_radiance",
            },
        )
        utc_output: Path | None = None
        if include_utc_time:
            utc_dataset_path, utc_dataset = _find_dataset(handle, _UTC_TIME_DATASET)
            utc_output = output.with_name(f"{output.stem}_UTC_Time{output.suffix}")
            _write_clipped_tif(
                utc_output,
                _scaled_values(utc_dataset),
                transform,
                target_geometry,
                tags={
                    "source_h5": str(source),
                    "source_dataset": utc_dataset_path,
                    "product": "VNP46A1",
                    "semantic_role": "acquisition_time_utc_hours",
                },
            )
    return output, utc_output


def run_vnp46a1_download(request: Vnp46a1DownloadRequest) -> ToolResult:
    """Plan the official VNP46A1 country or BBox pipeline before execution."""
    if request.execution_mode != "plan":
        return ToolResult.failed(
            tool="download_vnp46a1_official_h5",
            error=ToolError(
                code="VNP46A1_RUN_NOT_IMPLEMENTED",
                message="VNP46A1 run phases are not available yet.",
                suggestion="Use execution_mode='plan' while the local pipeline is being installed.",
            ),
        )
    return ToolResult.succeeded(
        tool="download_vnp46a1_official_h5",
        summary="Prepared VNP46A1 execution plan.",
        metrics={
            "short_name": "VNP46A1",
            "primary_dataset": _RADIANCE_DATASET,
            "target_mode": request.target_mode,
            "target_id": request.target_id,
            "include_utc_time": request.include_utc_time,
            "phases": request.phase_list,
            "run_root": str(request.run_root),
        },
    )


def _parse_date(value: str, name: str) -> None:
    try:
        datetime.strptime(value, _DATE_FORMAT)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def _normalize_bbox(value: list[float] | tuple[float, float, float, float] | None) -> tuple[float, float, float, float]:
    if value is None or len(value) != 4:
        raise ValueError("bbox must contain minx, miny, maxx, maxy")
    minx, miny, maxx, maxy = (float(item) for item in value)
    if not -180 <= minx < maxx <= 180 or not -90 <= miny < maxy <= 90:
        raise ValueError("bbox must be a valid WGS84 extent")
    return minx, miny, maxx, maxy


def _find_dataset(handle: h5py.File, dataset_name: str) -> tuple[str, h5py.Dataset]:
    matches: list[str] = []

    def collect(name: str, value: Any) -> None:
        if isinstance(value, h5py.Dataset) and name.replace("-", "_").endswith(dataset_name):
            matches.append(name)

    handle.visititems(collect)
    if not matches:
        raise KeyError(f"{dataset_name} not found in {handle.filename}")
    selected = matches[0]
    return selected, handle[selected]


def _as_scalar(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.ravel()[0].item() if value.size else None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _geographic_transform(attrs: dict[str, Any], shape: tuple[int, ...]):
    try:
        west = float(attrs["WestBoundingCoord"])
        east = float(attrs["EastBoundingCoord"])
        north = float(attrs["NorthBoundingCoord"])
        south = float(attrs["SouthBoundingCoord"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("VNP46A1 HDF5 lacks geographic tile bounding metadata") from exc
    height, width = shape[-2:]
    if east <= west or north <= south:
        raise ValueError("VNP46A1 HDF5 has invalid geographic tile bounds")
    return from_origin(west, north, (east - west) / width, (north - south) / height)


def _scaled_values(dataset: h5py.Dataset) -> np.ndarray:
    values = dataset[()].astype("float32")
    attrs = {name: _as_scalar(value) for name, value in dataset.attrs.items()}
    fill = float(attrs.get("_FillValue", attrs.get("FillValue", NODATA)))
    scale = float(attrs.get("scale_factor", attrs.get("ScaleFactor", 1.0)))
    offset = float(attrs.get("add_offset", attrs.get("Offset", 0.0)))
    values[values == fill] = np.nan
    values = values * scale + offset
    values[~np.isfinite(values)] = NODATA
    return values


def _write_clipped_tif(path: Path, values: np.ndarray, transform, target_geometry: Any, *, tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"_{path.name}")
    profile = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": NODATA,
    }
    try:
        with rasterio.open(temporary, "w", **profile) as dataset:
            dataset.write(values, 1)
        with rasterio.open(temporary) as dataset:
            clipped, clipped_transform = mask(dataset, [mapping(target_geometry)], crop=True, nodata=NODATA, filled=True)
            clipped_profile = dataset.profile.copy()
        clipped_profile.update(height=clipped.shape[1], width=clipped.shape[2], transform=clipped_transform, compress="deflate")
        with rasterio.open(path, "w", **clipped_profile) as dataset:
            dataset.write(clipped)
            dataset.update_tags(**tags)
    finally:
        temporary.unlink(missing_ok=True)
