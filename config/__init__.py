"""Configuration package providing access to static resources and settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:  # Optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> None:  # type: ignore
        return None

PACKAGE_ROOT = Path(__file__).resolve().parent

CAPABILITIES_FILE = PACKAGE_ROOT / "capabilities.json"

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Settings resolved from environment variables (with defaults)."""

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    weather_api_key: str = os.getenv("WEATHER_API_KEY", "")
    distance_api_key: str = os.getenv("DISTANCEMATRIX_API_KEY", "")
    geocoding_api_key: str = os.getenv("GEOCODING_API_KEY", "")
    porcupine_access_key: str = os.getenv("PORCUPINE_ACCESS_KEY", "")
    jarvis_access_key: str = os.getenv("JARVIS_ACCESS_KEY", "")
    listen_access_key: str = os.getenv("LISTEN_ACCESS_KEY", "")
    remote_api_key: str = os.getenv("REMOTE_API_KEY", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


__all__ = ["Settings", "get_settings", "PACKAGE_ROOT", "CAPABILITIES_FILE"]
