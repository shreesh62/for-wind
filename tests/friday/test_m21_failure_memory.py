"""M21 — Failure Memory tests (persistent, queryable failure tier).

Feature: m21-failure-memory

Failure memory is a consumer of the M24 failure→recovery loop: it records unmet
verdicts and annotates them with the proposed recovery, and answers
"have we failed at this before?" so past failures inform future planning.
"""

from __future__ import annotations

from typing import List

from friday.kernel.kernel import CognitiveKernel
from friday.kernel.reactive_loop import attach_reactive_loop
from friday.memory.failure_memory import FailureMemory, FailureRecord
from friday.verification.evidence_law import ExecutionEvidence
from friday.verification.failure import FailureDomain, Severity, StructuredFailure
from friday.verification.publisher import VerificationEventPublisher


def _fm(tmp_path, name="fm"):
    return FailureMemory(store_path=str(tmp_path / f"{name}.json"))


def test_record_and_recall(tmp_path):
    # Feature: m21-failure-memory: a recorded failure is recallable by filters.
    fm = _fm(tmp_path)
    fm.record_failure(
        requirement="gather info about X", domain="perception",
        capability="research", environment="web", goal_id="g1",
    )
    recalled = fm.recall(capability="research")
    assert len(recalled) == 1
    assert recalled[0].domain == "perception"
    assert fm.has_failed_before("gather info about X", capability="research")
    assert not fm.has_failed_before("something else")


def test_record_structured_failure(tmp_path):
    # Feature: m21-failure-memory: an M24 StructuredFailure is recorded directly.
    fm = _fm(tmp_path, "struct")
    sf = StructuredFailure(
        domain=FailureDomain.EXECUTION, severity=Severity.HIGH,
        category="adapter_failed", message="motor failed",
        capability="click", environment="desktop", goal_id="g2",
        requirement="the button must be clicked",
    )
    fm.record_structured(sf)
    recalled = fm.recall(domain="execution")
    assert len(recalled) == 1
    assert recalled[0].capability == "click"
    assert recalled[0].category == "adapter_failed"


def test_failure_count_and_statistics(tmp_path):
    # Feature: m21-failure-memory: counts and domain distribution aggregate.
    fm = _fm(tmp_path, "stats")
    fm.record_failure(requirement="a", domain="perception", capability="c1")
    fm.record_failure(requirement="b", domain="perception", capability="c2")
    fm.record_failure(requirement="c", domain="execution", capability="c1")
    assert fm.failure_count() == 3
    assert fm.failure_count(domain="perception") == 2
    assert fm.failure_count(capability="c1") == 2
    stats = fm.statistics()
    assert stats["total_failures"] == 3
    assert stats["by_domain"]["perception"] == 2


def test_bounded_storage(tmp_path):
    # Feature: m21-failure-memory: storage is bounded (oldest evicted).
    fm = FailureMemory(store_path=str(tmp_path / "bound.json"), max_entries=5)
    for i in range(20):
        fm.record_failure(requirement=f"req-{i}", domain="execution")
    assert fm.failure_count() <= 5


def test_consumes_kernel_loop_records_failure_and_recovery(tmp_path):
    # Feature: m21-failure-memory: attached to the live loop, it records the failure
    # AND annotates it with the recovery that was proposed.
    kernel = CognitiveKernel(store_path=str(tmp_path / "k.jsonl"))
    fm = _fm(tmp_path, "loop")
    attach_reactive_loop(kernel, failure_memory=fm)

    pub = VerificationEventPublisher(kernel=kernel)
    pub.publish_verdict(
        goal_id="g-loop",
        requirement="information about tidal energy must be gathered",
        satisfied=False,
        evidence=ExecutionEvidence(),
        capability="research",
        environment="web",
    )

    recalled = fm.recall(capability="research")
    assert len(recalled) == 1
    rec = recalled[0]
    assert rec.goal_id == "g-loop"
    assert rec.domain == "verification"  # unmet requirement = verification-stage
    # recovery.proposed fired synchronously and annotated the record.
    assert rec.recovery_class != ""
    assert rec.recovery_actionable is True


def test_satisfied_verdict_not_remembered(tmp_path):
    # Feature: m21-failure-memory: satisfied verdicts are not failures.
    kernel = CognitiveKernel(store_path=str(tmp_path / "k2.jsonl"))
    fm = _fm(tmp_path, "sat")
    attach_reactive_loop(kernel, failure_memory=fm)
    VerificationEventPublisher(kernel=kernel).publish_verdict(
        goal_id="g", requirement="r", satisfied=True,
    )
    assert fm.failure_count() == 0


def test_handlers_never_raise_on_malformed_event(tmp_path):
    # Feature: m21-failure-memory: defensive handlers never raise into the bus.
    fm = _fm(tmp_path, "mal")
    fm._on_verification(object())
    fm._on_recovery(None)
    assert fm.failure_count() == 0
