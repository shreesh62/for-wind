"""M9 — Property-based tests (Hypothesis) for learning/temporal/horizon/background.

Realizes the correctness properties from the M9 design document
(``.kiro/specs/m9-learning-temporal-background/design.md``) as Hypothesis
property tests. Every test runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O
or external surface is ever touched.

Each test carries its design property number and a ``Validates: Requirements``
annotation in its docstring.
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import fnmatch
from typing import Any, List, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from friday.events.event import Event, make_event
from friday.learning import LearningEngine, Principle
from friday.temporal import DeadlineState, DeadlineTracker, KnowledgeAging

# Validator policy anchors (engine defaults) the learning properties reason against.
# ingest derives observed = neutral_prior + competence_delta and baseline = neutral_prior,
# so the measured improvement equals competence_delta.
_MIN_IMPROVEMENT = 0.05
_RETIRE_FLOOR = 0.2
_MIN_REPETITIONS = 3


def _is_non_increasing(values: List[float], tol: float = 1e-9) -> bool:
    return all(values[i] + tol >= values[i + 1] for i in range(len(values) - 1))


# --------------------------------------------------------------------------- #
# Property 4 — Temporal decay is monotonic
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    observed_at=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    half_life=st.floats(min_value=1e-3, max_value=1e7, allow_nan=False, allow_infinity=False),
    deltas=st.lists(
        st.floats(min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    ),
)
def test_property_4_temporal_decay_is_monotonic(
    observed_at: float, half_life: float, deltas: List[float]
) -> None:
    """Property 4: Temporal decay is monotonic.

    For a fixed ``observed_at`` and ``half_life``, ``KnowledgeAging.freshness`` is
    monotonically non-increasing as ``now`` increases, always stays within
    ``[0, 1]``, and equals ``1.0`` when ``now == observed_at``.

    Validates: Requirements 2.2
    """
    aging = KnowledgeAging(half_life_seconds=half_life)

    # Equals exactly 1.0 at the moment of observation.
    assert aging.freshness(observed_at, observed_at) == 1.0

    # Evaluate at strictly non-decreasing times now = observed_at + cumulative delta.
    now = observed_at
    freshness_values: List[float] = []
    for delta in sorted(deltas):
        now = observed_at + delta
        value = aging.freshness(observed_at, now)
        assert 0.0 <= value <= 1.0
        freshness_values.append(value)

    assert _is_non_increasing(freshness_values)


# --------------------------------------------------------------------------- #
# Fake kernel — captures published events + routes them to subscribed handlers,
# mirroring the real CognitiveKernel wiring (subscribe(pattern, handler)).
# --------------------------------------------------------------------------- #
class FakeKernel:
    """Minimal kernel double for exercising the DeadlineTracker in isolation."""

    def __init__(self) -> None:
        self.published: List[Event] = []
        self._subscribers: List[Tuple[str, Any]] = []
        self._logical = 0

    def subscribe(self, pattern: str, handler: Any) -> str:
        self._subscribers.append((pattern, handler))
        return f"sub-{len(self._subscribers)}"

    def publish_event(self, event: Event) -> None:
        self.published.append(event)
        for pattern, handler in list(self._subscribers):
            if fnmatch.fnmatch(event.event_type, pattern):
                handler(event)

    def health(self) -> dict:
        return {"tick": self._logical}

    def next_logical(self) -> int:
        self._logical += 1
        return self._logical


def _events_of(kernel: FakeKernel, event_type: str) -> List[Event]:
    return [e for e in kernel.published if e.event_type == event_type]


# --------------------------------------------------------------------------- #
# Property 5 — Deadline detection
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    created_wall=st.floats(
        min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
    ),
    total_window=st.floats(
        min_value=1.0, max_value=1e7, allow_nan=False, allow_infinity=False
    ),
    approach_fraction=st.floats(
        min_value=0.05, max_value=0.9, allow_nan=False, allow_infinity=False
    ),
    # A fraction (0..2) of the window that has elapsed at evaluation time; > 1
    # means the deadline has already passed.
    elapsed_fraction=st.floats(
        min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False
    ),
)
def test_property_5_deadline_detection(
    created_wall: float,
    total_window: float,
    approach_fraction: float,
    elapsed_fraction: float,
) -> None:
    """Property 5: Deadline detection.

    For generated windows/now values, a goal past its deadline is ``MISSED`` and
    emits ``temporal.deadline_missed``; a goal within ``approach_fraction`` of the
    window remaining is ``APPROACHING`` and emits ``temporal.deadline_approaching``.
    Classification is verified against the same anchors the tracker uses, and the
    published events must agree with the classification.

    Validates: Requirements 2.4, 2.5
    """
    deadline_wall = created_wall + total_window
    now_wall = created_wall + elapsed_fraction * total_window

    kernel = FakeKernel()
    tracker = DeadlineTracker(approach_fraction=approach_fraction)
    tracker.attach(kernel)

    goal_id = "g-deadline"
    # goal.created carries the deadline on a constraints mapping and pins the
    # creation-time anchor (now == created_wall at creation). now_wall pins the
    # evaluation time deterministically (no real clock under DRY_RUN).
    kernel.publish_event(
        make_event(
            event_type="goal.created",
            source="test",
            logical_time=kernel.next_logical(),
            payload={
                "goal_id": goal_id,
                "text": "some goal",
                "constraints": {"deadline": deadline_wall},
                "now_wall": created_wall,
            },
        )
    )
    # A later state change drives re-evaluation at now_wall.
    kernel.publish_event(
        make_event(
            event_type="goal.state_changed",
            source="test",
            logical_time=kernel.next_logical(),
            payload={
                "goal_id": goal_id,
                "state": "active",
                "reason": "",
                "now_wall": now_wall,
            },
        )
    )

    # Reference classification using the tracker's OWN stored anchors so the
    # boundary comparison matches bit-for-bit (the tracker recomputes
    # total_window as deadline_wall - created_wall, which can differ from the
    # generated total_window by float rounding).
    remaining = deadline_wall - now_wall
    stored_window = deadline_wall - created_wall
    if now_wall > deadline_wall:
        expected = DeadlineState.MISSED
    elif stored_window > 0.0 and remaining <= approach_fraction * stored_window:
        expected = DeadlineState.APPROACHING
    else:
        expected = DeadlineState.ON_TRACK

    # The pure core must agree with the reference model.
    statuses = tracker.evaluate(now_wall)
    assert len(statuses) == 1
    assert statuses[0].state == expected

    missed = _events_of(kernel, "temporal.deadline_missed")
    approaching = _events_of(kernel, "temporal.deadline_approaching")

    if expected is DeadlineState.MISSED:
        assert len(missed) == 1
        assert not approaching
        assert missed[0].payload["goal_id"] == goal_id
        assert missed[0].payload["overrun_seconds"] == now_wall - deadline_wall
        assert missed[0].payload["deadline_wall"] == deadline_wall
    elif expected is DeadlineState.APPROACHING:
        assert len(approaching) == 1
        assert not missed
        assert approaching[0].payload["goal_id"] == goal_id
        assert approaching[0].payload["remaining_seconds"] == remaining
        assert approaching[0].payload["deadline_wall"] == deadline_wall
    else:
        assert not missed
        assert not approaching


# --------------------------------------------------------------------------- #
# Learning helpers — build the M8-stream events the LearningEngine folds.
# --------------------------------------------------------------------------- #
def _reflection_event(
    kernel: FakeKernel,
    *,
    goal_id: str,
    capability: str,
    environment: str,
    outcome_signature: str,
    verified: bool,
    competence_delta: float,
    prediction_error: float = 0.1,
) -> Event:
    """A ``reflection.completed`` event carrying a fully-specified experience.

    Supplies inline ``capability``/``environment``/``outcome_signature`` so
    ``LearningEngine._on_reflection_completed`` builds a deterministic
    :class:`~friday.learning.models.VerifiedExperience` without needing cached context.
    """

    return make_event(
        event_type="reflection.completed",
        source="test",
        logical_time=kernel.next_logical(),
        payload={
            "goal_id": goal_id,
            "capability": capability,
            "environment": environment,
            "outcome_signature": outcome_signature,
            "prediction_error": prediction_error,
            "verified": verified,
            "competence_delta": competence_delta,
        },
    )


# --------------------------------------------------------------------------- #
# Property 1 — Learn only from verified experience
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    capability=st.text(min_size=1, max_size=12),
    environment=st.text(min_size=1, max_size=12),
    signature=st.text(min_size=1, max_size=12),
    # Repeat the SAME unverified signature well past the repetition threshold, so
    # only the verified gate — never a lack of repetition — can prevent learning.
    repetitions=st.integers(min_value=_MIN_REPETITIONS, max_value=10),
    # A delta that WOULD validate if the experience were verified (rules out the
    # improvement gate as the reason nothing is learned).
    competence_delta=st.floats(
        min_value=_MIN_IMPROVEMENT, max_value=0.49, allow_nan=False, allow_infinity=False
    ),
)
def test_property_1_learn_only_from_verified_experience(
    capability: str,
    environment: str,
    signature: str,
    repetitions: int,
    competence_delta: float,
) -> None:
    """Property 1: Learn only from verified experience.

    An experience whose ``verified`` flag is not ``True`` never contributes to a
    discovered pattern, never produces a validated principle, and never yields a
    procedural ``memory.candidate`` — even when the same signature repeats past the
    repetition threshold and carries a delta that would otherwise validate.

    Validates: Requirements 1.1, 1.9
    """
    kernel = FakeKernel()
    engine = LearningEngine()
    engine.attach(kernel)

    for _ in range(repetitions):
        kernel.publish_event(
            _reflection_event(
                kernel,
                goal_id="g-unverified",
                capability=capability,
                environment=environment,
                outcome_signature=signature,
                verified=False,
                competence_delta=competence_delta,
            )
        )

    # No learning of any stage may occur from unverified experience.
    assert _events_of(kernel, "learning.pattern_discovered") == []
    assert _events_of(kernel, "learning.validated") == []
    assert _events_of(kernel, "memory.candidate") == []


# --------------------------------------------------------------------------- #
# Property 3 — Validated before promotion
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    capability=st.text(min_size=1, max_size=12),
    environment=st.text(min_size=1, max_size=12),
    signature=st.text(min_size=1, max_size=12),
    # Signed delta spanning both sides of the min_improvement gate (and negatives).
    competence_delta=st.floats(
        min_value=-0.49, max_value=0.49, allow_nan=False, allow_infinity=False
    ),
)
def test_property_3_validated_before_promotion(
    capability: str,
    environment: str,
    signature: str,
    competence_delta: float,
) -> None:
    """Property 3: Validated before promotion.

    A verified pattern is promoted — emitting ``learning.validated`` and exactly one
    procedural ``memory.candidate`` (``kind="pattern"``, ``verified=True``) — only when
    the measured improvement (``observed - baseline`` == ``competence_delta``) is at least
    ``min_improvement``. Otherwise the pipeline emits ``learning.rejected`` and NO
    ``memory.candidate``.

    Validates: Requirements 1.6, 1.7, 1.8
    """
    kernel = FakeKernel()
    engine = LearningEngine()
    engine.attach(kernel)

    # Repeat the SAME verified signature exactly the threshold count → one pattern,
    # one validation outcome.
    for _ in range(_MIN_REPETITIONS):
        kernel.publish_event(
            _reflection_event(
                kernel,
                goal_id="g-verified",
                capability=capability,
                environment=environment,
                outcome_signature=signature,
                verified=True,
                competence_delta=competence_delta,
            )
        )

    validated = _events_of(kernel, "learning.validated")
    rejected = _events_of(kernel, "learning.rejected")
    candidates = _events_of(kernel, "memory.candidate")

    # A pattern must have emerged from the repeated verified evidence.
    assert len(_events_of(kernel, "learning.pattern_discovered")) == 1

    if competence_delta >= _MIN_IMPROVEMENT:
        assert len(validated) == 1
        assert rejected == []
        assert len(candidates) == 1
        payload = candidates[0].payload
        assert payload["kind"] == "pattern"
        assert payload["verified"] is True
    else:
        assert validated == []
        assert len(rejected) == 1
        assert candidates == []


# --------------------------------------------------------------------------- #
# Property 9 — Unlearning retires low-confidence principles
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    confidence=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
)
def test_property_9_unlearning_retires_low_confidence_principles(
    confidence: float,
) -> None:
    """Property 9: Unlearning retires low-confidence principles.

    ``unlearn`` on a principle whose confidence has decayed at/below the retire floor
    marks it retired and emits exactly one ``learning.unlearned``; a principle whose
    confidence is above the floor is refused (``ValueError``) and no event is emitted.

    Validates: Requirements 1.10
    """
    kernel = FakeKernel()
    engine = LearningEngine()
    engine.attach(kernel)

    principle_id = "principle-under-test"
    principle = Principle(
        id=principle_id,
        statement="Some capability reliably yields its verified outcome.",
        applicability=("cap", "cap::*"),
        source_signatures=("sig",),
        support=3,
        confidence=confidence,
    )
    # Register the principle in the engine's own store so unlearn can find it.
    engine._principles[principle_id] = principle

    if confidence <= _RETIRE_FLOOR:
        retired = engine.unlearn(principle_id, reason="confidence decayed")
        assert retired.id == principle_id
        unlearned = _events_of(kernel, "learning.unlearned")
        assert len(unlearned) == 1
        assert unlearned[0].payload["principle_id"] == principle_id
        # No longer proposed for procedural promotion.
        assert principle_id in engine._retired
    else:
        with pytest.raises(ValueError):
            engine.unlearn(principle_id, reason="still confident")
        assert _events_of(kernel, "learning.unlearned") == []
        assert principle_id not in engine._retired


# --------------------------------------------------------------------------- #
# Property 10 — Measurable improvement is real
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    capability=st.text(min_size=1, max_size=12),
    environment=st.text(min_size=1, max_size=12),
    confidences=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=12,
    ),
)
def test_property_10_measurable_improvement_is_real(
    capability: str,
    environment: str,
    confidences: List[float],
) -> None:
    """Property 10: Measurable improvement is real.

    ``improvement(key)`` is ``0.0`` for an unseen key and otherwise equals the signed
    difference between the latest and first observed confidence for that key, derived
    only from ``competence.updated`` evidence fed through the attached engine.

    Validates: Requirements 1.11
    """
    kernel = FakeKernel()
    engine = LearningEngine()
    engine.attach(kernel)

    key = (capability, environment)
    # Unseen key improvement is always 0.0 (never fabricated) before any evidence.
    assert engine.improvement(key) == 0.0
    # A distinct never-observed key stays 0.0 throughout.
    unseen_key = (capability + "\x00unseen", environment)

    for confidence in confidences:
        kernel.publish_event(
            make_event(
                event_type="competence.updated",
                source="test",
                logical_time=kernel.next_logical(),
                payload={
                    "capability": capability,
                    "environment": environment,
                    "confidence": confidence,
                },
            )
        )

    assert engine.improvement(key) == confidences[-1] - confidences[0]
    assert engine.improvement(unseen_key) == 0.0


# --------------------------------------------------------------------------- #
# Property 8 — Determinism
# --------------------------------------------------------------------------- #
from friday.horizon import LongHorizonPlanner, Milestone, Project  # noqa: E402


def _build_m9_subsystems() -> Tuple[FakeKernel, LearningEngine, DeadlineTracker, LongHorizonPlanner]:
    """Freshly construct and attach the kernel-driven M9 subsystems.

    Each call builds a brand-new :class:`FakeKernel` and a fresh set of M9
    subsystems (``LearningEngine`` / ``DeadlineTracker`` / ``LongHorizonPlanner``)
    with default configuration, attached via ``subscribe`` — exactly the wiring a
    real kernel uses. Replaying an identical event log through two independent
    such sets must produce identical emissions and identical internal state.
    """
    kernel = FakeKernel()
    engine = LearningEngine()
    engine.attach(kernel)
    deadlines = DeadlineTracker()
    deadlines.attach(kernel)
    planner = LongHorizonPlanner()
    planner.attach(kernel)
    # A registered roadmap so goal/checkpoint events reach a non-empty planner.
    planner.define_project(
        Project(
            id="proj",
            vision="deterministic vision",
            milestones=(
                Milestone(id="m1", text="first"),
                Milestone(id="m2", text="second", prerequisites=("m1",)),
            ),
        )
    )
    return kernel, engine, deadlines, planner


def _payload_modulo_volatile(payload: dict) -> dict:
    """Drop fields allowed to vary run-to-run (none today) — payloads are stable.

    Emitted M9 payloads carry no event id or wall_time (those live on the Event
    envelope, which we already strip), so the payload compares verbatim. This
    helper documents that contract and gives a single place to relax it later.
    """
    return dict(payload)


def _emission_fingerprint(kernel: FakeKernel) -> List[Tuple[str, tuple]]:
    """Ordered (event_type, sorted-payload-items) for every published event.

    Event id and wall_time live on the :class:`Event` envelope and are excluded
    by construction (we never read them); the payload is compared verbatim.
    """
    fingerprint: List[Tuple[str, tuple]] = []
    for event in kernel.published:
        items = tuple(sorted(_payload_modulo_volatile(dict(event.payload)).items()))
        fingerprint.append((event.event_type, items))
    return fingerprint


def _internal_state(
    engine: LearningEngine, deadlines: DeadlineTracker, planner: LongHorizonPlanner
) -> dict:
    """A comparable snapshot of the M9 subsystems' internal state after replay."""
    return {
        "principles": sorted(engine._principles.keys()),
        "retired": sorted(engine._retired),
        "competence_history": {
            "\x00".join(k): v for k, v in sorted(engine._competence_history.items())
        },
        "contexts": {k: list(v) for k, v in sorted(engine._contexts.items())},
        "deadlines": {k: v for k, v in sorted(deadlines._deadlines.items())},
        "last_emitted": {
            k: v.value for k, v in sorted(deadlines._last_emitted.items())
        },
        "planner": planner.checkpoint(),
    }


