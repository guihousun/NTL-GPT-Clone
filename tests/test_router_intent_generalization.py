import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "GEE_specialist_toolkit.py"
    spec = importlib.util.spec_from_file_location("gee_specialist_toolkit_generalization", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load GEE_specialist_toolkit module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _route(query: str):
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": query,
            "temporal_resolution": "daily",
            "start_date": "2025-04-01",
            "end_date": "2025-04-10",
            "analysis_intent": "zonal_stats",
        }
    )
    return json.loads(payload)


def test_router_generalizes_to_earthquake_event_impact():
    data = _route(
        "Assess earthquake impact with GEE Python API and compute ANTL for pre-event and post-event periods."
    )
    assert data["estimated_image_count"] == 10
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_generalizes_to_wildfire_event_impact():
    data = _route(
        "Assess wildfire damage with GEE Python API and compute daily ANTL change before and after the event."
    )
    assert data["estimated_image_count"] == 10
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_generalizes_to_conflict_event_impact():
    data = _route(
        "Compute ANTL disruption for conflict impact assessment using GEE Python API and pre-event/post-event windows."
    )
    assert data["estimated_image_count"] == 10
    assert data["recommended_execution_mode"] == "gee_server_side"


def test_router_generalizes_to_flood_event_impact():
    data = _route(
        "Assess flood impact and compute ANTL in pre-event and post-event periods with Earth Engine Python API."
    )
    assert data["estimated_image_count"] == 10
    assert data["recommended_execution_mode"] == "gee_server_side"
