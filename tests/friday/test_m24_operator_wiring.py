"""M24 — Operator verdict-publishing wiring tests.

Feature: m24-structured-failure-recovery-activation

Property 6: the Operator without a kernel behaves identically to pre-M24 (no
events); with a kernel it publishes one verification.completed per requirement.
"""

from __future__ import annotations

from typing import List

from friday.events.event import Event
from friday.operator import Operator
from friday.planner.requirements import Requirement, RequirementSet
from friday.verification.evidence_law import ExecutionEvidence


class _FakeKernel:
    def __init__(self):
        self.published: List[Event] = []

    def health(self):
        return {"tick": 0}

    def publish_event(self, event):
        self.published.append(event)


class _ExecResult:
    def __init__(self, evidence):
        self.evidence = evidence
        self.blocked = False


def _req_set():
    return RequirementSet(
        goal="research and write about X",
        requirements=[
            Requirement(description="gather information about X"),
            Requirement(description="produce a written summary"),
        ],
    )


def test_p6_without_kernel_publishes_nothing():
    # Feature: m24-structured-failure-recovery-activation, Property 6:
    # no kernel -> inert; verdicts still computed, no events. Validates: Requirements 5.1
    op = Operator()  # no kernel
    assert op._verdict_publisher.active is False
    req_set = _req_set()
    op._verify_requirements(req_set, _ExecResult(ExecutionEvidence()))
    # Requirements were still evaluated (both unmet with empty evidence).
    assert all(not r.satisfied for r in req_set.requirements)


def test_p6_with_kernel_publishes_one_event_per_requirement():
    # Feature: m24-structured-failure-recovery-activation, Property 6:
    # with a kernel -> one verification.completed per requirement. Validates: 5.2
    kernel = _FakeKernel()
    op = Operator(kernel=kernel)
    assert op._verdict_publisher.active is True
    req_set = _req_set()
    op._verify_requirements(req_set, _ExecResult(ExecutionEvidence()))

    assert len(kernel.published) == 2
    assert all(e.event_type == "verification.completed" for e in kernel.published)
    goal_ids = {e.payload["goal_id"] for e in kernel.published}
    assert goal_ids == {"research and write about X"}
    # Both requirements were unmet (empty evidence) -> satisfied False in payloads.
    assert all(e.payload["satisfied"] is False for e in kernel.published)


def test_p6_satisfied_requirement_publishes_satisfied_true():
    # Feature: m24-structured-failure-recovery-activation, Property 6:
    # a met requirement publishes satisfied=True. Validates: Requirements 5.2
    kernel = _FakeKernel()
    op = Operator(kernel=kernel)
    evidence = ExecutionEvidence()
    evidence.add_generated_content("a real written summary of X with substance")
    req_set = RequirementSet(
        goal="write about X",
        requirements=[Requirement(description="produce a written summary")],
    )
    op._verify_requirements(req_set, _ExecResult(evidence))
    assert len(kernel.published) == 1
    assert kernel.published[0].payload["satisfied"] is True