# A single generated event descriptor: (event_type, payload). Hypothesis builds an
# ordered list of these; both runs replay the SAME list, event-for-event.
@st.composite
def _m9_event_log(draw: Any) -> List[Tuple[str, dict]]:
    """Generate an ordered log of M9-relevant kernel events.

    Draws a bounded sequence of reflection.completed / competence.updated /
    goal.created / goal.state_changed descriptors with realistic payloads over a
    small shared vocabulary so signatures recur (letting patterns actually form).
    Only the ORDER and CONTENT matter — both determinism runs replay this exact
    list, so no per-run randomness leaks in.
    """
    capabilities = draw(
        st.lists(st.text(min_size=1, max_size=4), min_size=1, max_size=3, unique=True)
    )
    environments = draw(
        st.lists(st.text(min_size=1, max_size=4), min_size=1, max_size=3, unique=True)
    )
    signatures = draw(
        st.lists(st.text(min_size=1, max_size=4), min_size=1, max_size=3, unique=True)
    )

    cap = st.sampled_from(capabilities)
    env = st.sampled_from(environments)
    sig = st.sampled_from(signatures)
    delta = st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False)
    conf = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    wall = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)

    reflection = st.builds(
        lambda c, e, s, d, v: (
            "reflection.completed",
            {
                "goal_id": "g",
                "capability": c,
                "environment": e,
                "outcome_signature": s,
                "prediction_error": 0.1,
                "verified": v,
                "competence_delta": d,
            },
        ),
        cap,
        env,
        sig,
        delta,
        st.booleans(),
    )
    competence = st.builds(
        lambda c, e, k: (
            "competence.updated",
            {"capability": c, "environment": e, "confidence": k},
        ),
        cap,
        env,
        conf,
    )
    goal_created = st.builds(
        lambda w: (
            "goal.created",
            {
                "goal_id": "g-dl",
                "text": "goal",
                "constraints": {"deadline": w + 100.0},
                "now_wall": w,
            },
        ),
        wall,
    )
    goal_changed = st.builds(
        lambda w: (
            "goal.state_changed",
            {"goal_id": "g-dl", "state": "active", "reason": "", "now_wall": w},
        ),
        wall,
    )

    return draw(
        st.lists(
            st.one_of(reflection, competence, goal_created, goal_changed),
            min_size=1,
            max_size=25,
        )
    )


