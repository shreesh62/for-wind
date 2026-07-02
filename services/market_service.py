"""Utility helpers for stock and crypto quotes via Yahoo Finance."""

from __future__ import annotations

from typing import Iterable

import requests

from config import get_settings

_YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"


def get_quote(symbol: str) -> str:
    """Return a human-readable summary for the requested ticker symbol."""

    if not symbol:
        return "Please specify a ticker symbol, for example AAPL or BTC-USD."

    settings = get_settings()
    _ = settings.market_api_key  # Reserved for future premium providers

    params = {"symbols": symbol.upper().strip()}
    try:
        response = requests.get(_YAHOO_QUOTE_URL, params=params, timeout=6)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure paths
        return f"I couldn't reach the market data service ({exc})."

    payload = response.json()
    results: Iterable[dict] = payload.get("quoteResponse", {}).get("result", [])
    if not results:
        return f"I couldn't find market data for {symbol.upper()}."

    record = next(iter(results))
    name = record.get("longName") or record.get("shortName") or symbol.upper()
    price = record.get("regularMarketPrice")
    change = record.get("regularMarketChange")
    percent = record.get("regularMarketChangePercent")
    market_time = record.get("regularMarketTime")

    if price is None:
        return f"Quote data for {name} is currently unavailable."

    change_str = ""
    if change is not None and percent is not None:
        change_str = f" ({change:+.2f}, {percent:+.2f}%)"
    elif change is not None:
        change_str = f" ({change:+.2f})"

    timestamp = ""
    if market_time:
        from datetime import datetime

        ts = datetime.fromtimestamp(market_time)
        timestamp = f" as of {ts:%Y-%m-%d %H:%M}"  # local time

    currency = record.get("currency") or ""
    currency_str = f" {currency}" if currency else ""
    return f"{name} is trading at {price:.2f}{currency_str}{change_str}{timestamp}."
