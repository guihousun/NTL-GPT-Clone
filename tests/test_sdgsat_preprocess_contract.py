from __future__ import annotations

from pathlib import Path

import numpy as np
from osgeo import gdal

from storage_manager import current_thread_id, storage_manager
from tools.NTL_preprocess import calibrate_rgb_from_calib_file
from tools.SDGSAT1_INDEX import classify_jia_light_from_rgb_tif


def _write_rgb(path: Path) -> None:
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 2, 2, 3, gdal.GDT_Float32)
    assert dataset is not None
    dataset.SetGeoTransform((120.0, 0.01, 0.0, 31.0, 0.0, -0.01))
    dataset.SetProjection("EPSG:4326")
    values = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    for index in range(1, 4):
        dataset.GetRasterBand(index).WriteArray(values)
    dataset.FlushCache()
    dataset = None


def _write_jia_rgb(path: Path) -> np.ndarray:
    """Write the compact Jia-threshold fixture and return its expected classes."""

    rrli = np.array(
        [
            [0.2, 10.0, 0.4, 9.0, 9.0, 10.0],
            [0.1, 12.0, 0.5, 8.0, 1.0, 2.0],
            [0.3, 9.5, 0.2, 5.0, 0.6, np.nan],
            [0.2, 0.4, 10.1, 8.5, 0.7, np.nan],
        ],
        dtype=np.float32,
    )
    rbli = np.array(
        [
            [0.8, 0.1, 0.3, 0.58, 0.57, 0.9],
            [0.6, 0.2, 0.4, 0.7, 0.1, 0.59],
            [0.9, 0.56, 0.2, 0.58, 0.57, np.nan],
            [0.3, 0.8, 0.2, 0.1, 0.6, np.nan],
        ],
        dtype=np.float32,
    )
    green = np.full(rrli.shape, 10.0, dtype=np.float32)
    red = rrli * green
    blue = rbli * green
    invalid = ~np.isfinite(rrli) | ~np.isfinite(rbli)
    for array in (red, green, blue):
        array[invalid] = -9999.0

    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 6, 4, 3, gdal.GDT_Float32)
    assert dataset is not None
    dataset.SetGeoTransform((120.0, 0.01, 0.0, 31.0, 0.0, -0.01))
    dataset.SetProjection("EPSG:4326")
    for index, array in enumerate((red, green, blue), start=1):
        band = dataset.GetRasterBand(index)
        band.WriteArray(array)
        band.SetNoDataValue(-9999.0)
    dataset.FlushCache()
    dataset = None

    return np.array(
        [
            [1, 2, 3, 1, 3, 2],
            [1, 2, 3, 1, 3, 1],
            [1, 2, 3, 1, 3, 255],
            [3, 1, 2, 3, 1, 255],
        ],
        dtype=np.uint8,
    )


def test_sdgsat_calibration_writes_declared_nodata_for_invalid_source_pixels(
    tmp_path: Path, monkeypatch
) -> None:
    """A source background/invalid pixel must not be emitted as zero radiance."""

    thread_id = "sdgsat-calibration"
    monkeypatch.setattr(storage_manager, "base_dir", tmp_path)
    token = current_thread_id.set(thread_id)
    try:
        workspace = tmp_path / thread_id
        inputs = workspace / "inputs"
        inputs.mkdir(parents=True)
        source = inputs / "raw_rgb.tif"
        _write_rgb(source)

        result = calibrate_rgb_from_calib_file(
            "raw_rgb.tif", "calibrated_rgb.tif", "calibrated_gray.tif"
        )

        assert result.startswith("Calibration completed")
        rgb = gdal.Open(str(workspace / "outputs" / "calibrated_rgb.tif"))
        gray = gdal.Open(str(workspace / "outputs" / "calibrated_gray.tif"))
        assert rgb is not None and gray is not None
        for index in range(1, 4):
            band = rgb.GetRasterBand(index)
            assert band.GetNoDataValue() == -9999.0
            assert band.ReadAsArray()[0, 0] == -9999.0
        gray_band = gray.GetRasterBand(1)
        assert gray_band.GetNoDataValue() == -9999.0
        assert gray_band.ReadAsArray()[0, 0] == -9999.0
        assert rgb.GetRasterBand(1).ReadAsArray()[0, 1] > 0.0
    finally:
        current_thread_id.reset(token)


