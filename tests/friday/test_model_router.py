"""Tests for friday.models.router — ModelRouter and routing logic."""

import asyncio
import time
import pytest

from friday.models.router import (
    ModelCapability,
    ModelInfo,
    ModelResponse,
    ModelRouter,
)


class MockProvider:
    """Mock model provider for testing."""

    def __init__(
        self,
        name: str = "mock",
        available: bool = True,
        models: list = None,
        fail: bool = False,
    ):
        self._name = name
        self._available = available
        self._models = models or [
            ModelInfo(
                provider=name,
                model_id=f"{name}-model",
                capabilities=[ModelCapability.REASONING, ModelCapability.CONVERSATION],
                priority=5,
            )
        ]
        self._fail = fail
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return self._available

    @property
    def models(self) -> list:
        return self._models

    async def complete(self, prompt, *, model=None, max_tokens=1024,
                       temperature=0.7, system_prompt=None, **kwargs):
        self.call_count += 1
        if self._fail:
            raise RuntimeError(f"Provider {self._name} failed")
        return ModelResponse(
            text=f"Response from {self._name}",
            model_used=model or self._models[0].model_id,
            provider=self._name,
            tokens_used=50,
        )

    async def check_health(self) -> bool:
        return self._available


class TestModelRouter:
    """Test ModelRouter routing and failover behavior."""

    def _run(self, coro):
        """Helper to run async tests."""
        return asyncio.get_event_loop().run_until_complete(coro)

    @pytest.fixture(autouse=True)
    def setup_loop(self):
        """Ensure event loop exists."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_register_provider(self):
        """Router accepts provider registration."""
        router = ModelRouter()
        provider = MockProvider(name="test")
        router.register_provider(provider)

        assert "test" in router.get_available_providers()

    def test_basic_routing(self):
        """Router routes to registered provider."""
        router = ModelRouter()
        provider = MockProvider(name="groq")
        router.register_provider(provider)

        response = self._run(router.complete(
            "Hello", capability=ModelCapability.REASONING
        ))

        assert response.text == "Response from groq"
        assert response.provider == "groq"
        assert provider.call_count == 1

    def test_failover(self):
        """Router fails over to next provider on error."""
        router = ModelRouter()
        primary = MockProvider(name="primary", fail=True)
        fallback = MockProvider(name="fallback", fail=False)

        router.register_provider(primary)
        router.register_provider(fallback)

        response = self._run(router.complete(
            "Hello", capability=ModelCapability.REASONING
        ))

        assert response.provider == "fallback"
        assert primary.call_count == 1
        assert fallback.call_count == 1

    def test_all_providers_fail(self):
        """Router raises when all providers fail."""
        router = ModelRouter()
        router.register_provider(MockProvider(name="p1", fail=True))
        router.register_provider(MockProvider(name="p2", fail=True))

        with pytest.raises(RuntimeError, match="All providers failed"):
            self._run(router.complete("Hello"))

    def test_unavailable_provider_skipped(self):
        """Unavailable providers are skipped."""
        router = ModelRouter()
        router.register_provider(MockProvider(name="down", available=False))
        router.register_provider(MockProvider(name="up", available=True))

        response = self._run(router.complete("Hello"))
        assert response.provider == "up"

    def test_explicit_provider_selection(self):
        """Can request a specific provider."""
        router = ModelRouter()
        router.register_provider(MockProvider(name="groq"))
        router.register_provider(MockProvider(name="nvidia"))

        response = self._run(router.complete(
            "Hello", provider="nvidia"
        ))
        assert response.provider == "nvidia"

    def test_capability_filtering(self):
        """Router selects models based on capability."""
        router = ModelRouter()

        vision_provider = MockProvider(
            name="vision",
            models=[ModelInfo(
                provider="vision",
                model_id="clip-model",
                capabilities=[ModelCapability.VISION],
                priority=10,
            )],
        )
        text_provider = MockProvider(
            name="text",
            models=[ModelInfo(
                provider="text",
                model_id="llama-model",
                capabilities=[ModelCapability.REASONING],
                priority=5,
            )],
        )

        router.register_provider(vision_provider)
        router.register_provider(text_provider)

        response = self._run(router.complete(
            "Describe image", capability=ModelCapability.VISION
        ))
        assert response.provider == "vision"

    def test_usage_stats(self):
        """Usage stats track requests."""
        router = ModelRouter()
        router.register_provider(MockProvider(name="groq"))

        self._run(router.complete("Hello"))
        self._run(router.complete("World"))

        stats = router.get_usage_stats()
        assert stats["total_requests"] == 2
        assert stats["by_provider"]["groq"] == 2

    def test_get_models_for_capability(self):
        """Can query available models for a capability."""
        router = ModelRouter()
        router.register_provider(MockProvider(
            name="multi",
            models=[
                ModelInfo(provider="multi", model_id="m1",
                         capabilities=[ModelCapability.REASONING], priority=5),
                ModelInfo(provider="multi", model_id="m2",
                         capabilities=[ModelCapability.VISION], priority=10),
            ],
        ))

        reasoning_models = router.get_models_for_capability(ModelCapability.REASONING)
        assert len(reasoning_models) == 1
        assert reasoning_models[0].model_id == "m1"

    def test_selects_highest_priority_model(self):
        """Router selects the highest-priority model for a capability."""
        router = ModelRouter()
        provider = MockProvider(
            name="multi",
            models=[
                ModelInfo(provider="multi", model_id="low-model",
                         capabilities=[ModelCapability.REASONING], priority=3),
                ModelInfo(provider="multi", model_id="high-model",
                         capabilities=[ModelCapability.REASONING], priority=9),
            ],
        )
        router.register_provider(provider)

        best = router._best_model_for(provider, ModelCapability.REASONING)
        assert best == "high-model"
