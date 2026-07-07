"""M9 — Tests for the BackgroundRuntime (tasks 8.3 + 8.4).

Covers:
- **Property 6: Background yields to foreground** (task 8.3) — a foreground
  activity event resets the idle counter so no Background_Work_Unit runs until
  ``idle_ticks_required`` idle ticks have elapsed again.
- Unit tests for the RuntimeContract surface, ``checkpoint()``/``restore()``
  round-trips, and degraded-mode containment when a work unit raises (task 8.4).

Every test runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external
surface is ever touched.

_Requirements: 4.1, 4.2, 4.3, 4.4, 4.7, 6.3, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import fnmatch
from typing import Any, List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.background.runtime import (
    FOREGROUND_ACTIVITY_EVENTS,
    BackgroundRuntime,
)
from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract


# --------------------------------------------------------------------------- #
# Fake kernel — captures published events + routes them to runtime.receive,
# mirroring the real CognitiveKernel wiring (subscribe("*", runtime.receive)).
# --------------------------------------------------------------------------- #
class FakeKernel:
    """Minimal kernel double for exercising a runtime in isolation."""

    def __init__(self) -> None:
        self.published: List[Event] = []
        self._subscribers: List[Tuple[str, Any]] = []
        self._logical = 0

    def subscribe(self, pattern: str, handler: Any) -> str:
        self._subscribers.append((pattern, handler))
        return f"sub-{len(self._subscribers)}"

    def publish_event(self, event: Event) -> None:
        # Mirror the real EventBus: dispatch by fnmatch pattern so a handler
        # subscribed to specific event types is not invoked for others.
        self.published.append(event)
        for pattern, handler in list(self._subscribers):
            if fnmatch.fnmatch(event.event_type, pattern):
                handler(event)

    def next_logical(self) -> int:
        self._logical += 1
        return self._logical


def _foreground_event(logical_time: int) -> Event:
    return make_event(
        event_type=FOREGROUND_ACTIVITY_EVENTS[0],
        source="test",
        logical_time=logical_time,
        payload={"goal_id": "g-1", "state": "active"},
    )


def _work_done_events(kernel: FakeKernel) -> List[Event]:
    return [e for e in kernel.published if e.event_type == "background.work_done"]


# --------------------------------------------------------------------------- #
# Property 6: Background yields to foreground (task 8.3)
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    idle_required=st.integers(min_value=1, max_value=6),
    # A schedule of booleans: True = inject a foreground event before this tick.
    schedule=st.lists(st.booleans(), min_size=1, max_size=40),
)
def test_property6_background_yields_to_foreground(
    idle_required: int, schedule: List[bool]
) -> None:
    """**Property 6: Background yields to foreground**

    **Validates: Requirements 4.2, 4.3, 4.4, 6.3**

    For any interleaving of foreground-activity events and ticks, a work unit is
    performed on a tick only if no foreground activity occurred within the
    preceding ``idle_ticks_required`` ticks. Any foreground event resets the
    idle counter, so background never runs while the foreground is active.
    """
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=idle_required, max_work_per_tick=1)
    runtime.initialize(kernel)

    # Track consecutive idle ticks with an independent reference model.
    idle_streak = 0
    for inject_foreground in schedule:
        if inject_foreground:
            # A foreground event arrives before this tick — resets idleness.
            kernel.publish_event(_foreground_event(kernel.next_logical()))
            idle_streak = 0

        before = runtime.health()["work_done"]
        runtime.tick(kernel.next_logical())
        after = runtime.health()["work_done"]
        did_work = after > before

        # Reference model: this tick counts toward the idle streak.
        idle_streak += 1
        should_be_allowed = idle_streak >= idle_required

        if did_work:
            # Work is only ever permitted once idle long enough (Req 4.2/4.3).
            assert should_be_allowed, (
                f"work performed after only {idle_streak} idle ticks "
                f"(required {idle_required})"
            )

    # A foreground event immediately preempts: right after one, the next tick
    # must not perform work unless idle_required == 1.
    kernel.publish_event(_foreground_event(kernel.next_logical()))
    before = runtime.health()["work_done"]
    runtime.tick(kernel.next_logical())
    after = runtime.health()["work_done"]
    if idle_required > 1:
        assert after == before, "background did not yield immediately after foreground"


@settings(max_examples=100, deadline=None)
@given(idle_required=st.integers(min_value=1, max_value=5))
def test_property6_work_resumes_after_idle_gap(idle_required: int) -> None:
    """**Property 6: Background yields to foreground**

    **Validates: Requirements 4.2, 4.3, 4.4, 6.3**

    After a foreground event resets idleness, exactly ``idle_ticks_required``
    consecutive idle ticks are needed before a work unit runs again.
    """
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=idle_required, max_work_per_tick=1)
    runtime.initialize(kernel)

    # Reset idleness with a foreground event.
    kernel.publish_event(_foreground_event(kernel.next_logical()))

    # The first (idle_required - 1) idle ticks must perform no work.
    for _ in range(idle_required - 1):
        before = runtime.health()["work_done"]
        runtime.tick(kernel.next_logical())
        assert runtime.health()["work_done"] == before

    # The idle_required-th idle tick is allowed to perform work.
    before = runtime.health()["work_done"]
    runtime.tick(kernel.next_logical())
    assert runtime.health()["work_done"] == before + 1


# --------------------------------------------------------------------------- #
# Task 8.4 — RuntimeContract surface + checkpoint/restore + degraded mode
# --------------------------------------------------------------------------- #
def test_implements_runtime_contract_surface() -> None:
    """All RuntimeContract members are present (Req 4.1)."""
    runtime = BackgroundRuntime()
    assert isinstance(runtime, RuntimeContract)
    assert runtime.name == "background"
    for member in (
        "initialize",
        "tick",
        "observe",
        "receive",
        "publish",
        "checkpoint",
        "restore",
        "shutdown",
        "health",
    ):
        assert callable(getattr(runtime, member)), f"missing {member}"
    assert runtime.observe() == []


def test_checkpoint_restore_round_trips() -> None:
    """``checkpoint()`` → ``restore()`` reproduces the runtime stats."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=2, max_work_per_tick=1)
    runtime.initialize(kernel)

    # Drive some idle ticks so work is performed and internal counters advance.
    for _ in range(5):
        runtime.tick(kernel.next_logical())

    snapshot = runtime.checkpoint()
    assert isinstance(snapshot, dict)
    # Must be JSON-serializable (no exotic types).
    import json

    json.dumps(snapshot)

    restored = BackgroundRuntime()
    restored.restore(snapshot)
    restored_snapshot = restored.checkpoint()

    for key in ("idle_ticks", "idle_ticks_required", "max_work_per_tick", "work_done"):
        assert restored_snapshot[key] == snapshot[key], f"mismatch on {key}"


