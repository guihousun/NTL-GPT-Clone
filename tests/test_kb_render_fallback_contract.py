import ast
from pathlib import Path


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyStreamlit:
    def __init__(self):
        self.warning_calls = []
        self.info_calls = []
        self.markdown_calls = []
        self.json_calls = []
        self.write_calls = []

    def warning(self, text):
        self.warning_calls.append(str(text))

    def info(self, text):
        self.info_calls.append(str(text))

    def markdown(self, text, unsafe_allow_html=False):
        del unsafe_allow_html
        self.markdown_calls.append(str(text))

    def json(self, payload):
        self.json_calls.append(payload)

    def write(self, text):
        self.write_calls.append(text)

    def popover(self, title):
        del title
        return _DummyContext()

    def expander(self, title, expanded=False):
        del title, expanded
        return _DummyContext()


def _load_functions():
    app_ui_path = Path(__file__).resolve().parent.parent / "app_ui.py"
    source = app_ui_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    lines = source.splitlines()

    needed = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"_normalize_kb_payload", "render_kb_output"}:
            needed[node.name] = "\n".join(lines[node.lineno - 1 : node.end_lineno])

    dummy_st = _DummyStreamlit()
    namespace = {
        "st": dummy_st,
        "_extract_json": lambda s: (None, s),
        "_render_popover": lambda title: _DummyContext(),
    }
    exec(needed["_normalize_kb_payload"], namespace)
    exec(needed["render_kb_output"], namespace)
    return namespace["render_kb_output"], dummy_st


def test_render_kb_output_handles_empty_store_status_with_warning():
    render_kb_output, dummy_st = _load_functions()
    render_kb_output(
        {
            "status": "empty_store",
            "store": "Code_RAG",
            "reason": "Code_RAG currently has no indexed documents.",
        }
    )

    assert dummy_st.warning_calls
    assert "empty_store" in dummy_st.warning_calls[0]


def test_render_kb_output_falls_back_to_reason_message_without_empty_card():
    render_kb_output, dummy_st = _load_functions()
    render_kb_output(
        {
            "message": "workflow payload unavailable for this request",
            "reason": "No valid workflow generated.",
            "sources": [],
        }
    )

    assert dummy_st.warning_calls
    all_markdown = " ".join(dummy_st.markdown_calls).lower()
    assert "task:" not in all_markdown
