"""M9 — Unit tests for LearningEngine improvement tracking and unlearning (task 2.2).

Validates the two methods added to ``friday/learning/engine.py``:

- ``improvement(key)`` returns ``0.0`` for an unseen key (never fabricated) and otherwise the
  signed difference between the latest and first observed confidence for that key, derived only
  from ``competence.updated`` evidence recorded via ``_record_competence``.
- ``unlearn(principle_id, reason)`` retires a validated principle whose confidence dropped to/below
  the validator's retire floor, so it is no longer proposed for procedural promotion; it raises
  ``KeyError`` on an unknown id and ``ValueError`` when the principle is still confident.

Runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external surface is touched.

_Requirements: 1.10, 1.11, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest

from friday.learning.engine import LearningEngine
from friday.learning.models import Principle
from friday.learning.validation import LearningValidator


def _principle(pid: str = "principle-test", confidence: float = 0.5) -> Principle:
    return Principle(
        id=pid,
        statement="Capability yields its verified outcome across its environment class.",
        applicability=("cap", "cap::*"),
        source_signatures=("cap\x00env\x00outcome",),
        support=3,
        confidence=confidence,
    )


# --------------------------------------------------------------------------- #
# improvement: derived only from recorded competence.updated evidence
# --------------------------------------------------------------------------- #
def test_improvement_unseen_key_is_zero() -> None:
    engine = LearningEngine()
    assert engine.improvement(("cap", "env")) == 0.0


def test_improvement_single_observation_is_zero() -> None:
    engine = LearningEngine()
    engine._record_competence(("cap", "env"), 0.4)
    # Latest == first -> no measured change yet.
    assert engine.improvement(("cap", "env")) == pytest.approx(0.0)


def test_improvement_is_latest_minus_first() -> None:
    engine = LearningEngine()
    key = ("cap", "env")
    for c in (0.30, 0.55, 0.80):
        engine._record_competence(key, c)
    # 0.80 (latest) - 0.30 (first), independent of intermediate values.
    assert engine.improvement(key) == pytest.approx(0.50)


def test_improvement_can_be_negative() -> None:
    engine = LearningEngine()
    key = ("cap", "env")
    for c in (0.70, 0.20):
        engine._record_competence(key, c)
    assert engine.improvement(key) == pytest.approx(-0.50)


def test_improvement_is_per_key_isolated() -> None:
    engine = LearningEngine()
    engine._record_competence(("cap-a", "env"), 0.10)
    engine._record_competence(("cap-a", "env"), 0.60)
    engine._record_competence(("cap-b", "env"), 0.90)
    assert engine.improvement(("cap-a", "env")) == pytest.approx(0.50)
    # Single observation for cap-b -> zero; keys never bleed into each other.
    assert engine.improvement(("cap-b", "env")) == pytest.approx(0.0)
    # Distinct environment is a distinct key.
    assert engine.improvement(("cap-a", "other-env")) == 0.0


# --------------------------------------------------------------------------- #
# unlearn: retire a decayed validated principle
# --------------------------------------------------------------------------- #
def test_unlearn_retires_principle_at_or_below_retire_floor() -> None:
    validator = LearningValidator(retire_floor=0.2)
    engine = LearningEngine(validator=validator)
    principle = _principle(confidence=0.15)  # below the retire floor
    engine._principles[principle.id] = principle

    retired = engine.unlearn(principle.id, reason="confidence decayed")

    assert retired is principle
    # Retired -> no longer proposed for procedural promotion.
    assert principle.id in engine._retired


def test_unlearn_fires_exactly_at_retire_floor() -> None:
    validator = LearningValidator(retire_floor=0.2)
    engine = LearningEngine(validator=validator)
    principle = _principle(confidence=0.2)  # exactly at the (inclusive) floor
    engine._principles[principle.id] = principle

    retired = engine.unlearn(principle.id, reason="boundary")
    assert retired is principle
    assert principle.id in engine._retired


def test_unlearn_unknown_principle_raises_key_error() -> None:
    engine = LearningEngine()
    with pytest.raises(KeyError):
        engine.unlearn("does-not-exist", reason="nope")


def test_unlearn_refuses_still_confident_principle() -> None:
    validator = LearningValidator(retire_floor=0.2)
    engine = LearningEngine(validator=validator)
    principle = _principle(confidence=0.9)  # well above the retire floor
    engine._principles[principle.id] = principle

    with pytest.raises(ValueError):
        engine.unlearn(principle.id, reason="unfounded")
    # Untouched: still not retired.
    assert principle.id not in engine._retired
