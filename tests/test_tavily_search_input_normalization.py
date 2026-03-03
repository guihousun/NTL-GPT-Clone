from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_tavily_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "TavilySearch.py"
    spec = importlib.util.spec_from_file_location("tavily_search_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_normalize_domain_list_supports_json_string_list():
    tavily_module = _load_tavily_module()
    domains, warning = tavily_module._normalize_domain_list(
        '["usgs.gov", "https://reliefweb.int/path", "earthquake.usgs.gov"]'
    )

    assert warning is None
    assert domains == ["earthquake.usgs.gov", "reliefweb.int", "usgs.gov"]


def test_normalize_domain_list_supports_comma_separated_string():
    tavily_module = _load_tavily_module()
    domains, warning = tavily_module._normalize_domain_list("usgs.gov, reliefweb.int, earthquake.usgs.gov")

    assert warning is None
    assert domains == ["earthquake.usgs.gov", "reliefweb.int", "usgs.gov"]


def test_normalize_domain_list_drops_invalid_tokens_with_warning():
    tavily_module = _load_tavily_module()
    domains, warning = tavily_module._normalize_domain_list("<<not-domain>>")

    assert domains is None
    assert warning is not None
    assert "no valid domains were parsed" in warning


def test_normalize_domain_list_handles_list_input_and_dedupes():
    tavily_module = _load_tavily_module()
    domains, warning = tavily_module._normalize_domain_list(
        ["USGS.GOV", "https://usgs.gov/path", "reliefweb.int"]
    )

    assert warning is None
    assert domains == ["reliefweb.int", "usgs.gov"]
