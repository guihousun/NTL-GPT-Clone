from pathlib import Path


def _read(path: str) -> str:
    return (Path(__file__).resolve().parent.parent / path).read_text(encoding="utf-8")


def test_target_case_lightweight_shanghai_download_prefers_direct_download_without_forced_boundary():
    content = _read("agents/NTL_Data_Searcher.py")
    assert "lightweight direct-download requests" in content
    assert "default to `NTL_download_tool` first and do NOT force pre-boundary retrieval." in content
    assert "daily <=14 or annual <=12 or monthly <=12" in content


def test_non_target_variant_non_china_boundary_route_is_kept():
    content = _read("agents/NTL_Data_Searcher.py")
    assert "outside-China task requires explicit boundary validation via GEE geoBoundaries (internal match)." in content


def test_non_target_variant_analysis_path_still_requires_confirmed_boundary():
    ds = _read("agents/NTL_Data_Searcher.py")
    eng = _read("agents/NTL_Engineer.py")
    assert "analysis/statistics/execution task" in ds
    assert "/skills/gee-ntl-date-boundary-handling/" in eng
