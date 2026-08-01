"""M24 — VerificationEventPublisher tests (recovery activation).

Feature: m24-structured-failure-recovery-activation

Property 3: publisher is a no-op without a kernel; with a kernel it emits exactly a
`verification.completed` event with the required payload keys.
Property 4 (integration): a real RecoveryEngine + publisher on a real CognitiveKernel
yields a `recovery.proposed` event on a failed verdict — the dormant loop is ACTIVATED.
"""

from __future__ import annotations

from typing import Any, List

from friday.events.event import Event, make_event
from friday.kernel.kernel import CognitiveKernel
from friday.recovery.engine import RecoveryEngine
from friday.verification.evidence_law import ExecutionEvidence
from friday.verification.publisher import VerificationEventPublisher


class _FakeKernel:
    def __init__(self):
        self.published: List[Event] = []
        self._tick = 5

    def health(self):
        return {"tick": self._tick}

    def publish_event(self, event):
        self.published.append(event)


def test_p3_no_kernel_is_noop():
    # Feature: m24-structured-failure-recovery-activation, Property 3:
    # no kernel -> publish is a no-op returning False, never raises. Validates: 3.2
    pub = VerificationEventPublisher()
    assert pub.active is False
    assert pub.publish_verdict(goal_id="g", requirement="r", satisfied=False) is False


def test_p3_with_kernel_emits_verification_completed():
    # Feature: m24-structured-failure-recovery-activation, Property 3:
    # attached -> emits exactly one verification.completed with the required keys.
    # Validates: Requirements 3.1
    kernel = _FakeKernel()
    pub = VerificationEventPublisher()
    pub.attach(kernel)
    ok = pub.publish_verdict(
        goal_id="g1", requirement="gather info", satisfied=False,
        evidence=ExecutionEvidence(), capability="research", environment="web",
        blocked=False,
    )
    assert ok is True
    assert len(kernel.published) == 1
    ev = kernel.published[0]
    assert ev.event_type == "verification.completed"
    for key in ("goal_id", "satisfied", "requirement", "evidence",
                "capability", "environment", "reversible", "blocked", "competence"):
        assert key in ev.payload
    assert ev.payload["satisfied"] is False
    assert ev.logical_time == 6  # tick(5) + 1


def test_p3_payload_is_json_safe_for_persistence():
    # Feature: m24-structured-failure-recovery-activation, Property 3:
    # the event survives EventStore JSON serialization (evidence is a summary, not
    # the live object). Validates: Requirements 3.1
    import json
    kernel = _FakeKernel()
    pub = VerificationEventPublisher(kernel=kernel)
    ev = ExecutionEvidence()
    ev.add_generated_content("some produced text")
    pub.publish_verdict(goal_id="g", requirement="r", satisfied=False, evidence=ev)
    event = kernel.published[0]
    json.dumps(event.to_dict())  # must not raise
    assert event.payload["evidence"] is None
    assert event.payload["evidence_summary"]["artifact_count"] == 1


def test_p4_activates_recovery_loop(tmp_path):
    # Feature: m24-structured-failure-recovery-activation, Property 4:
    # a REAL kernel + REAL RecoveryEngine + publisher: a failed verdict causes a
    # recovery.proposed event. The previously dormant loop is now ACTIVE.
    # Validates: Requirements 3.3
    kernel = CognitiveKernel(store_path=str(tmp_path / "m24.jsonl"))
    recovery = RecoveryEngine()
    recovery.attach(kernel)

    proposed: List[str] = []
    kernel.subscribe("recovery.proposed", lambda e: proposed.append(e.event_type))

    pub = VerificationEventPublisher()
    pub.attach(kernel)
    pub.publish_verdict(
        goal_id="goal-123",
        requirement="gather information about renewable energy",
        satisfied=False,
        evidence=ExecutionEvidence(),
        reversible=True,
        blocked=False,
    )

    assert proposed == ["recovery.proposed"], (
        "RecoveryEngine did not react — the failure->recovery loop is still dormant"
    )


def test_p4_satisfied_verdict_does_not_trigger_recovery(tmp_path):
    # Feature: m24-structured-failure-recovery-activation, Property 4:
    # a SATISFIED verdict must NOT propose recovery. Validates: Requirements 3.3
    kernel = CognitiveKernel(store_path=str(tmp_path / "m24b.jsonl"))
    RecoveryEngine().attach(kernel)
    proposed: List[str] = []
    kernel.subscribe("recovery.proposed", lambda e: proposed.append(e.event_type))

    pub = VerificationEventPublisher(kernel=kernel)
    pub.publish_verdict(goal_id="g", requirement="r", satisfied=True)
    assert proposed == []
