"""Kernel goal suspension / resume (C3 interrupt capability).

The kernel could record and execute a goal but had no way to interrupt one, so
`interrupt.pause_resume` was unprovable. These tests pin the cooperative
suspension contract: state and events are recorded, a runtime honors it at its
checkpoint, work is neither lost nor repeated, and suspension survives replay.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

from friday.events.store import EventStore
from friday.kernel.execution import GoalExecutionRuntime
from friday.kernel.kernel import CognitiveKernel


@pytest.fixture()
def store_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _kernel(store_dir, name="ev.jsonl"):
    return CognitiveKernel(event_store=EventStore(os.path.join(store_dir, name)))


class _Outcome:
    completed = True
    summary = "done"
    created_files: tuple = ()


class _BlockingOperator:
    """Blocks inside run() so a goal can be interrupted genuinely in flight."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.run_calls = 0

    def run(self, goal_text):
        self.run_calls += 1
        self.entered.set()
        self.release.wait(timeout=30)
        return _Outcome()


# --------------------------------------------------------------------------- #
# API contract
# --------------------------------------------------------------------------- #
def test_interrupt_unknown_goal_returns_false(store_dir):
    assert _kernel(store_dir).interrupt_goal("no-such-goal") is False


def test_resume_a_goal_that_is_not_suspended_returns_false(store_dir):
    kernel = _kernel(store_dir)
    goal_id = kernel.submit_goal("a goal")
    assert kernel.resume_goal(goal_id) is False


def test_interrupt_records_state_and_event(store_dir):
    kernel = _kernel(store_dir)
    seen = []
    kernel.subscribe("goal.suspended", lambda e: seen.append(e.event_type))
    goal_id = kernel.submit_goal("a goal")

    assert kernel.interrupt_goal(goal_id, reason="user asked") is True
    assert kernel.is_goal_suspended(goal_id) is True
    assert seen == ["goal.suspended"]
    states = {g["id"]: g["state"] for g in kernel.query_goals()}
    assert states[goal_id] == "suspended"


def test_resume_clears_state_and_emits(store_dir):
    kernel = _kernel(store_dir)
    seen = []
    kernel.subscribe("goal.resumed", lambda e: seen.append(e.event_type))
    goal_id = kernel.submit_goal("a goal")
    kernel.interrupt_goal(goal_id)

    assert kernel.resume_goal(goal_id) is True
    assert kernel.is_goal_suspended(goal_id) is False
    assert seen == ["goal.resumed"]
    states = {g["id"]: g["state"] for g in kernel.query_goals()}
    assert states[goal_id] == "active"


def test_interrupt_is_idempotent(store_dir):
    kernel = _kernel(store_dir)
    goal_id = kernel.submit_goal("a goal")
    assert kernel.interrupt_goal(goal_id) is True
    assert kernel.interrupt_goal(goal_id) is True
    assert kernel.is_goal_suspended(goal_id) is True


def test_a_completed_goal_cannot_be_interrupted(store_dir):
    kernel = _kernel(store_dir)
    goal_id = kernel.submit_goal("a goal")
    for goal in kernel.query_goals():
        if goal["id"] == goal_id:
            goal["state"] = "completed"
    kernel._goals[goal_id]["state"] = "completed"
    assert kernel.interrupt_goal(goal_id) is False


# --------------------------------------------------------------------------- #
# The runtime honors the suspension
# --------------------------------------------------------------------------- #
def test_runtime_waits_for_resume_before_finalizing(store_dir):
    """The decisive behavior: the goal must not finalize while suspended."""
    kernel = _kernel(store_dir)
    operator = _BlockingOperator()
    kernel.register_runtime(GoalExecutionRuntime(lambda _t: operator))

    order = []
    kernel.subscribe("goal.suspended", lambda e: order.append("suspended"))
    kernel.subscribe("goal.resumed", lambda e: order.append("resumed"))
    kernel.subscribe("goal.completed", lambda e: order.append("completed"))

    worker = threading.Thread(target=lambda: kernel.submit_goal("slow goal"))
    worker.start()
    try:
        assert operator.entered.wait(timeout=10), "goal never entered execution"
        goal_id = next(iter(kernel._goals))
        assert kernel.interrupt_goal(goal_id) is True

        # Let the unit of work finish; the runtime must then WAIT at its checkpoint.
        operator.release.set()
        time.sleep(0.2)
        assert "completed" not in order, (
            "the goal finalized while suspended — the suspension was not honored"
        )

        kernel.resume_goal(goal_id)
        worker.join(timeout=10)
    finally:
        operator.release.set()
        worker.join(timeout=10)

    assert order == ["suspended", "resumed", "completed"]
    assert operator.run_calls == 1, "work must not be repeated across suspend/resume"


def test_runtime_is_inert_without_the_capability(store_dir):
    """A kernel lacking is_goal_suspended must not break execution."""
    runtime = GoalExecutionRuntime(lambda _t: _Outcome())

    class _NoSuspendKernel:
        pass

    runtime._kernel = _NoSuspendKernel()
    assert runtime._await_resume("any-goal") is False


def test_suspend_wait_is_bounded(store_dir):
    """A goal suspended and never resumed must not pin a thread forever."""
    kernel = _kernel(store_dir)
    runtime = GoalExecutionRuntime(lambda _t: _Outcome())
    kernel.register_runtime(runtime)
    goal_id = kernel.submit_goal("a goal")
    kernel.interrupt_goal(goal_id)

    started = time.perf_counter()
    waited = runtime._await_resume(goal_id, timeout=0.3)
    elapsed = time.perf_counter() - started
    assert waited is True
    assert elapsed < 5.0
    assert any("suspend_wait_timeout" in r for r in runtime.health()["degraded_reasons"])


# --------------------------------------------------------------------------- #
# Suspension survives checkpoint/replay
# --------------------------------------------------------------------------- #
def test_suspension_survives_replay(store_dir):
    """Restoring must not silently resume work the user paused."""
    path = os.path.join(store_dir, "replay.jsonl")
    kernel = CognitiveKernel(event_store=EventStore(path))
    goal_id = kernel.submit_goal("a goal")
    kernel.interrupt_goal(goal_id)

    store = EventStore(path)
    fresh = CognitiveKernel(event_store=store)
    fresh.restore(store.checkpoint({}, 0))

    assert fresh.is_goal_suspended(goal_id) is True
    states = {g["id"]: g["state"] for g in fresh.query_goals()}
    assert states[goal_id] == "suspended"


def test_resume_after_suspend_survives_replay(store_dir):
    path = os.path.join(store_dir, "replay2.jsonl")
    kernel = CognitiveKernel(event_store=EventStore(path))
    goal_id = kernel.submit_goal("a goal")
    kernel.interrupt_goal(goal_id)
    kernel.resume_goal(goal_id)

    store = EventStore(path)
    fresh = CognitiveKernel(event_store=store)
    fresh.restore(store.checkpoint({}, 0))

    assert fresh.is_goal_suspended(goal_id) is False


def test_checkpoint_carries_suspended_goals(store_dir):
    kernel = _kernel(store_dir, "cp.jsonl")
    goal_id = kernel.submit_goal("a goal")
    kernel.interrupt_goal(goal_id)
    snapshot = kernel._snapshot_state()
    assert goal_id in snapshot["suspended_goals"]
