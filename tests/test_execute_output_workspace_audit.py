import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "NTL_Code_generation.py"
    spec = importlib.util.spec_from_file_location("ntl_code_generation_artifact_audit", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load NTL_Code_generation module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_artifact_audit_flags_cross_workspace_output():
    mod = _load_module()
    log = (
        "Visualization saved to: "
        "E:\\NTL-GPT-Clone\\user_data\\debug\\outputs\\shanghai_ntl_2020_viridis.png"
    )
    audit = mod._build_artifact_audit(log, thread_id="26cf1633")
    assert audit.get("pass") is False
    assert audit.get("out_of_workspace_paths")


def test_artifact_audit_accepts_current_thread_output():
    mod = _load_module()
    p = (Path("user_data") / "26cf1633" / "outputs" / "ok.png").resolve()
    log = f"Saved to: {p}"
    audit = mod._build_artifact_audit(log, thread_id="26cf1633")
    assert audit.get("pass") is True
    assert not audit.get("out_of_workspace_paths")
