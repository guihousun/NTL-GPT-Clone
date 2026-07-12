from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ntl_toolkit.core import gee_download
from ntl_toolkit.core.gee_download import (
    GeeDownloadRequest,
    download_gee_raster,
    validate_gee_request,
)


class _FakeImage:
    def select(self, _band: str) -> "_FakeImage":
        return self

    def mean(self) -> "_FakeImage":
        return self

    def median(self) -> "_FakeImage":
        return self

    def mosaic(self) -> "_FakeImage":
        return self


class _FakeCollection:
    def filterDate(self, _start: str, _end: str) -> "_FakeCollection":
        return self

    def filterBounds(self, _geometry: object) -> "_FakeCollection":
        return self

    def select(self, _band: str) -> "_FakeCollection":
        return self

    def mean(self) -> _FakeImage:
        return _FakeImage()

    def median(self) -> _FakeImage:
        return _FakeImage()

    def mosaic(self) -> _FakeImage:
        return _FakeImage()

    def first(self) -> _FakeImage:
        return _FakeImage()

    def size(self) -> "_FakeCollection":
        return self

    def getInfo(self) -> int:
        return 1


class _FakeGeometry:
    @staticmethod
    def Rectangle(bounds: list[float]) -> tuple[str, tuple[float, ...]]:
        return "rectangle", tuple(bounds)


class _FakeEe:
    Geometry = _FakeGeometry

    @staticmethod
    def ImageCollection(_dataset_id: str) -> _FakeCollection:
        return _FakeCollection()


def _valid_request(tmp_path: Path) -> GeeDownloadRequest:
    return GeeDownloadRequest(
        dataset_id="NASA/VIIRS/002/VNP46A2",
        band="Gap_Filled_DNB_BRDF_Corrected_NTL",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 21),
        bbox=(34.0, 29.0, 35.0, 30.0),
        output=str(tmp_path / "export.tif"),
        reducer="mean",
    )


def _write_valid_tif(_image: object, _request: GeeDownloadRequest, output: Path) -> Path:
    with rasterio.open(
        output,
        "w",
        driver="GTiff",
        height=1,
        width=1,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(34.0, 30.0, 1.0, 1.0),
    ) as dataset:
        dataset.write(np.array([[1.0]], dtype=np.float32), 1)
    return output


def test_gee_request_rejects_reverse_dates(tmp_path: Path) -> None:
    request = GeeDownloadRequest(
        dataset_id="NASA/VIIRS/002/VNP46A2",
        band="Gap_Filled_DNB_BRDF_Corrected_NTL",
        start_date=date(2026, 4, 21),
        end_date=date(2026, 4, 20),
        bbox=(34.0, 29.0, 35.0, 30.0),
        output=str(tmp_path / "out.tif"),
    )

    with pytest.raises(ValueError, match="end_date"):
        validate_gee_request(request)


def test_gee_request_rejects_non_wgs84_bbox(tmp_path: Path) -> None:
    request = _valid_request(tmp_path).model_copy(update={"bbox": (34.0, 91.0, 35.0, 92.0)})

    with pytest.raises(ValueError, match="latitude"):
        validate_gee_request(request)


def test_gee_export_reports_all_phases_and_reserves_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[tuple[float, float | None, str]] = []
    request = _valid_request(tmp_path)
    Path(request.output).write_bytes(b"already-exists")
    monkeypatch.setattr(gee_download, "_initialize_ee", lambda _project: _FakeEe())
    monkeypatch.setattr(gee_download, "_export_image", _write_valid_tif)

    result = download_gee_raster(
        request,
        progress=lambda current, total, message: events.append((current, total, message)),
    )

    assert result.status == "succeeded"
    assert Path(result.outputs[0].path).name == "export_001.tif"
    assert [event[2] for event in events] == [
        "initializing Earth Engine",
        "selecting imagery",
        "exporting GeoTIFF",
        "validating output",
        "completed",
    ]


def test_gee_initialization_failure_is_structured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        gee_download,
        "_initialize_ee",
        lambda _project: (_ for _ in ()).throw(RuntimeError("credentials missing")),
    )

    result = download_gee_raster(_valid_request(tmp_path))

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "GEE_NOT_INITIALIZED"
    assert "EasyGEE" in result.error.suggestion
