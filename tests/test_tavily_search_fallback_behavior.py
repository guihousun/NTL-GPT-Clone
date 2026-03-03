from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_tavily_module():
    module_path = Path(__file__).resolve().parent.parent / "tools" / "TavilySearch.py"
    spec = importlib.util.spec_from_file_location("tavily_search_module_fallback", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeTavily:
    def __init__(self):
        self.last_args = None

    def invoke(self, args):
        self.last_args = args
        return {"results": [{"title": "ok"}], "query": args.get("query")}


def test_tavily_search_safe_drops_invalid_include_domains_and_continues(monkeypatch):
    tavily_module = _load_tavily_module()
    fake = _FakeTavily()
    monkeypatch.setattr(tavily_module, "_get_base_tavily", lambda: fake)

    output = tavily_module._tavily_search_safe(
        query="2025 Myanmar earthquake USGS epicenter",
        include_domains='[not-valid-json',
        search_depth="advanced",
    )

    assert fake.last_args == {
        "query": "2025 Myanmar earthquake USGS epicenter",
        "search_depth": "advanced",
    }
    assert output["results"][0]["title"] == "ok"
    assert output["normalized_domains_applied"] is False
    assert "domain_filter_dropped_reason" in output


def test_tavily_search_safe_applies_normalized_domain_filters(monkeypatch):
    tavily_module = _load_tavily_module()
    fake = _FakeTavily()
    monkeypatch.setattr(tavily_module, "_get_base_tavily", lambda: fake)

    output = tavily_module._tavily_search_safe(
        query="official earthquake report",
        include_domains='["usgs.gov", "reliefweb.int"]',
        exclude_domains="example.com",
    )

    assert fake.last_args == {
        "query": "official earthquake report",
        "include_domains": ["reliefweb.int", "usgs.gov"],
        "exclude_domains": ["example.com"],
    }
    assert output["normalized_domains_applied"] is True
    assert output["normalized_include_domains"] == ["reliefweb.int", "usgs.gov"]
    assert output["normalized_exclude_domains"] == ["example.com"]
