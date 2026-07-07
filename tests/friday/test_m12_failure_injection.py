"""M12 — Failure-injection, adversarial, and replay tests (Ch 56 Testing Philosophy).

The audit (TD-10) flagged that the suite was almost entirely happy-path / mocked
and lacked failure-injection and replay coverage. This module hardens the M12
kernel-execution path against adversarial conditions and proves deterministic
replay of the goal lifecycle from the durable event log.

These are additive, behaviour-preserving tests: they exercise the EXISTING
GoalExecutionRuntime / CognitiveKernel under injected failures and verify the
architecture's fail-safe guarantees (a failure is data, never a crash; the tick
loop always survives; the event log is replayable).

Requirements: 1.3, 1.4, 4.2, 4.4
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import types
from typing import List

from friday.events.store import EventStore
from friday.kernel.execution import GoalExecutionRuntime
from friday.kernel.kernel import CognitiveKernel


def _kernel(tmp_path, name="events") -> CognitiveKernel:
    return CognitiveKernel(event_store=EventStore(str(tmp_path / f"{name}.jsonl")))


def _ok_factory(summary="done", files=()):
    outcome = types.SimpleNamespace(completed=True, summary=summary, created_files=list(files))
    return lambda goal_text: types.SimpleNamespace(run=lambda g: outcome)


# --------------------------------------------------------------------------- #
# Failure injection — a broken operator never crashes the kernel tick loop
# --------------------------------------------------------------------------- #
def test_operator_run_raises_kernel_survives(tmp_path):
    kernel = _kernel(tmp_path)
    failed: List[str] = []
    kernel.subscribe("goal.failed", lambda e: failed.append(e.payload.get("error", "")))

    def exploding(goal_text):
        return types.SimpleNamespace(run=lambda g: (_ for _ in ()).throw(RuntimeError("kaboom")))

    kernel.register_runtime(GoalExecutionRuntime(exploding))
    kernel.submit_goal("do a thing")

    # The failure surfaced as an event, not an exception; kernel health stays sane.
    assert failed and "kaboom" in failed[0]
    assert kernel.health()["running"] in (True, False)  # health() itself must not raise


def test_factory_raises_kernel_survives(tmp_path):
    kernel = _kernel(tmp_path)
    failed: List[str] = []
    kernel.subscribe("goal.failed", lambda e: failed.append(e.event_type))

    def bad_factory(goal_text):
        raise ValueError("cannot build operator")

    kernel.register_runtime(GoalExecutionRuntime(bad_factory))
    kernel.submit_goal("goal")
    assert failed == ["goal.failed"]


def test_memory_sink_failure_does_not_block_completion(tmp_path):
    kernel = _kernel(tmp_path)
    completed: List[str] = []
    kernel.subscribe("goal.completed", lambda e: completed.append(e.event_type))

    class ExplodingSink:
        def record_episode(self, episode):
            raise RuntimeError("disk full")

    runtime = GoalExecutionRuntime(_ok_factory(), memory_sink=ExplodingSink())
    kernel.register_runtime(runtime)
    kernel.submit_goal("goal")

    # Completion still emitted despite the sink blowing up; runtime notes degraded.
    assert completed == ["goal.completed"]
    assert runtime.health()["status"] == "degraded"


# --------------------------------------------------------------------------- #
# Adversarial payloads — malformed goal.created events are ignored, not fatal
# --------------------------------------------------------------------------- #
def test_malformed_goal_events_are_ignored(tmp_path):
    kernel = _kernel(tmp_path)
    emitted: List[str] = []
    kernel.subscribe("goal.completed", lambda e: emitted.append(e.event_type))
    kernel.subscribe("goal.failed", lambda e: emitted.append(e.event_type))

    runtime = GoalExecutionRuntime(_ok_factory())
    kernel.register_runtime(runtime)

    # Directly feed adversarial events to the handler (missing fields / bad types).
    runtime._on_goal_created(types.SimpleNamespace(payload=None))
    runtime._on_goal_created(types.SimpleNamespace(payload={}))
    runtime._on_goal_created(types.SimpleNamespace(payload={"goal_id": "g"}))  # no text
    runtime._on_goal_created(types.SimpleNamespace(payload={"text": "t"}))     # no id

    # None of these produced a lifecycle event, and nothing raised.
    assert emitted == []


def test_operator_returns_garbage_outcome_is_handled(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("goal.*", lambda e: seen.append(e.event_type))

    # Outcome missing attributes entirely — mapping must default SAFELY to
    # completed=False (→ goal.failed), never falsely report success or crash.
    garbage = object()
    runtime = GoalExecutionRuntime(lambda g: types.SimpleNamespace(run=lambda gg: garbage))
    kernel.register_runtime(runtime)
    kernel.submit_goal("goal")

    assert "goal.failed" in seen
    assert "goal.completed" not in seen


# --------------------------------------------------------------------------- #
# Replay determinism — the goal lifecycle is reconstructable from the log
# --------------------------------------------------------------------------- #
def test_goal_lifecycle_is_persisted_and_replayable(tmp_path):
    store = EventStore(str(tmp_path / "replay.jsonl"))
    kernel = CognitiveKernel(event_store=store)
    kernel.register_runtime(GoalExecutionRuntime(_ok_factory(summary="s1")))

    kernel.submit_goal("first goal")
    kernel.submit_goal("second goal")

    # Replay the durable log; the goal.created + goal.completed events are all there.
    replayed = [e.event_type for e in store.replay(from_logical_time=0)]
    assert replayed.count("goal.created") == 2
    assert replayed.count("goal.completed") == 2


def test_replay_event_types_are_deterministic(tmp_path):
    """Running the identical goal sequence twice yields identical ordered event
    types on the durable log (deterministic reconstruction)."""

    def run_once(tag: str) -> List[str]:
        store = EventStore(str(tmp_path / f"det_{tag}.jsonl"))
        kernel = CognitiveKernel(event_store=store)
        kernel.register_runtime(GoalExecutionRuntime(_ok_factory(summary="fixed")))
        kernel.submit_goal("alpha")
        kernel.submit_goal("beta")
        return [
            e.event_type
            for e in store.replay(from_logical_time=0)
            if e.event_type.startswith("goal.")
        ]

    assert run_once("a") == run_once("b")
