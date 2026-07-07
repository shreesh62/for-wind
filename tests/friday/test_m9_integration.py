"""M9 Task 11.1 — kernel-event integration test (learning/temporal/horizon/background).

Builds a REAL ``CognitiveKernel``, attaches the M8 ``ReflectionEngine`` producer
plus the M9 ``LearningEngine``, ``DeadlineTracker``, and ``LongHorizonPlanner``,
and ``register_runtime``s the ``BackgroundRuntime``. It then drives
``action.executed`` / ``verification.completed`` / ``reflection.completed`` /
``competence.updated`` / ``goal.*`` events through ``kernel.publish_event`` and
asserts the expected ``learning.*`` / ``temporal.*`` / ``horizon.*`` /
``background.work_done`` events land on the kernel event log in causal order.

Everything flows through ``kernel.subscribe`` / ``kernel.publish_event`` — no M9
subsystem is ever called directly to route an event (the planner's verification-
gated ``advance`` is the sole deliberate exception, and it too emits via
``publish_event``). The kernel routes synchronously in ``_persist_and_route``, so
by the time a ``publish_event`` returns the entire nested causal chain is already
on the log. To stay deterministic the background scheduler thread is never
started; the ``BackgroundRuntime`` is ticked manually.

Runs under ``FRIDAY_DRY_RUN=1`` so no real filesystem/LLM/OS surface is touched.

Validates: Requirements 5.1, 6.2, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List

from friday.background.runtime import BackgroundRuntime
from friday.cognition.reflection import ReflectionEngine
from friday.events.event import make_event
from friday.horizon import LongHorizonPlanner, Milestone, Project
from friday.kernel.kernel import CognitiveKernel
from friday.learning import LearningEngine
from friday.temporal import DeadlineTracker


def _publish(kernel: CognitiveKernel, event_type: str, payload: dict) -> None:
    """Publish an event through the kernel with a monotonically advancing tick."""
    tick = int(kernel.health().get("tick", 0)) + 1
    kernel.publish_event(
        make_event(
            event_type=event_type,
            source="test",
            logical_time=tick,
            payload=payload,
        )
    )


def _first(collected: List[str], event_type: str) -> int:
    """First-occurrence index of an event type (asserts presence)."""
    assert event_type in collected, f"expected {event_type!r} on the event log"
    return collected.index(event_type)


def test_m9_kernel_event_integration(tmp_path) -> None:
    # Unique store path per test so parallel/repeat runs never collide on disk.
    kernel = CognitiveKernel(
        store_path=str(tmp_path / "m9.jsonl"), auto_checkpoint_every=0
    )

    # Collector subscribed FIRST so it records every event in causal order,
    # including the nested events subsystems publish from their handlers.
    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    # Wire the M8 producer + M9 subsystems — ALL routing is via kernel events.
    reflection = ReflectionEngine()
    reflection.attach(kernel)

    learning = LearningEngine()  # default min_repetitions=3
    learning.attach(kernel)

    deadlines = DeadlineTracker(approach_fraction=0.2)
    deadlines.attach(kernel)

    planner = LongHorizonPlanner()
    planner.attach(kernel)

    # idle_ticks_required=1 so a single manual tick (after foreground goes quiet)
    # is enough to perform one bounded background work unit deterministically.
    background = BackgroundRuntime(idle_ticks_required=1, max_work_per_tick=1)
    kernel.register_runtime(background)

    capability, environment, signature = "search", "web", "sig-outcome"

    # --- M8 producer flow: action.executed → verification.completed ----------
    # Demonstrates the M8 ReflectionEngine producing reflection.completed +
    # memory.candidate purely through the kernel bus.
    _publish(
        kernel,
        "action.executed",
        {
            "goal_id": "g1",
            "capability": capability,
            "environment": environment,
            "prediction": {
                "expected_beliefs": ["found info"],
                "confidence": 0.6,
                "reversible": True,
            },
        },
    )
    _publish(
        kernel,
        "verification.completed",
        {
            "goal_id": "g1",
            "capability": capability,
            "environment": environment,
            "satisfied": True,
            "observed_beliefs": ["found info"],
        },
    )
    assert "reflection.completed" in collected
    assert "memory.candidate" in collected

    # --- Learning flow: repeated VERIFIED reflection.completed → promotion ----
    # Publish the same fully-specified verified experience min_repetitions times;
    # the LearningEngine folds each through ingest() and, on the threshold
    # crossing, emits learning.pattern_discovered → learning.validated → a
    # verified procedural memory.candidate.
    for _ in range(3):
        _publish(
            kernel,
            "reflection.completed",
            {
                "goal_id": "g1",
                "capability": capability,
                "environment": environment,
                "outcome_signature": signature,
                "prediction_error": 0.1,
                "verified": True,
                "competence_delta": 0.2,  # >= min_improvement → VALIDATED
            },
        )

    # --- Competence flow: competence.updated feeds improvement tracking -------
    for confidence in (0.4, 0.7):
        _publish(
            kernel,
            "competence.updated",
            {
                "capability": capability,
                "environment": environment,
                "confidence": confidence,
            },
        )
    assert learning.improvement((capability, environment)) == 0.7 - 0.4

    # --- Temporal flow: goal.created with a deadline → goal.state_changed ------
    # created at wall 100 with a deadline at 200; a later state change at 300 is
    # past the deadline → temporal.deadline_missed.
    _publish(
        kernel,
        "goal.created",
        {
            "goal_id": "g-deadline",
            "text": "time-boxed goal",
            "constraints": {"deadline": 200.0},
            "now_wall": 100.0,
        },
    )
    _publish(
        kernel,
        "goal.state_changed",
        {
            "goal_id": "g-deadline",
            "state": "active",
            "reason": "",
            "now_wall": 300.0,
        },
    )

    # --- Horizon flow: define a roadmap, advance a milestone (verification-gated)
    project = Project(
        id="proj-1",
        vision="ship the thing",
        milestones=(
            Milestone(id="m1", text="first", goal_ids=("g1",)),
            Milestone(id="m2", text="second", prerequisites=("m1",)),
        ),
    )
    planner.define_project(project)
    # advance() emits horizon.milestone_reached + horizon.project_advanced via
    # kernel.publish_event once the verification point passes.
    planner.advance("proj-1", "m1", verified=True)

    # --- Background flow: foreground is now quiet; tick the runtime manually ---
    # The last foreground-activity event (goal.state_changed) reset the idle
    # counter; a single tick reaches the idle threshold and performs one bounded
    # work unit, publishing background.work_done through the kernel.
    background.tick(logical_time=int(kernel.health().get("tick", 0)) + 1)

    kernel.shutdown()

    # ------------------------------------------------------------------ #
    # Assertions: every expected family landed on the log, in causal order.
    # ------------------------------------------------------------------ #
    i_reflection = _first(collected, "reflection.completed")
    i_pattern = _first(collected, "learning.pattern_discovered")
    i_validated = _first(collected, "learning.validated")
    _first(collected, "memory.candidate")  # present (from reflection and learning)
    i_goal_created = _first(collected, "goal.created")
    i_missed = _first(collected, "temporal.deadline_missed")
    i_reached = _first(collected, "horizon.milestone_reached")
    i_advanced = _first(collected, "horizon.project_advanced")
    i_work = _first(collected, "background.work_done")

    # Learning: a pattern must be discovered before it can be validated. The
    # validated learning is accompanied by a verified procedural memory.candidate
    # (asserted from the durable log below).
    assert i_reflection < i_pattern, "pattern follows the reflection stream"
    assert i_pattern < i_validated, "validation follows pattern discovery"

    # Temporal: a deadline can only be missed after the goal that carries it is
    # created.
    assert i_goal_created < i_missed, "deadline_missed follows goal.created"

    # Horizon: a project advances only after a milestone is reached.
    assert i_reached < i_advanced, "project_advanced follows milestone_reached"

    # Background: opportunistic work happens last, once the foreground is idle.
    assert i_work > i_missed, "background work runs after foreground activity"

    # The validated payload carries the promotion evidence (Event Vocabulary).
    validated = next(
        e for e in _log_events(kernel_store_path=str(tmp_path / "m9.jsonl"))
        if e["event_type"] == "learning.validated"
    )
    assert "principle_id" in validated["payload"]
    assert "improvement" in validated["payload"]

    # A verified, pattern-kind procedural candidate was proposed by learning.
    learning_candidates = [
        e
        for e in _log_events(kernel_store_path=str(tmp_path / "m9.jsonl"))
        if e["event_type"] == "memory.candidate"
        and e["payload"].get("kind") == "pattern"
        and e["payload"].get("verified") is True
    ]
    assert learning_candidates, "expected a verified pattern memory.candidate"

    # background.work_done payload names the unit and is DRY_RUN-audited.
    work_events = [
        e
        for e in _log_events(kernel_store_path=str(tmp_path / "m9.jsonl"))
        if e["event_type"] == "background.work_done"
    ]
    assert work_events
    assert "unit" in work_events[0]["payload"]


def _log_events(*, kernel_store_path: str) -> List[dict]:
    """Read the durable JSON-lines event log back as dicts (causal order)."""
    import json
    from pathlib import Path

    path = Path(kernel_store_path)
    events: List[dict] = []
    if not path.exists():
        return events
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            events.append(json.loads(raw))
    return events
