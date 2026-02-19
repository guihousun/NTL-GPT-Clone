import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "GEE_download.py"
    spec = importlib.util.spec_from_file_location("gee_download_suffix_mod", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load GEE_download module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ensure_tif_suffix_adds_extension_when_missing():
    mod = _load_module()
    assert mod._ensure_tif_suffix("shanghai_ntl_2013_2022") == "shanghai_ntl_2013_2022.tif"


def test_ensure_tif_suffix_keeps_existing_extension():
    mod = _load_module()
    assert mod._ensure_tif_suffix("shanghai_ntl_2013.tif") == "shanghai_ntl_2013.tif"
    assert mod._ensure_tif_suffix("shanghai_ntl_2013.tiff") == "shanghai_ntl_2013.tiff"

