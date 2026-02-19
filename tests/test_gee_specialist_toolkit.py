import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "GEE_specialist_toolkit.py"
    spec = importlib.util.spec_from_file_location("gee_specialist_toolkit", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load GEE_specialist_toolkit module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dataset_router_long_daily_uses_server_side():
    mod = _load_module()
    payload = mod.GEE_dataset_router_tool.invoke(
        {
            "query": "daily ANTL for full year",
            "temporal_resolution": "daily",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "analysis_intent": "time_series",
        }
    )
    data = json.loads(payload)
    assert data["recommended_execution_mode"] == "gee_server_side"
    assert data["status"] == "supported"


def test_script_blueprint_python_returns_storage_manager_template():
    mod = _load_module()
    payload = mod.GEE_script_blueprint_tool.invoke(
        {
            "language": "python",
            "dataset_id": "NASA/VIIRS/002/VNP46A2",
            "band": "Gap_Filled_DNB_BRDF_Corrected_NTL",
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "analysis_mode": "time_series",
            "output_format": "csv",
            "output_filename": "daily_antl.csv",
        }
    )
    data = json.loads(payload)
    assert data["language"] == "python"
    assert "storage_manager.resolve_output_path" in data["script"]


def test_discovery_and_metadata_tools_are_registered():
    mod = _load_module()
    assert mod.GEE_catalog_discovery_tool.name == "GEE_catalog_discovery_tool"
    assert mod.GEE_dataset_metadata_tool.name == "GEE_dataset_metadata_tool"
