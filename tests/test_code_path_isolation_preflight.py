import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_path_isolation", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preflight_blocks_windows_backslash_absolute_path():
    mod = _load_module()
    code = (
        "from storage_manager import storage_manager\n"
        "out = r'E:\\NTL-GPT-Clone\\user_data\\debug\\outputs\\a.png'\n"
        "print(out)\n"
    )
    report = mod._preflight_checks(code, strict_mode=True)
    errors = [str(x).lower() for x in report.get("blocking_errors", [])]
    assert any("absolute path" in err for err in errors)


def test_preflight_blocks_windows_slash_absolute_path():
    mod = _load_module()
    code = (
        "from storage_manager import storage_manager\n"
        "import pandas as pd\n"
        "df = pd.DataFrame([{'x': 1}])\n"
        "df.to_csv('C:/temp/a.csv', index=False)\n"
    )
    report = mod._preflight_checks(code, strict_mode=True)
    errors = [str(x).lower() for x in report.get("blocking_errors", [])]
    assert any("absolute path" in err for err in errors)


def test_preflight_allows_storage_manager_output_path():
    mod = _load_module()
    code = (
        "from storage_manager import storage_manager\n"
        "import pandas as pd\n"
        "df = pd.DataFrame([{'x': 1}])\n"
        "out = storage_manager.resolve_output_path('ok.csv')\n"
        "df.to_csv(out, index=False)\n"
    )
    report = mod._preflight_checks(code, strict_mode=True)
    errors = report.get("blocking_errors", [])
    assert all("absolute path" not in str(err).lower() for err in errors)
