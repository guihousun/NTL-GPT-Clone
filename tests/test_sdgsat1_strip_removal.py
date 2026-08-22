from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"

from tools import NTL_preprocess as preprocess  # noqa: E402


TRANSFORM = from_origin(500000.0, 3450000.0, 40.0, 40.0)
STRIPE_ROWS = (45, 90)


def _fixture() -> tuple[np.ndarray, np.ndarray]:
    clean = np.full((3, 128, 128), 7, dtype=np.uint16)
    clean[0, 8:-8, 8:-8] = 120
    clean[1, 8:-8, 8:-8] = 90
    clean[2, 8:-8, 8:-8] = 60
    clean[:, 20:35, 20:35] = np.array([200, 150, 100], dtype=np.uint16)[:, None, None]
    striped = clean.copy()
    for row in STRIPE_ROWS:
        striped[:, row, 8:-8] = 0
    return clean, striped


def _write_fixture(path: Path, array: np.ndarray) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[1],
        width=array.shape[2],
        count=3,
        dtype="uint16",
        crs="EPSG:32651",
        transform=TRANSFORM,
        nodata=0,
    ) as dst:
        dst.write(array)


def test_rgb_stripe_loc_uses_all_requested_angles_and_detects_rows() -> None:
    _, striped = _fixture()
    candidates = (striped[0] < 7).astype(np.uint8)
    detected = preprocess.RGB_Stripe_loc(
        candidates,
        theta=np.arange(80, 100),
        threshold=80,
    )
    assert detected.dtype == np.uint8
    assert detected.shape == candidates.shape
    for row in STRIPE_ROWS:
        assert np.all(detected[row, 8:-8] == 1)
    assert np.all(detected[10, 8:-8] == 0)


@pytest.mark.parametrize("method", ("median", "percentile"))
def test_registered_strip_tool_restores_synthetic_stripes_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    clean, striped = _fixture()
    input_path = tmp_path / "SDGSAT1_GLI_striped.tif"
    output_path = tmp_path / f"SDGSAT1_GLI_destriped_{method}.tif"
    _write_fixture(input_path, striped)

    def resolve_input(value: str) -> str:
        assert not Path(value).is_absolute(), "input path was resolved twice"
        return str(input_path)

    def resolve_output(value: str) -> str:
        assert not Path(value).is_absolute(), "output path was resolved twice"
        return str(output_path)

    monkeypatch.setattr(preprocess.storage_manager, "resolve_input_path", resolve_input)
    monkeypatch.setattr(preprocess.storage_manager, "resolve_output_path", resolve_output)
    response = preprocess.SDGSAT1_strip_removal_tool.invoke(
        {
            "img_input_filename": input_path.name,
            "img_output_filename": output_path.name,
            "method": method,
            "start_angle": 80,
            "end_angle": 100,
            "threshold": 80,
        }
    )
    assert response.startswith("Striping removed.")

    with rasterio.open(output_path) as src:
        actual = src.read()
        assert src.crs.to_string() == "EPSG:32651"
        assert src.transform == TRANSFORM
        assert src.dtypes == ("uint16", "uint16", "uint16")
        assert src.nodata == 0
        assert src.descriptions == ("R", "G", "B")

    for row in STRIPE_ROWS:
        np.testing.assert_array_equal(actual[:, row, 8:-8], clean[:, row, 8:-8])
    np.testing.assert_array_equal(actual[:, 20:35, 20:35], clean[:, 20:35, 20:35])
    assert np.count_nonzero(actual[:, 8:-8, 8:-8] == 0) == 0
    assert np.all(actual[:, :8, :] == 0)


def test_strip_tool_rejects_empty_angle_window() -> None:
    response = preprocess.run_strip_removal(
        "unused.tif",
        "unused-output.tif",
        method="median",
        start_angle=90,
        end_angle=90,
        threshold=80,
    )
    assert response == "Error: start_angle must be smaller than end_angle."