def test_jia_light_classification_uses_fixed_thresholds_and_rled_first_order(
    tmp_path: Path, monkeypatch
) -> None:
    """The cited method must not be left to model-authored threshold code."""

    thread_id = "sdgsat-jia-light"
    monkeypatch.setattr(storage_manager, "base_dir", tmp_path)
    token = current_thread_id.set(thread_id)
    try:
        inputs = tmp_path / thread_id / "inputs"
        inputs.mkdir(parents=True)
        expected = _write_jia_rgb(inputs / "rgb.tif")

        result = classify_jia_light_from_rgb_tif(
            "rgb.tif", "rrli.tif", "rbli.tif", "light_class.tif"
        )

        assert "RLED if RRLI>9" in result
        assert "otherwise WLED if RBLI>0.57" in result
        workspace = tmp_path / thread_id / "outputs"
        classified = gdal.Open(str(workspace / "light_class.tif"))
        rrli = gdal.Open(str(workspace / "rrli.tif"))
        rbli = gdal.Open(str(workspace / "rbli.tif"))
        assert classified is not None and rrli is not None and rbli is not None
        class_band = classified.GetRasterBand(1)
        observed = class_band.ReadAsArray()
        assert class_band.GetNoDataValue() == 255
        np.testing.assert_array_equal(observed, expected)
        assert int(np.count_nonzero(observed == 1)) == 9
        assert int(np.count_nonzero(observed == 2)) == 5
        assert int(np.count_nonzero(observed == 3)) == 8
        assert int(np.count_nonzero(observed == 255)) == 2
        valid = observed != 255
        np.testing.assert_allclose(rrli.GetRasterBand(1).ReadAsArray()[valid], np.array(
            [0.2, 10.0, 0.4, 9.0, 9.0, 10.0, 0.1, 12.0, 0.5, 8.0, 1.0, 2.0,
             0.3, 9.5, 0.2, 5.0, 0.6, 0.2, 0.4, 10.1, 8.5, 0.7], dtype=np.float32
        ))
        np.testing.assert_allclose(rbli.GetRasterBand(1).ReadAsArray()[valid], np.array(
            [0.8, 0.1, 0.3, 0.58, 0.57, 0.9, 0.6, 0.2, 0.4, 0.7, 0.1, 0.59,
             0.9, 0.56, 0.2, 0.58, 0.57, 0.3, 0.8, 0.2, 0.1, 0.6], dtype=np.float32
        ))
    finally:
        current_thread_id.reset(token)


def test_jia_light_classification_propagates_nonpositive_green_nodata_and_nonfinite(
    tmp_path: Path, monkeypatch
) -> None:
    """Undefined source pixels must remain NoData in every Jia output."""

    thread_id = "sdgsat-jia-invalid"
    monkeypatch.setattr(storage_manager, "base_dir", tmp_path)
    token = current_thread_id.set(thread_id)
    try:
        inputs = tmp_path / thread_id / "inputs"
        inputs.mkdir(parents=True)

        red = np.array([[1.0, 20.0, 1.0], [1.0, -9999.0, np.nan]], dtype=np.float32)
        green = np.array([[1.0, 0.0, -1.0], [2.0, 10.0, 2.0]], dtype=np.float32)
        blue = np.array([[1.0, 1.0, 1.0], [2.0, 10.0, 2.0]], dtype=np.float32)
        source = inputs / "rgb_invalid.tif"
        dataset = gdal.GetDriverByName("GTiff").Create(str(source), 3, 2, 3, gdal.GDT_Float32)
        assert dataset is not None
        for index, array in enumerate((red, green, blue), start=1):
            band = dataset.GetRasterBand(index)
            band.WriteArray(array)
            band.SetNoDataValue(-9999.0)
        dataset.FlushCache()
        dataset = None

        result = classify_jia_light_from_rgb_tif(
            "rgb_invalid.tif", "rrli_invalid.tif", "rbli_invalid.tif", "light_class_invalid.tif"
        )

        assert result.startswith("Jia et al. (2024) light classification completed")
        outputs = tmp_path / thread_id / "outputs"
        classified = gdal.Open(str(outputs / "light_class_invalid.tif"))
        rrli = gdal.Open(str(outputs / "rrli_invalid.tif"))
        rbli = gdal.Open(str(outputs / "rbli_invalid.tif"))
        assert classified is not None and rrli is not None and rbli is not None

        observed = classified.GetRasterBand(1).ReadAsArray()
        expected = np.array([[1, 255, 255], [1, 255, 255]], dtype=np.uint8)
        np.testing.assert_array_equal(observed, expected)
        assert classified.GetRasterBand(1).GetNoDataValue() == 255

        invalid = expected == 255
        rrli_band = rrli.GetRasterBand(1)
        rbli_band = rbli.GetRasterBand(1)
        assert rrli_band.GetNoDataValue() == -9999.0
        assert rbli_band.GetNoDataValue() == -9999.0
        np.testing.assert_array_equal(rrli_band.ReadAsArray()[invalid], -9999.0)
        np.testing.assert_array_equal(rbli_band.ReadAsArray()[invalid], -9999.0)
    finally:
        current_thread_id.reset(token)
