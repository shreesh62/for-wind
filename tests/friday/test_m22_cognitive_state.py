"""M22 — Cognitive State Manager (completion) tests.

Feature: m22-cognitive-state

Proves the additive completion of FAS §A2.12 over the existing
``friday/cognition/state.py::CognitiveStateManager``: the two new mind-state
elements (``cognitive_load`` + ``background_active``), full engagement-mode
coverage driven from the kernel event stream (exploration / conversation /
return-to-idle, not just execution), the pure query surface
(``should_interrupt`` / ``suggested_thinking_depth``), and the manager's
isolation invariant (imports only ``friday.events`` + stdlib; usable without a
kernel; handlers never raise).

Property tests (Hypothesis, >=100 examples) cover Correctness Properties 1-6 from
design.md. Property tests run against a lightweight fake kernel (fresh,
deterministic, hermetic per example); one integration-style test drives a REAL
``CognitiveKernel`` (confined to pytest ``tmp_path``) to prove the manager reacts
to real bus events via ``snapshot()``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from friday.cognition.state import (
    CognitiveMode,
    CognitiveState,
    CognitiveStateManager,
    ThinkingDepth,
)
from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel


# ----------------------------------------------------------------- test doubles


class FakeKernel:
    """Minimal kernel mirroring the EventBus surface the manager depends on.

    Exposes ``subscribe(event_type, handler)`` (exact-match dispatch — the
    manager subscribes to concrete event types), ``publish_event(event)``
    (persist-free routing), and ``health() -> {"tick": int}``. Fresh per example
    → deterministic, hermetic, no file I/O.
    """

    def __init__(self) -> None:
        self._subs: List[Tuple[str, Any]] = []
        self._tick = 0
        self.published: List[Any] = []

    def subscribe(self, pattern: str, handler: Any) -> str:
        self._subs.append((pattern, handler))
        return f"sub-{len(self._subs)}"

    def publish_event(self, event: Any) -> None:
        self._tick = max(self._tick, int(getattr(event, "logical_time", 0)))
        self.published.append(event)
        for pattern, handler in list(self._subs):
            if event.event_type == pattern:
                handler(event)

    def health(self) -> Dict[str, Any]:
        return {"tick": self._tick}


def _event(kernel: Any, event_type: str, payload: Optional[Dict[str, Any]]) -> Any:
    """Build a synthetic event on the fake/real kernel's logical clock."""
    tick = int(kernel.health().get("tick", 0)) + 1
    return make_event(
        event_type=event_type,
        source="test",
        logical_time=tick,
        payload=payload,
    )


def _publish(kernel: Any, event_type: str, payload: Optional[Dict[str, Any]]) -> None:
    kernel.publish_event(_event(kernel, event_type, payload))


def _attached_manager() -> Tuple[CognitiveStateManager, FakeKernel]:
    mgr = CognitiveStateManager()
    kernel = FakeKernel()
    mgr.attach(kernel)
    return mgr, kernel


# =============================================================== Property 1


