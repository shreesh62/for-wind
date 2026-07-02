"""Model Router — intelligent task-to-model routing.

All LLM/AI inference in FRIDAY goes through this router.
No direct provider calls from agent logic.

The router:
1. Classifies the task (reasoning, vision, coding, memory, summarization)
2. Selects the best available provider/model
3. Handles failover if primary is unavailable
4. Tracks usage and rate limits
5. Returns standardized responses
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol


class ModelCapability(str, Enum):
    """Task categories for model routing."""

    REASONING = "reasoning"         # General reasoning, planning, analysis
    VISION = "vision"               # Image understanding, screenshot analysis
    CODING = "coding"               # Code generation, debugging
    SUMMARIZATION = "summarization" # Text summarization, distillation
    MEMORY = "memory"               # Memory retrieval, knowledge queries
    CLASSIFICATION = "classification"  # Intent classification, routing
    CONVERSATION = "conversation"   # Conversational responses
    EMBEDDING = "embedding"         # Text embeddings for similarity


@dataclass
class ModelInfo:
    """Information about an available model."""

    provider: str
    model_id: str
    capabilities: List[ModelCapability]
    max_tokens: int = 4096
    supports_streaming: bool = False
    supports_vision: bool = False
    cost_per_1k_tokens: float = 0.0  # 0 = free
    priority: int = 0  # Higher = preferred
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000


@dataclass
class ModelResponse:
    """Standardized response from any model provider."""

    text: str
    model_used: str
    provider: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageRecord:
    """Track model usage for analytics."""

    timestamp: float
    provider: str
    model_id: str
    capability: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


class ModelProvider(Protocol):
    """Protocol that all model providers must implement."""

    @property
    def name(self) -> str:
        """Provider name (e.g., 'groq', 'nvidia_nim')."""
        ...

    @property
    def available(self) -> bool:
        """Whether this provider is currently available."""
        ...

    @property
    def models(self) -> List[ModelInfo]:
        """List of available models from this provider."""
        ...

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
        """Generate a completion."""
        ...

    async def check_health(self) -> bool:
        """Check if provider is responsive."""
        ...


class ModelRouter:
    """Routes inference requests to the best available model.

    Usage:
        router = ModelRouter()
        router.register_provider(groq_provider)
        router.register_provider(nvidia_provider)

        response = await router.complete(
            prompt="Plan the steps to open Chrome",
            capability=ModelCapability.REASONING,
        )
    """

    def __init__(self) -> None:
        self._providers: Dict[str, ModelProvider] = {}
        self._usage_log: List[UsageRecord] = []
        self._rate_trackers: Dict[str, List[float]] = {}  # provider -> timestamps
        self._fallback_order: List[str] = []

    def register_provider(self, provider: ModelProvider) -> None:
        """Register a model provider."""
        self._providers[provider.name] = provider
        self._fallback_order.append(provider.name)

    def set_fallback_order(self, order: List[str]) -> None:
        """Set explicit failover order."""
        self._fallback_order = [p for p in order if p in self._providers]

    def get_available_providers(self) -> List[str]:
        """Get list of currently available providers."""
        return [name for name, p in self._providers.items() if p.available]

    def get_models_for_capability(self, capability: ModelCapability) -> List[ModelInfo]:
        """Get all models that support a given capability, sorted by priority."""
        models: List[ModelInfo] = []
        for provider in self._providers.values():
            if not provider.available:
                continue
            for model in provider.models:
                if capability in model.capabilities:
                    models.append(model)
        models.sort(key=lambda m: m.priority, reverse=True)
        return models

    async def complete(
        self,
        prompt: str,
        *,
        capability: ModelCapability = ModelCapability.REASONING,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Route a completion request to the best available model.

        Routing logic:
        1. If provider specified, use that provider
        2. If model specified, find provider for that model
        3. Otherwise, select best model for the capability
        4. On failure, failover to next provider
        """
        start = time.perf_counter()

        # Determine provider order
        if provider and provider in self._providers:
            providers_to_try = [provider]
        else:
            providers_to_try = self._get_providers_for_capability(capability)

        last_error: Optional[str] = None

        for provider_name in providers_to_try:
            p = self._providers.get(provider_name)
            if not p or not p.available:
                continue

            if self._is_rate_limited(provider_name):
                continue

            # Select the best model for this capability from this provider
            # (unless an explicit model was requested)
            selected_model = model
            if not selected_model:
                selected_model = self._best_model_for(p, capability)

            try:
                response = await p.complete(
                    prompt,
                    model=selected_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    **kwargs,
                )
                latency = (time.perf_counter() - start) * 1000

                self._record_usage(UsageRecord(
                    timestamp=time.time(),
                    provider=provider_name,
                    model_id=response.model_used,
                    capability=capability.value,
                    tokens_in=0,
                    tokens_out=response.tokens_used,
                    latency_ms=latency,
                    success=True,
                ))

                response.latency_ms = latency
                return response

            except Exception as exc:
                last_error = str(exc)
                self._record_usage(UsageRecord(
                    timestamp=time.time(),
                    provider=provider_name,
                    model_id=model or "unknown",
                    capability=capability.value,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    success=False,
                    error=last_error,
                ))
                continue

        # All providers failed
        raise RuntimeError(
            f"All providers failed for capability={capability.value}. "
            f"Last error: {last_error}"
        )

    def get_usage_stats(self, since: Optional[float] = None) -> Dict[str, Any]:
        """Get usage statistics."""
        records = self._usage_log
        if since:
            records = [r for r in records if r.timestamp >= since]

        if not records:
            return {"total_requests": 0}

        by_provider: Dict[str, int] = {}
        total_tokens = 0
        total_latency = 0.0
        failures = 0

        for r in records:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            total_tokens += r.tokens_out
            total_latency += r.latency_ms
            if not r.success:
                failures += 1

        return {
            "total_requests": len(records),
            "total_tokens": total_tokens,
            "avg_latency_ms": total_latency / len(records),
            "failure_rate": failures / len(records),
            "by_provider": by_provider,
        }

    def _best_model_for(self, provider: ModelProvider, capability: ModelCapability) -> Optional[str]:
        """Pick the highest-priority model from a provider for a capability."""
        candidates = [
            m for m in provider.models if capability in m.capabilities
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda m: m.priority)
        return best.model_id

    def _get_providers_for_capability(self, capability: ModelCapability) -> List[str]:
        """Get providers sorted by priority for a capability."""
        scored: List[tuple] = []
        for name in self._fallback_order:
            p = self._providers.get(name)
            if not p or not p.available:
                continue
            max_priority = max(
                (m.priority for m in p.models if capability in m.capabilities),
                default=-1,
            )
            if max_priority >= 0:
                scored.append((max_priority, name))
        scored.sort(reverse=True)
        return [name for _, name in scored]

    def _is_rate_limited(self, provider_name: str) -> bool:
        """Check if provider is currently rate-limited."""
        timestamps = self._rate_trackers.get(provider_name, [])
        now = time.time()
        # Simple sliding window: max 60 requests per minute
        recent = [t for t in timestamps if now - t < 60]
        self._rate_trackers[provider_name] = recent
        return len(recent) >= 55  # Leave some headroom

    def _record_usage(self, record: UsageRecord) -> None:
        """Record a usage event."""
        self._usage_log.append(record)
        # Track rate
        timestamps = self._rate_trackers.setdefault(record.provider, [])
        timestamps.append(record.timestamp)
        # Bound log size
        if len(self._usage_log) > 10000:
            self._usage_log = self._usage_log[-5000:]
