"""M24 (activation) — end-to-end reactive-loop wiring tests.

Feature: m24-structured-failure-recovery-activation

Proves attach_reactive_loop wires the FULL loop to a real kernel so a single
published verdict drives recovery + competence + observability together — the
production activation, not just the isolated producer.
"""

from __future__ import annotations

from typing import List

from friday.kernel.kernel import CognitiveKernel
from friday.kernel.reactive_loop import ReactiveLoop, attach_reactive_loop
from friday.verification.evidence_law import ExecutionEvidence
from friday.verification.publisher import VerificationEventPublisher


def test_attach_returns_all_components(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # the helper attaches recovery/competence/reflection/observability.
    kernel = CognitiveKernel(store_path=str(tmp_path / "rl.jsonl"))
    before = kernel._bus.subscription_count
    loop = attach_reactive_loop(kernel)
    assert isinstance(loop, ReactiveLoop)
    assert loop.recovery is not None
    assert loop.competence is not None
    assert loop.reflection is not None
    assert loop.failure_log is not None
    # Several subscriptions were added (recovery + competence + reflection + logs).
    assert kernel._bus.subscription_count > before


def test_full_loop_reacts_to_a_failed_verdict(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # one failed verdict -> recovery.proposed AND competence.updated AND a log record.
    kernel = CognitiveKernel(store_path=str(tmp_path / "rl2.jsonl"))
    loop = attach_reactive_loop(kernel)

    seen: List[str] = []
    kernel.subscribe("recovery.proposed", lambda e: seen.append(e.event_type))
    kernel.subscribe("competence.updated", lambda e: seen.append(e.event_type))

    pub = VerificationEventPublisher(kernel=kernel)
    pub.publish_verdict(
        goal_id="g-1",
        requirement="gather information about tidal energy",
        satisfied=False,
        evidence=ExecutionEvidence(),
        capability="research",
        environment="web",
    )

    assert "recovery.proposed" in seen
    assert "competence.updated" in seen  # capability present -> competence reacts
    assert loop.failure_log.records_emitted >= 1


def test_logging_can_be_disabled(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # observability is optional; recovery/competence still wire.
    kernel = CognitiveKernel(store_path=str(tmp_path / "rl3.jsonl"))
    loop = attach_reactive_loop(kernel, enable_logging=False)
    assert loop.failure_log is None
    assert loop.recovery is not None


def test_existing_components_are_reused(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # passing components reuses them rather than constructing new ones.
    from friday.competence.model import CompetenceModel
    kernel = CognitiveKernel(store_path=str(tmp_path / "rl4.jsonl"))
    shared = CompetenceModel()
    loop = attach_reactive_loop(kernel, competence_model=shared)
    assert loop.competence is shared
