"""ModelRouter per-model failover and dead-model circuit breaker.

The router failed over between *providers* only. With a single provider it tried
one model and gave up, so one retired model id made every LLM call in the system
fail while the same provider offered working alternatives. The whole agent silently
ran on non-LLM fallbacks. These tests pin the fix.
"""

from __future__ import annotations

import asyncio

import pytest

from friday.models.router import (
    ModelCapability,
    ModelInfo,
    ModelResponse,
    ModelRouter,
)


class _FakeProvider:
    """Provider whose per-model behavior is scripted."""

    def __init__(self, name="fake", behavior=None, models=None):
        self.name = name
        self.available = True
        self._behavior = behavior or {}
        self._models = models or []
        self.calls = []

    @property
    def models(self):
        return self._models

    async def complete(self, prompt, *, model=None, max_tokens=1024,
                       temperature=0.7, system_prompt=None, **kwargs):
        self.calls.append(model)
        outcome = self._behavior.get(model, "ok")
        if outcome != "ok":
            raise RuntimeError(outcome)
        return ModelResponse(text=f"answer from {model}", model_used=model,
                             provider=self.name, tokens_used=7)


def _model(model_id, priority, capability=ModelCapability.REASONING,
           capabilities=None, capability_priority=None):
    return ModelInfo(
        provider="fake",
        model_id=model_id,
        capabilities=capabilities or [capability],
        max_tokens=1024,
        priority=priority,
        capability_priority=capability_priority or {},
    )


def _router(provider):
    router = ModelRouter()
    router.register_provider(provider)
    return router


def _complete(router, **kwargs):
    return asyncio.run(router.complete("hi", **kwargs))


# --------------------------------------------------------------------------- #
# Per-model failover
# --------------------------------------------------------------------------- #
def test_failover_tries_the_next_model_when_the_primary_is_gone():
    provider = _FakeProvider(
        behavior={"primary": "NVIDIA API returned 404: Not Found"},
        models=[_model("primary", 12), _model("secondary", 5)],
    )
    response = _complete(_router(provider), capability=ModelCapability.REASONING)
    assert response.text == "answer from secondary"
    assert provider.calls == ["primary", "secondary"]


def test_models_are_tried_in_priority_order():
    provider = _FakeProvider(
        behavior={"high": "500 boom", "mid": "500 boom"},
        models=[_model("low", 1), _model("high", 10), _model("mid", 5)],
    )
    response = _complete(_router(provider), capability=ModelCapability.REASONING)
    assert provider.calls == ["high", "mid", "low"]
    assert response.text == "answer from low"


def test_all_models_failing_still_raises():
    provider = _FakeProvider(
        behavior={"a": "500 boom", "b": "500 boom"},
        models=[_model("a", 2), _model("b", 1)],
    )
    with pytest.raises(RuntimeError, match="All providers failed"):
        _complete(_router(provider), capability=ModelCapability.REASONING)
    assert provider.calls == ["a", "b"]


def test_an_explicitly_requested_model_is_not_substituted():
    """Asking for a model by name must not silently get a different one."""
    provider = _FakeProvider(
        behavior={"asked": "404 Not Found"},
        models=[_model("asked", 5), _model("other", 9)],
    )
    with pytest.raises(RuntimeError):
        _complete(_router(provider), capability=ModelCapability.REASONING,
                  model="asked")
    assert provider.calls == ["asked"]


def test_capability_priority_overrides_the_global_priority():
    """A fast small model must be able to lead one capability without leading all."""
    fast = ModelInfo(
        provider="fake", model_id="fast", max_tokens=1024, priority=1,
        capabilities=[ModelCapability.CLASSIFICATION, ModelCapability.REASONING],
        capability_priority={ModelCapability.CLASSIFICATION: 20},
    )
    big = ModelInfo(
        provider="fake", model_id="big", max_tokens=1024, priority=10,
        capabilities=[ModelCapability.CLASSIFICATION, ModelCapability.REASONING],
    )
    router = _router(_FakeProvider(models=[fast, big]))
    provider = router._providers["fake"]

    assert router._models_for(provider, ModelCapability.CLASSIFICATION)[0] == "fast"
    assert router._models_for(provider, ModelCapability.REASONING)[0] == "big"


