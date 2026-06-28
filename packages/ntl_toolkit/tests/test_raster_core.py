from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


def _raster_module():
    spec = importlib.util.find_spec("ntl_toolkit.core.raster")
    assert spec is not None, "ntl_toolkit.core.raster should exist"
    return importlib.import_module("ntl_toolkit.core.raster")


def test_raster_module_exports_required_public_callables() -> None:
    module = _raster_module()

    for name in ["inspect_raster", "validate_geodata"]:
        assert hasattr(module, name), f"ntl_toolkit.core.raster missing {name}"


def test_inspect_raster_full_mode_reports_masked_stats_for_fixture(
    sample_raster_path: Path,
) -> None:
    result = _raster_module().inspect_raster(sample_raster_path)

    assert result.status == "succeeded"
    assert result.tool == "inspect_raster"
    assert result.metrics["path"] == str(sample_raster_path.resolve(strict=False))
    assert result.metrics["driver"] == "GTiff"
    assert result.metrics["crs"] == "EPSG:4326"
    assert result.metrics["width"] == 2
    assert result.metrics["height"] == 2
    assert result.metrics["band_count"] == 1
    assert result.metrics["dtype"] == "float32"
    assert result.metrics["resolution"] == [1.0, 1.0]
    assert result.metrics["nodata"] == pytest.approx(-9999.0)
    assert result.metrics["bounds"] == [0.0, 0.0, 2.0, 2.0]
    assert result.metrics["transform"] == [1.0, 0.0, 0.0, 0.0, -1.0, 2.0, 0.0, 0.0, 1.0]
    assert result.metrics["grid_signature"] == "EPSG:4326|2|2|1.0|1.0|1.0|0.0|0.0|0.0|-1.0|2.0|0.0|0.0|1.0"
    assert result.metrics["readable"] is True
    assert result.metrics["valid_count"] == 3
    assert result.metrics["min"] == pytest.approx(1.0)
    assert result.metrics["max"] == pytest.approx(3.0)
    assert result.metrics["mean"] == pytest.approx(2.0)
    assert result.metrics["std"] == pytest.approx(0.81649658)
    assert result.metrics["hints"] == []


def test_inspect_raster_basic_mode_omits_expensive_stats(
    sample_raster_path: Path,
) -> None:
    result = _raster_module().inspect_raster(sample_raster_path, mode="basic")

    assert result.status == "succeeded"
    assert "valid_count" not in result.metrics
    assert "min" not in result.metrics
    assert "max" not in result.metrics
    assert "mean" not in result.metrics
    assert "std" not in result.metrics
    assert "hints" not in result.metrics


def test_inspect_raster_sampling_is_deterministic_and_nodata_safe(
    sample_raster_path: Path,
) -> None:
    first = _raster_module().inspect_raster(sample_raster_path, sample_pixels=1)
    second = _raster_module().inspect_raster(sample_raster_path, sample_pixels=1)

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert first.metrics["sample_pixels"] == 1
    assert first.metrics["valid_count"] == 1
    assert first.metrics["mean"] == pytest.approx(1.0)
    assert first.metrics["std"] == pytest.approx(0.0)
    assert first.metrics["valid_count"] == second.metrics["valid_count"]
    assert first.metrics["mean"] == second.metrics["mean"]
    assert first.metrics["std"] == second.metrics["std"]


@pytest.mark.parametrize(
    ("kwargs", "details"),
    [
        ({"mode": "banana"}, {"parameter": "mode", "value": "banana"}),
        ({"sample_pixels": -1}, {"parameter": "sample_pixels", "value": -1}),
        ({"sample_pixels": 1.5}, {"parameter": "sample_pixels", "value": 1.5}),
    ],
)
def test_inspect_raster_rejects_invalid_parameters(
    sample_raster_path: Path,
    kwargs: dict[str, object],
    details: dict[str, object],
) -> None:
    result = _raster_module().inspect_raster(sample_raster_path, **kwargs)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_PARAMETER"
    assert result.error.details == details


def test_inspect_raster_reports_missing_and_corrupt_inputs(
    corrupt_raster_path: Path,
) -> None:
    missing = _raster_module().inspect_raster(Path("inputs") / "missing.tif")
    corrupt = _raster_module().inspect_raster(corrupt_raster_path)

    assert missing.status == "failed"
    assert missing.error is not None
    assert missing.error.code == "INPUT_NOT_FOUND"
    assert missing.error.details["path"].endswith("inputs\\missing.tif")

    assert corrupt.status == "failed"
    assert corrupt.error is not None
    assert corrupt.error.code == "RASTER_READ_FAILED"
    assert corrupt.error.details["path"] == str(corrupt_raster_path.resolve(strict=False))


def test_validate_geodata_flags_shifted_raster_grid_mismatch(
    sample_raster_path: Path,
    shifted_raster_path: Path,
) -> None:
    result = _raster_module().validate_geodata(
        raster_paths=[sample_raster_path, shifted_raster_path]
    )

    assert result.status == "succeeded"
    assert "GRID_MISMATCH" in result.warnings
    assert result.metrics["raster_count"] == 2
    pair_report = result.metrics["raster_pair_reports"][0]
    assert pair_report["left_path"] == str(sample_raster_path.resolve(strict=False))
    assert pair_report["right_path"] == str(shifted_raster_path.resolve(strict=False))
    assert pair_report["grid_compatible"] is False
    assert "GRID_MISMATCH" in pair_report["warning_codes"]


