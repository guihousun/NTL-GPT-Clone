import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_raster_stats.py"
    spec = importlib.util.spec_from_file_location("ntl_raster_stats_batch_mod", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_raster_stats module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collect_ntl_inputs_supports_single_and_batch_and_dedup():
    mod = _load_module()
    values = mod._collect_ntl_inputs(
        "ntl_2013.tif",
        ["ntl_2014.tif", "ntl_2013.tif", " ", "ntl_2015.tif"],
    )
    assert values == ["ntl_2013.tif", "ntl_2014.tif", "ntl_2015.tif"]


def test_extract_year_from_filename():
    mod = _load_module()
    assert mod._extract_year_from_filename("shanghai_ntl_2013_2022_2020.tif") == 2020
    assert mod._extract_year_from_filename("ntl_no_year.tif") is None

