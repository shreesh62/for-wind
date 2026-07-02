"""Groq provider — wraps Groq API behind the ModelProvider protocol.

Groq provides fast inference for open-weight models.
Used as primary reasoning provider in FRIDAY.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.models.router import ModelCapability, ModelInfo, ModelResponse


def _remove_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _clean_output(text: str) -> str:
    """Clean model output of persona prefixes and think blocks."""
    text = _remove_think_blocks(text)
    text = text.replace("Jarvis:", "").replace("JARVIS:", "").replace("Friday:", "").strip()
    return text


@dataclass
class GroqConfig:
    """Configuration for Groq provider."""

    api_key: str = ""
    default_model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1536
    max_retries: int = 3
    retry_backoff: float = 0.8
    timeout: float = 30.0


class GroqProvider:
    """Groq API provider implementing the ModelProvider protocol.

    Supports:
    - Reasoning (primary)
    - Conversation
    - Summarization
    - Classification
    """

    AVAILABLE_MODELS: List[ModelInfo] = [
        ModelInfo(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CONVERSATION,
                ModelCapability.SUMMARIZATION,
                ModelCapability.CLASSIFICATION,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,  # Free tier
            priority=5,  # Lower priority — NVIDIA preferred
            rate_limit_rpm=30,
            rate_limit_tpm=100000,
        ),
        ModelInfo(
            provider="groq",
            model_id="llama-3.1-8b-instant",
            capabilities=[
                ModelCapability.CONVERSATION,
                ModelCapability.CLASSIFICATION,
                ModelCapability.SUMMARIZATION,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=3,  # Fallback only
            rate_limit_rpm=60,
            rate_limit_tpm=200000,
        ),
        ModelInfo(
            provider="groq",
            model_id="mixtral-8x7b-32768",
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CODING,
                ModelCapability.CONVERSATION,
            ],
            max_tokens=32768,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=4,  # Fallback
            rate_limit_rpm=30,
            rate_limit_tpm=100000,
        ),
    ]

    def __init__(self, config: Optional[GroqConfig] = None) -> None:
        self._config = config or GroqConfig()
        self._client = None
        self._available = False
        self._last_error: Optional[str] = None
        self._init_client()

    @property
    def name(self) -> str:
        return "groq"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def models(self) -> List[ModelInfo]:
        return self.AVAILABLE_MODELS

    def _init_client(self) -> None:
        """Initialize the Groq client."""
        api_key = self._config.api_key or os.getenv("GROQ_API_KEY", "")
        if not api_key:
            self._available = False
            self._last_error = "GROQ_API_KEY not set"
            return

        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
            self._available = True
        except ImportError:
            self._available = False
            self._last_error = "groq package not installed"
        except Exception as exc:
            self._available = False
            self._last_error = str(exc)

    async def complete(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate a completion via Groq API.

        Note: Groq's Python client is synchronous, so we run it directly.
        For true async, we'd use httpx against the REST API.
        """
        if not self._available or not self._client:
            raise RuntimeError(f"Groq provider unavailable: {self._last_error}")

        model_id = model or self._config.default_model
        sys_content = system_prompt or (
            "You are FRIDAY, an intelligent AI assistant. "
            "Be concise, accurate, and helpful."
        )

        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt},
        ]

        last_error: Optional[str] = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                start = time.perf_counter()
                response = self._client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency = (time.perf_counter() - start) * 1000

                raw_text = (response.choices[0].message.content or "").strip()
                cleaned = _clean_output(raw_text)
                text = cleaned if cleaned else raw_text

                tokens_used = 0
                if hasattr(response, "usage") and response.usage:
                    tokens_used = getattr(response.usage, "total_tokens", 0)

                return ModelResponse(
                    text=text,
                    model_used=model_id,
                    provider="groq",
                    tokens_used=tokens_used,
                    latency_ms=latency,
                    metadata={
                        "finish_reason": getattr(
                            response.choices[0], "finish_reason", None
                        ),
                    },
                )

            except Exception as exc:
                last_error = str(exc)
                if attempt < self._config.max_retries:
                    time.sleep(self._config.retry_backoff * attempt)
                    # Recreate client on connection errors
                    if "connection" in last_error.lower() or "protocol" in last_error.lower():
                        self._init_client()
                    continue

        raise RuntimeError(f"Groq API failed after {self._config.max_retries} attempts: {last_error}")

    async def check_health(self) -> bool:
        """Check if Groq is responsive."""
        if not self._available:
            return False
        try:
            await self.complete("ping", max_tokens=5, temperature=0)
            return True
        except Exception:
            return False