def test_capability_priority_can_demote_to_last_resort():
    slow = ModelInfo(
        provider="fake", model_id="slow", max_tokens=1024, priority=9,
        capabilities=[ModelCapability.CONVERSATION],
        capability_priority={ModelCapability.CONVERSATION: 0},
    )
    normal = ModelInfo(
        provider="fake", model_id="normal", max_tokens=1024, priority=5,
        capabilities=[ModelCapability.CONVERSATION],
    )
    router = _router(_FakeProvider(models=[slow, normal]))
    order = router._models_for(router._providers["fake"], ModelCapability.CONVERSATION)
    assert order == ["normal", "slow"]


def test_a_model_without_overrides_keeps_its_global_priority():
    a = ModelInfo(provider="fake", model_id="a", max_tokens=1024, priority=7,
                  capabilities=[ModelCapability.REASONING])
    b = ModelInfo(provider="fake", model_id="b", max_tokens=1024, priority=3,
                  capabilities=[ModelCapability.REASONING])
    router = _router(_FakeProvider(models=[a, b]))
    order = router._models_for(router._providers["fake"], ModelCapability.REASONING)
    assert order == ["a", "b"]


def test_capability_filters_the_candidates():
    provider = _FakeProvider(
        models=[
            _model("reasoner", 5, ModelCapability.REASONING),
            _model("embedder", 9, ModelCapability.EMBEDDING),
        ],
    )
    response = _complete(_router(provider), capability=ModelCapability.REASONING)
    assert response.text == "answer from reasoner"
    assert "embedder" not in provider.calls


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "error",
    [
        "NVIDIA API returned 404: Not Found",
        "NVIDIA API returned 410: Gone",
        "NVIDIA API returned 400: Conversation roles must alternate",
    ],
)
def test_a_permanently_failing_model_is_skipped_next_time(error):
    provider = _FakeProvider(
        behavior={"dead": error},
        models=[_model("dead", 12), _model("alive", 5)],
    )
    router = _router(provider)

    _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls == ["dead", "alive"]

    provider.calls.clear()
    _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls == ["alive"], "a dead model must not be retried every call"


@pytest.mark.parametrize(
    "error",
    [
        "Request timed out after 45s",
        "NVIDIA NIM API failed after 3 attempts: ",
        "503 Service Unavailable",
    ],
)
def test_one_failure_is_forgiven_but_a_repeatedly_broken_model_is_skipped(error):
    """A provider may hide the reason, so the breaker is reason-agnostic."""
    provider = _FakeProvider(
        behavior={"slow": error},
        models=[_model("slow", 12), _model("alive", 5)],
    )
    router = _router(provider)

    _complete(router, capability=ModelCapability.REASONING)
    assert "fake/slow" not in router.unavailable_models, "one failure must be forgiven"

    provider.calls.clear()
    _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls == ["slow", "alive"]
    assert "fake/slow" in router.unavailable_models

    provider.calls.clear()
    _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls == ["alive"], "a repeatedly broken model must be skipped"


def test_a_single_transient_failure_does_not_disable_a_model():
    provider = _FakeProvider(
        behavior={"flaky": "503 Service Unavailable"},
        models=[_model("flaky", 12), _model("alive", 5)],
    )
    router = _router(provider)
    _complete(router, capability=ModelCapability.REASONING)

    provider.calls.clear()
    _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls == ["flaky", "alive"], (
        "one transient error must not permanently disable a model"
    )


def test_unavailable_models_are_observable():
    provider = _FakeProvider(
        behavior={"dead": "NVIDIA API returned 410: Gone"},
        models=[_model("dead", 12), _model("alive", 5)],
    )
    router = _router(provider)
    _complete(router, capability=ModelCapability.REASONING)
    assert "fake/dead" in router.unavailable_models
    assert "410" in router.unavailable_models["fake/dead"]