@settings(max_examples=150)
@given(
    ops=st.lists(
        st.one_of(
            st.tuples(
                st.just("set"),
                st.floats(allow_nan=False, allow_infinity=False, min_value=-5.0, max_value=5.0),
            ),
            st.tuples(
                st.just("adjust"),
                st.floats(allow_nan=False, allow_infinity=False, min_value=-5.0, max_value=5.0),
            ),
            st.tuples(
                st.just("focus"),
                st.floats(allow_nan=False, allow_infinity=False, min_value=-5.0, max_value=5.0),
            ),
        ),
        min_size=0,
        max_size=40,
    ),
)
def test_p1_load_clamped_snapshot_independent_json(ops):
    # Feature: m22-cognitive-state, Property 1: cognitive_load stays in [0,1] under any
    # sequence of set_load/adjust_load/focus changes; background_active is a bool;
    # snapshot() is an independent copy; to_dict() JSON-serializes.
    # Validates: Requirements 1.1, 1.2, 2.1, 2.3
    mgr = CognitiveStateManager()
    for kind, value in ops:
        if kind == "set":
            mgr.set_load(value)
        elif kind == "adjust":
            mgr.adjust_load(value)
        else:
            mgr.set_focus("g", attention=value)
        snap = mgr.snapshot()
        assert 0.0 <= snap.cognitive_load <= 1.0
        assert isinstance(snap.background_active, bool)

    # snapshot() returns an independent copy: mutating it must not change the manager.
    snap = mgr.snapshot()
    baseline = mgr.snapshot().cognitive_load
    snap.cognitive_load = 0.123456
    snap.background_active = not snap.background_active
    snap.mode = CognitiveMode.EXECUTION
    assert mgr.snapshot().cognitive_load == baseline
    assert mgr.snapshot().cognitive_load != 0.123456 or baseline == 0.123456

    # to_dict() is JSON-safe and round-trips through json.dumps.
    d = mgr.snapshot().to_dict()
    restored = json.loads(json.dumps(d))
    assert restored == d
    assert 0.0 <= restored["cognitive_load"] <= 1.0
    assert isinstance(restored["background_active"], bool)


def test_p1_additive_fields_default_and_projection():
    # Feature: m22-cognitive-state, Property 1: the additive fields default correctly
    # and to_dict() projects the full state as JSON primitives.
    # Validates: Requirements 1.1, 1.2
    state = CognitiveState()
    assert state.cognitive_load == 0.0
    assert state.background_active is False
    d = state.to_dict()
    # Enums are emitted as their .value strings (JSON-safe).
    assert d["mode"] == "idle"
    assert d["thinking_depth"] == "normal"
    assert isinstance(d["cognitive_load"], float)
    assert isinstance(d["background_active"], bool)
    json.dumps(d)


# =============================================================== Property 2


