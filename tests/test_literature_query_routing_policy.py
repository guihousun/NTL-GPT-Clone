import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "NTL_Knowledge_Base_Searcher.py"


def _load_functions(*names: str):
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    namespace = {"re": re}

    loaded = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            fn_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            exec(fn_source, namespace)
            loaded[node.name] = namespace[node.name]
    return loaded


def test_methodology_reproduction_query_intent_detection():
    fns = _load_functions("_is_methodology_reproduction_query")
    detect = fns["_is_methodology_reproduction_query"]

    assert detect("Reproduce the method and equations from this NTL paper")
    assert detect("paper method and parameter setting for NTL regression")
    assert not detect("download monthly viirs data for beijing")


def test_tool_priority_prefers_literature_for_reproduction_queries():
    fns = _load_functions(
        "_contains_any",
        "_count_matches",
        "_is_methodology_reproduction_query",
        "_fallback_intent_profile",
        "_tool_priority_names",
    )
    choose = fns["_tool_priority_names"]

    names = choose("code", "Reproduce the method from paper and provide equation settings")
    assert names[0] == "NTL_Literature_Knowledge"

    default_names = choose("auto", "download ntl data and compute zonal stats")
    assert default_names == ["NTL_Solution_Knowledge", "NTL_Code_Knowledge"]
    assert "NTL_Literature_Knowledge" not in default_names

    workflow_names = choose("workflow", "download ntl data and compute zonal stats")
    assert workflow_names == ["NTL_Solution_Knowledge", "NTL_Code_Knowledge"]


def test_infer_tool_from_query_handles_official_earthquake_source_query():
    fns = _load_functions(
        "_contains_any",
        "_count_matches",
        "_is_methodology_reproduction_query",
        "_extract_first_json_dict",
        "_extract_first_json_list",
        "_safe_json_loads",
        "_fallback_intent_profile",
        "_normalize_intent_payload",
        "_classify_query_intent_with_fallback",
        "_infer_tool_from_intent",
        "_infer_tool_from_query",
    )
    infer = fns["_infer_tool_from_query"]
    query = (
        "Retrieve earthquake details from official sources including USGS and ReliefWeb, "
        "then summarize epicenter information."
    )
    chosen = infer(query, {"tavily_search"})
    assert chosen == "tavily_search"


def test_infer_tool_from_query_generalizes_to_other_event_types():
    fns = _load_functions(
        "_contains_any",
        "_count_matches",
        "_is_methodology_reproduction_query",
        "_extract_first_json_dict",
        "_extract_first_json_list",
        "_safe_json_loads",
        "_fallback_intent_profile",
        "_normalize_intent_payload",
        "_classify_query_intent_with_fallback",
        "_infer_tool_from_intent",
        "_infer_tool_from_query",
    )
    infer = fns["_infer_tool_from_query"]
    query = (
        "Retrieve authoritative conflict event details from official sources and summarize "
        "location, timeline, and impacts."
    )
    chosen = infer(query, {"tavily_search", "NTL_download_tool"})
    assert chosen == "tavily_search"
