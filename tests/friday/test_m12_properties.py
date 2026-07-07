"""M12 — Property tests for kernel-backed execution.

Realizes correctness properties 1–4 and 8 from the M12 design over
GoalExecutionRuntime + MemorySink, using stub operator factories (no real
Operator required). All tests run under FRIDAY_DRY_RUN=1.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 4.2, 4.3
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import types
from typing import List

from hypothesis import given, settings, strategies as st

from friday.kernel.contracts.runtime import RuntimeContract
from friday.kernel.execution import GoalExecutionRuntime
from friday.kernel.memory_sink import MemorySink


class _FakeKernel:
    """A minimal kernel double capturing published events."""

    def __init__(self):
        self.published: List[object] = []
        self._subs = []

    def subscribe(self, pattern, handler):
        self._subs.append((pattern, handler))
        return "sub"

    def publish_event(self, event):
        self.published.append(event)

    def health(self):
        return {"tick": 0}


def _factory(outcome):
    return lambda goal_text: types.SimpleNamespace(run=lambda g: outcome)


_TEXT = st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=10)


# --------------------------------------------------------------------------- #
# Property 1 — delegates, never re-implements
# --------------------------------------------------------------------------- #
@given(summary=_TEXT, goal=_TEXT)
@settings(max_examples=100)
def test_property1_delegates_and_maps(summary, goal):
    outcome = types.SimpleNamespace(completed=True, summary=summary, created_files=[])
    calls = {"n": 0}

    def factory(goal_text):
        calls["n"] += 1
        assert goal_text == goal
        return types.SimpleNamespace(run=lambda g: outcome)

    rec = GoalExecutionRuntime(factory).execute_goal("gid", goal)
    assert calls["n"] == 1
    assert rec.completed is True
    assert rec.summary == summary


# --------------------------------------------------------------------------- #
# Property 2 — execution never raises
# --------------------------------------------------------------------------- #
@given(mode=st.sampled_from(["factory_raise", "run_raise", "ok"]))
@settings(max_examples=50)
def test_property2_execution_never_raises(mode):
    if mode == "factory_raise":
        factory = lambda g: (_ for _ in ()).throw(RuntimeError("f"))
    elif mode == "run_raise":
        factory = lambda g: types.SimpleNamespace(
            run=lambda gg: (_ for _ in ()).throw(RuntimeError("r"))
        )
    else:
        factory = _factory(types.SimpleNamespace(completed=True, summary="ok", created_files=[]))

    rec = GoalExecutionRuntime(factory).execute_goal("g", "t")
    assert rec.completed is (mode == "ok")


def test_property2_on_goal_created_never_raises():
    runtime = GoalExecutionRuntime(lambda g: (_ for _ in ()).throw(RuntimeError("x")))
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    # A malformed event and a valid one both must not raise.
    runtime._on_goal_created(types.SimpleNamespace(payload=None))
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))


# --------------------------------------------------------------------------- #
# Property 3 — lifecycle events emitted exactly once
# --------------------------------------------------------------------------- #
def test_property3_completed_emits_one_completed_event():
    outcome = types.SimpleNamespace(completed=True, summary="s", created_files=[])
    runtime = GoalExecutionRuntime(_factory(outcome))
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))

    types_emitted = [getattr(e, "event_type", "") for e in kernel.published]
    assert types_emitted.count("goal.completed") == 1
    assert types_emitted.count("goal.failed") == 0


def test_property3_failure_emits_one_failed_event():
    runtime = GoalExecutionRuntime(lambda g: (_ for _ in ()).throw(RuntimeError("boom")))
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))

    types_emitted = [getattr(e, "event_type", "") for e in kernel.published]
    assert types_emitted.count("goal.failed") == 1
    assert types_emitted.count("goal.completed") == 0


# --------------------------------------------------------------------------- #
# Property 4 — memory sink optional and fail-safe
# --------------------------------------------------------------------------- #
def test_property4_no_sink_completes_and_records_nothing():
    outcome = types.SimpleNamespace(completed=True, summary="s", created_files=[])
    runtime = GoalExecutionRuntime(_factory(outcome), memory_sink=None)
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))
    # Completed event still emitted.
    assert any(getattr(e, "event_type", "") == "goal.completed" for e in kernel.published)


def test_property4_throwing_sink_does_not_break_execution():
    class BadSink:
        def record_episode(self, episode):
            raise RuntimeError("sink down")

    outcome = types.SimpleNamespace(completed=True, summary="s", created_files=[])
    runtime = GoalExecutionRuntime(_factory(outcome), memory_sink=BadSink())
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    # Must not raise.
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))
    assert any(getattr(e, "event_type", "") == "goal.completed" for e in kernel.published)


def test_property4_working_sink_records_one_episode():
    recorded = []

    class Sink:
        def record_episode(self, episode):
            recorded.append(episode)
            return True

    outcome = types.SimpleNamespace(completed=True, summary="s", created_files=["a.md"])
    runtime = GoalExecutionRuntime(_factory(outcome), memory_sink=Sink())
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))
    assert len(recorded) == 1
    assert recorded[0]["goal_id"] == "g"


# --------------------------------------------------------------------------- #
# Property 8 — RuntimeContract completeness + checkpoint round-trip
# --------------------------------------------------------------------------- #
def test_property8_implements_runtime_contract():
    runtime = GoalExecutionRuntime(_factory(types.SimpleNamespace(completed=True, summary="", created_files=[])))
    assert isinstance(runtime, RuntimeContract)
    assert runtime.name == "goal_execution"
    assert runtime.observe() == []
    assert runtime.tick(0) is None
    assert runtime.shutdown() is None
    health = runtime.health()
    assert health["status"] in ("ok", "degraded")


def test_property8_checkpoint_restore_round_trips():
    runtime = GoalExecutionRuntime(_factory(types.SimpleNamespace(completed=True, summary="", created_files=[])))
    kernel = _FakeKernel()
    runtime.initialize(kernel)
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g", "text": "t"}))
    snap = runtime.checkpoint()
    assert snap["executed_count"] == 1

    fresh = GoalExecutionRuntime(_factory(types.SimpleNamespace(completed=True, summary="", created_files=[])))
    fresh.restore(snap)
    assert fresh.checkpoint()["executed_count"] == 1