@settings(max_examples=150)
@given(
    lo=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hi=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_p2_higher_attention_yields_higher_load(lo, hi):
    # Feature: m22-cognitive-state, Property 2: focusing with higher attention yields
    # load >= focusing with lower attention (monotonic in committed attention).
    # Validates: Requirements 2.2
    if hi < lo:
        lo, hi = hi, lo

    m_lo = CognitiveStateManager()
    m_lo.set_focus("g", attention=lo)
    m_hi = CognitiveStateManager()
    m_hi.set_focus("g", attention=hi)

    assert m_hi.snapshot().cognitive_load >= m_lo.snapshot().cognitive_load


@settings(max_examples=150)
@given(
    attention=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_p2_return_to_idle_does_not_increase_load(attention):
    # Feature: m22-cognitive-state, Property 2: returning to idle (terminal goal state)
    # does not increase load — it lowers it toward 0. Validates: Requirements 2.2
    mgr, kernel = _attached_manager()
    # Focus a goal (commits attention → raises load).
    _publish(kernel, "goal.state_changed", {"state": "active", "goal_id": "g1"})
    mgr.set_focus("g1", attention=attention)
    before = mgr.snapshot().cognitive_load

    # Terminal state for the focused goal → return to idle.
    _publish(kernel, "goal.state_changed", {"state": "completed", "goal_id": "g1"})
    after = mgr.snapshot().cognitive_load

    assert after <= before
    assert after == 0.0
    assert mgr.snapshot().mode is CognitiveMode.IDLE


# =============================================================== Property 3


def test_p3_action_executed_enters_execution():
    # Feature: m22-cognitive-state, Property 3: action.executed => EXECUTION.
    # Validates: Requirements 3.1
    mgr, kernel = _attached_manager()
    _publish(kernel, "action.executed", {"action": "x"})
    assert mgr.snapshot().mode is CognitiveMode.EXECUTION


def test_p3_observation_received_enters_exploration():
    # Feature: m22-cognitive-state, Property 3: observation.received => EXPLORATION.
    # Validates: Requirements 3.2
    mgr, kernel = _attached_manager()
    _publish(kernel, "observation.received", {"obs": "y"})
    assert mgr.snapshot().mode is CognitiveMode.EXPLORATION


def test_p3_goal_created_enters_conversation():
    # Feature: m22-cognitive-state, Property 3: goal.created => CONVERSATION.
    # Validates: Requirements 3.2
    mgr, kernel = _attached_manager()
    _publish(kernel, "goal.created", {"goal_id": "g1"})
    assert mgr.snapshot().mode is CognitiveMode.CONVERSATION


def test_p3_goal_active_sets_focus():
    # Feature: m22-cognitive-state, Property 3: goal.state_changed active => focus set.
    # Validates: Requirements 3.2
    mgr, kernel = _attached_manager()
    _publish(kernel, "goal.state_changed", {"state": "active", "goal_id": "g7"})
    snap = mgr.snapshot()
    assert snap.focus == "g7"
    assert snap.active_goal == "g7"


@settings(max_examples=120)
@given(terminal=st.sampled_from(["completed", "failed", "abandoned", "cancelled"]))
def test_p3_terminal_state_for_focused_goal_returns_to_idle(terminal):
    # Feature: m22-cognitive-state, Property 3: a terminal state for the focused goal
    # => IDLE + cleared focus. Validates: Requirements 3.3
    mgr, kernel = _attached_manager()
    _publish(kernel, "goal.state_changed", {"state": "active", "goal_id": "gf"})
    assert mgr.snapshot().focus == "gf"
    _publish(kernel, "goal.state_changed", {"state": terminal, "goal_id": "gf"})
    snap = mgr.snapshot()
    assert snap.mode is CognitiveMode.IDLE
    assert snap.focus is None
    assert snap.active_goal is None
    assert snap.cognitive_load == 0.0


def test_p3_terminal_state_for_different_goal_does_not_reset():
    # Feature: m22-cognitive-state, Property 3: a terminal state for a DIFFERENT goal
    # does not reset the focused goal. Validates: Requirements 3.3
    mgr, kernel = _attached_manager()
    _publish(kernel, "goal.state_changed", {"state": "active", "goal_id": "focused"})
    _publish(kernel, "goal.state_changed", {"state": "completed", "goal_id": "other"})
    snap = mgr.snapshot()
    assert snap.focus == "focused"
    assert snap.active_goal == "focused"


@settings(max_examples=150)
@given(
    payload=st.one_of(
        st.none(),
        st.just({}),
        st.dictionaries(
            keys=st.sampled_from(["state", "goal_id", "junk"]),
            values=st.one_of(st.none(), st.integers(), st.text(max_size=5), st.booleans()),
            max_size=3,
        ),
        st.text(max_size=8),
        st.integers(),
        st.lists(st.integers(), max_size=3),
    ),
    event_type=st.sampled_from(
        [
            "action.executed",
            "observation.received",
            "goal.created",
            "goal.state_changed",
            "reflection.completed",
        ]
    ),
)
def test_p3_malformed_events_never_raise_or_corrupt(payload, event_type):
    # Feature: m22-cognitive-state, Property 3: malformed/empty events never raise and
    # never corrupt state (load stays in [0,1], mode remains a valid enum, background
    # remains a bool). Validates: Requirements 3.4
    mgr, kernel = _attached_manager()
    # payload must be a Mapping for make_event; non-mapping payloads become None so we
    # still exercise the handler's defensive reads on a junk/empty payload.
    safe_payload = payload if isinstance(payload, dict) else None
    _publish(kernel, event_type, safe_payload)
    snap = mgr.snapshot()
    assert 0.0 <= snap.cognitive_load <= 1.0
    assert isinstance(snap.mode, CognitiveMode)
    assert isinstance(snap.background_active, bool)


def test_p3_reflection_while_idle_marks_background_active():
    # Feature: m22-cognitive-state, Property 3: reflection.completed while IDLE marks
    # background_active; foreground work clears it. Validates: Requirements 3.3
    mgr, kernel = _attached_manager()
    assert mgr.snapshot().mode is CognitiveMode.IDLE
    _publish(kernel, "reflection.completed", {"goal_id": "g"})
    assert mgr.snapshot().background_active is True
    # Foreground work (execution) clears background cognition.
    _publish(kernel, "action.executed", {"action": "x"})
    assert mgr.snapshot().background_active is False


# =============================================================== Property 4


def _load_scaled_threshold(load: float) -> float:
    """Mirror the manager's documented interruptibility bar (state.py)."""
    return max(0.0, min(1.0, 0.5 + 0.5 * load))


@settings(max_examples=150)
@given(
    urgency=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    load=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    interruptible=st.booleans(),
)
def test_p4_should_interrupt_matches_formula_and_is_pure(urgency, load, interruptible):
    # Feature: m22-cognitive-state, Property 4: should_interrupt returns True when
    # interruptible; when not interruptible, True iff urgency >= the load-scaled
    # threshold (0.5 + 0.5*load); pure (no state mutation).
    # Validates: Requirements 4.1, 4.3
    mgr = CognitiveStateManager()
    mgr.set_load(load)
    mgr.set_interruptible(interruptible)

    before = mgr.snapshot().to_dict()
    result = mgr.should_interrupt(urgency)
    after = mgr.snapshot().to_dict()

    # Pure read: no state change.
    assert before == after

    if interruptible:
        assert result is True
    else:
        expected = urgency >= _load_scaled_threshold(load)
        assert result is expected

    # Deterministic: repeated calls give the same answer.
    assert mgr.should_interrupt(urgency) is result


@settings(max_examples=120)
@given(
    urgency=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    lo=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    hi=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_p4_higher_load_raises_the_bar(urgency, lo, hi):
    # Feature: m22-cognitive-state, Property 4: while non-interruptible, higher load
    # raises the interruption bar — it is never EASIER to interrupt at higher load.
    # Validates: Requirements 4.1
    if hi < lo:
        lo, hi = hi, lo

    m_lo = CognitiveStateManager()
    m_lo.set_interruptible(False)
    m_lo.set_load(lo)
    m_hi = CognitiveStateManager()
    m_hi.set_interruptible(False)
    m_hi.set_load(hi)

    # If a higher-load manager surfaces the interruption, the lower-load one must too.
    if m_hi.should_interrupt(urgency):
        assert m_lo.should_interrupt(urgency)


# =============================================================== Property 5


@settings(max_examples=150)
@given(
    budget=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    load=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_p5_suggested_thinking_depth_matches_thresholds_and_is_pure(budget, load):
    # Feature: m22-cognitive-state, Property 5: suggested_thinking_depth is SHALLOW
    # under low budget (<0.3) or high load (>0.7), DEEP under ample budget (>0.7) and
    # low load (<0.3), NORMAL otherwise; pure and deterministic.
    # Validates: Requirements 4.2, 4.3
    mgr = CognitiveStateManager()
    # reasoning_budget starts at 1.0; drive it via consume_budget to the target value.
    mgr.consume_budget(1.0 - budget)
    mgr.set_load(load)

    actual_budget = mgr.snapshot().reasoning_budget
    actual_load = mgr.snapshot().cognitive_load

    before = mgr.snapshot().to_dict()
    depth = mgr.suggested_thinking_depth()
    after = mgr.snapshot().to_dict()
    assert before == after  # pure read

    if actual_budget < 0.3 or actual_load > 0.7:
        assert depth is ThinkingDepth.SHALLOW
    elif actual_budget > 0.7 and actual_load < 0.3:
        assert depth is ThinkingDepth.DEEP
    else:
        assert depth is ThinkingDepth.NORMAL

    # Deterministic.
    assert mgr.suggested_thinking_depth() is depth


def test_p5_depth_concrete_examples():
    # Feature: m22-cognitive-state, Property 5: concrete corner cases for depth.
    # Validates: Requirements 4.2
    # Ample budget (1.0) + low load (0.0) => DEEP.
    mgr = CognitiveStateManager()
    mgr.set_load(0.0)
    assert mgr.suggested_thinking_depth() is ThinkingDepth.DEEP
    # High load => SHALLOW regardless of budget.
    mgr.set_load(0.8)
    assert mgr.suggested_thinking_depth() is ThinkingDepth.SHALLOW
    # Low budget => SHALLOW.
    mgr2 = CognitiveStateManager()
    mgr2.consume_budget(0.8)  # budget -> 0.2 (< 0.3)
    mgr2.set_load(0.0)
    assert mgr2.suggested_thinking_depth() is ThinkingDepth.SHALLOW
    # Mid budget + mid load => NORMAL.
    mgr3 = CognitiveStateManager()
    mgr3.consume_budget(0.5)  # budget -> 0.5
    mgr3.set_load(0.5)
    assert mgr3.suggested_thinking_depth() is ThinkingDepth.NORMAL


# =============================================================== Property 6


def test_p6_module_imports_only_events_and_stdlib():
    # Feature: m22-cognitive-state, Property 6: state.py never imports goals/world/
    # deliberation/memory/competence (isolation invariant). Scan actual import
    # STATEMENTS only (docstring mentions are not import/from lines).
    # Validates: Requirements 5.1
    import friday.cognition.state as mod

    with open(mod.__file__, "r", encoding="utf-8") as fh:
        source = fh.read()

    forbidden = re.compile(
        r"^\s*(?:import|from)\s+friday\.(?:goals|world|deliberation|memory|competence)\b",
        re.MULTILINE,
    )
    matches = forbidden.findall(source)
    assert matches == [], f"forbidden import found: {matches}"

    # The only friday.* import allowed is friday.events (if any friday import exists).
    friday_imports = re.findall(
        r"^\s*(?:import|from)\s+(friday\.[\w.]+)", source, re.MULTILINE
    )
    for imp in friday_imports:
        assert imp.startswith("friday.events"), f"unexpected friday import: {imp}"


def test_p6_manager_fully_usable_without_kernel():
    # Feature: m22-cognitive-state, Property 6: the manager is a usable in-memory object
    # WITHOUT a kernel — construct, set_load, set_focus, should_interrupt,
    # suggested_thinking_depth, snapshot all work with _kernel is None.
    # Validates: Requirements 5.1
    mgr = CognitiveStateManager()
    assert mgr._kernel is None

    mgr.set_load(0.4)
    assert mgr.snapshot().cognitive_load == pytest.approx(0.4)

    mgr.set_focus("g1", attention=0.6)
    snap = mgr.snapshot()
    assert snap.focus == "g1"
    assert snap.cognitive_load == pytest.approx(0.6)

    # Queries work without a kernel and never mutate.
    before = mgr.snapshot().to_dict()
    assert isinstance(mgr.should_interrupt(0.9), bool)
    assert isinstance(mgr.suggested_thinking_depth(), ThinkingDepth)
    assert mgr.snapshot().to_dict() == before

    # Still no kernel wired.
    assert mgr._kernel is None


# =============================================================== integration


def test_integration_real_kernel_drives_modes(tmp_path):
    # Feature: m22-cognitive-state: attach to a REAL CognitiveKernel and prove the
    # manager reacts to real bus events via snapshot(): action.executed => EXECUTION,
    # goal.created => CONVERSATION. Validates: Requirements 3.1, 3.2, 5.2
    kernel = CognitiveKernel(store_path=str(tmp_path / "m22.jsonl"))
    mgr = CognitiveStateManager()
    mgr.attach(kernel)
    assert mgr._kernel is kernel

    _publish(kernel, "action.executed", {"action": "noop"})
    assert mgr.snapshot().mode is CognitiveMode.EXECUTION

    _publish(kernel, "goal.created", {"goal_id": "g-int"})
    assert mgr.snapshot().mode is CognitiveMode.CONVERSATION
