from experiments.official_daily_ntl_fastpath.monitor_server import (
    _lag_days,
    _parse_bbox,
    _parse_download_date_range,
)


def test_parse_bbox_valid():
    bbox = _parse_bbox("120.1,30.2,121.3,31.4")
    assert bbox == (120.1, 30.2, 121.3, 31.4)


def test_parse_bbox_non_target_variation_invalid_order():
    try:
        _parse_bbox("121,31,120,30")
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for invalid bbox order.")


def test_lag_days_handles_invalid_date():
    assert _lag_days("not-a-date") is None


def test_parse_download_date_range_single_and_range():
    s, e = _parse_download_date_range({"start_date": ["2026-02-10"], "end_date": ["2026-02-12"]})
    assert s == "2026-02-10"
    assert e == "2026-02-12"
    s2, e2 = _parse_download_date_range({"start_date": ["2026-02-10"]})
    assert s2 == "2026-02-10"
    assert e2 == "2026-02-10"


def test_parse_download_date_range_non_target_variation_invalid_order():
    try:
        _parse_download_date_range({"start_date": ["2026-02-12"], "end_date": ["2026-02-10"]})
    except ValueError:
        assert True
        return
    raise AssertionError("Expected ValueError for end_date earlier than start_date.")
