"""Lightweight client for fetching news headlines via GNews API."""

from __future__ import annotations

from typing import Iterable

import requests

from config import get_settings

_GNEWS_URL = "https://gnews.io/api/v4/top-headlines"


def fetch_headlines(topic: str | None = None, *, max_results: int = 5, language: str = "en") -> str:
    """Return a formatted news digest for the requested topic.

    Falls back to a generic headline list if no topic is provided. Requires
    ``NEWS_API_KEY`` to be set in the environment.
    """

    settings = get_settings()
    api_key = settings.news_api_key
    if not api_key:
        return "News service is not configured yet. Please add NEWS_API_KEY to your environment."

    params = {
        "token": api_key,
        "lang": language,
        "max": max(1, min(max_results, 10)),
    }
    if topic:
        params["q"] = topic

    try:
        response = requests.get(_GNEWS_URL, params=params, timeout=6)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure paths
        return f"Unable to reach the news service right now ({exc})."

    payload = response.json()
    articles: Iterable[dict] = payload.get("articles", []) or []
    if not articles:
        return "I couldn't find any recent headlines for that topic."

    lines = []
    for article in list(articles)[: params["max"]]:
        title = article.get("title") or "Untitled"
        source = article.get("source", {}).get("name") or "Unknown source"
        url = article.get("url") or ""
        lines.append(f"• {title} ({source}){f' — {url}' if url else ''}")

    header = f"Here are the latest headlines{f' about {topic}' if topic else ''}:"
    return "\n".join([header, *lines])
