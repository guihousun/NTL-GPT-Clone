import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "langgraph_case_runner.py"
    spec = importlib.util.spec_from_file_location("langgraph_case_runner_casefile_csv_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load langgraph_case_runner module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_csv_case_file_with_auto_expect(tmp_path: Path):
    mod = _load_module()
    csv_path = tmp_path / "cases.csv"
    csv_path.write_text(
        "Unnamed: 0,Category,Label,Case\n"
        "1,data retrieval and preprocessing,NPP VIIRS annual,"
        "\"Retrieve NPP VIIRS annual NTL data for Shanghai from 2015 to 2020.\"\n"
        "2,data retrieval and preprocessing,Monthly composite,"
        "\"Retrieve VNP46A2 daily NTL data and composite monthly from Jan 1 to Jan 31, 2020.\"\n",
        encoding="utf-8",
    )

    cases = mod._load_case_file(str(csv_path), auto_expect=True)
    assert len(cases) == 2

    annual = cases[0]
    assert annual["id"] == "1"
    assert annual["expect_years"] == "2015-2020"
    assert annual["expect_direct_download"] is True
    assert annual["expect_no_partial_transfer"] is True

    composite = cases[1]
    assert composite["expect_direct_download"] is False


def test_build_batch_metrics_counts_issue_buckets():
    mod = _load_module()
    results = [
        {"final": "PASS", "issue_bucket": "none", "assertions": {"expect_years": {"pass": True}}, "meta": {"category": "A"}},
        {"final": "FAIL", "issue_bucket": "model_design_error", "assertions": {"expect_years": {"pass": False}}, "meta": {"category": "A"}},
        {"final": "ERROR", "issue_bucket": "non_design_error", "assertions": {}, "meta": {"category": "B"}},
    ]
    metrics = mod.build_batch_metrics(results)
    assert metrics["total_cases"] == 3
    assert metrics["pass"] == 1
    assert metrics["fail"] == 1
    assert metrics["error"] == 1
    assert metrics["model_design_error"] == 1
    assert metrics["non_design_error"] == 1
    assert metrics["assertion_case_count"] == 2
    assert metrics["assertion_pass_case_count"] == 1
