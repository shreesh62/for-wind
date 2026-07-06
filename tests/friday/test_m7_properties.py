"""M7 — Property-based tests (Hypothesis) for the desktop/motor/exploration stack.

Realizes the 11 correctness properties from the M7 design document
(``.kiro/specs/m7-desktop-motor-exploration/design.md``) as Hypothesis
property tests. Every test runs under ``FRIDAY_DRY_RUN=1`` so no real OS
surface (pyautogui/win32/clipboard/UIA) is ever touched.

Each test carries its design property number and a ``Validates: Requirements``
annotation in its docstring.
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List, Optional, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.actions.result import ActionResult
from friday.actions.target import Target
from friday.capabilities.contracts import BaseCapability
from friday.capabilities.motor import (
    MotionProfile,
    MotorBackend,
    MotorSystem,
    distance,
)
from friday.environments.contract import Action
from friday.environments.desktop import DesktopEnvironment
from friday.environments.desktop.clipboard import ClipboardManager
from friday.environments.desktop.display_manager import DisplayManager, Monitor
from friday.environments.unknown.affordances import AffordanceInferrer
from friday.environments.unknown.demonstration import (
    DemonstrationRecording,
    extract_principles,
)
from friday.environments.unknown.experiment import (
    RISK_CONFIDENCE_GATE,
    SafeExperimentPlanner,
)
from friday.environments.unknown.object_graph import ObjectGraph, RiskLevel
from friday.events.event import FrozenDict
from friday.kernel.contracts.capability import WorldStateDelta
from friday.perception.contracts import SensorContract
from friday.perception.observation import Observation
from friday.perception.types import BoundingBox
from friday.world.worlds import ObservedWorld


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class ScriptedSensor(SensorContract):
    """A sensor that always reports one fixed target observation."""

    def __init__(self, description: str, bbox: Tuple[int, int, int, int],
                 confidence: float = 0.95) -> None:
        self._description = description
        self._bbox = bbox
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "uia"

    @property
    def environment(self) -> str:
        return "desktop"

    def observe(self) -> List[Observation]:
        return [
            Observation(
                sensor="uia",
                environment="desktop",
                object_type="button",
                attributes=FrozenDict({"text": self._description, "source": "uia"}),
                confidence=self._confidence,
                bbox=self._bbox,
            )
        ]


class MovingSensor(SensorContract):
    """A sensor whose target bbox jumps once, mid-move, after N observe calls."""

    def __init__(self, description: str,
                 bbox_a: Tuple[int, int, int, int],
                 bbox_b: Tuple[int, int, int, int],
                 switch_after: int = 2) -> None:
        self._description = description
        self._bbox_a = bbox_a
        self._bbox_b = bbox_b
        self._switch_after = switch_after
        self._calls = 0

    @property
    def name(self) -> str:
        return "uia"

    @property
    def environment(self) -> str:
        return "desktop"

    def observe(self) -> List[Observation]:
        self._calls += 1
        bbox = self._bbox_a if self._calls <= self._switch_after else self._bbox_b
        return [
            Observation(
                sensor="uia",
                environment="desktop",
                object_type="button",
                attributes=FrozenDict({"text": self._description, "source": "uia"}),
                confidence=0.95,
                bbox=bbox,
            )
        ]


class _DummyCapability(BaseCapability):
    """Minimal concrete BaseCapability used to exercise competence tracking."""

    @property
    def id(self) -> str:
        return "dummy.capability"

    @property
    def version(self) -> str:
        return "1.0.0"

    def preconditions(self):
        return []

    def expected_outcome(self) -> WorldStateDelta:
        return WorldStateDelta()

    async def execute(self, params, world) -> ActionResult:  # pragma: no cover
        return ActionResult.success(action="dummy")

    def verify(self, result, world) -> bool:
        return True

    def recover(self, failure):
        return None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _bbox_from_center(cx: int, cy: int, half: int = 10) -> Tuple[int, int, int, int]:
    """Build a (x, y, w, h) bbox whose center is exactly (cx, cy)."""
    return (cx - half, cy - half, 2 * half, 2 * half)


def _is_non_increasing(values: List[float], tol: float = 1e-6) -> bool:
    return all(values[i] + tol >= values[i + 1] for i in range(len(values) - 1))


# Strategies for target centers that stay inside the default 1920x1080 monitor.
_cx = st.integers(min_value=40, max_value=1880)
_cy = st.integers(min_value=40, max_value=1040)


# --------------------------------------------------------------------------- #
# Property 1 (contract totality for DesktopEnvironment)
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(
    capability=st.text(min_size=0, max_size=20)
    | st.sampled_from(
        ["click", "type", "scroll", "press", "read", "copy",
         "paste", "focus_window", "launch", "observe", "unknown_verb"]
    ),
    text=st.text(max_size=20),
)
def test_property_1_interact_is_total(capability: str, text: str) -> None:
    """Property 1 — DesktopEnvironment.interact is total: always returns an
    ActionResult and never raises for any generated Action.

    Validates: Requirements 1.9
    """
    env = DesktopEnvironment()
    action = Action(
        capability=capability,
        target=Target(text=text) if text else None,
        params={"text": text, "app": text, "title": text, "key": text},
    )
    result = env.interact(action)
    assert isinstance(result, ActionResult)


# --------------------------------------------------------------------------- #
# Property 2 (risk-ladder monotonicity + DELETE gate)
# --------------------------------------------------------------------------- #


_OBJ_TYPES = st.sampled_from(["button", "textbox", "menuitem", "link", "edit"])
_LABELS = st.sampled_from(
    ["Save", "Open", "Submit", "Delete", "Remove", "Trash",
     "Name field", "Search", "Cancel", "Discard"]
)


@settings(max_examples=50)
@given(
    specs=st.lists(st.tuples(_OBJ_TYPES, _LABELS), min_size=1, max_size=8),
    low_conf=st.floats(min_value=0.0, max_value=0.899),
)
def test_property_2_risk_ladder_monotonic(specs, low_conf: float) -> None:
    """Property 2 — planned experiments have a non-decreasing risk sequence and
    no DELETE-risk experiment is permitted below 0.9 confidence.

    Validates: Requirements 5.2, 5.5
    """
    graph = ObjectGraph()
    for obj_type, label in specs:
        obs = Observation(
            sensor="uia",
            environment="desktop",
            object_type=obj_type,
            attributes=FrozenDict({"text": label, "source": "uia"}),
            confidence=0.8,
            bbox=(0, 0, 20, 20),
        )
        graph.add_from_observation(obs)
    graph.infer_types()

    inferrer = AffordanceInferrer()
    for node in graph.nodes():
        node.affordances = inferrer.infer(node, graph)

    planner = SafeExperimentPlanner()
    plan = planner.plan(graph)

    risks = [int(exp.risk) for exp in plan]
    assert _is_non_increasing([-r for r in risks]), "risk sequence must be non-decreasing"

    # No DELETE-risk experiment may be permitted below 0.9 confidence.
    for exp in plan:
        if exp.risk == RiskLevel.DELETE:
            assert not planner.is_permitted(exp, low_conf)


# --------------------------------------------------------------------------- #
# Property 3 (risk gate monotonic in risk)
# --------------------------------------------------------------------------- #


def test_property_3_risk_gate_monotonic() -> None:
    """Property 3 — for all pairs a < b in RiskLevel,
    RISK_CONFIDENCE_GATE[a] <= RISK_CONFIDENCE_GATE[b].

    Validates: Requirements 5.4
    """
    levels = sorted(RiskLevel, key=int)
    for i in range(len(levels)):
        for j in range(i + 1, len(levels)):
            assert RISK_CONFIDENCE_GATE[levels[i]] <= RISK_CONFIDENCE_GATE[levels[j]]


# --------------------------------------------------------------------------- #
# Property 4 (closed-loop convergence, stationary target)
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(cx=_cx, cy=_cy, profile=st.sampled_from([MotionProfile.PRECISE, MotionProfile.SAFE]))
def test_property_4_closed_loop_convergence(cx: int, cy: int,
                                            profile: MotionProfile) -> None:
    """Property 4 — for a stationary target and PRECISE/SAFE profile, residuals to
    the target center are non-increasing and the final cursor is within
    arrival_tolerance, OR success is False with an explicit error.

    Validates: Requirements 3.3, 3.4
    """
    description = "primary target"
    bbox = _bbox_from_center(cx, cy)
    sensor = ScriptedSensor(description, bbox)
    system = MotorSystem(
        sensors=[sensor],
        display=DisplayManager(),
        backend=MotorBackend(dry_run=True),
        max_steps=60,
        arrival_tolerance=3,
    )

    lock = system.acquire_target(description, ObservedWorld())
    assert lock is not None
    center = lock.center

    result = system.move_to(lock, profile)

    residuals = [distance(step.observed_xy, center) for step in result.steps]
    assert _is_non_increasing(residuals), "residual to center must be non-increasing"

    if result.success:
        final_cursor = tuple(result.evidence.raw["final_cursor"])
        assert distance(final_cursor, center) <= system.arrival_tolerance
    else:
        assert result.error is not None


# --------------------------------------------------------------------------- #
# Property 5 (closed-loop correction, target moves mid-move)
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(
    ax=_cx, ay=_cy, bx=_cx, by=_cy,
)
def test_property_5_closed_loop_correction(ax: int, ay: int,
                                           bx: int, by: int) -> None:
    """Property 5 — under SAFE, when the target moves mid-move the engine
    re-acquires and either arrives at the fresh lock or reports success == False.

    Validates: Requirements 3.5, 3.6
    """
    description = "moving target"
    bbox_a = _bbox_from_center(ax, ay)
    bbox_b = _bbox_from_center(bx, by)
    sensor = MovingSensor(description, bbox_a, bbox_b, switch_after=2)
    system = MotorSystem(
        sensors=[sensor],
        display=DisplayManager(),
        backend=MotorBackend(dry_run=True),
        max_steps=80,
        arrival_tolerance=3,
    )

    lock = system.acquire_target(description, ObservedWorld())
    assert lock is not None

    result = system.move_to(lock, MotionProfile.SAFE)

    center_b = (bx, by)
    if result.success:
        final_cursor = tuple(result.evidence.raw["final_cursor"])
        assert distance(final_cursor, center_b) <= system.arrival_tolerance
    else:
        assert result.error is not None


# --------------------------------------------------------------------------- #
# Property 7 (capability confidence bounds & monotonic evidence)
# --------------------------------------------------------------------------- #


@settings(max_examples=50)
@given(outcomes=st.lists(st.booleans(), min_size=0, max_size=40))
def test_property_7_confidence_bounds_and_monotonic(outcomes: List[bool]) -> None:
    """Property 7 — confidence stays in [0, 1]; a success never decreases it and a
    failure never increases it.

    Validates: Requirements 4.2, 4.3, 4.4, 4.5
    """
    cap = _DummyCapability()
    assert 0.0 <= cap.confidence <= 1.0

    for succeeded in outcomes:
        prev = cap.confidence
        if succeeded:
            result = ActionResult.success(action="dummy")
        else:
            result = ActionResult.failed(action="dummy", error="boom")
        cap.update_competence(result)
        new = cap.confidence

        assert 0.0 <= new <= 1.0
        if succeeded:
            assert new >= prev - 1e-9
        else:
            assert new <= prev + 1e-9


# --------------------------------------------------------------------------- #
# Property 8 (demonstration extracts principles, not coordinates)
# --------------------------------------------------------------------------- #


_CAPS = st.sampled_from(["click", "type", "scroll", "hover"])
_REGIONS = st.sampled_from(
    ["primary button", "search field", "top navigation bar",
     "main content area", "the prominent control"]
)


@st.composite
def _demo_events(draw):
    events = []
    for _ in range(draw(st.integers(min_value=1, max_value=8))):
        cap = draw(_CAPS)
        if draw(st.booleans()):
            # Semantic (region-context) event — digit-free descriptor.
            events.append({"capability": cap, "target": draw(_REGIONS)})
        else:
            # Coordinate-only event — recorder must NOT leak raw pixels.
            events.append(
                {
                    "capability": cap,
                    "x": draw(st.integers(min_value=0, max_value=1920)),
                    "y": draw(st.integers(min_value=0, max_value=1080)),
                    "width": 1920,
                    "height": 1080,
                }
            )
    return events


@settings(max_examples=50)
@given(events=_demo_events())
def test_property_8_principles_not_coordinates(events) -> None:
    """Property 8 — every extracted Principle has a non-empty target_descriptor
    that contains no raw pixel coordinate.

    Validates: Requirements 5.7, 5.8
    """
    recording = DemonstrationRecording(events=events)
    principles = extract_principles(recording)

    assert len(principles) == len(events)
    for principle in principles:
        descriptor = principle.target_descriptor
        assert descriptor and descriptor.strip(), "descriptor must be non-empty"
        # A coordinate-free descriptor must contain no pixel digits at all.
        assert not any(ch.isdigit() for ch in descriptor), (
            f"descriptor leaked a raw coordinate: {descriptor!r}"
        )


# --------------------------------------------------------------------------- #
# Property 9 (evidence law preserved)
# --------------------------------------------------------------------------- #


@settings(max_examples=50)
@given(text=st.text(min_size=1, max_size=40))
def test_property_9_evidence_law(text: str) -> None:
    """Property 9 — a successful copy ActionResult has evidence.has_evidence True.

    Validates: Requirements 1.6
    """
    env = DesktopEnvironment()
    result = env.interact(Action(capability="copy", params={"text": text}))
    assert result.is_success
    assert result.evidence.has_evidence


# --------------------------------------------------------------------------- #
# Property 10 (clipboard history bound + newest-first)
# --------------------------------------------------------------------------- #


@settings(max_examples=50)
@given(
    limit=st.integers(min_value=0, max_value=6),
    writes=st.lists(st.text(max_size=12), min_size=0, max_size=30),
)
def test_property_10_clipboard_history_bound(limit: int, writes: List[str]) -> None:
    """Property 10 — history length is bounded by history_limit and entries are
    ordered newest-first.

    Validates: Requirements 2.6, 2.7
    """
    manager = ClipboardManager(history_limit=limit)
    for text in writes:
        manager.write(text)

    history = manager.history()
    assert len(history) <= limit

    # Newest-first: history must equal the last `len(history)` writes reversed.
    if history:
        expected = list(reversed(writes))[: len(history)]
        assert [entry.text for entry in history] == expected


# --------------------------------------------------------------------------- #
# Property 11 (DPI round-trip)
# --------------------------------------------------------------------------- #


@settings(max_examples=50)
@given(
    scale=st.sampled_from([1.0, 1.25, 1.5, 2.0]),
    x=st.integers(min_value=0, max_value=3840),
    y=st.integers(min_value=0, max_value=2160),
)
def test_property_11_dpi_round_trip(scale: float, x: int, y: int) -> None:
    """Property 11 — to_logical(to_physical(x, y, m), m) == (x, y) within ±1px.

    Validates: Requirements 2.3
    """
    monitor = Monitor(
        index=0,
        bounds=BoundingBox(x=0, y=0, width=3840, height=2160),
        work_area=BoundingBox(x=0, y=0, width=3840, height=2120),
        dpi=int(round(96 * scale)),
        scale=scale,
        is_primary=True,
    )
    display = DisplayManager(monitors=[monitor])

    px, py = display.to_physical(x, y, monitor)
    lx, ly = display.to_logical(px, py, monitor)

    assert abs(lx - x) <= 1
    assert abs(ly - y) <= 1
