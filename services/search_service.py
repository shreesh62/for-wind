"""Simple web search abstraction using DuckDuckGo Instant Answer API."""

from __future__ import annotations

import requests

from config import get_settings

_DDG_URL = "https://api.duckduckgo.com/"


def web_search(query: str, *, max_results: int = 5) -> str:
    """Return a concise summary of search results for the given query."""

    if not query:
        return "Please tell me what to search for."

    settings = get_settings()
    _ = settings.search_api_key  # placeholder for future providers

    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    }

    try:
        response = requests.get(_DDG_URL, params=params, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure paths
        return f"Web search is unavailable at the moment ({exc})."

    payload = response.json()
    abstract = payload.get("AbstractText")
    if abstract:
        return abstract

    related = payload.get("RelatedTopics") or []
    snippets = []
    for topic in related:
        if isinstance(topic, dict) and topic.get("Text"):
            snippets.append(topic["Text"])
        elif isinstance(topic, dict) and topic.get("Topics"):
            for sub in topic["Topics"]:
                if sub.get("Text"):
                    snippets.append(sub["Text"])
        if len(snippets) >= max_results:
            break

    if not snippets:
        return "I couldn't find much on that topic."

    header = f"Here's what I found about {query}:"
    return "\n".join([header, *snippets[:max_results]])
