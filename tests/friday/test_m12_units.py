"""M12 — Unit tests for GoalExecutionRuntime + MemorySink cores.

Verifies the runtime delegates to the injected operator factory and maps the
outcome, never raises on a failing operator, and that the MemorySink is optional
and fail-safe.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import types

import pytest

from friday.kernel.execution import GoalExecutionRecord, GoalExecutionRuntime
from friday.kernel.memory_sink import MemorySink


def _outcome(completed=True, summary="did it", created_files=("a.md",)):
    return types.SimpleNamespace(
        completed=completed, summary=summary, created_files=list(created_files)
    )


def _factory(outcome):
    return lambda goal_text: types.SimpleNamespace(run=lambda g: outcome)


# --------------------------------------------------------------------------- #
# execute_goal mapping
# --------------------------------------------------------------------------- #
def test_execute_goal_maps_successful_outcome():
    runtime = GoalExecutionRuntime(_factory(_outcome()))
    rec = runtime.execute_goal("g1", "do x")
    assert isinstance(rec, GoalExecutionRecord)
    assert rec.completed is True
    assert rec.summary == "did it"
    assert rec.created_files == ("a.md",)
    assert rec.goal_id == "g1"


def test_execute_goal_maps_incomplete_outcome():
    runtime = GoalExecutionRuntime(_factory(_outcome(completed=False, summary="partial")))
    rec = runtime.execute_goal("g2", "do y")
    assert rec.completed is False
    assert rec.summary == "partial"


def test_execute_goal_calls_factory_exactly_once():
    calls = {"n": 0}

    def factory(goal_text):
        calls["n"] += 1
        return types.SimpleNamespace(run=lambda g: _outcome())

    runtime = GoalExecutionRuntime(factory)
    runtime.execute_goal("g3", "z")
    assert calls["n"] == 1


def test_execute_goal_never_raises_on_factory_error():
    def bad_factory(goal_text):
        raise RuntimeError("factory boom")

    runtime = GoalExecutionRuntime(bad_factory)
    rec = runtime.execute_goal("g4", "z")
    assert rec.completed is False
    assert "boom" in rec.error


def test_execute_goal_never_raises_on_run_error():
    def factory(goal_text):
        return types.SimpleNamespace(
            run=lambda g: (_ for _ in ()).throw(RuntimeError("run boom"))
        )

    runtime = GoalExecutionRuntime(factory)
    rec = runtime.execute_goal("g5", "z")
    assert rec.completed is False
    assert "boom" in rec.error


def test_record_is_frozen():
    rec = GoalExecutionRecord(goal_id="g", goal_text="t", completed=True)
    with pytest.raises(Exception):
        rec.completed = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# MemorySink
# --------------------------------------------------------------------------- #
def test_memory_sink_noop_without_backend():
    assert MemorySink().record_episode({"a": 1}) is False


def test_memory_sink_records_via_backend():
    captured = []

    class Backend:
        def record_episode(self, episode):
            captured.append(episode)

    assert MemorySink(Backend()).record_episode({"goal": "x"}) is True
    assert captured == [{"goal": "x"}]


def test_memory_sink_swallows_backend_error():
    class Backend:
        def record_episode(self, episode):
            raise RuntimeError("backend down")

    assert MemorySink(Backend()).record_episode({"goal": "x"}) is False


def test_memory_sink_tries_alternate_method_names():
    captured = []

    class Backend:
        def add_episode(self, episode):
            captured.append(episode)

    assert MemorySink(Backend()).record_episode({"g": 1}) is True
    assert captured == [{"g": 1}]