def test_restore_ignores_non_dict_state() -> None:
    """A malformed (non-dict) restore payload is tolerated without raising."""
    runtime = BackgroundRuntime()
    runtime.restore(None)  # type: ignore[arg-type]
    runtime.restore("not-a-dict")  # type: ignore[arg-type]
    assert runtime.checkpoint()["name"] == "background"


def test_work_units_emit_auditable_events_under_dry_run() -> None:
    """Idle ticks publish auditable ``background.work_done`` events (Req 4.6/4.8)."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=1, max_work_per_tick=1)
    runtime.initialize(kernel)

    runtime.tick(kernel.next_logical())

    work_events = _work_done_events(kernel)
    assert len(work_events) == 1
    payload = work_events[0].payload
    assert payload["dry_run"] is True
    assert payload["unit"]
    assert "logical_time" in payload


def test_memory_proposals_only_via_memory_candidate() -> None:
    """A memory write is proposed ONLY through a ``memory.candidate`` event."""
    kernel = FakeKernel()
    # max_work_per_tick large enough to eventually run the consolidation unit.
    runtime = BackgroundRuntime(idle_ticks_required=1, max_work_per_tick=4)
    runtime.initialize(kernel)

    # Several idle ticks so the round-robin reaches _consolidate_memory.
    for _ in range(4):
        runtime.tick(kernel.next_logical())

    candidates = [e for e in kernel.published if e.event_type == "memory.candidate"]
    assert candidates, "consolidation never proposed a memory.candidate"
    for cand in candidates:
        assert cand.payload.get("kind") == "pattern"
        assert cand.payload.get("verified") is True


def test_raising_work_unit_is_contained_and_reports_degraded() -> None:
    """A raising work unit is contained; ``health()`` reports degraded (Req 4.7)."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=1, max_work_per_tick=1)
    runtime.initialize(kernel)

    boom_calls: List[int] = []

    def _boom(logical_time: int) -> bool:
        boom_calls.append(logical_time)
        raise RuntimeError("simulated work-unit failure")

    # Force the very first unit to raise.
    runtime._consolidate_memory = _boom  # type: ignore[assignment]

    # The tick must NOT raise into the kernel loop.
    runtime.tick(kernel.next_logical())

    assert boom_calls, "the raising unit was never invoked"
    health = runtime.health()
    assert health["status"] == "degraded"
    assert "work_unit_failed" in health["reason"]


def test_tick_loop_survives_repeated_failures() -> None:
    """Repeated failing units never crash the tick loop (Req 4.7)."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=1, max_work_per_tick=1)
    runtime.initialize(kernel)

    def _boom(logical_time: int) -> bool:  # noqa: ARG001
        raise ValueError("boom")

    runtime._consolidate_memory = _boom  # type: ignore[assignment]
    runtime._apply_competence_decay = _boom  # type: ignore[assignment]
    runtime._check_freshness = _boom  # type: ignore[assignment]
    runtime._advance_long_horizon = _boom  # type: ignore[assignment]

    for _ in range(10):
        runtime.tick(kernel.next_logical())  # must never raise

    assert runtime.health()["status"] == "degraded"


def test_no_work_before_idle_threshold() -> None:
    """No work unit runs until the idle threshold is reached (Req 4.2)."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=3, max_work_per_tick=1)
    runtime.initialize(kernel)

    runtime.tick(kernel.next_logical())
    runtime.tick(kernel.next_logical())
    assert _work_done_events(kernel) == []

    runtime.tick(kernel.next_logical())  # third idle tick — allowed
    assert len(_work_done_events(kernel)) == 1


def test_receive_resets_idle_on_foreground_event() -> None:
    """``receive`` resets the idle counter on a foreground-activity event (Req 4.4)."""
    kernel = FakeKernel()
    runtime = BackgroundRuntime(idle_ticks_required=2, max_work_per_tick=1)
    runtime.initialize(kernel)

    runtime.tick(kernel.next_logical())  # idle streak = 1
    runtime.receive(_foreground_event(kernel.next_logical()))  # reset

    before = runtime.health()["work_done"]
    runtime.tick(kernel.next_logical())  # idle streak = 1 again -> no work
    assert runtime.health()["work_done"] == before
