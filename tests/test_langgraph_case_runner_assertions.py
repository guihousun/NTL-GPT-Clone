import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "langgraph_case_runner.py"
    spec = importlib.util.spec_from_file_location("langgraph_case_runner_assertions_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load langgraph_case_runner module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_assertions_pass_when_all_conditions_met():
    mod = _load_module()
    analysis = {
        "detected_years": [2015, 2016, 2017, 2018, 2019, 2020],
        "router_recommended_mode": "direct_download",
        "tool_calls_by_name": {"NTL_download_tool": 1},
        "partial_transfer_detected": False,
    }
    assertions, final = mod.evaluate_assertions(
        analysis=analysis,
        expect_years="2015-2020",
        expect_direct_download=True,
        expect_no_partial_transfer=True,
    )
    assert final == "PASS"
    assert all(v["pass"] for v in assertions.values())


def test_assertions_fail_on_missing_years_and_partial_transfer():
    mod = _load_module()
    analysis = {
        "detected_years": [2015, 2016],
        "router_recommended_mode": "direct_download",
        "tool_calls_by_name": {"NTL_download_tool": 1},
        "partial_transfer_detected": True,
    }
    assertions, final = mod.evaluate_assertions(
        analysis=analysis,
        expect_years="2015-2020",
        expect_no_partial_transfer=True,
    )
    assert final == "FAIL"
    assert assertions["expect_years"]["pass"] is False
    assert assertions["expect_no_partial_transfer"]["pass"] is False


def test_assertions_inconclusive_without_expectations():
    mod = _load_module()
    assertions, final = mod.evaluate_assertions(
        analysis={
            "detected_years": [2015],
            "router_recommended_mode": None,
            "tool_calls_by_name": {},
            "partial_transfer_detected": False,
        }
    )
    assert assertions == {}
    assert final == "INCONCLUSIVE"
