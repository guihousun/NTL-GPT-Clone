from experiments.official_daily_ntl_fastpath.boundary_resolver import _resolver_chain, _safe_boundary_filename


def test_safe_boundary_filename_keeps_cjk_names():
    name = _safe_boundary_filename("上海市")
    assert name.startswith("boundary_")
    assert name.endswith(".shp")
    assert name != "boundary_.shp"


def test_safe_boundary_filename_handles_non_target_variation():
    name = _safe_boundary_filename("Yangon, Myanmar")
    assert name == "boundary_Yangon_Myanmar.shp"


def test_resolver_chain_order_for_china_and_non_china():
    chain_cn = [x[0] for x in _resolver_chain(True)]
    chain_global = [x[0] for x in _resolver_chain(False)]
    assert chain_cn == ["amap", "osm", "gee"]
    assert chain_global == ["osm", "amap", "gee"]
