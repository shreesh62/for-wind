"""Central configuration for Jarvis assistant."""

from dataclasses import dataclass
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv, find_dotenv


_env_path = Path(__file__).resolve().parent / ".env"
if not load_dotenv(dotenv_path=_env_path, override=True):
    _found = find_dotenv(filename=".env", usecwd=True)
    if _found:
        load_dotenv(_found, override=True)


@dataclass(frozen=True)
class Settings:
    """Settings resolved from environment variables with sensible defaults."""

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    weather_api_key: str = os.getenv("WEATHER_API_KEY", "")
    distance_api_key: str = os.getenv("DISTANCEMATRIX_API_KEY", "")
    geocoding_api_key: str = os.getenv("GEOCODING_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    porcupine_access_key: str = os.getenv("PORCUPINE_ACCESS_KEY", "")
    jarvis_access_key: str = os.getenv("JARVIS_ACCESS_KEY", "")
    listen_access_key: str = os.getenv("LISTEN_ACCESS_KEY", "")
    remote_api_key: str = os.getenv("REMOTE_API_KEY", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()