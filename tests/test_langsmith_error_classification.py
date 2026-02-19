import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "scripts" / "langgraph_case_runner.py"
    spec = importlib.util.spec_from_file_location("langgraph_case_runner_langsmith_test", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load langgraph_case_runner module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parent_command_is_non_blocking_when_root_success():
    mod = _load_module()
    out = mod.classify_langsmith_error("ParentCommand(Command(graph='__parent__', update={...}))", "success")
    assert out["kind"] == "handoff_control_flow"
    assert out["blocking"] is False


def test_parent_command_is_blocking_when_root_not_success():
    mod = _load_module()
    out = mod.classify_langsmith_error("ParentCommand(Command(graph='__parent__', update={...}))", "error")
    assert out["kind"] == "execution_error"
    assert out["blocking"] is True


def test_regular_error_is_blocking():
    mod = _load_module()
    out = mod.classify_langsmith_error("ValueError: bad tool arguments", "success")
    assert out["kind"] == "execution_error"
    assert out["blocking"] is True
