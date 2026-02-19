import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "China_official_stats.py"
    spec = importlib.util.spec_from_file_location("china_official_stats_mod", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load China_official_stats module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_region_resolution_shanghai():
    mod = _load_module()
    assert mod._resolve_region_code("Shanghai") == "310000"
    assert mod._resolve_region_code("上海市") == "310000"


def test_china_official_gdp_tool_saves_csv_and_reports_coverage(tmp_path, monkeypatch):
    mod = _load_module()

    monkeypatch.setattr(mod.storage_manager, "get_workspace", lambda thread_id=None: tmp_path)
    monkeypatch.setattr(
        mod,
        "_query_single_year_gdp",
        lambda region_code, year, timeout_s=20: float(year) * 10.0,
    )

    result = mod.China_Official_GDP_tool.invoke(
        {"region": "Shanghai", "start_year": 2013, "end_year": 2015, "indicator": "GDP"},
        config={"configurable": {"thread_id": "thread_cn_stats"}},
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["coverage"]["expected_count"] == 3
    assert payload["coverage"]["actual_count"] == 3
    assert payload["coverage"]["missing_years"] == []
    out_name = payload["output_file"]
    assert out_name
    assert (tmp_path / "inputs" / out_name).exists()


def test_china_official_gdp_tool_rejects_unsupported_region():
    mod = _load_module()
    result = mod.china_official_gdp_tool(region="Mars", start_year=2013, end_year=2014, indicator="GDP")
    payload = json.loads(result)
    assert payload["status"] == "region_not_supported"

