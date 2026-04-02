import json
import logging

from langchain.tools import tool
from tavily import TavilyClient

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)


def _duckduckgo_search_results(
    query: str,
    max_results: int = 5,
    *,
    region: str = "wt-wt",
    safesearch: str = "moderate",
) -> list[dict]:
    """Fallback web search via DuckDuckGo (no API key). Kept local to avoid importing ddg_search.tools (duplicate @tool registration)."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.error("ddgs library not installed. Run: uv add ddgs (or pip install ddgs)")
        return []

    ddgs = DDGS(timeout=30)
    try:
        rows = ddgs.text(
            query,
            region=region,
            safesearch=safesearch,
            max_results=max_results,
        )
        return list(rows) if rows else []
    except Exception as e:
        logger.warning("DuckDuckGo fallback search failed: %s", e)
        return []


def _normalize_ddg_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", r.get("link", "")),
            "snippet": r.get("body", r.get("snippet", "")),
        }
        for r in rows
    ]


def _get_tavily_client() -> TavilyClient:
    config = get_app_config().get_tool_config("web_search")
    api_key = None
    if config is not None and "api_key" in config.model_extra:
        api_key = config.model_extra.get("api_key")
    return TavilyClient(api_key=api_key)


@tool("web_search", parse_docstring=True)
def web_search_tool(query: str) -> str:
    """Search the web.

    Args:
        query: The query to search for.
    """
    config = get_app_config().get_tool_config("web_search")
    max_results = 5
    if config is not None and "max_results" in config.model_extra:
        max_results = config.model_extra.get("max_results")

    normalized_results: list[dict] = []
    try:
        client = _get_tavily_client()
        res = client.search(query, max_results=max_results)
        raw = res.get("results") if isinstance(res, dict) else None
        if not raw:
            raise ValueError("Tavily returned no results")
        normalized_results = [
            {
                "title": result["title"],
                "url": result["url"],
                "snippet": result["content"],
            }
            for result in raw
        ]
    except Exception as e:
        logger.warning("Tavily web_search failed (%s), falling back to DuckDuckGo", e)
        ddg_rows = _duckduckgo_search_results(query, max_results=max_results)
        normalized_results = _normalize_ddg_rows(ddg_rows)
        if not normalized_results:
            return json.dumps(
                {"error": "Web search failed (Tavily and DuckDuckGo)", "query": query},
                indent=2,
                ensure_ascii=False,
            )

    json_results = json.dumps(normalized_results, indent=2, ensure_ascii=False)
    return json_results


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str) -> str:
    """Fetch the contents of a web page at a given URL.
    Only fetch EXACT URLs that have been provided directly by the user or have been returned in results from the web_search and web_fetch tools.
    This tool can NOT access content that requires authentication, such as private Google Docs or pages behind login walls.
    Do NOT add www. to URLs that do NOT have them.
    URLs must include the schema: https://example.com is a valid URL while example.com is an invalid URL.

    Args:
        url: The URL to fetch the contents of.
    """
    client = _get_tavily_client()
    res = client.extract([url])
    if "failed_results" in res and len(res["failed_results"]) > 0:
        return f"Error: {res['failed_results'][0]['error']}"
    elif "results" in res and len(res["results"]) > 0:
        result = res["results"][0]
        return f"# {result['title']}\n\n{result['raw_content'][:4096]}"
    else:
        return "Error: No results found"
