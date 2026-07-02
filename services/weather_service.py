# weather_service.py
import os
import time
from typing import Dict, Tuple

import requests

from config import get_settings

_WEATHER_BASE = os.getenv("WEATHER_BASE", "http://api.weatherapi.com")
BASE_URL = f"{_WEATHER_BASE.rstrip('/')}/v1/current.json"
_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE: Dict[str, Tuple[float, str]] = {}
_LAST_REPORT: Tuple[float, str, str] | None = None  # (timestamp, location, message)


def get_weather(location: str) -> str:
    settings = get_settings()
    api_key = settings.weather_api_key

    if not api_key:
        return "Weather service is not configured. Please set WEATHER_API_KEY in your environment."

    key = location.lower().strip()
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]

    global _LAST_REPORT

    try:
        url = f"{BASE_URL}?key={api_key}&q={location}&aqi=no"
        for attempt in range(2):
            resp = requests.get(url, timeout=5)
            if resp.status_code >= 500 and attempt == 0:
                time.sleep(1)
                continue
            data = resp.json()
            break
        else:
            data = resp.json()

        if "error" in data:
            return f"I couldn’t fetch weather for {location}. {data['error']['message']}"

        current = data.get("current", {})
        cond = current.get("condition", {}).get("text", "unknown conditions")
        temp_c = current.get("temp_c")
        feels = current.get("feelslike_c")
        humidity = current.get("humidity")
        wind_kph = current.get("wind_kph")

        parts = [f"The weather in {location.title()} is {cond}"]
        if temp_c is not None:
            parts.append(f"{temp_c}°C")
        if feels is not None:
            parts.append(f"feels like {feels}°C")
        if humidity is not None:
            parts.append(f"humidity {humidity}%")
        if wind_kph is not None:
            parts.append(f"winds {wind_kph} km/h")

        message = ", ".join(parts) + "."
        _CACHE[key] = (now, message)
        _LAST_REPORT = (now, location.title(), message)
        return message
    except Exception as e:
        return f"Error fetching weather: {e}"


def get_last_weather_report() -> dict | None:
    if not _LAST_REPORT:
        return None
    ts, location, message = _LAST_REPORT
    return {"timestamp": ts, "location": location, "message": message}
