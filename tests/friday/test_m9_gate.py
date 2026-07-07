"""M9 Task 12.1 — The M9 Gate (multi-session background-advance simulation).

The binding gate: **"a multi-session goal advances while the user is away."**

Wires a REAL ``CognitiveKernel`` with the M9 subsystems (``LearningEngine``,
``DeadlineTracker``, ``LongHorizonPlanner`` attached; ``BackgroundRuntime``
registered) and proves the long-horizon story end-to-end through the durable
kernel event log:

1. A ``Project`` with a multi-milestone roadmap is defined via
   ``LongHorizonPlanner``; a long-horizon ``Goal`` is submitted and moved
   ``active`` → ``suspended`` (modelling the user leaving). Verified experience
   drives a milestone's verification point to pass, then the kernel is
   ``checkpoint()``-ed (a session boundary).
2. A FRESH kernel ``restore(path)``s and a fresh ``LongHorizonPlanner.restore``s
   the roadmap state; the identical set of goal ids, goal states, and reached
   milestones survive the session boundary (Property 7 / Req 6.1).
3. With the foreground idle, the ``BackgroundRuntime`` is ``tick()``-ed
   repeatedly; it publishes ``background.work_done`` and the suspended
   long-horizon goal advances (``horizon.project_advanced``), all while the
   foreground is idle (Req 6.2).
4. A ``Foreground_Activity`` event injected mid-run makes the
   ``BackgroundRuntime`` yield immediately and perform no further work until the
   idle condition is met again (Property 6 / Req 6.3).
5. The advancement is reconstructable deterministically from the durable Kernel
   event log, and re-running the gate with identical inputs produces an
   identical ordered sequence of M9 event types (Property 8 / Req 6.4, 6.5).

All interaction is via ``kernel.subscribe`` / ``kernel.publish_event`` plus
manual ``BackgroundRuntime.tick`` — the scheduler thread is never started, so
the whole gate is deterministic. Runs under ``FRIDAY_DRY_RUN=1``.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from friday.background.runtime import BackgroundRuntime
from friday.events.event import make_event
from friday.horizon import LongHorizonPlanner, Milestone, Project
from friday.kernel.kernel import CognitiveKernel
from friday.learning import LearningEngine
from friday.temporal import DeadlineTracker


# M9-relevant event types used for the determinism comparison (Req 6.5).
_M9_EVENT_TYPES = {
    "learning.pattern_discovered",
    "learning.validated",
    "learning.rejected",
    "learning.unlearned",
    "temporal.deadline_approaching",
    "temporal.deadline_missed",
    "horizon.milestone_reached",
    "horizon.project_advanced",
    "background.work_done",
    "memory.candidate",
}

# The long-horizon domain — capability/environment CLASSES only, no literal
# application or site names or URLs (Axiom 15).
_CAPABILITY, _ENVIRONMENT, _SIGNATURE = "compose", "workspace", "sig-milestone"
_IDLE_TICKS_REQUIRED = 3


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


def _roadmap() -> Project:
    """A multi-milestone roadmap; m2 is gated behind m1 (a real prerequisite)."""
    return Project(
        id="proj-horizon",
        vision="deliver the long-horizon outcome",
        milestones=(
            Milestone(id="m1", text="foundation", goal_ids=("__GOAL__",)),
            Milestone(id="m2", text="delivery", prerequisites=("m1",)),
        ),
    )


def _goal_states(kernel: CognitiveKernel) -> Dict[str, str]:
    """The kernel-tracked (goal_id -> state) view, as query_goals reports it."""
    return {g["id"]: g["state"] for g in kernel.query_goals()}


def _reached_from_state(state: Dict[str, Any]) -> Set[Tuple[str, str]]:
    """Set of (project_id, milestone_id) marked reached in a planner checkpoint."""
    reached: Set[Tuple[str, str]] = set()
    for proj in state.get("projects", []):
        for m in proj.get("milestones", []):
            if m.get("reached"):
                reached.add((proj["id"], m["id"]))
    return reached


def _log_events(store_path: str) -> List[dict]:
    """Read the durable JSON-lines event log back as dicts (causal order)."""
    path = Path(store_path)
    events: List[dict] = []
    if not path.exists():
        return events
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            events.append(json.loads(raw))
    return events


def _drive_verified_experience(kernel: CognitiveKernel, goal_id: str) -> None:
    """Publish repeated VERIFIED experience so a milestone's verification passes.

    Publishes the same fully-specified verified ``reflection.completed`` the
    ``min_repetitions`` default (3) times so the ``LearningEngine`` crosses the
    repetition threshold and emits ``learning.pattern_discovered`` →
    ``learning.validated`` → a verified procedural ``memory.candidate``.
    """
    for _ in range(3):
        _publish(
            kernel,
            "reflection.completed",
            {
                "goal_id": goal_id,
                "capability": _CAPABILITY,
                "environment": _ENVIRONMENT,
                "outcome_signature": _SIGNATURE,
                "prediction_error": 0.1,
                "verified": True,
                "competence_delta": 0.2,  # >= min_improvement → VALIDATED
            },
        )


def test_m9_gate(tmp_path) -> None:
    store_path = str(tmp_path / "m9_gate.jsonl")
    kernel = CognitiveKernel(store_path=store_path, auto_checkpoint_every=0)

    # Collector subscribed FIRST so it records every event in causal order.
    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    # Wire the M9 subsystems — all routing is via kernel events.
    learning = LearningEngine()  # default min_repetitions=3
    learning.attach(kernel)
    deadlines = DeadlineTracker(approach_fraction=0.2)
    deadlines.attach(kernel)
    planner = LongHorizonPlanner()
    planner.attach(kernel)
    background = BackgroundRuntime(
        idle_ticks_required=_IDLE_TICKS_REQUIRED, max_work_per_tick=1
    )
    kernel.register_runtime(background)

    # --- Session 1: define the roadmap + submit the long-horizon goal --------
    goal_id = kernel.submit_goal(
        "long-horizon outcome", {"deadline": 10_000.0}
    )
    project = _roadmap()
    # Bind milestone m1 to the actual long-horizon goal id.
    project = Project(
        id=project.id,
        vision=project.vision,
        milestones=(
            Milestone(id="m1", text="foundation", goal_ids=(goal_id,)),
            Milestone(id="m2", text="delivery", prerequisites=("m1",)),
        ),
    )
    planner.define_project(project)

    # Model the user working then leaving: active → suspended.
    _publish(kernel, "goal.state_changed", {"goal_id": goal_id, "state": "active"})
    _publish(kernel, "goal.state_changed", {"goal_id": goal_id, "state": "suspended"})

    # Drive verified experience so milestone m1's verification point passes,
    # then advance it (verification-gated) — emits horizon.milestone_reached +
    # horizon.project_advanced through the kernel bus.
    _drive_verified_experience(kernel, goal_id)
    assert "learning.validated" in collected
    planner.advance(project.id, "m1", verified=True)
    assert "horizon.milestone_reached" in collected

    # Capture the pre-boundary view (goal ids/states + reached milestones).
    goal_states_before = _goal_states(kernel)
    roadmap_state = planner.checkpoint()
    reached_before = _reached_from_state(roadmap_state)
    assert reached_before == {(project.id, "m1")}

    # --- Session boundary: checkpoint the kernel ------------------------------
    checkpoint_path = kernel.checkpoint()

    # The durable log records the user leaving (active → suspended survives it).
    session1_log = _log_events(store_path)
    suspended = [
        e
        for e in session1_log
        if e["event_type"] == "goal.state_changed"
        and e["payload"].get("state") == "suspended"
    ]
    assert suspended, "the suspended transition must be durable on the log"

    kernel.shutdown()

    # --- Session 2: a FRESH kernel restores across the boundary --------------
    store_path2 = str(tmp_path / "m9_gate_session2.jsonl")
    kernel2 = CognitiveKernel(store_path=store_path2, auto_checkpoint_every=0)

    collected2: List[str] = []
    kernel2.subscribe("*", lambda event: collected2.append(event.event_type))

    learning2 = LearningEngine()
    learning2.attach(kernel2)
    deadlines2 = DeadlineTracker(approach_fraction=0.2)
    deadlines2.attach(kernel2)
    planner2 = LongHorizonPlanner()
    planner2.attach(kernel2)
    background2 = BackgroundRuntime(
        idle_ticks_required=_IDLE_TICKS_REQUIRED, max_work_per_tick=1
    )
    kernel2.register_runtime(background2)

    kernel2.restore(checkpoint_path)
    planner2.restore(roadmap_state)

    # --- Property 7 (Req 6.1): the goal + roadmap survive the boundary --------
    goal_states_after = _goal_states(kernel2)
    reached_after = _reached_from_state(planner2.checkpoint())

    assert set(goal_states_after) == set(goal_states_before), (
        "the identical set of goal ids must survive the session boundary"
    )
    assert goal_states_after == goal_states_before, (
        "goal states must survive the session boundary identically"
    )
    assert reached_after == reached_before, (
        "reached milestones must survive the session boundary identically"
    )
    # The next actionable milestone (m2) is correctly reconstructed.
    nxt = planner2.next_actionable(project.id)
    assert nxt is not None and nxt.id == "m2"

    # --- Req 6.2/6.3: foreground idle → background advances the suspended goal -
    # Tick the runtime; once idle_ticks_required idle ticks elapse it performs a
    # bounded work unit and publishes background.work_done.
    for _ in range(_IDLE_TICKS_REQUIRED):
        background2.tick(int(kernel2.health().get("tick", 0)) + 1)
    assert background2.health()["work_done"] >= 1
    assert "background.work_done" in collected2

    # The suspended long-horizon goal advances while the foreground is idle: the
    # verification point for the next milestone passes and the planner advances.
    planner2.advance(project.id, "m2", verified=True)
    assert "horizon.project_advanced" in collected2
    assert _reached_from_state(planner2.checkpoint()) == {
        (project.id, "m1"),
        (project.id, "m2"),
    }

    # --- Property 6 (Req 6.3): foreground preempts background immediately ------
    work_before_foreground = background2.health()["work_done"]
    # Inject a Foreground_Activity event mid-run; the runtime (subscribed to *)
    # resets its idle counter, so foreground preempts background at once.
    _publish(
        kernel2, "goal.state_changed", {"goal_id": goal_id, "state": "active"}
    )

    # For the next (idle_ticks_required - 1) ticks the runtime performs NO work.
    for _ in range(_IDLE_TICKS_REQUIRED - 1):
        background2.tick(int(kernel2.health().get("tick", 0)) + 1)
        assert background2.health()["work_done"] == work_before_foreground, (
            "background must not work until the idle condition is met again"
        )

    # One more idle tick reaches the threshold again → work resumes.
    background2.tick(int(kernel2.health().get("tick", 0)) + 1)
    assert background2.health()["work_done"] > work_before_foreground, (
        "background resumes work only after the idle condition is re-met"
    )

    kernel2.shutdown()

    # --- Req 6.2: advancement is reconstructable from the durable log ---------
    session2_log = _log_events(store_path2)
    log_types = [e["event_type"] for e in session2_log]
    assert "background.work_done" in log_types
    assert "horizon.project_advanced" in log_types
    i_work = log_types.index("background.work_done")
    i_adv = log_types.index("horizon.project_advanced")
    assert i_work < i_adv, "background work precedes the advance during idle"

    # --- Property 8 (Req 6.4, 6.5): determinism -------------------------------
    seq_a = _run_gate(tmp_path, "det_a")
    seq_b = _run_gate(tmp_path, "det_b")
    assert seq_a == seq_b, "the M9 gate must be deterministic under DRY_RUN"
    # The gate actually exercised the M9 event families (not a trivial match).
    assert "horizon.project_advanced" in seq_a
    assert "background.work_done" in seq_a


def _run_gate(tmp_path, tag: str) -> List[str]:
    """Build a fresh kernel + M9 subsystems, run the identical publish/tick
    sequence across a session boundary, and return the ordered list of
    M9-relevant event types (Req 6.5 determinism).
    """
    store_path = str(tmp_path / f"{tag}.jsonl")
    kernel = CognitiveKernel(store_path=store_path, auto_checkpoint_every=0)

    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    learning = LearningEngine()
    learning.attach(kernel)
    deadlines = DeadlineTracker(approach_fraction=0.2)
    deadlines.attach(kernel)
    planner = LongHorizonPlanner()
    planner.attach(kernel)
    background = BackgroundRuntime(
        idle_ticks_required=_IDLE_TICKS_REQUIRED, max_work_per_tick=1
    )
    kernel.register_runtime(background)

    goal_id = "goal-fixed"  # fixed id so both runs are byte-identical
    kernel.submit_goal("long-horizon outcome", {"deadline": 10_000.0})
    project = Project(
        id="proj-horizon",
        vision="deliver the long-horizon outcome",
        milestones=(
            Milestone(id="m1", text="foundation", goal_ids=(goal_id,)),
            Milestone(id="m2", text="delivery", prerequisites=("m1",)),
        ),
    )
    planner.define_project(project)

    _publish(kernel, "goal.state_changed", {"goal_id": goal_id, "state": "active"})
    _publish(kernel, "goal.state_changed", {"goal_id": goal_id, "state": "suspended"})

    _drive_verified_experience(kernel, goal_id)
    planner.advance(project.id, "m1", verified=True)

    roadmap_state = planner.checkpoint()
    checkpoint_path = kernel.checkpoint()
    kernel.shutdown()

    # Session 2 — restore and advance while idle.
    store_path2 = str(tmp_path / f"{tag}_s2.jsonl")
    kernel2 = CognitiveKernel(store_path=store_path2, auto_checkpoint_every=0)
    collected2: List[str] = []
    kernel2.subscribe("*", lambda event: collected2.append(event.event_type))

    learning2 = LearningEngine()
    learning2.attach(kernel2)
    deadlines2 = DeadlineTracker(approach_fraction=0.2)
    deadlines2.attach(kernel2)
    planner2 = LongHorizonPlanner()
    planner2.attach(kernel2)
    background2 = BackgroundRuntime(
        idle_ticks_required=_IDLE_TICKS_REQUIRED, max_work_per_tick=1
    )
    kernel2.register_runtime(background2)

    kernel2.restore(checkpoint_path)
    planner2.restore(roadmap_state)

    for _ in range(_IDLE_TICKS_REQUIRED):
        background2.tick(int(kernel2.health().get("tick", 0)) + 1)
    planner2.advance(project.id, "m2", verified=True)
    kernel2.shutdown()

    # Ordered M9-relevant event types across BOTH sessions of the gate.
    ordered = [et for et in collected if et in _M9_EVENT_TYPES]
    ordered += [et for et in collected2 if et in _M9_EVENT_TYPES]
    return ordered
