from experiments.official_daily_ntl_fastpath.gee_baseline import get_gee_monitor_products


def test_gee_monitor_products_include_daily_monthly_annual_and_variation():
    rows = get_gee_monitor_products()
    ids = {x["dataset_id"] for x in rows}
    temporals = {x["temporal_resolution"] for x in rows}

    assert "NASA/VIIRS/002/VNP46A2" in ids
    assert "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG" in ids
    assert "NOAA/VIIRS/DNB/ANNUAL_V22" in ids
    assert "projects/sat-io/open-datasets/npp-viirs-ntl" in ids
    assert temporals == {"daily", "monthly", "annual"}
