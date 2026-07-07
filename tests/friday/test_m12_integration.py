"""M12 — Kernel-event integration test (goal execution end-to-end).

Wires a REAL CognitiveKernel with a registered GoalExecutionRuntime driven by a
STUB operator factory, and confirms submit_goal → the runtime executes → a
goal.completed / goal.failed lifecycle event lands on the bus, and a memory sink
captures one episode. This is the first end-to-end kernel goal execution.

Requirements: 1.4, 2.1, 4.2
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import types
from typing import List

from friday.events.store import EventStore
from friday.kernel.execution import GoalExecutionRuntime
from friday.kernel.kernel import CognitiveKernel


def _kernel(tmp_path) -> CognitiveKernel:
    return CognitiveKernel(event_store=EventStore(str(tmp_path / "events.jsonl")))


def _factory(outcome):
    return lambda goal_text: types.SimpleNamespace(run=lambda g: outcome)


def test_submit_goal_executes_and_emits_completed(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("goal.completed", lambda e: seen.append(e.event_type))

    outcome = types.SimpleNamespace(completed=True, summary="research done", created_files=["r.md"])
    runtime = GoalExecutionRuntime(_factory(outcome))
    kernel.register_runtime(runtime)

    kernel.submit_goal("research quantum computing")

    assert "goal.completed" in seen


def test_submit_goal_failure_emits_failed(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("goal.failed", lambda e: seen.append(e.event_type))

    def bad_factory(goal_text):
        return types.SimpleNamespace(run=lambda g: (_ for _ in ()).throw(RuntimeError("boom")))

    runtime = GoalExecutionRuntime(bad_factory)
    kernel.register_runtime(runtime)

    kernel.submit_goal("do the impossible")

    assert "goal.failed" in seen


def test_memory_sink_captures_one_episode(tmp_path):
    kernel = _kernel(tmp_path)
    recorded = []

    class Sink:
        def record_episode(self, episode):
            recorded.append(episode)
            return True

    outcome = types.SimpleNamespace(completed=True, summary="s", created_files=[])
    runtime = GoalExecutionRuntime(_factory(outcome), memory_sink=Sink())
    kernel.register_runtime(runtime)

    kernel.submit_goal("a goal")

    assert len(recorded) == 1
    assert recorded[0]["goal"] == "a goal"
