from langchain_tavily import TavilySearch
Tavily_search = TavilySearch(
    topic="general",
    max_results=5,
    search_depth="advanced",
    auto_parameters=True,
    include_favicon=True,
    include_images=False,
)