"""NVIDIA NIM provider — wraps NVIDIA NIM free API endpoints.

NVIDIA NIM provides free inference for many models. The registry below lists only
models VERIFIED responsive on the free tier (latency-probed); catalog membership
alone is not enough — some listed models hang, return HTTP 410/404, or emit empty
content via a separate reasoning channel. Representative verified models:
- Reasoning/coding/prose: openai/gpt-oss-120b, mistralai/mistral-medium-3.5-128b
- Fast/light: openai/gpt-oss-20b
- Coding: qwen/qwen3.5-397b-a17b
- Vision: meta/llama-3.2-90b-vision-instruct
- Safety: meta/llama-guard-4-12b
- Embedding: nvidia/nv-embed-v1

All accessed via OpenAI-compatible API at integrate.api.nvidia.com.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from friday.models.router import ModelCapability, ModelInfo, ModelResponse


NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"


@dataclass
class NvidiaConfig:
    """Configuration for NVIDIA NIM provider."""

    api_key: str = ""
    base_url: str = NVIDIA_API_BASE
    # gpt-oss-120b is the responsive default: on the free NIM tier it answers in
    # ~1-2s with clean output. The former default (meta/llama-3.3-70b-instruct)
    # now hangs to timeout on the free tier (verified 2024), so it must not be the
    # default or a routing target.
    default_model: str = "openai/gpt-oss-120b"
    max_retries: int = 2
    timeout: float = 60.0


class NvidiaProvider:
    """NVIDIA NIM API provider implementing the ModelProvider protocol.

    Uses OpenAI-compatible chat completions endpoint.
    Supports vision, reasoning, coding, summarization, and embedding.
    """

    AVAILABLE_MODELS: List[ModelInfo] = [
        # --- Reasoning / Decomposition (Tier 1: fast + accurate, verified) ---
        # NOTE (free-tier availability, verified 2024): three formerly-listed models
        # became unusable on the free NIM endpoint and were removed —
        #   * qwen/qwen3-next-80b-a3b-instruct  — hangs to timeout
        #   * meta/llama-3.3-70b-instruct       — hangs to timeout
        #   * qwen/qwen3-coder-480b-a35b-instruct — HTTP 410 Gone (retired)
        # The gpt-oss models below are the responsive general reasoning/coding tier
        # (~1-2s). gpt-oss-120b is the top general model (reasoning + coding + prose);
        # gpt-oss-20b is the fast lightweight option.
        # gpt-oss-120b — strong reasoning + coding + prose, ~1.7s, clean output.
        ModelInfo(
            provider="nvidia",
            model_id="openai/gpt-oss-120b",
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CODING,
                ModelCapability.CONVERSATION,
                ModelCapability.SUMMARIZATION,
                ModelCapability.CLASSIFICATION,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=10,
            rate_limit_rpm=30,
        ),
        # gpt-oss-20b — fast lightweight reasoning/classification (~1.7s).
        ModelInfo(
            provider="nvidia",
            model_id="openai/gpt-oss-20b",
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CLASSIFICATION,
                ModelCapability.SUMMARIZATION,
                ModelCapability.CONVERSATION,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=9,
            rate_limit_rpm=40,
        ),
        # mistral-medium-3.5-128b — very fast (~1.0s), clean output. A reasoning /
        # content FAILOVER below the gpt-oss primaries: the free tier intermittently
        # returns 503 "all workers busy", so a second healthy general model matters.
        ModelInfo(
            provider="nvidia",
            model_id="mistralai/mistral-medium-3.5-128b",
            capabilities=[
                ModelCapability.REASONING,
                ModelCapability.CONVERSATION,
                ModelCapability.SUMMARIZATION,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=8,
            rate_limit_rpm=30,
        ),
        # qwen3.5-397b-a17b — large sparse MoE (17B active), ~1.1s, clean output.
        # Strong dedicated CODING model (failover below gpt-oss-120b for coding).
        ModelInfo(
            provider="nvidia",
            model_id="qwen/qwen3.5-397b-a17b",
            capabilities=[
                ModelCapability.CODING,
                ModelCapability.REASONING,
            ],
            max_tokens=8192,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=7,
            rate_limit_rpm=20,
        ),
        # NOTE: several catalog models were probed and rejected — they return EMPTY
        # `content` because they emit into a separate reasoning channel our extractor
        # does not read (minimaxai/minimax-m2.7, nvidia/llama-3.3-nemotron-super-49b-v1.5,
        # stepfun-ai/step-3.7-flash, nvidia/nvidia-nemotron-nano-9b-v2). Do not add them
        # to the general path without handling the reasoning-channel response shape.
        # --- Safety / Content Moderation (verified) ---
        # Used to gate risky actions (send/email/post) and screen generated
        # content before delivery. See ADR for the safety gate.
        ModelInfo(
            provider="nvidia",
            model_id="meta/llama-guard-4-12b",
            capabilities=[ModelCapability.CLASSIFICATION],
            max_tokens=2048,
            supports_streaming=False,
            cost_per_1k_tokens=0.0,
            priority=10,
            rate_limit_rpm=40,
        ),
        ModelInfo(
            provider="nvidia",
            model_id="nvidia/nemotron-content-safety-reasoning-4b",
            capabilities=[ModelCapability.CLASSIFICATION],
            max_tokens=2048,
            supports_streaming=False,
            cost_per_1k_tokens=0.0,
            priority=8,
            rate_limit_rpm=60,
        ),
        # --- Vision ---
        ModelInfo(
            provider="nvidia",
            model_id="meta/llama-3.2-90b-vision-instruct",
            capabilities=[ModelCapability.VISION, ModelCapability.REASONING],
            max_tokens=4096,
            supports_streaming=False,
            supports_vision=True,
            cost_per_1k_tokens=0.0,
            priority=10,
            rate_limit_rpm=20,
        ),
        ModelInfo(
            provider="nvidia",
            model_id="microsoft/phi-4-multimodal-instruct",
            capabilities=[ModelCapability.VISION, ModelCapability.REASONING],
            max_tokens=4096,
            supports_streaming=False,
            supports_vision=True,
            cost_per_1k_tokens=0.0,
            priority=7,
            rate_limit_rpm=20,
        ),
        # --- Coding ---
        # NOTE: qwen/qwen3-coder-480b-a35b-instruct was removed — the free NIM
        # endpoint returns HTTP 410 Gone. Coding is covered by gpt-oss-120b above
        # (which carries ModelCapability.CODING).
        # --- Fast/Light ---
        ModelInfo(
            provider="nvidia",
            model_id="nvidia/nemotron-mini-4b-instruct",
            capabilities=[
                ModelCapability.CLASSIFICATION,
                ModelCapability.SUMMARIZATION,
            ],
            max_tokens=4096,
            supports_streaming=True,
            cost_per_1k_tokens=0.0,
            priority=3,
            rate_limit_rpm=60,
        ),
        # --- Embedding ---
        ModelInfo(
            provider="nvidia",
            model_id="nvidia/nv-embed-v1",
            capabilities=[ModelCapability.EMBEDDING],
            max_tokens=512,
            supports_streaming=False,
            cost_per_1k_tokens=0.0,
            priority=10,
            rate_limit_rpm=60,
        ),
    ]

    def __init__(self, config: Optional[NvidiaConfig] = None) -> None:
        self._config = config or NvidiaConfig()
        self._available = False
        self._last_error: Optional[str] = None
        self._check_availability()

    @property
    def name(self) -> str:
        return "nvidia"

    @property
    def available(self) -> bool:
        return self._available

    @property
    def models(self) -> List[ModelInfo]:
        return self.AVAILABLE_MODELS

    def _check_availability(self) -> None:
        """Check if provider can be used."""
        from friday.models.credentials import resolve_secret

        api_key = self._config.api_key or resolve_secret("NVIDIA_API_KEY")
        if not api_key:
            self._available = False
            self._last_error = "NVIDIA_API_KEY not set"
            return

        if httpx is None:
            self._available = False
            self._last_error = "httpx package not installed"
            return

        self._available = True

    def _get_api_key(self) -> str:
        """Get API key from config or the SecretVault (env fallback)."""
        from friday.models.credentials import resolve_secret

        return self._config.api_key or resolve_secret("NVIDIA_API_KEY")

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
        """Generate a completion via NVIDIA NIM API.

        Uses OpenAI-compatible chat completions endpoint.
        """
        if not self._available:
            raise RuntimeError(f"NVIDIA provider unavailable: {self._last_error}")

        api_key = self._get_api_key()
        model_id = model or self._config.default_model

        sys_content = system_prompt or (
            "You are FRIDAY, an intelligent AI assistant. "
            "Be concise, accurate, and helpful."
        )

        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt},
        ]

        # Handle vision requests with image content
        if "image_url" in kwargs:
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": kwargs["image_url"]}},
                ],
            }

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._config.base_url}/chat/completions"

        last_error: Optional[str] = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                start = time.perf_counter()
                async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)

                latency = (time.perf_counter() - start) * 1000

                if response.status_code == 429:
                    # Rate limited — wait and retry
                    retry_after = float(response.headers.get("Retry-After", "2"))
                    if attempt < self._config.max_retries:
                        import asyncio
                        await asyncio.sleep(retry_after)
                        continue
                    raise RuntimeError("Rate limited by NVIDIA NIM API")

                if response.status_code != 200:
                    error_body = response.text[:200]
                    raise RuntimeError(
                        f"NVIDIA API returned {response.status_code}: {error_body}"
                    )

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("No choices returned from NVIDIA API")

                text = (choices[0].get("message", {}).get("content", "") or "").strip()
                usage = data.get("usage", {})
                tokens_used = usage.get("total_tokens", 0)

                return ModelResponse(
                    text=text,
                    model_used=model_id,
                    provider="nvidia",
                    tokens_used=tokens_used,
                    latency_ms=latency,
                    metadata={
                        "finish_reason": choices[0].get("finish_reason"),
                        "usage": usage,
                    },
                )

            except RuntimeError:
                raise
            except Exception as exc:
                exc_str = str(exc)
                if "timed out" in exc_str.lower() or "timeout" in exc_str.lower():
                    last_error = "Request timed out"
                else:
                    last_error = exc_str
                if attempt < self._config.max_retries:
                    import asyncio
                    await asyncio.sleep(1.0 * attempt)
                    continue
                    await asyncio.sleep(1.0 * attempt)
                    continue

        raise RuntimeError(
            f"NVIDIA NIM API failed after {self._config.max_retries} attempts: {last_error}"
        )

    async def check_health(self) -> bool:
        """Check if NVIDIA NIM API is responsive."""
        if not self._available:
            return False
        try:
            # Use a lightweight model for health check
            await self.complete(
                "Hi",
                model="nvidia/nemotron-mini-4b-instruct",
                max_tokens=5,
                temperature=0,
            )
            return True
        except Exception:
            return False

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generate embeddings via NVIDIA NIM embedding API.

        Args:
            text: Text to embed
            model: Embedding model (defaults to nv-embed-v1)

        Returns:
            List of floats (embedding vector)
        """
        if not self._available:
            raise RuntimeError(f"NVIDIA provider unavailable: {self._last_error}")

        api_key = self._get_api_key()
        model_id = model or "nvidia/nv-embed-v1"

        payload = {
            "model": model_id,
            "input": [text],
            "input_type": "query",
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._config.base_url}/embeddings"

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise RuntimeError(
                f"NVIDIA embedding API returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        embeddings = data.get("data", [])
        if not embeddings:
            raise RuntimeError("No embeddings returned")

        return embeddings[0].get("embedding", [])
