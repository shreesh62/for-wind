"""M9 — Unit tests for the LearningValidator (task 1.8).

Validates ``friday/learning/validation.py`` (Ch 15.4/15.19 validated pipeline):
- ``validate`` returns ``VALIDATED`` iff ``verified is True`` AND
  ``observed - baseline >= min_improvement``; otherwise ``REJECTED``. This is table-tested
  across the verified × improvement matrix: unverified is always ``REJECTED``, improvement
  below ``min_improvement`` is ``REJECTED``, and verified + sufficient improvement is
  ``VALIDATED``. The result always carries the signed ``improvement`` delta.
- ``should_unlearn`` fires exactly at/below the retire floor.

Runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external surface is touched.

_Requirements: 1.6, 1.10, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest

from friday.learning.models import Principle, ValidationStatus
from friday.learning.validation import LearningValidator


def _principle(pid: str = "principle-test") -> Principle:
    return Principle(
        id=pid,
        statement="Capability yields its verified outcome across its environment class.",
        applicability=("cap", "cap::*"),
        source_signatures=("cap\x00env\x00outcome",),
        support=3,
        confidence=0.5,
    )


# --------------------------------------------------------------------------- #
# validate: verified × improvement matrix
# --------------------------------------------------------------------------- #
# min_improvement defaults to 0.05.
# (verified, baseline, observed, expected_status)
_VALIDATE_MATRIX = [
    # Unverified is ALWAYS rejected, even with huge improvement.
    (False, 0.0, 1.0, ValidationStatus.REJECTED),
    (False, 0.0, 0.0, ValidationStatus.REJECTED),
    (False, 0.5, 0.5, ValidationStatus.REJECTED),
    # Verified but improvement below min_improvement -> rejected.
    (True, 0.50, 0.50, ValidationStatus.REJECTED),   # zero improvement
    (True, 0.50, 0.54, ValidationStatus.REJECTED),   # 0.04 < 0.05
    (True, 0.50, 0.40, ValidationStatus.REJECTED),   # negative improvement
    # Verified + improvement exactly at threshold -> validated.
    (True, 0.50, 0.55, ValidationStatus.VALIDATED),  # exactly 0.05
    # Verified + improvement above threshold -> validated.
    (True, 0.20, 0.90, ValidationStatus.VALIDATED),
]


@pytest.mark.parametrize("verified, baseline, observed, expected", _VALIDATE_MATRIX)
def test_validate_matrix(verified, baseline, observed, expected) -> None:
    validator = LearningValidator()
    result = validator.validate(
        _principle(),
        baseline=baseline,
        observed=observed,
        verified=verified,
    )
    assert result.status is expected
    # The signed improvement delta is always carried on the result.
    assert result.improvement == pytest.approx(observed - baseline)
    assert result.principle_id == _principle().id


def test_validate_respects_custom_min_improvement() -> None:
    validator = LearningValidator(min_improvement=0.5)
    # 0.3 improvement is enough by default but not against a 0.5 floor.
    result = validator.validate(_principle(), baseline=0.0, observed=0.3, verified=True)
    assert result.status is ValidationStatus.REJECTED

    ok = validator.validate(_principle(), baseline=0.0, observed=0.5, verified=True)
    assert ok.status is ValidationStatus.VALIDATED


def test_validate_result_reports_signed_improvement() -> None:
    validator = LearningValidator()
    result = validator.validate(_principle(), baseline=0.7, observed=0.3, verified=True)
    assert result.improvement == pytest.approx(-0.4)
    assert result.status is ValidationStatus.REJECTED


# --------------------------------------------------------------------------- #
# should_unlearn: fires exactly at/below the retire floor
# --------------------------------------------------------------------------- #
def test_should_unlearn_fires_at_and_below_retire_floor() -> None:
    validator = LearningValidator(retire_floor=0.2)
    principle = _principle()

    # Below the floor -> retire.
    assert validator.should_unlearn(principle, 0.1) is True
    # Exactly at the floor -> retire (boundary is inclusive).
    assert validator.should_unlearn(principle, 0.2) is True
    # Above the floor -> keep.
    assert validator.should_unlearn(principle, 0.2001) is False
    assert validator.should_unlearn(principle, 0.9) is False


def test_should_unlearn_respects_custom_retire_floor() -> None:
    validator = LearningValidator(retire_floor=0.5)
    principle = _principle()
    assert validator.should_unlearn(principle, 0.5) is True
    assert validator.should_unlearn(principle, 0.49) is True
    assert validator.should_unlearn(principle, 0.51) is False
