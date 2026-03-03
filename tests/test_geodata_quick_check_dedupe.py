import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "geodata_inspector_tool.py"
    spec = importlib.util.spec_from_file_location("geodata_inspector_tool_for_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load geodata_inspector_tool module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stub_environment(mod, monkeypatch):
    monkeypatch.setattr(mod.sm, "resolve_input_path", lambda p: f"E:/fake_workspace/inputs/{p}")
    monkeypatch.setattr(mod.sm, "resolve_output_path", lambda p: f"E:/fake_workspace/outputs/{p}")
    monkeypatch.setattr(mod.os.path, "exists", lambda p: True)
    monkeypatch.setattr(
        mod,
        "_raster_report",
        lambda path, sample_pixels=0, mode="full": {"path": path, "exists": True, "readable": True},
    )


def test_quick_check_default_keeps_per_year_files(monkeypatch):
    mod = _load_module()
    _stub_environment(mod, monkeypatch)

    paths = [
        "NTL_Shanghai_2015.tif",
        "NTL_Shanghai_2016.tif",
        "NTL_Shanghai_2017.tif",
        "NTL_Shanghai_2018.tif",
        "NTL_Shanghai_2019.tif",
        "NTL_Shanghai_2020.tif",
    ]
    payload = mod.inspect_geospatial_assets_quick(raster_paths=paths)
    data = json.loads(payload)

    assert data["requested_raster_count"] == 6
    assert data["resolved_raster_count"] == 6
    assert data["summary"]["raster_ok"] == 6
    assert data["dedupe_raster"]["policy"] == "none"
    assert data["dedupe_applied"] is False


def test_dedupe_modes_are_explicit_and_predictable(monkeypatch):
    mod = _load_module()
    _stub_environment(mod, monkeypatch)

    paths = ["NTL_Shanghai_2015.tif", "NTL_Shanghai_2015.tif", "NTL_Shanghai_2016.tif"]

    exact_payload = mod.inspect_geospatial_assets(
        raster_paths=paths,
        mode="basic",
        dedupe_mode="exact_path",
    )
    exact_data = json.loads(exact_payload)
    assert exact_data["resolved_raster_count"] == 2
    assert exact_data["summary"]["raster_ok"] == 2
    assert exact_data["dedupe_raster"]["policy"] == "exact_path_keep_first"
    assert len(exact_data["dedupe_raster"]["dropped"]) == 1

    stem_payload = mod.inspect_geospatial_assets(
        raster_paths=paths,
        mode="basic",
        dedupe_mode="stem_no_digits",
    )
    stem_data = json.loads(stem_payload)
    assert stem_data["resolved_raster_count"] == 1
    assert stem_data["summary"]["raster_ok"] == 1
    assert stem_data["dedupe_raster"]["policy"] == "by_name_no_digits_keep_first"


def test_quick_check_can_resolve_outputs_when_requested(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.sm, "resolve_input_path", lambda p: f"E:/fake_workspace/inputs/{p}")
    monkeypatch.setattr(mod.sm, "resolve_output_path", lambda p: f"E:/fake_workspace/outputs/{p}")
    monkeypatch.setattr(mod.os.path, "exists", lambda p: str(p).startswith("E:/fake_workspace/outputs/"))
    monkeypatch.setattr(
        mod,
        "_raster_report",
        lambda path, sample_pixels=0, mode="full": {"path": path, "exists": True, "readable": True},
    )

    payload = mod.inspect_geospatial_assets_quick(
        raster_paths=["result_2022.tif"],
        workspace_lookup="outputs",
    )
    data = json.loads(payload)
    assert data["resolved_raster_count"] == 1
    assert data["summary"]["raster_ok"] == 1
    assert data["raster_reports"][0]["resolved_location"] == "outputs"
    assert data["raster_reports"][0]["path"].endswith("outputs/result_2022.tif")


def test_quick_check_skips_cross_checks_by_default(monkeypatch):
    mod = _load_module()
    _stub_environment(mod, monkeypatch)
    monkeypatch.setattr(
        mod,
        "_raster_report",
        lambda path, sample_pixels=0, mode="full": {
            "path": path,
            "exists": True,
            "readable": True,
            "crs": "EPSG:4326",
            "bounds": {"left": 0, "right": 1, "bottom": 0, "top": 1},
        },
    )
    monkeypatch.setattr(
        mod,
        "_vector_report",
        lambda path, mode="full": {
            "path": path,
            "exists": True,
            "readable": True,
            "crs": "EPSG:4326",
            "bounds": {"minx": 0, "maxx": 1, "miny": 0, "maxy": 1},
        },
    )

    payload = mod.inspect_geospatial_assets_quick(
        raster_paths=["r.tif"],
        vector_paths=["b.shp"],
    )
    data = json.loads(payload)
    assert data["cross_checks"] == []