def test_validate_geodata_does_not_flag_grid_mismatch_for_matching_rasters(
    sample_raster_path: Path,
    matching_raster_path: Path,
) -> None:
    result = _raster_module().validate_geodata(
        raster_paths=[sample_raster_path, matching_raster_path]
    )

    assert result.status == "succeeded"
    assert "GRID_MISMATCH" not in result.warnings
    assert result.metrics["raster_pair_reports"][0]["grid_compatible"] is True


def test_validate_geodata_tolerates_harmless_transform_noise(
    sample_raster_path: Path,
    noisy_transform_raster_path: Path,
) -> None:
    result = _raster_module().validate_geodata(
        raster_paths=[sample_raster_path, noisy_transform_raster_path]
    )

    assert result.status == "succeeded"
    assert "GRID_MISMATCH" not in result.warnings
    assert result.metrics["raster_pair_reports"][0]["grid_compatible"] is True


def test_validate_geodata_reports_vector_crs_mismatch_and_no_overlap(
    sample_raster_path: Path,
    mercator_overlap_vector_path: Path,
    far_vector_path: Path,
) -> None:
    result = _raster_module().validate_geodata(
        raster_paths=[sample_raster_path],
        vector_paths=[mercator_overlap_vector_path, far_vector_path],
    )

    assert result.status == "succeeded"
    assert "CRS_MISMATCH" in result.warnings
    assert "NO_BBOX_INTERSECTION" in result.warnings
    comparisons = result.metrics["raster_vector_reports"]
    mercator_report = next(
        report
        for report in comparisons
        if report["vector_path"] == str(mercator_overlap_vector_path.resolve(strict=False))
    )
    far_report = next(
        report
        for report in comparisons
        if report["vector_path"] == str(far_vector_path.resolve(strict=False))
    )
    assert mercator_report["crs_match"] is False
    assert mercator_report["bbox_intersects"] is True
    assert "CRS_MISMATCH" in mercator_report["warning_codes"]
    assert far_report["crs_match"] is True
    assert far_report["bbox_intersects"] is False
    assert "NO_BBOX_INTERSECTION" in far_report["warning_codes"]


def test_validate_geodata_propagates_invalid_geometry_without_claiming_bbox_overlap(
    sample_raster_path: Path,
    invalid_vector_path: Path,
) -> None:
    result = _raster_module().validate_geodata(
        raster_paths=[sample_raster_path],
        vector_paths=[invalid_vector_path],
    )

    assert result.status == "succeeded"
    assert "INVALID_GEOMETRY" in result.warnings
    vector_report = result.metrics["vector_reports"][0]
    pair_report = result.metrics["raster_vector_reports"][0]
    assert vector_report["invalid_geometry"] is True
    assert vector_report["bounds"] is None
    assert "INVALID_GEOMETRY" in vector_report["warning_codes"]
    assert pair_report["bbox_intersects"] is None
    assert "INVALID_GEOMETRY" in pair_report["warning_codes"]
    assert "NO_BBOX_INTERSECTION" not in pair_report["warning_codes"]


def test_validate_geodata_reports_empty_invalid_and_unreadable_inputs(
    empty_vector_path: Path,
    invalid_vector_path: Path,
    corrupt_vector_path: Path,
) -> None:
    missing_path = Path("inputs") / "missing.geojson"
    result = _raster_module().validate_geodata(
        vector_paths=[empty_vector_path, invalid_vector_path, corrupt_vector_path, missing_path]
    )

    assert result.status == "succeeded"
    assert "EMPTY_DATASET" in result.warnings
    assert "INVALID_GEOMETRY" in result.warnings
    assert "UNREADABLE" in result.warnings
    reports = {
        report["requested_path"]: report for report in result.metrics["vector_reports"]
    }
    assert reports[str(empty_vector_path)]["empty_dataset"] is True
    assert "EMPTY_DATASET" in reports[str(empty_vector_path)]["warning_codes"]
    assert reports[str(invalid_vector_path)]["invalid_geometry"] is True
    assert "INVALID_GEOMETRY" in reports[str(invalid_vector_path)]["warning_codes"]
    assert reports[str(corrupt_vector_path)]["readable"] is False
    assert "UNREADABLE" in reports[str(corrupt_vector_path)]["warning_codes"]
    assert reports[str(missing_path)]["exists"] is False
    assert "UNREADABLE" in reports[str(missing_path)]["warning_codes"]


def test_validate_geodata_does_not_mutate_caller_input_lists(
    sample_raster_path: Path,
    shifted_raster_path: Path,
    far_vector_path: Path,
) -> None:
    raster_paths = [sample_raster_path, shifted_raster_path]
    vector_paths = [far_vector_path]

    result = _raster_module().validate_geodata(
        raster_paths=raster_paths,
        vector_paths=vector_paths,
    )

    assert result.status == "succeeded"
    assert raster_paths == [sample_raster_path, shifted_raster_path]
    assert vector_paths == [far_vector_path]
