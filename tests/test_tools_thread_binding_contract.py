from __future__ import annotations

import ast
from pathlib import Path
import types


def _load_resolver(path: str):
    src_path = Path(path)
    source = src_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    target = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_thread_id_from_config":
            target = node
            break
    if target is None:
        raise RuntimeError(f"_resolve_thread_id_from_config not found in {path}")

    class _FakeVar:
        def __init__(self):
            self._value = None

        def get(self):
            return self._value

    fake_var = _FakeVar()
    fake_current_tid = types.SimpleNamespace(get=lambda: "ctx-default")
    fake_storage = types.SimpleNamespace(
        get_thread_id_from_config=lambda cfg: cfg.get("configurable", {}).get("thread_id", "")
    )
    ns = {
        "RunnableConfig": dict,
        "Optional": object,
        "var_child_runnable_config": fake_var,
        "current_thread_id": fake_current_tid,
        "storage_manager": fake_storage,
    }
    exec(compile(ast.Module(body=[target], type_ignores=[]), filename=str(src_path), mode="exec"), ns)
    return ns["_resolve_thread_id_from_config"], fake_var, fake_current_tid


def test_gaode_tool_prefers_explicit_config_thread_id():
    resolver, _, _ = _load_resolver("tools/GaoDe_tool.py")
    assert resolver({"configurable": {"thread_id": "tid-gaode"}}) == "tid-gaode"


def test_china_stats_tool_uses_inherited_runtime_thread_id():
    resolver, fake_var, _ = _load_resolver("tools/China_official_stats.py")
    fake_var._value = {"configurable": {"thread_id": "tid-cnstats"}}
    assert resolver(None) == "tid-cnstats"


def test_other_image_tool_falls_back_to_context_thread_id():
    resolver, fake_var, fake_current_tid = _load_resolver("tools/Other_image_download.py")
    fake_var._value = {"configurable": {}}
    fake_current_tid.get = lambda: "tid-context"
    assert resolver(None) == "tid-context"

