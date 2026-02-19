from experiments.official_daily_ntl_fastpath.download_gee_daily_ntl import (
    _serialize_region_for_download,
    infer_temporal_resolution,
    parse_bbox,
    parse_period,
    periods_from_date_range,
    resolve_band,
    validate_dataset_period,
)


def test_parse_bbox_valid():
    assert parse_bbox("120.1,30.2,121.3,31.4") == (120.1, 30.2, 121.3, 31.4)


def test_parse_bbox_non_target_variation_invalid_order():
    try:
        parse_bbox("121.3,31.4,120.1,30.2")
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for invalid bbox order.")


def test_resolve_band_defaults_for_daily_products():
    assert resolve_band("NASA/VIIRS/002/VNP46A2", None) == "Gap_Filled_DNB_BRDF_Corrected_NTL"
    assert resolve_band("NOAA/VIIRS/001/VNP46A1", None) == "DNB_At_Sensor_Radiance_500m"


def test_resolve_band_requires_explicit_for_unknown_dataset():
    try:
        resolve_band("UNKNOWN/DATASET", None)
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for unknown dataset without band.")


def test_parse_period_monthly_and_annual():
    assert parse_period("monthly", "2026-02") == ("2026-02-01", "2026-03-01", "2026-02")
    assert parse_period("annual", "2025") == ("2025-01-01", "2026-01-01", "2025")


def test_validate_dataset_period_daily_min_date():
    try:
        validate_dataset_period(
            dataset_id="NASA/VIIRS/002/VNP46A2",
            temporal_resolution="daily",
            start_date="2013-12-31",
            period_label="2013-12-31",
        )
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for pre-2014 daily request.")


def test_validate_dataset_period_annual_dmsp_range():
    validate_dataset_period(
        dataset_id="NOAA/DMSP-OLS/NIGHTTIME_LIGHTS",
        temporal_resolution="annual",
        start_date="2013-01-01",
        period_label="2013",
    )
    try:
        validate_dataset_period(
            dataset_id="NOAA/DMSP-OLS/NIGHTTIME_LIGHTS",
            temporal_resolution="annual",
            start_date="2014-01-01",
            period_label="2014",
        )
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for DMSP annual 2014.")


def test_validate_dataset_period_annual_npp_viirs_like_range():
    validate_dataset_period(
        dataset_id="projects/sat-io/open-datasets/npp-viirs-ntl",
        temporal_resolution="annual",
        start_date="2000-01-01",
        period_label="2000",
    )
    try:
        validate_dataset_period(
            dataset_id="projects/sat-io/open-datasets/npp-viirs-ntl",
            temporal_resolution="annual",
            start_date="1999-01-01",
            period_label="1999",
        )
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for NPP-VIIRS-Like annual 1999.")


def test_infer_temporal_resolution_and_non_target_variation():
    assert infer_temporal_resolution("NASA/VIIRS/002/VNP46A2") == "daily"
    assert infer_temporal_resolution("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG") == "monthly"
    assert infer_temporal_resolution("projects/sat-io/open-datasets/npp-viirs-ntl") == "annual"
    try:
        infer_temporal_resolution("UNKNOWN/DATASET")
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for unsupported dataset.")


def test_periods_from_date_range_for_daily_monthly_annual():
    assert periods_from_date_range(
        temporal_resolution="daily",
        start_date="2026-02-10",
        end_date="2026-02-12",
    ) == ["2026-02-10", "2026-02-11", "2026-02-12"]
    assert periods_from_date_range(
        temporal_resolution="monthly",
        start_date="2026-01-20",
        end_date="2026-03-05",
    ) == ["2026-01", "2026-02", "2026-03"]
    assert periods_from_date_range(
        temporal_resolution="annual",
        start_date="2024-06-01",
        end_date="2026-01-01",
    ) == ["2024", "2025", "2026"]


def test_serialize_region_for_download_fallback_to_getinfo():
    class FakeGeom:
        def toGeoJSONString(self):
            raise RuntimeError("Cannot convert a computed geometry to GeoJSON")

        def getInfo(self):
            return {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}

    payload = _serialize_region_for_download(FakeGeom())
    assert '"type": "Polygon"' in payload


def test_serialize_region_for_download_direct_geojson():
    class FakeGeom:
        def toGeoJSONString(self):
            return '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}'

    payload = _serialize_region_for_download(FakeGeom())
    assert payload.startswith("{")
