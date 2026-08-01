"""M24 — Structured failure model property tests.

Feature: m24-structured-failure-recovery-activation

Property 1: classify_error_category is a TOTAL, pure function; every known
free-form category maps to a non-UNKNOWN FailureDomain; no app/site branching.
Property 2: StructuredFailure constructors never raise and to_payload() is
JSON-serializable.
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.actions.result import ActionResult, ActionStatus
from friday.verification.evidence_law import RequirementKind, RequirementVerdict
from friday.verification.failure import (
    FailureDomain,
    Severity,
    StructuredFailure,
    classify_error_category,
    _EXACT_CATEGORY_MAP,
)


@settings(max_examples=200)
@given(st.text())
def test_p1_classifier_is_total(category):
    # Feature: m24-structured-failure-recovery-activation, Property 1:
    # any string yields a FailureDomain, never raises. Validates: Requirements 1.1
    domain = classify_error_category(category)
    assert isinstance(domain, FailureDomain)


def test_p1_every_known_category_maps_non_unknown():
    # Feature: m24-structured-failure-recovery-activation, Property 1:
    # every existing free-form error_category classifies to a real domain.
    # Validates: Requirements 1.2
    for category in _EXACT_CATEGORY_MAP:
        assert classify_error_category(category) is not FailureDomain.UNKNOWN


def test_p1_empty_and_none_are_unknown():
    # Feature: m24-structured-failure-recovery-activation, Property 1.
    # Validates: Requirements 1.1
    assert classify_error_category(None) is FailureDomain.UNKNOWN
    assert classify_error_category("") is FailureDomain.UNKNOWN
    assert classify_error_category("   ") is FailureDomain.UNKNOWN


def test_p1_case_insensitive():
    # Feature: m24-structured-failure-recovery-activation, Property 1.
    assert classify_error_category("TARGET_NOT_FOUND") is FailureDomain.PERCEPTION
    assert classify_error_category("Adapter_Failed") is FailureDomain.EXECUTION


@settings(max_examples=100)
@given(
    category=st.sampled_from(sorted(_EXACT_CATEGORY_MAP.keys()) + ["", "weird_thing"]),
    status=st.sampled_from(list(ActionStatus)),
    error=st.text(max_size=80),
)
def test_p2_from_action_result_never_raises_and_serializes(category, status, error):
    # Feature: m24-structured-failure-recovery-activation, Property 2:
    # constructor never raises; payload is JSON-safe. Validates: Requirements 2.1, 2.2, 2.3
    result = ActionResult.failed(action="x", error=error, error_category=category)
    object.__setattr__(result, "status", status)
    failure = StructuredFailure.from_action_result(
        result, goal_id="g1", capability="cap", environment="env"
    )
    assert isinstance(failure.domain, FailureDomain)
    assert isinstance(failure.severity, Severity)
    payload = failure.to_payload()
    # Must be JSON-serializable (replay/observability requirement).
    json.dumps(payload)
    assert payload["domain"] == failure.domain.value
    assert payload["goal_id"] == "g1"


def test_p2_from_verdict_is_verification_domain():
    # Feature: m24-structured-failure-recovery-activation, Property 2:
    # an unmet requirement verdict → VERIFICATION domain, JSON-safe. Validates: 2.1, 2.3
    verdict = RequirementVerdict(
        description="gather info about X",
        kind=RequirementKind.GATHER,
        satisfied=False,
        reason="no sources read",
    )
    failure = StructuredFailure.from_verdict(verdict, goal_id="g2")
    assert failure.domain is FailureDomain.VERIFICATION
    assert failure.recoverable is True
    json.dumps(failure.to_payload())


def test_p2_recommended_recovery_escalates_when_unrecoverable():
    # Feature: m24-structured-failure-recovery-activation, Property 2:
    # a SKIPPED result is not recoverable → recommended recovery escalates to HUMAN(4).
    result = ActionResult.failed(action="x", error="e", error_category="not_found")
    object.__setattr__(result, "status", ActionStatus.SKIPPED)
    failure = StructuredFailure.from_action_result(result)
    assert failure.recoverable is False
    assert failure.recommended_recovery == 4  # RecoveryLevel.HUMAN
