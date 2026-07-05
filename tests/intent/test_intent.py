"""M5 tests — Intent object and assumption spectrum."""

import dataclasses

import pytest

from friday.intent.intent import Assumption, Intent


def test_intent_is_immutable():
    intent = Intent(raw_text="do x", objective="do x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        intent.objective = "do y"


def test_safe_assumption_needs_no_clarification():
    safe = Assumption(description="default browser used", confidence=0.95)
    assert not safe.needs_clarification


def test_critical_low_confidence_assumption_needs_clarification():
    risky = Assumption(
        description="which account to send from", confidence=0.3, critical=True
    )
    assert risky.needs_clarification


def test_intent_clarification_policy():
    intent = Intent(
        raw_text="send it",
        objective="send it",
        assumptions=(
            Assumption("what 'it' refers to", confidence=0.2, critical=True),
            Assumption("send immediately", confidence=0.9, critical=False),
        ),
    )
    assert intent.requires_clarification
    assert intent.clarification_questions == ("what 'it' refers to",)


def test_confidence_and_complexity_clamped():
    assert Assumption("a", confidence=5.0).confidence == 1.0
    assert Intent(raw_text="x", objective="x", complexity=9.0).complexity == 1.0


def test_payload_roundtrip_fields():
    intent = Intent(
        raw_text="find the report",
        objective="find the report",
        assumptions=(Assumption("latest report meant", confidence=0.8),),
        complexity=0.3,
    )
    payload = intent.to_payload()
    assert payload["objective"] == "find the report"
    assert payload["assumptions"][0]["confidence"] == 0.8
    assert payload["requires_clarification"] is False
