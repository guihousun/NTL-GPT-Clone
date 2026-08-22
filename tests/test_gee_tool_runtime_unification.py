from __future__ import annotations

import ast
import importlib
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATED_TOOL_FILES = (
    "tools/geodata_inspector_tool.py",
    "tools/GEE_download.py",
    "tools/Other_image_download.py",
    "tools/ntl_preview_tool.py",
    "tools/GEE_specialist_toolkit.py",
    "tools/VNP46A2_angular_correction.py",
    "tools/NTL_raster_stats_GEE.py",
    "tools/vnp46a2_official_h5/vnp46a2_country_common.py",
    "tools/NTL_Composite.py",
)


def _actual_ee_calls(source: str, method: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != method:
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "ee":
            calls.append(node)
    return calls


def test_formal_gee_tools_have_one_runtime_entry_and_no_legacy_fallbacks():
    for relative_path in MIGRATED_TOOL_FILES:
        source = ROOT.joinpath(relative_path).read_text(encoding="utf-8")
        assert "from gee_runtime import initialize_ee" in source, relative_path
        assert "empyrean-caster-430308-m2" not in source, relative_path
        assert not _actual_ee_calls(source, "Authenticate"), relative_path
        assert not _actual_ee_calls(source, "Initialize"), relative_path


def test_download_adapters_delegate_initialization(monkeypatch):
    cases = (
        ("tools.GEE_download", "_ensure_ee_initialized"),
        ("tools.Other_image_download", "_ensure_ee_initialized"),
    )
    monkeypatch.delenv("EE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("EE_PRIVATE_KEY_JSON", raising=False)

    for module_name, function_name in cases:
        module = importlib.import_module(module_name)
        calls: list[dict] = []

        def fake_initialize_ee(**kwargs):
            calls.append(kwargs)
            return "configured-project"

        monkeypatch.setattr(module, "initialize_ee", fake_initialize_ee)
        assert getattr(module, function_name)() == "configured-project"
        assert calls == [{"ee_module": module.ee}]


def test_lazy_gee_adapters_delegate_with_explicit_override(monkeypatch):
    fake_ee = types.ModuleType("ee")
    monkeypatch.setitem(sys.modules, "ee", fake_ee)

    angular = importlib.import_module("tools.VNP46A2_angular_correction")
    angular_calls: list[dict] = []
    monkeypatch.setattr(
        angular,
        "initialize_ee",
        lambda **kwargs: angular_calls.append(kwargs) or "explicit-project",
    )
    assert angular._load_ee("explicit-project") is fake_ee
    assert angular_calls == [
        {"explicit_project_id": "explicit-project", "ee_module": fake_ee}
    ]

    inspector = importlib.import_module("tools.geodata_inspector_tool")
    inspector_calls: list[dict] = []
    monkeypatch.setattr(
        inspector,
        "initialize_ee",
        lambda **kwargs: inspector_calls.append(kwargs) or "configured-project",
    )
    initialized_module, error = inspector._init_ee()
    assert initialized_module is fake_ee
    assert error is None
    assert inspector_calls == [{"ee_module": fake_ee}]

    preview = importlib.import_module("tools.ntl_preview_tool")
    preview_calls: list[dict] = []
    monkeypatch.setattr(
        preview,
        "initialize_ee",
        lambda **kwargs: preview_calls.append(kwargs) or "configured-project",
    )
    assert preview._initialize_earth_engine() is fake_ee
    assert preview_calls == [{"ee_module": fake_ee}]


def test_metadata_probe_fails_closed_through_unified_initializer(monkeypatch):
    toolkit = importlib.import_module("tools.GEE_specialist_toolkit")
    fake_ee = types.ModuleType("ee")
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    calls: list[object] = []

    def fail_initialize(*, ee_module):
        calls.append(ee_module)
        raise RuntimeError("transport unavailable")

    monkeypatch.setattr(toolkit, "initialize_ee", fail_initialize)
    result = json.loads(toolkit.gee_dataset_metadata("NASA/VIIRS/002/VNP46A2"))
    assert calls == [fake_ee]
    assert result["status"] == "partial"
    assert result["source"] == "built_in_catalog"
    assert "transport unavailable" in result["warning"]


def test_daily_antl_initializes_before_building_project_assets(monkeypatch):
    module = importlib.import_module("tools.NTL_raster_stats_GEE")
    asset_ids: list[str] = []

    class FakeValue:
        def getInfo(self):
            return 0

    class FakeCollection:
        def filter(self, _condition):
            return self

        def size(self):
            return FakeValue()

    fake_ee = types.ModuleType("ee")
    fake_ee.FeatureCollection = lambda asset_id: asset_ids.append(asset_id) or FakeCollection()
    fake_ee.Filter = types.SimpleNamespace(eq=lambda field, value: (field, value))
    monkeypatch.setitem(sys.modules, "ee", fake_ee)
    calls: list[object] = []
    monkeypatch.setattr(
        module,
        "initialize_ee",
        lambda **kwargs: calls.append(kwargs["ee_module"]) or "configured-project",
    )
    monkeypatch.setattr(
        module,
        "resolve_gee_boundary_asset_project_id",
        lambda: "configured-project",
    )

    result = module.calculate_daily_antl_tool(
        "missing-region",
        "province",
        "2025-01-01",
        "2025-01-02",
    )

    assert calls == [fake_ee]
    assert result.startswith("Error: Region")
    assert asset_ids == [
        "projects/configured-project/assets/province",
        "projects/configured-project/assets/city",
        "projects/configured-project/assets/county",
    ]


def test_daily_antl_skips_missing_reducer_property_without_key_error():
    module = importlib.import_module("tools.NTL_raster_stats_GEE")

    rows = module._daily_rows(
        [
            {"properties": {"date": "2024-01-01", "daily_mean_ntl": 12.5}},
            {"properties": {"date": "2024-01-02"}},
            {"properties": {"daily_mean_ntl": 9.0}},
            {"properties": None},
        ],
        "上海市",
    )

    assert rows == [
        {"Date": "2024-01-01", "Daily_Mean_ANTL": 12.5, "Region": "上海市"}
    ]


def test_generated_python_blueprint_uses_runtime_initializer():
    toolkit = importlib.import_module("tools.GEE_specialist_toolkit")
    payload = json.loads(
        toolkit.gee_script_blueprint(
            language="python",
            dataset_id="NASA/VIIRS/002/VNP46A2",
            band="DNB_BRDF_Corrected_NTL",
            start_date="2025-01-01",
            end_date="2025-01-02",
            output_filename="daily.csv",
        )
    )
    assert "from gee_runtime import initialize_ee" in payload["script"]
    assert "initialize_ee(ee_module=ee)" in payload["script"]
    assert "ee.Initialize" not in payload["script"]
