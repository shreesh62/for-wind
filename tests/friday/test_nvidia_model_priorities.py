"""NVIDIA registry ordering — the measured latency/reliability decisions.

Each assertion here encodes an observation from probing the live endpoint, so a
future registry edit that silently reintroduces a known-bad lead will fail:

* a moderation model led general classification and rejected every plain chat
  request with HTTP 400;
* a model that times out (and is retried 3x by the provider before raising) sat
  ahead of fast working models on the interactive capabilities;
* the top working reasoning model cost ~25s per call and was the one that
  rate-limited out mid-run.

These are ordering assertions only — no network access.
"""

from __future__ import annotations

import pytest

from friday.models.router import ModelCapability, ModelRouter
from friday.models.providers.nvidia_provider import NvidiaProvider


@pytest.fixture(scope="module")
def provider():
    return NvidiaProvider()


@pytest.fixture(scope="module")
def router(provider):
    r = ModelRouter()
    # Registered directly so ordering is testable without an API key.
    r._providers["nvidia"] = provider
    return r


def _order(router, provider, capability):
    return router._models_for(provider, capability)


def test_classification_is_led_by_a_fast_model(router, provider):
    order = _order(router, provider, ModelCapability.CLASSIFICATION)
    assert order[0] == "nvidia/nemotron-mini-4b-instruct"


def test_moderation_models_never_lead_general_classification(router, provider):
    order = _order(router, provider, ModelCapability.CLASSIFICATION)
    for moderation in (
        "meta/llama-guard-4-12b",
        "nvidia/nemotron-content-safety-reasoning-4b",
    ):
        assert moderation in order, "the safety-gate model must stay registered"
        assert order.index(moderation) > 0, (
            f"{moderation} is a moderation model and must not lead classification"
        )


def test_conversation_is_led_by_the_fastest_working_model(router, provider):
    order = _order(router, provider, ModelCapability.CONVERSATION)
    assert order[0] == "openai/gpt-oss-20b"


def test_the_timing_out_model_is_last_resort_on_interactive_capabilities(router, provider):
    for capability in (ModelCapability.CONVERSATION, ModelCapability.CLASSIFICATION):
        order = _order(router, provider, capability)
        assert order[-1] in (
            "openai/gpt-oss-120b",
            "meta/llama-guard-4-12b",
            "nvidia/nemotron-content-safety-reasoning-4b",
        )
        assert order.index("openai/gpt-oss-120b") > 1, (
            f"a model that times out must not be tried early for {capability.value}"
        )


def test_reasoning_is_led_by_a_large_instruct_model(router, provider):
    """Synthesis keeps a large model — just not the 25s one."""
    order = _order(router, provider, ModelCapability.REASONING)
    assert order[0] == "meta/llama-3.2-90b-vision-instruct"
    assert "mistralai/mistral-medium-3.5-128b" in order, "failover must remain"


def test_the_4b_model_does_not_lead_summarization(router, provider):
    """Summarization is user-facing prose; a 4B model is the wrong trade there."""
    order = _order(router, provider, ModelCapability.SUMMARIZATION)
    assert order[0] != "nvidia/nemotron-mini-4b-instruct"


def test_embedding_stays_isolated_from_chat_capabilities(provider):
    embed = next(m for m in provider.models if m.model_id == "nvidia/nv-embed-v1")
    assert embed.capabilities == [ModelCapability.EMBEDDING]


def test_every_text_capability_has_more_than_one_candidate(router, provider):
    """Failover is meaningless with a single candidate."""
    for capability in (
        ModelCapability.CLASSIFICATION,
        ModelCapability.CONVERSATION,
        ModelCapability.REASONING,
        ModelCapability.SUMMARIZATION,
    ):
        order = _order(router, provider, capability)
        assert len(order) >= 2, f"{capability.value} has no failover candidate"
