from experiments.official_daily_ntl_fastpath.study_area_catalog import _normalize_name_list


def test_normalize_name_list_dedup_sort_and_trim():
    values = ["  China ", "Myanmar", "China", "", None, "india"]
    out = _normalize_name_list(values, limit=10)
    assert out == ["China", "india", "Myanmar"]


def test_normalize_name_list_non_target_variation_limit():
    values = [f"item_{i}" for i in range(50)]
    out = _normalize_name_list(values, limit=7)
    assert len(out) == 7