def test_all_candidates_dead_still_attempts_rather_than_going_silent():
    """If everything got marked, retry rather than report "no models"."""
    provider = _FakeProvider(
        behavior={"a": "404 Not Found", "b": "404 Not Found"},
        models=[_model("a", 2), _model("b", 1)],
    )
    router = _router(provider)
    with pytest.raises(RuntimeError):
        _complete(router, capability=ModelCapability.REASONING)

    provider.calls.clear()
    with pytest.raises(RuntimeError, match="All providers failed"):
        _complete(router, capability=ModelCapability.REASONING)
    assert provider.calls, "a request must still attempt something, not silently no-op"


# --------------------------------------------------------------------------- #
# Usage accounting
# --------------------------------------------------------------------------- #
def test_failed_model_is_recorded_by_its_own_id():
    """A failure recorded as "unknown" hides which model is broken."""
    provider = _FakeProvider(
        behavior={"dead": "404 Not Found"},
        models=[_model("dead", 12), _model("alive", 5)],
    )
    router = _router(provider)
    _complete(router, capability=ModelCapability.REASONING)

    stats = router.get_usage_stats()
    assert stats["total_requests"] == 2
    assert stats["failure_rate"] == pytest.approx(0.5)


def test_a_successful_call_is_not_recorded_as_a_failure():
    provider = _FakeProvider(models=[_model("alive", 5)])
    router = _router(provider)
    _complete(router, capability=ModelCapability.REASONING)
    stats = router.get_usage_stats()
    assert stats["failure_rate"] == 0.0
    assert stats["total_tokens"] == 7


# --------------------------------------------------------------------------- #
# Per-capability priority — a fast model may lead one capability and not another
# --------------------------------------------------------------------------- #
def test_capability_priority_overrides_the_global_priority():
    """Declared capability_priority must actually drive selection, not be metadata."""
    big = _model(
        "big", 12,
        capabilities=[ModelCapability.REASONING, ModelCapability.CLASSIFICATION],
    )
    fast = _model(
        "fast", 5,
        capabilities=[ModelCapability.REASONING, ModelCapability.CLASSIFICATION],
        capability_priority={ModelCapability.CLASSIFICATION: 20},
    )
    provider = _FakeProvider(models=[big, fast])
    router = _router(provider)

    # Classification: the fast model leads despite a lower global priority.
    assert _complete(
        router, capability=ModelCapability.CLASSIFICATION
    ).text == "answer from fast"

    # Reasoning: unchanged, the big model still leads.
    provider.calls.clear()
    assert _complete(
        router, capability=ModelCapability.REASONING
    ).text == "answer from big"


def test_a_capability_not_listed_falls_back_to_the_global_priority():
    model = _model(
        "m", 7,
        capabilities=[ModelCapability.REASONING, ModelCapability.CLASSIFICATION],
        capability_priority={ModelCapability.CLASSIFICATION: 20},
    )
    assert model.priority_for(ModelCapability.CLASSIFICATION) == 20
    assert model.priority_for(ModelCapability.REASONING) == 7


def test_a_zeroed_capability_priority_demotes_a_model_to_last():
    """Used for moderation models that reject a general chat shape."""
    guard = _model(
        "guard", 10,
        capabilities=[ModelCapability.CLASSIFICATION],
        capability_priority={ModelCapability.CLASSIFICATION: 0},
    )
    general = _model("general", 3, capabilities=[ModelCapability.CLASSIFICATION])
    provider = _FakeProvider(models=[guard, general])

    response = _complete(_router(provider), capability=ModelCapability.CLASSIFICATION)
    assert response.text == "answer from general"
    assert provider.calls == ["general"], "a demoted model must not be tried first"


def test_reporting_surface_matches_actual_selection_order():
    """get_models_for_capability must not disagree with what complete() picks."""
    big = _model("big", 12, capabilities=[ModelCapability.CLASSIFICATION])
    fast = _model(
        "fast", 5,
        capabilities=[ModelCapability.CLASSIFICATION],
        capability_priority={ModelCapability.CLASSIFICATION: 20},
    )
    router = _router(_FakeProvider(models=[big, fast]))
    reported = [m.model_id for m in
                router.get_models_for_capability(ModelCapability.CLASSIFICATION)]
    assert reported[0] == "fast"
