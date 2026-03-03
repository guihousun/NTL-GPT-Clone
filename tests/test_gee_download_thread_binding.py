from __future__ import annotations

import ast
from pathlib import Path
import types


def _load_resolver():
    src_path = Path("tools/GEE_download.py")
    source = src_path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    target = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_thread_id_from_config":
            target = node
            break
    if target is None:
        raise RuntimeError("Function _resolve_thread_id_from_config not found")

    class _FakeVar:
        def __init__(self):
            self._value = None

        def get(self):
            return self._value

    fake_var = _FakeVar()
    fake_current_tid = types.SimpleNamespace(get=lambda: "ctx-fallback")
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


def test_resolve_thread_id_from_explicit_config():
    resolver, _, _ = _load_resolver()
    tid = resolver({"configurable": {"thread_id": "tid-123"}})
    assert tid == "tid-123"


def test_resolve_thread_id_from_inherited_runtime_config():
    resolver, fake_var, _ = _load_resolver()
    fake_var._value = {"configurable": {"thread_id": "tid-inherited"}}
    tid = resolver(None)
    assert tid == "tid-inherited"


def test_resolve_thread_id_falls_back_to_context_when_config_missing():
    resolver, fake_var, fake_current_tid = _load_resolver()
    fake_var._value = {"configurable": {}}
    fake_current_tid.get = lambda: "ctx-thread"
    tid = resolver(None)
    assert tid == "ctx-thread"

