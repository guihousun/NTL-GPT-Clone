from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from tools import NTL_preprocess


TRANSFORM = from_origin(0.0, 2.0, 1.0, 1.0)


def write_raster(
    path: Path,
    values: np.ndarray,
    *,
    nodata: float,
    transform=TRANSFORM,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=str(values.dtype),
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
    ) as destination:
        destination.write(values, 1)


def bind_paths(monkeypatch, inputs: dict[str, Path], output: Path) -> None:
    monkeypatch.setattr(
        NTL_preprocess.storage_manager,
        "resolve_input_path",
        lambda name: str(inputs[name]),
    )
    monkeypatch.setattr(
        NTL_preprocess.storage_manager,
        "resolve_output_path",
        lambda name: str(output),
    )


def test_registered_dmsp_evi_tool_uses_fixed_dn63_and_preserves_nodata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dmsp = np.array([[0, 10, 20], [30, 40, 63]], dtype=np.float32)
    evi = np.array([[0.005, 0.2, 0.5], [0.8, 1.0, -9999]], dtype=np.float32)
    dmsp_path = tmp_path / "dmsp.tif"
    evi_path = tmp_path / "evi.tif"
    output_path = tmp_path / "outputs" / "eantli.tif"
    write_raster(dmsp_path, dmsp, nodata=-9999.0)
    write_raster(evi_path, evi, nodata=-9999.0)
    bind_paths(
        monkeypatch,
        {"dmsp.tif": dmsp_path, "evi.tif": evi_path},
        output_path,
    )

    result = NTL_preprocess.dmsp_evi_preprocess_tool.invoke(
        {"dmsp_tif": "dmsp.tif", "evi_tif": "evi.tif", "output_tif": "eantli.tif"}
    )

    assert result == (
        "Success: EANTLI image saved to 'outputs/eantli.tif' with 4 valid pixels."
    )
    with rasterio.open(output_path) as source:
        actual = source.read(1)
        assert source.dtypes == ("float32",)
        assert source.nodata == -9999.0
        assert source.crs.to_epsg() == 4326
        assert source.transform == TRANSFORM

    expected = np.array(
        [
            [-9999.0, 9.207317352294922, 13.825502395629883],
            [15.32374095916748, 18.604652404785156, -9999.0],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-5)


def test_dmsp_evi_tool_excludes_explicit_nodata_and_out_of_domain_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dmsp = np.array([[255, 64, 63], [10, 20, 30]], dtype=np.float32)
    evi = np.array([[0.2, 0.2, 0.0], [1.1, 0.01, 0.5]], dtype=np.float32)
    dmsp_path = tmp_path / "dmsp.tif"
    evi_path = tmp_path / "evi.tif"
    output_path = tmp_path / "eantli.tif"
    write_raster(dmsp_path, dmsp, nodata=255.0)
    write_raster(evi_path, evi, nodata=-9999.0)
    bind_paths(monkeypatch, {"dmsp": dmsp_path, "evi": evi_path}, output_path)

    result = NTL_preprocess.preprocess_dmsp_evi("dmsp", "evi", "eantli.tif")

    assert result.endswith("with 2 valid pixels.")
    with rasterio.open(output_path) as source:
        actual = source.read(1)
    assert np.count_nonzero(actual != -9999.0) == 2
    assert np.all(actual[0] == -9999.0)
    assert actual[1, 0] == -9999.0
    assert np.all(np.isfinite(actual[actual != -9999.0]))
    expected = np.full(dmsp.shape, -9999.0, dtype=np.float32)
    for row, column in ((1, 1), (1, 2)):
        difference = float(dmsp[row, column]) / 63.0 - float(evi[row, column])
        expected[row, column] = (
            (1.0 + difference) / (1.0 - difference)
        ) * float(dmsp[row, column])
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-5)


def test_dmsp_evi_tool_rejects_misaligned_grids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    values = np.ones((2, 3), dtype=np.float32)
    dmsp_path = tmp_path / "dmsp.tif"
    evi_path = tmp_path / "evi.tif"
    output_path = tmp_path / "eantli.tif"
    write_raster(dmsp_path, values, nodata=-9999.0)
    write_raster(
        evi_path,
        values,
        nodata=-9999.0,
        transform=from_origin(0.5, 2.0, 1.0, 1.0),
    )
    bind_paths(monkeypatch, {"dmsp": dmsp_path, "evi": evi_path}, output_path)

    result = NTL_preprocess.preprocess_dmsp_evi("dmsp", "evi", "eantli.tif")

    assert "not aligned" in result
    assert not output_path.exists()
