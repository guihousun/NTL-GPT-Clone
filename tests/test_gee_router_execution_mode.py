import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "GEE_specialist_toolkit.py"
    spec = importlib.util.spec_from_file_location("gee_specialist_toolkit_router", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load GEE_specialist_toolkit module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_router_annual_2015_2020_prefers_direct_download():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Retrieve annual NTL files for 2015-2020",
            "temporal_resolution": "annual",
            "start_date": "2015",
            "end_date": "2020",
        }
    )
    data = json.loads(payload)
    assert data["recommended_execution_mode"] == "direct_download"
    assert data["estimated_image_count"] == 6


def test_router_monthly_small_range_prefers_direct_download():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Retrieve monthly NTL files for one year",
            "temporal_resolution": "monthly",
            "start_date": "2024-01",
            "end_date": "2024-12",
        }
    )
    data = json.loads(payload)
    assert data["recommended_execution_mode"] == "direct_download"
    assert data["estimated_image_count"] == 12


def test_router_daily_long_range_uses_server_side():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Retrieve daily NTL for one year",
            "temporal_resolution": "daily",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
    )
    data = json.loads(payload)
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_composite_export_is_treated_as_heavy_intent():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Generate annual composite export",
            "temporal_resolution": "annual",
            "start_date": "2015",
            "end_date": "2020",
            "analysis_intent": "composite_export",
        }
    )
    data = json.loads(payload)
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_zonal_stats_annual_small_count_prefers_direct_download():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Calculate district-level ANTL zonal statistics for Shanghai in 2020",
            "temporal_resolution": "annual",
            "start_date": "2020",
            "end_date": "2020",
            "analysis_intent": "zonal_stats",
        }
    )
    data = json.loads(payload)
    assert data["estimated_image_count"] == 1
    assert data["recommended_execution_mode"] == "direct_download"


def test_router_zonal_stats_monthly_six_months_prefers_direct_download():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Compute zonal statistics for six monthly NTL files",
            "temporal_resolution": "monthly",
            "start_date": "2024-01",
            "end_date": "2024-06",
            "analysis_intent": "zonal_stats",
        }
    )
    data = json.loads(payload)
    assert data["estimated_image_count"] == 6
    assert data["recommended_execution_mode"] == "direct_download"


def test_router_zonal_stats_daily_six_days_prefers_direct_download_non_target_variation():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Flood impact zonal stats for a six-day window around event date",
            "temporal_resolution": "daily",
            "start_date": "2025-07-01",
            "end_date": "2025-07-06",
            "analysis_intent": "zonal_stats",
        }
    )
    data = json.loads(payload)
    assert data["estimated_image_count"] == 6
    assert data["recommended_execution_mode"] == "direct_download"


def test_router_zonal_stats_daily_seven_days_uses_server_side():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "Flood impact zonal stats for a seven-day window around event date",
            "temporal_resolution": "daily",
            "start_date": "2025-07-01",
            "end_date": "2025-07-07",
            "analysis_intent": "zonal_stats",
        }
    )
    data = json.loads(payload)
    assert data["estimated_image_count"] == 7
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_query_with_event_analysis_forces_server_side_even_for_short_daily_range():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": (
                "Assess wildfire impact with GEE Python API and compute daily ANTL "
                "for pre-event and post-event windows."
            ),
            "temporal_resolution": "daily",
            "start_date": "2025-03-20",
            "end_date": "2025-04-05",
        }
    )
    data = json.loads(payload)
    assert data["estimated_image_count"] == 17
    assert data["recommended_execution_mode"] == "gee_server_side"
