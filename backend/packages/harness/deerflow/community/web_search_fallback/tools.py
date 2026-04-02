"""
Web search: try Tavily first, fall back to DuckDuckGo on failure or quota.
"""

from __future__ import annotations

import json
import logging

from langchain.tools import tool
from tavily import TavilyClient
from tavily.errors import MissingAPIKeyError

from deerflow.community.ddg_search.tools import _search_text
from deerflow.config import get_app_config

logger = logging.getLogger(__name__)


def _get_tavily_client() -> TavilyClient | None:
    config = get_app_config().get_tool_config("web_search")
    api_key = None
    if config is not None and "api_key" in config.model_extra:
        api_key = config.model_extra.get("api_key")
    if not api_key:
        return None
    return TavilyClient(api_key=api_key)


def _tavily_search_json(query: str, max_results: int) -> str:
    client = _get_tavily_client()
    if client is None:
        raise MissingAPIKeyError()
    res = client.search(query, max_results=max_results)
    normalized_results = [
        {
            "title": result["title"],
            "url": result["url"],
            "snippet": result["content"],
        }
        for result in res["results"]
    ]
    return json.dumps(normalized_results, indent=2, ensure_ascii=False)


def _ddg_search_json(query: str, max_results: int) -> str:
    results = _search_text(query=query, max_results=max_results)
    if not results:
        return json.dumps(
            {"error": "No results found (DuckDuckGo)", "query": query},
            indent=2,
            ensure_ascii=False,
        )
    normalized_results = [
        {
            "title": r.get("title", ""),
            "url": r.get("href", r.get("link", "")),
            "snippet": r.get("body", r.get("snippet", "")),
        }
        for r in results
    ]
    return json.dumps(normalized_results, indent=2, ensure_ascii=False)


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

    prefer_ddg = False
    if config is not None:
        prefer_ddg = config.model_extra.get("search_primary") == "ddg"

    if prefer_ddg:
        logger.info("web_search: primary=DuckDuckGo (config search_primary=ddg)")
        return _ddg_search_json(query, max_results)

    try:
        return _tavily_search_json(query, max_results)
    except MissingAPIKeyError:
        logger.info("web_search: Tavily API key missing, using DuckDuckGo")
        return _ddg_search_json(query, max_results)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        logger.warning("web_search: Tavily failed (%s), falling back to DuckDuckGo", e)
        return _ddg_search_json(query, max_results)
