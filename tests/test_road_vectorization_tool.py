from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import rasterio
import pytest
import shapefile
from rasterio.transform import from_origin
from skimage import filters, morphology

from tools.road_vectorization import (
    resolve_road_input_path,
    vectorize_road_mask_file,
)


def _reference_road_mask() -> np.ndarray:
    """Recreate the small provider-free BV1-067 road mask fixture."""

    data = np.zeros((3, 64, 64), dtype=np.uint16)
    data[:, 20:25, 5:59] = 50000
    data[:, 5:59, 38:43] = 40000
    for index in range(8, 57):
        data[:, index, max(0, index - 1) : min(64, index + 2)] = 45000

    gain = np.array([0.00001354, 0.00000507, 0.0000099253], dtype=np.float32)
    bias = np.array([0.0000136754, 0.000006084, 0.0000099253], dtype=np.float32)
    weights = np.array([0.2989, 0.5870, 0.1140], dtype=np.float32)
    valid = np.any(data > 0, axis=0)
    calibrated = data.astype(np.float32) * gain[:, None, None] + bias[:, None, None]
    gray = (calibrated * weights[:, None, None]).sum(axis=0)
    gray[~valid] = 0.0

    threshold = filters.threshold_otsu(gray)
    mask = gray > threshold
    mask = morphology.remove_small_objects(mask, min_size=15)
    mask = morphology.binary_closing(mask)
    return morphology.skeletonize(mask).astype(np.uint8)


def test_bv1_067_road_fixture_writes_polyline_with_39_features(tmp_path: Path) -> None:
    mask_path = tmp_path / "inputs" / "SDG_road_centerline_mask.tif"
    output_base = tmp_path / "outputs" / "SDG_urban_main_roads.shp"
    mask_path.parent.mkdir(parents=True)

    mask = _reference_road_mask()
    assert int(mask.sum()) == 151
    with rasterio.open(
        mask_path,
        "w",
        driver="GTiff",
        height=mask.shape[0],
        width=mask.shape[1],
        count=1,
        dtype="uint8",
        crs="EPSG:32651",
        transform=from_origin(500000.0, 3450000.0, 10.0, 10.0),
        nodata=255,
    ) as dst:
        dst.write(mask, 1)

    result = vectorize_road_mask_file(mask_path, output_base)

    assert result["geometry_type"] == "PolyLine"
    assert result["feature_count"] == 39
    assert result["total_length_m"] == pytest.approx(1824.680374315355)
    assert {Path(path).suffix for path in result["sidecars"]} == {
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
        ".cpg",
    }
    reader = shapefile.Reader(str(output_base))
    try:
        assert reader.shapeType == shapefile.POLYLINE
        assert len(reader.shapes()) == 39
        assert len(reader.records()) == 39
    finally:
        reader.close()
    assert all(Path(path).is_file() and Path(path).stat().st_size > 0 for path in result["sidecars"])
    expected_hashes = {
        "SDG_urban_main_roads.cpg": "146d6789ffe033a5297c1ad046e6a62ee35319b86b021444f05b6ea2aa8a1f4a",
        "SDG_urban_main_roads.dbf": "6e6053f7a4182c82e117c62ebfde094bb91c31f1e44aff7fe2cb680417f4e595",
        "SDG_urban_main_roads.prj": "9521dee7dbab056c9097187fb451f45b7f47110348841f1d5638b1e7b5864632",
        "SDG_urban_main_roads.shp": "49f03ce363fc7015ea4854215c02a9840a71b7ecefa06ea0da3a985cf5090262",
        "SDG_urban_main_roads.shx": "09bbeec0a7506b517d95b9329645b1dd74bef9ac35b880886beaec27bfe59e34",
    }
    actual_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(item) for item in result["sidecars"])
    }
    assert actual_hashes == expected_hashes


def test_road_input_resolution_accepts_previous_output(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "thread"
    output_path = workspace / "outputs" / "road_intensity.tif"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"synthetic")

    from tools import road_vectorization

    monkeypatch.setattr(road_vectorization.storage_manager, "get_workspace", lambda _thread=None: workspace)
    monkeypatch.setattr(
        road_vectorization.storage_manager,
        "resolve_input_path",
        lambda filename, _thread=None: str(workspace / "inputs" / filename),
    )

    resolved = resolve_road_input_path("road_intensity.tif")
    assert resolved == output_path.resolve()


def test_extract_road_reads_previous_output_artifact(monkeypatch, tmp_path: Path) -> None:
    from tools import main_road

    workspace = tmp_path / "thread"
    source_path = workspace / "outputs" / "SDG_grayscale_brightness.tif"
    target_path = workspace / "outputs" / "SDG_road_centerline_mask.tif"
    source_path.parent.mkdir(parents=True)
    gray = np.zeros((32, 32), dtype=np.float32)
    gray[14:18, 3:29] = 10.0
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        height=gray.shape[0],
        width=gray.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32651",
        transform=from_origin(500000.0, 3450000.0, 10.0, 10.0),
        nodata=255,
    ) as dst:
        dst.write(gray, 1)

    monkeypatch.setattr(main_road.storage_manager, "get_workspace", lambda _thread=None: workspace)
    monkeypatch.setattr(
        main_road.storage_manager,
        "resolve_input_path",
        lambda filename, _thread=None: str(workspace / "inputs" / filename),
    )
    monkeypatch.setattr(
        main_road.storage_manager,
        "resolve_output_path",
        lambda filename, _thread=None: str(workspace / "outputs" / Path(filename).name),
    )

    response = main_road.extract_road_mask_by_otsu(
        "outputs/SDG_grayscale_brightness.tif",
        "SDG_road_centerline_mask.tif",
    )

    assert response.startswith("✅")
    assert target_path.is_file()
    with rasterio.open(target_path) as src:
        assert src.count == 1
        assert src.crs.to_string() == "EPSG:32651"
        assert set(np.unique(src.read(1))).issubset({0, 1})
