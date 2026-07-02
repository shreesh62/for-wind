"""Tests for friday.models.providers — Groq and NVIDIA providers.

Uses mocks to avoid real API calls. Integration tests that require
real API keys are marked with @pytest.mark.integration.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from friday.models.router import ModelCapability, ModelResponse, ModelRouter
from friday.models.providers.groq_provider import GroqProvider, GroqConfig
from friday.models.providers.nvidia_provider import NvidiaProvider, NvidiaConfig


def _run(coro):
    """Helper to run async coroutines in tests."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestGroqProvider:
    """Test Groq provider behavior."""

    def test_unavailable_without_api_key(self):
        """Provider reports unavailable when no API key."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure no key in env
            env_copy = os.environ.copy()
            env_copy.pop("GROQ_API_KEY", None)
            with patch.dict(os.environ, env_copy, clear=True):
                config = GroqConfig(api_key="")
                provider = GroqProvider(config=config)
                assert provider.available is False

    def test_provider_name(self):
        """Provider reports correct name."""
        config = GroqConfig(api_key="test-key")
        with patch("friday.models.providers.groq_provider.GroqProvider._init_client"):
            provider = GroqProvider.__new__(GroqProvider)
            provider._config = config
            provider._available = True
            provider._client = None
            provider._last_error = None
            assert provider.name == "groq"

    def test_models_list(self):
        """Provider exposes available models."""
        models = GroqProvider.AVAILABLE_MODELS
        assert len(models) >= 3

        # Check primary model has reasoning capability
        primary = next(m for m in models if "70b" in m.model_id)
        assert ModelCapability.REASONING in primary.capabilities
        assert primary.provider == "groq"

    def test_complete_with_mock_client(self):
        """Provider returns ModelResponse on successful completion."""
        config = GroqConfig(api_key="test-key")
        provider = GroqProvider.__new__(GroqProvider)
        provider._config = config
        provider._available = True
        provider._last_error = None

        # Mock the Groq client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello! I'm FRIDAY."
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 42

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        result = _run(provider.complete("Hello", max_tokens=100))

        assert isinstance(result, ModelResponse)
        assert "FRIDAY" in result.text
        assert result.provider == "groq"
        assert result.tokens_used == 42
        assert result.latency_ms > 0

    def test_complete_cleans_output(self):
        """Provider removes think blocks and persona prefixes."""
        config = GroqConfig(api_key="test-key")
        provider = GroqProvider.__new__(GroqProvider)
        provider._config = config
        provider._available = True
        provider._last_error = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "<think>reasoning here</think>JARVIS: The weather is nice."
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 20

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        result = _run(provider.complete("What's the weather?"))

        assert "think" not in result.text
        assert "JARVIS:" not in result.text
        assert "weather is nice" in result.text

    def test_complete_retries_on_error(self):
        """Provider retries on transient errors."""
        config = GroqConfig(api_key="test-key", max_retries=3, retry_backoff=0.01)
        provider = GroqProvider.__new__(GroqProvider)
        provider._config = config
        provider._available = True
        provider._last_error = None

        # First call fails, second succeeds
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Success"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            RuntimeError("Temporary failure"),
            mock_response,
        ]
        provider._client = mock_client

        # Patch _init_client so it doesn't recreate a real client
        with patch.object(provider, '_init_client'):
            result = _run(provider.complete("Test"))
        assert result.text == "Success"
        assert mock_client.chat.completions.create.call_count == 2

    def test_complete_raises_after_max_retries(self):
        """Provider raises after exhausting retries."""
        config = GroqConfig(api_key="test-key", max_retries=2, retry_backoff=0.01)
        provider = GroqProvider.__new__(GroqProvider)
        provider._config = config
        provider._available = True
        provider._last_error = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Persistent error")
        provider._client = mock_client

        with pytest.raises(RuntimeError, match="Persistent error"):
            _run(provider.complete("Test"))


class TestNvidiaProvider:
    """Test NVIDIA NIM provider behavior."""

    def test_unavailable_without_api_key(self):
        """Provider reports unavailable when no API key."""
        env_copy = os.environ.copy()
        env_copy.pop("NVIDIA_API_KEY", None)
        with patch.dict(os.environ, env_copy, clear=True):
            config = NvidiaConfig(api_key="")
            provider = NvidiaProvider(config=config)
            assert provider.available is False

    def test_available_with_api_key(self):
        """Provider reports available when API key is set."""
        config = NvidiaConfig(api_key="nvapi-test-key")
        provider = NvidiaProvider(config=config)
        assert provider.available is True

    def test_provider_name(self):
        """Provider reports correct name."""
        config = NvidiaConfig(api_key="nvapi-test")
        provider = NvidiaProvider(config=config)
        assert provider.name == "nvidia"

    def test_models_include_vision(self):
        """Provider exposes vision-capable models."""
        models = NvidiaProvider.AVAILABLE_MODELS
        vision_models = [m for m in models if ModelCapability.VISION in m.capabilities]
        assert len(vision_models) >= 2
        assert any("vision" in m.model_id for m in vision_models)

    def test_models_include_coding(self):
        """Provider exposes coding-capable models."""
        models = NvidiaProvider.AVAILABLE_MODELS
        coding_models = [m for m in models if ModelCapability.CODING in m.capabilities]
        assert len(coding_models) >= 1

    def test_models_include_embedding(self):
        """Provider exposes embedding model."""
        models = NvidiaProvider.AVAILABLE_MODELS
        embed_models = [m for m in models if ModelCapability.EMBEDDING in m.capabilities]
        assert len(embed_models) >= 1

    @patch("friday.models.providers.nvidia_provider.httpx")
    def test_complete_success(self, mock_httpx):
        """Provider returns ModelResponse on successful API call."""
        config = NvidiaConfig(api_key="nvapi-test")
        provider = NvidiaProvider(config=config)

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "The answer is 42."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 30, "prompt_tokens": 10, "completion_tokens": 20},
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        mock_httpx.AsyncClient.return_value = mock_client_instance

        result = _run(provider.complete("What is the meaning of life?"))

        assert isinstance(result, ModelResponse)
        assert result.text == "The answer is 42."
        assert result.provider == "nvidia"
        assert result.tokens_used == 30
        assert result.latency_ms > 0

    @patch("friday.models.providers.nvidia_provider.httpx")
    def test_complete_rate_limited(self, mock_httpx):
        """Provider handles 429 rate limit responses."""
        config = NvidiaConfig(api_key="nvapi-test", max_retries=2)
        provider = NvidiaProvider(config=config)

        # First call: 429, second call: success
        mock_rate_limited = MagicMock()
        mock_rate_limited.status_code = 429
        mock_rate_limited.headers = {"Retry-After": "0.01"}

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [mock_rate_limited, mock_success]
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        mock_httpx.AsyncClient.return_value = mock_client_instance

        result = _run(provider.complete("Test"))
        assert result.text == "OK"

    @patch("friday.models.providers.nvidia_provider.httpx")
    def test_complete_api_error(self, mock_httpx):
        """Provider raises on non-200 responses after retries."""
        config = NvidiaConfig(api_key="nvapi-test", max_retries=1)
        provider = NvidiaProvider(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        mock_httpx.AsyncClient.return_value = mock_client_instance

        with pytest.raises(RuntimeError, match="500"):
            _run(provider.complete("Test"))


class TestRouterWithProviders:
    """Test ModelRouter integration with real provider classes."""

    def test_router_with_groq_provider(self):
        """Router works with Groq provider registration."""
        router = ModelRouter()

        # Create provider with mock
        provider = GroqProvider.__new__(GroqProvider)
        provider._config = GroqConfig(api_key="test")
        provider._available = True
        provider._last_error = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 10
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        provider._client = mock_client

        router.register_provider(provider)

        result = _run(router.complete("Hi", capability=ModelCapability.REASONING))
        assert result.provider == "groq"
        assert result.text == "Hello"

    def test_router_failover_groq_to_nvidia(self):
        """Router fails over from Groq to NVIDIA on error."""
        router = ModelRouter()

        # Groq provider that fails
        groq = GroqProvider.__new__(GroqProvider)
        groq._config = GroqConfig(api_key="test", max_retries=1, retry_backoff=0.01)
        groq._available = True
        groq._last_error = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Groq down")
        groq._client = mock_client

        # NVIDIA provider that succeeds (mocked)
        nvidia = NvidiaProvider.__new__(NvidiaProvider)
        nvidia._config = NvidiaConfig(api_key="nvapi-test", max_retries=1)
        nvidia._available = True
        nvidia._last_error = None

        # Patch httpx for nvidia
        with patch("friday.models.providers.nvidia_provider.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "NVIDIA response"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 15},
            }
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client_instance

            router.register_provider(groq)
            router.register_provider(nvidia)

            result = _run(router.complete("Hello", capability=ModelCapability.REASONING))

        assert result.provider == "nvidia"
        assert result.text == "NVIDIA response"

    def test_router_selects_vision_from_nvidia(self):
        """Router routes vision tasks to NVIDIA (which has vision models)."""
        router = ModelRouter()

        # Groq has no vision models
        groq = GroqProvider.__new__(GroqProvider)
        groq._config = GroqConfig(api_key="test")
        groq._available = True
        groq._last_error = None
        groq._client = MagicMock()

        # NVIDIA has vision models
        nvidia = NvidiaProvider.__new__(NvidiaProvider)
        nvidia._config = NvidiaConfig(api_key="nvapi-test")
        nvidia._available = True
        nvidia._last_error = None

        router.register_provider(groq)
        router.register_provider(nvidia)

        # Check which models are available for vision
        vision_models = router.get_models_for_capability(ModelCapability.VISION)
        assert len(vision_models) >= 1
        assert all(m.provider == "nvidia" for m in vision_models)
