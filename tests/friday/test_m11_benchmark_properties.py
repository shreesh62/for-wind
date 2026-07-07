"""M11 — Property + unit tests for benchmark scoring and regression detection.

Exercises the pure scoring core in ``friday/benchmarks/suite.py``:
- Property 5: a benchmark score is a bounded weighted pass ratio in [0, 1]
  (0.0 for an empty suite), with ``scenarios_passed`` equal to the pass count.
- Property 4 (monotonicity half): ``RegressionDetector.is_regression`` flags a
  candidate iff it scores below the incumbent, and a lower candidate is never
  less likely to be flagged.
- Unit edge cases: empty suite -> 0.0, all-pass -> 1.0, all-fail -> 0.0, and a
  scenario whose ``evaluate`` raises counts as a failed scenario.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green.

Validates: Requirements 2.1, 2.3, 2.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest
from hypothesis import given, settings, strategies as st

from friday.benchmarks.suite import (
    BenchmarkRunner,
    BenchmarkScenario,
    BenchmarkSuite,
    RegressionDetector,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_weights = st.floats(min_value=0.1, max_value=10, allow_nan=False, allow_infinity=False)


def _build_suite(weights):
    """Build a suite whose scenarios carry the given weights (ids 0..n-1)."""
    suite = BenchmarkSuite()
    for i, w in enumerate(weights):
        suite.add(BenchmarkScenario(id=str(i), description=f"scenario {i}", weight=w))
    return suite


# --------------------------------------------------------------------------- #
# Property 5: Benchmark score is a bounded weighted ratio
# --------------------------------------------------------------------------- #
@given(
    data=st.lists(
        st.tuples(_weights, st.booleans()), min_size=0, max_size=6
    )
)
@settings(max_examples=100)
def test_property5_score_is_bounded_weighted_ratio(data):
    """score == passed_weight / total_weight (or 0.0 empty), in [0, 1]."""
    weights = [w for (w, _passed) in data]
    mask = [passed for (_w, passed) in data]
    suite = _build_suite(weights)

    # Deterministic pass/fail decided purely by scenario id -> mask index.
    def evaluate(scenario):
        return mask[int(scenario.id)]

    report = BenchmarkRunner().run("cap.x", evaluate, suite)

    total_weight = sum(weights)
    passed_weight = sum(w for (w, passed) in data if passed)
    expected = passed_weight / total_weight if total_weight > 0 else 0.0

    assert report.score == pytest.approx(expected)
    assert 0.0 <= report.score <= 1.0
    assert report.scenarios_run == len(data)
    assert report.scenarios_passed == sum(1 for passed in mask if passed)


# --------------------------------------------------------------------------- #
# Property 4: regression monotonicity
# --------------------------------------------------------------------------- #
@given(
    incumbent=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    candidate=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_property4_is_regression_iff_candidate_below_incumbent(incumbent, candidate):
    """is_regression is True iff candidate < incumbent (tolerance 0)."""
    detector = RegressionDetector()
    assert detector.is_regression(incumbent, candidate) == (candidate < incumbent)


@given(
    incumbent=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    c1=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    c2=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_property4_monotonic_lower_candidate_never_less_flagged(incumbent, c1, c2):
    """A lower candidate is never less likely to be flagged as a regression."""
    detector = RegressionDetector()
    if c2 <= c1:
        # True >= False as ints/bools; a lower candidate stays at least as flagged.
        assert detector.is_regression(incumbent, c2) >= detector.is_regression(
            incumbent, c1
        )


# --------------------------------------------------------------------------- #
# Unit tests — scoring edge cases
# --------------------------------------------------------------------------- #
def test_empty_suite_scores_zero():
    report = BenchmarkRunner().run("cap.x", lambda s: True, BenchmarkSuite())
    assert report.score == 0.0
    assert report.scenarios_run == 0
    assert report.scenarios_passed == 0


def test_all_pass_scores_one():
    suite = _build_suite([1.0, 2.0, 3.0])
    report = BenchmarkRunner().run("cap.x", lambda s: True, suite)
    assert report.score == 1.0
    assert report.scenarios_passed == 3


def test_all_fail_scores_zero():
    suite = _build_suite([1.0, 2.0, 3.0])
    report = BenchmarkRunner().run("cap.x", lambda s: False, suite)
    assert report.score == 0.0
    assert report.scenarios_passed == 0


def test_throwing_scenario_counts_as_failure():
    suite = _build_suite([1.0, 1.0])

    def evaluate(scenario):
        if scenario.id == "0":
            raise RuntimeError("boom")
        return True

    report = BenchmarkRunner().run("cap.x", evaluate, suite)
    # Only the second scenario (weight 1 of 2) passes.
    assert report.score == 0.5
    assert report.scenarios_passed == 1