def _replay(log: List[Tuple[str, dict]]) -> Tuple[FakeKernel, dict]:
    """Replay an event log through a fresh set of M9 subsystems; return kernel+state."""
    kernel, engine, deadlines, planner = _build_m9_subsystems()
    for event_type, payload in log:
        kernel.publish_event(
            make_event(
                event_type=event_type,
                source="test",
                logical_time=kernel.next_logical(),
                payload=payload,
            )
        )
    return kernel, _internal_state(engine, deadlines, planner)


@settings(max_examples=150, deadline=None)
@given(log=_m9_event_log())
def test_property_8_determinism(log: List[Tuple[str, dict]]) -> None:
    """Property 8: Determinism.

    Replaying the same ordered event log through two freshly-constructed sets of
    M9 subsystems produces identical emitted kernel-event types and payloads
    (modulo event id and wall_time, which live on the Event envelope) and
    identical internal state. No M9 decision depends on anything but the ordered
    events it consumes.

    Validates: Requirements 6.4, 6.5
    """
    kernel_a, state_a = _replay(log)
    kernel_b, state_b = _replay(log)

    # Identical emitted event types + payloads, in identical order.
    assert _emission_fingerprint(kernel_a) == _emission_fingerprint(kernel_b)

    # Identical internal state across all three kernel-driven subsystems.
    assert state_a == state_b


