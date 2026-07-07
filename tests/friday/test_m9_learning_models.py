"""M9 — Unit tests for the learning data models (task 1.2).

Validates the frozen learning records defined in ``friday/learning/models.py``:
- ``Principle.confidence`` is clamped to ``[0, 1]`` on construction.
- All records are immutable (frozen dataclasses).
- ``applicability`` / ``source_signatures`` are tuples and carry no literal
  application/site name (Axiom 15).

Runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external surface is touched.

_Requirements: 1.4, 5.4, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import dataclasses

import pytest

from friday.learning import (
    CompetenceKey,
    DiscoveredPattern,
    LearningStep,
    Principle,
    ValidationResult,
    ValidationStatus,
    VerifiedExperience,
)


# --------------------------------------------------------------------------- #
# Confidence clamping
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (-1.0, 0.0),
        (-0.0001, 0.0),
        (0.0, 0.0),
        (0.5, 0.5),
        (1.0, 1.0),
        (1.0001, 1.0),
        (42.0, 1.0),
    ],
)
def test_principle_confidence_clamped_to_unit_interval(raw: float, expected: float) -> None:
    principle = Principle(
        id="p1",
        statement="broader capability generalizes across environment class",
        applicability=("capability_class", "environment_class"),
        source_signatures=("sig-a",),
        support=3,
        confidence=raw,
    )
    assert principle.confidence == expected
    assert 0.0 <= principle.confidence <= 1.0


# --------------------------------------------------------------------------- #
# Immutability (frozen)
# --------------------------------------------------------------------------- #
def _verified_experience() -> VerifiedExperience:
    return VerifiedExperience(
        goal_id="g1",
        capability="cap",
        environment="env",
        outcome_signature="sig",
        prediction_error=0.1,
        verified=True,
        competence_delta=0.05,
        logical_time=1,
        wall_time=123.0,
    )


def _discovered_pattern() -> DiscoveredPattern:
    return DiscoveredPattern(
        signature="sig",
        capability="cap",
        environment="env",
        support=3,
        mean_prediction_error=0.1,
    )


def _principle() -> Principle:
    return Principle(
        id="p1",
        statement="a transferable principle",
        applicability=("capability_class",),
        source_signatures=("sig",),
        support=3,
        confidence=0.6,
    )


def _validation_result() -> ValidationResult:
    return ValidationResult(
        status=ValidationStatus.VALIDATED,
        principle_id="p1",
        improvement=0.1,
        reason="measurable improvement",
    )


def _learning_step() -> LearningStep:
    return LearningStep(
        discovered=_discovered_pattern(),
        generalized=_principle(),
        validation=_validation_result(),
    )


@pytest.mark.parametrize(
    ("record", "field"),
    [
        (_verified_experience(), "verified"),
        (_discovered_pattern(), "support"),
        (_principle(), "confidence"),
        (_validation_result(), "improvement"),
        (_learning_step(), "discovered"),
    ],
)
def test_records_are_immutable(record: object, field: str) -> None:
    assert dataclasses.is_dataclass(record)
    assert record.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(record, field, None)


# --------------------------------------------------------------------------- #
# Tuple typing + no literal app/site name (Axiom 15)
# --------------------------------------------------------------------------- #
def test_principle_tuple_fields_are_tuples() -> None:
    principle = _principle()
    assert isinstance(principle.applicability, tuple)
    assert isinstance(principle.source_signatures, tuple)


# A conservative sample of common literal app/site names that MUST NOT appear.
_FORBIDDEN_LITERALS = (
    "chrome", "firefox", "safari", "edge", "google", "gmail", "youtube",
    "facebook", "twitter", "amazon", "outlook", "slack", "notion", "github",
    "http://", "https://", ".com", ".org", ".net",
)


def test_principle_fields_carry_no_literal_app_or_site_name() -> None:
    principle = Principle(
        id="p1",
        statement="generalize across the capability and environment class",
        applicability=("capability_class", "environment_class"),
        source_signatures=("sig-a", "sig-b"),
        support=5,
        confidence=0.7,
    )
    haystack = " ".join(
        (principle.statement, *principle.applicability, *principle.source_signatures)
    ).lower()
    for literal in _FORBIDDEN_LITERALS:
        assert literal not in haystack


# --------------------------------------------------------------------------- #
# CompetenceKey alias
# --------------------------------------------------------------------------- #
def test_competence_key_is_capability_environment_tuple() -> None:
    key: CompetenceKey = ("cap", "env")
    assert isinstance(key, tuple)
    assert len(key) == 2
