"""
Web research provider (spec section 39: external RAG sources).

Uses Tavily (https://tavily.com), a search API built for LLM/agent use
that returns clean, citable results (title/url/content/published date)
instead of raw HTML - a much better fit for an evidence-store pipeline
than scraping a generic search engine.

MOCK MODE: without TAVILY_API_KEY, `search()` returns an empty result set
tagged mode="mock" rather than fabricating sources. Downstream reasoning
modules must treat empty live results and mock mode identically: both mean
"state that this could not be independently verified," never "invent a
source."
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.config import get_settings

settings = get_settings()

TAVILY_URL = "https://api.tavily.com/search"


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    published_date: str | None = None


@dataclass
class SearchResponse:
    mode: str  # "live" | "mock"
    query: str
    results: list[SearchResult] = field(default_factory=list)


class SearchClient:
    @property
    def mode(self) -> str:
        return "live" if settings.search_available else "mock"

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        if not settings.search_available:
            return SearchResponse(mode="mock", query=query, results=[])

        payload = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
        }
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(TAVILY_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            # Network/provider failure must degrade to "unverifiable", never crash the module.
            return SearchResponse(mode="live", query=query, results=[])

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                published_date=r.get("published_date"),
            )
            for r in data.get("results", [])
        ]
        return SearchResponse(mode="live", query=query, results=results)


_search_singleton: SearchClient | None = None


def get_search_client() -> SearchClient:
    global _search_singleton
    if _search_singleton is None:
        _search_singleton = SearchClient()
    return _search_singleton