# --------------------------------------------------------------------------- #
# Property 7 — Long-horizon goal survives restart
# --------------------------------------------------------------------------- #
import json  # noqa: E402


@st.composite
def _roadmap_projects(draw: Any) -> List[Project]:
    """Generate a well-formed list of Projects with milestone roadmaps.

    Each project carries an immutable ``vision`` and a tuple of milestones with
    unique ids (within the project), goal_ids, prerequisites drawn from the
    project's own milestone ids, and a ``reached`` flag. Project ids are unique
    across the roadmap so ``define_project`` never clobbers an entry.
    """
    project_ids = draw(
        st.lists(st.text(min_size=1, max_size=6), min_size=1, max_size=4, unique=True)
    )
    projects: List[Project] = []
    for pid in project_ids:
        vision = draw(st.text(min_size=0, max_size=20))
        milestone_ids = draw(
            st.lists(st.text(min_size=1, max_size=6), min_size=0, max_size=5, unique=True)
        )
        milestones: List[Milestone] = []
        for index, mid in enumerate(milestone_ids):
            text = draw(st.text(min_size=0, max_size=20))
            goal_ids = tuple(
                draw(
                    st.lists(
                        st.text(min_size=1, max_size=8), min_size=0, max_size=4, unique=True
                    )
                )
            )
            # Prerequisites reference earlier milestones in this project (if any).
            earlier = milestone_ids[:index]
            prerequisites = (
                tuple(draw(st.lists(st.sampled_from(earlier), max_size=len(earlier), unique=True)))
                if earlier
                else ()
            )
            reached = draw(st.booleans())
            milestones.append(
                Milestone(
                    id=mid,
                    text=text,
                    goal_ids=goal_ids,
                    prerequisites=prerequisites,
                    reached=reached,
                )
            )
        projects.append(Project(id=pid, vision=vision, milestones=tuple(milestones)))
    return projects


