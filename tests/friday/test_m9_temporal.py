"""M9 — Unit tests for temporal edge cases (task 4.7).

Covers the total-input edge behaviour of the temporal classification cores:
- ``KnowledgeAging.stale_items`` returns exactly the items whose freshness at
  ``now`` is below ``stale_threshold`` (Req 2.3).
- ``DeadlineTracker.evaluate`` never divides by zero for non-positive / zero
  deadline windows and classifies such goals ``MISSED`` only when
  ``now_wall > deadline_wall`` (Req 2.8).
- Goals without a deadline constraint are never registered and so are never
  tracked (Req 2.7).

Runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external surface is touched.

_Requirements: 2.3, 2.7, 2.8, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.temporal import (
    AgingItem,
    DeadlineState,
    DeadlineTracker,
    KnowledgeAging,
)


# --------------------------------------------------------------------------- #
# KnowledgeAging.stale_items — exactly the items below stale_threshold (Req 2.3)
# --------------------------------------------------------------------------- #
def test_stale_items_returns_exactly_items_below_threshold() -> None:
    half_life = 100.0
    threshold = 0.25
    aging = KnowledgeAging(half_life_seconds=half_life, stale_threshold=threshold)

    now = 1_000.0
    # fresh: observed just now -> freshness 1.0 (>= threshold, not stale)
    fresh = AgingItem(key="fresh", observed_at=now, freshness=1.0)
    # borderline: freshness exactly at threshold -> NOT stale (strictly below only)
    # solve 0.5 ** (age/half_life) == threshold -> age = half_life * log2(1/threshold)
    import math

    age_at_threshold = half_life * math.log2(1.0 / threshold)
    at_threshold = AgingItem(
        key="at_threshold", observed_at=now - age_at_threshold, freshness=threshold
    )
    # stale: observed long ago -> freshness well below threshold
    stale = AgingItem(key="stale", observed_at=now - 10 * half_life, freshness=0.0)

    result = aging.stale_items([fresh, at_threshold, stale], now)

    keys = {item.key for item in result}
    assert keys == {"stale"}
    # freshness at exactly the threshold is not "below" it
    assert aging.freshness(at_threshold.observed_at, now) >= threshold
    # the recomputed stale freshness is genuinely below the threshold
    assert aging.freshness(stale.observed_at, now) < threshold


def test_stale_items_recomputes_from_observed_at_not_snapshot() -> None:
    # An item may carry a stale snapshot freshness; stale_items must recompute.
    aging = KnowledgeAging(half_life_seconds=50.0, stale_threshold=0.5)
    now = 500.0
    # snapshot says 1.0, but observed_at is ancient -> recomputed freshness is tiny
    liar = AgingItem(key="liar", observed_at=now - 1000.0, freshness=1.0)
    assert aging.stale_items([liar], now) == [liar]


# --------------------------------------------------------------------------- #
# DeadlineTracker — non-positive/zero windows never divide by zero (Req 2.8)
# --------------------------------------------------------------------------- #
def test_zero_window_no_divide_by_zero_classifies_on_now_past_deadline() -> None:
    tracker = DeadlineTracker(approach_fraction=0.2)
    # zero window: created_wall == deadline_wall
    tracker.register("g_zero", deadline_wall=100.0, created_wall=100.0)

    # now before/at deadline -> ON_TRACK (never divides by zero, never MISSED)
    before = {s.goal_id: s for s in tracker.evaluate(50.0)}
    assert before["g_zero"].state == DeadlineState.ON_TRACK

    at = {s.goal_id: s for s in tracker.evaluate(100.0)}
    assert at["g_zero"].state == DeadlineState.ON_TRACK

    # now strictly past deadline -> MISSED
    after = {s.goal_id: s for s in tracker.evaluate(150.0)}
    assert after["g_zero"].state == DeadlineState.MISSED
    assert after["g_zero"].remaining_seconds == -50.0


def test_negative_window_no_divide_by_zero_classifies_on_now_past_deadline() -> None:
    tracker = DeadlineTracker(approach_fraction=0.2)
    # non-positive (negative) window: deadline before creation
    tracker.register("g_neg", deadline_wall=100.0, created_wall=200.0)

    # at/behind the deadline but not past it -> ON_TRACK, no ZeroDivisionError
    at = {s.goal_id: s for s in tracker.evaluate(100.0)}
    assert at["g_neg"].state == DeadlineState.ON_TRACK

    # strictly past deadline -> MISSED
    after = {s.goal_id: s for s in tracker.evaluate(100.001)}
    assert after["g_neg"].state == DeadlineState.MISSED


def test_positive_window_classifies_on_track_approaching_missed() -> None:
    tracker = DeadlineTracker(approach_fraction=0.2)
    # window = 100 -> approaching when remaining <= 20
    tracker.register("g", deadline_wall=100.0, created_wall=0.0)

    on_track = {s.goal_id: s for s in tracker.evaluate(50.0)}["g"]
    assert on_track.state == DeadlineState.ON_TRACK
    assert on_track.remaining_seconds == 50.0

    approaching = {s.goal_id: s for s in tracker.evaluate(85.0)}["g"]
    assert approaching.state == DeadlineState.APPROACHING

    # exactly at the approach boundary (remaining == 20) is APPROACHING
    boundary = {s.goal_id: s for s in tracker.evaluate(80.0)}["g"]
    assert boundary.state == DeadlineState.APPROACHING

    missed = {s.goal_id: s for s in tracker.evaluate(120.0)}["g"]
    assert missed.state == DeadlineState.MISSED


# --------------------------------------------------------------------------- #
# DeadlineTracker — goals without a deadline constraint are not tracked (Req 2.7)
# --------------------------------------------------------------------------- #
def test_goals_without_deadline_are_not_tracked() -> None:
    tracker = DeadlineTracker()
    # No register() call for a goal lacking a deadline constraint.
    assert tracker.evaluate(1_000.0) == []
    # A goal that was never registered is not feasible-checkable.
    assert tracker.can_finish("unknown", 0.0, est_seconds=10.0) is False


def test_can_finish_reflects_remaining_time() -> None:
    tracker = DeadlineTracker()
    tracker.register("g", deadline_wall=100.0, created_wall=0.0)
    # 40s remaining at now=60
    assert tracker.can_finish("g", 60.0, est_seconds=40.0) is True
    assert tracker.can_finish("g", 60.0, est_seconds=40.001) is False
    # past the deadline: no time remaining
    assert tracker.can_finish("g", 120.0, est_seconds=1.0) is False
