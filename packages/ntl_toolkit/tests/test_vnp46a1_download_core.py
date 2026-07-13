from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio
from shapely.geometry import box


def _request(tmp_path: Path, **overrides):
    from ntl_toolkit.core.vnp46a1_download import Vnp46a1DownloadRequest

    values = {
        "start_date": "2020-01-02",
        "end_date": "2020-01-02",
        "output_root": str(tmp_path / "runs"),
        "bbox": [34.0, 29.0, 35.0, 30.0],
    }
    values.update(overrides)
    return Vnp46a1DownloadRequest(**values)


def _write_h5(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        handle.attrs["WestBoundingCoord"] = 34.0
        handle.attrs["EastBoundingCoord"] = 35.0
        handle.attrs["NorthBoundingCoord"] = 30.0
        handle.attrs["SouthBoundingCoord"] = 29.0
        group = handle.create_group("HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields")
        radiance = group.create_dataset(
            "DNB_At_Sensor_Radiance_500m",
            data=np.array([[10, 20], [65535, 40]], dtype="uint16"),
        )
        radiance.attrs["_FillValue"] = np.uint16(65535)
        radiance.attrs["scale_factor"] = 0.1
        radiance.attrs["add_offset"] = 0.0
        utc_time = group.create_dataset("UTC_Time", data=np.array([[18.0, 19.0], [-999.9, 20.0]], dtype="float32"))
        utc_time.attrs["_FillValue"] = -999.9


def test_request_requires_exactly_one_target_mode(tmp_path: Path) -> None:
    from ntl_toolkit.core.vnp46a1_download import Vnp46a1DownloadRequest

    with pytest.raises(ValueError, match="exactly one"):
        Vnp46a1DownloadRequest(
            start_date="2020-01-02",
            end_date="2020-01-02",
            output_root=str(tmp_path),
        )
    with pytest.raises(ValueError, match="exactly one"):
        _request(tmp_path, countries=["ISR"])


def test_bbox_target_id_is_stable_and_retry_safe(tmp_path: Path) -> None:
    request = _request(tmp_path)

    assert request.target_id.startswith("BBOX_")
    assert request.target_id == _request(tmp_path, bbox=[34, 29, 35, 30]).target_id
    assert request.validate_target(f"{request.target_id}:2020-01-02") == (request.target_id, "2020-01-02")
    with pytest.raises(ValueError, match="current request"):
        request.validate_target("ISR:2020-01-02")


def test_h5_conversion_applies_radiance_scale_and_optional_utc_time(tmp_path: Path) -> None:
    from ntl_toolkit.core.vnp46a1_download import h5_to_target_tifs

    h5_path = tmp_path / "VNP46A1.A2020002.h21v06.002.2020003000000.h5"
    _write_h5(h5_path)

    radiance_path, utc_path = h5_to_target_tifs(
        h5_path,
        tmp_path / "radiance.tif",
        target_geometry=box(34.0, 29.0, 35.0, 30.0),
        include_utc_time=True,
    )

    with rasterio.open(radiance_path) as dataset:
        values = dataset.read(1)
        assert dataset.crs.to_string() == "EPSG:4326"
        assert dataset.nodata == -9999.0
        assert values.tolist() == [[1.0, 2.0], [-9999.0, 4.0]]
        assert dataset.tags()["source_dataset"].endswith("DNB_At_Sensor_Radiance_500m")
    assert utc_path is not None
    with rasterio.open(utc_path) as dataset:
        assert dataset.read(1).tolist() == [[18.0, 19.0], [-9999.0, 20.0]]
        assert dataset.tags()["semantic_role"] == "acquisition_time_utc_hours"


def test_h5_conversion_can_skip_utc_time(tmp_path: Path) -> None:
    from ntl_toolkit.core.vnp46a1_download import h5_to_target_tifs

    h5_path = tmp_path / "sample.h5"
    _write_h5(h5_path)

    _radiance, utc_path = h5_to_target_tifs(
        h5_path,
        tmp_path / "radiance.tif",
        target_geometry=box(34.0, 29.0, 35.0, 30.0),
        include_utc_time=False,
    )

    assert utc_path is None


def test_plan_records_target_mode_and_utc_time(tmp_path: Path) -> None:
    from ntl_toolkit.core.vnp46a1_download import run_vnp46a1_download

    result = run_vnp46a1_download(_request(tmp_path, include_utc_time=True))

    assert result.status == "succeeded"
    assert result.tool == "download_vnp46a1_official_h5"
    assert result.metrics["target_mode"] == "bbox"
    assert result.metrics["include_utc_time"] is True
    assert result.metrics["short_name"] == "VNP46A1"