def _goal_id_set(planner: LongHorizonPlanner) -> set:
    """The union of every goal id referenced by every milestone in the planner."""
    ids: set = set()
    for project in planner._projects.values():
        for milestone in project.milestones:
            ids.update(milestone.goal_ids)
    return ids


def _reached_milestone_set(planner: LongHorizonPlanner) -> set:
    """The set of (project_id, milestone_id) pairs whose milestone is reached."""
    return {
        (project.id, milestone.id)
        for project in planner._projects.values()
        for milestone in project.milestones
        if milestone.reached
    }


def _vision_by_project(planner: LongHorizonPlanner) -> dict:
    """Map each project id to its immutable vision outcome."""
    return {pid: project.vision for pid, project in planner._projects.items()}


@settings(max_examples=200, deadline=None)
@given(projects=_roadmap_projects())
def test_property_7_long_horizon_goal_survives_restart(projects: List[Project]) -> None:
    """Property 7: Long-horizon goal survives restart.

    For any generated roadmap (multiple projects, milestones carrying goal_ids /
    prerequisites, some reached), ``LongHorizonPlanner.checkpoint()`` followed by a
    fresh ``LongHorizonPlanner.restore(state)`` reproduces the identical set of goal
    ids, goal states, and reached milestones, plus each project's immutable vision.
    The checkpoint state is JSON-serializable and round-trips cleanly.

    Validates: Requirements 3.5, 3.6, 6.1
    """
    original = LongHorizonPlanner()
    for project in projects:
        original.define_project(project)

    state = original.checkpoint()

    # The checkpoint state must round-trip cleanly through JSON.
    assert json.loads(json.dumps(state)) == state

    restored = LongHorizonPlanner()
    restored.restore(state)

    # Identical set of goal ids across all projects/milestones.
    assert _goal_id_set(restored) == _goal_id_set(original)

    # Identical reached-milestone set (project_id, milestone_id).
    assert _reached_milestone_set(restored) == _reached_milestone_set(original)

    # Identical immutable vision per project.
    assert _vision_by_project(restored) == _vision_by_project(original)

    # And the full serialized roadmaps agree (goal states included).
    assert restored.checkpoint() == state
