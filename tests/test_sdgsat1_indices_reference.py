from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from osgeo import gdal, osr


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = RUNTIME_ROOT / "tools" / "SDGSAT1_INDEX.py"
NODATA = np.float32(-9999.0)


def _load_module():
    spec = importlib.util.spec_from_file_location("sdgsat1_index_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def index_module():
    return _load_module()


def _write_rgb_fixture(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r = np.array([[2.0, 0.0, NODATA], [1.0, np.nan, 2.0]], dtype=np.float32)
    g = np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 2.0]], dtype=np.float32)
    b = np.array([[0.5, 2.0, 1.0], [0.0, 1.0, 4.0]], dtype=np.float32)
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(path), 3, 2, 3, gdal.GDT_Float32)
    assert ds is not None
    ds.SetGeoTransform((500000.0, 10.0, 0.0, 3450000.0, 0.0, -10.0))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32651)
    ds.SetProjection(srs.ExportToWkt())
    for band_number, (array, description) in enumerate(
        zip((r, g, b), ("R_radiance", "G_radiance", "B_radiance")), start=1
    ):
        band = ds.GetRasterBand(band_number)
        band.WriteArray(array)
        band.SetNoDataValue(float(NODATA))
        band.SetDescription(description)
    ds.FlushCache()
    ds = None
    return r, g, b


def _read_output(path: Path) -> tuple[np.ndarray, float, str, tuple[float, ...], str]:
    ds = gdal.Open(str(path), gdal.GA_ReadOnly)
    assert ds is not None
    band = ds.GetRasterBand(1)
    array = band.ReadAsArray().astype(np.float32)
    nodata = float(band.GetNoDataValue())
    description = band.GetDescription()
    transform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    ds = None
    return array, nodata, description, transform, projection


def test_formula_helpers_preserve_declared_formulas_and_mask_undefined(index_module):
    r = np.array([2.0, 0.0, np.nan, np.inf], dtype=np.float32)
    g = np.array([1.0, 0.0, 1.0, 1.0], dtype=np.float32)
    b = np.array([0.5, 2.0, 1.0, 1.0], dtype=np.float32)

    np.testing.assert_allclose(index_module.compute_ndigr(g, r)[:1], [-1.0 / 3.0])
    np.testing.assert_allclose(index_module.compute_ndibg(b, g)[:2], [-1.0 / 3.0, 1.0])
    np.testing.assert_allclose(index_module.compute_rrli(r, g)[:1], [2.0])
    np.testing.assert_allclose(index_module.compute_rbli(b, g)[:1], [0.5])

    assert np.isnan(index_module.compute_ndigr(g, r)[1:]).all()
    assert np.isnan(index_module.compute_rrli(r, g)[1:]).all()
    assert np.isnan(index_module.compute_rbli(b, g)[1])


@pytest.mark.parametrize(
    ("index_type", "expected", "valid_count", "description"),
    [
        (
            "NDIGR",
            [[-1.0 / 3.0, NODATA, NODATA], [-1.0, NODATA, 0.0]],
            3,
            "NDIGR (Green - Red) / (Green + Red)",
        ),
        (
            "NDIBG",
            [[-1.0 / 3.0, 1.0, NODATA], [NODATA, NODATA, 1.0 / 3.0]],
            3,
            "NDIBG (Blue - Green) / (Blue + Green)",
        ),
        (
            "RRLI",
            [[2.0, NODATA, NODATA], [NODATA, NODATA, 1.0]],
            2,
            "RRLI (Red / Green)",
        ),
        (
            "RBLI",
            [[0.5, NODATA, NODATA], [NODATA, NODATA, 2.0]],
            2,
            "RBLI (Blue / Green)",
        ),
    ],
)
def test_tool_propagates_nodata_nonfinite_and_zero_denominators(
    tmp_path: Path,
    index_module,
    index_type: str,
    expected: list[list[float]],
    valid_count: int,
    description: str,
):
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    input_path = inputs / "calibrated_rgb.tif"
    output_path = outputs / f"{index_type.lower()}.tif"
    _write_rgb_fixture(input_path)

    with (
        patch.object(index_module.storage_manager, "resolve_input_path", return_value=str(input_path)),
        patch.object(index_module.storage_manager, "resolve_output_path", return_value=str(output_path)),
    ):
        response = index_module.compute_index_from_rgb_tif(
            radiance_filename=input_path.name,
            output_filename=output_path.name,
            index_type=index_type,
        )

    assert response.startswith(f"✅ {index_type} computed")
    assert f"Valid pixel ratio: {valid_count / 6:.2%}" in response
    array, nodata, actual_description, transform, projection = _read_output(output_path)
    np.testing.assert_allclose(array, np.asarray(expected, dtype=np.float32), rtol=1e-6, atol=1e-6)
    assert nodata == float(NODATA)
    assert actual_description == description
    assert transform == (500000.0, 10.0, 0.0, 3450000.0, 0.0, -10.0)
    assert 'AUTHORITY["EPSG","32651"]' in projection
    assert int(np.count_nonzero(array != NODATA)) == valid_count
    assert np.isfinite(array[array != NODATA]).all()


def test_unsupported_index_does_not_write_an_artifact(tmp_path: Path, index_module):
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    input_path = inputs / "calibrated_rgb.tif"
    output_path = outputs / "unsupported.tif"
    _write_rgb_fixture(input_path)

    with (
        patch.object(index_module.storage_manager, "resolve_input_path", return_value=str(input_path)),
        patch.object(index_module.storage_manager, "resolve_output_path", return_value=str(output_path)),
    ):
        response = index_module.compute_index_from_rgb_tif(
            radiance_filename=input_path.name,
            output_filename=output_path.name,
            index_type="NOT_AN_INDEX",
        )

    assert response.startswith("❌ Unsupported index_type")
    assert not output_path.exists()
