"""M13 — the separate-process kernel goal submitter (crash-probe target).

The crash probe (C3) must kill a **real OS process** that has a goal in flight
against a **persisted** event log. This module is that process: it builds a real
:class:`~friday.kernel.kernel.CognitiveKernel` over an :class:`~friday.events.store.EventStore`
at the given path, submits the goal, and then idles until it is killed.

Run it as::

    python -m scripts.kernel_validation.child --store PATH --goal TEXT

Two properties matter to the parent:

* **The goal is genuinely in flight when the kill lands.** ``submit_goal`` runs
  synchronously: it emits ``goal.created``, which the ``GoalExecutionRuntime``
  handles on the same thread by calling ``operator.run(...)``. So the child injects
  a slow, offline operator (no LLM, no network) that simply blocks — the process
  therefore sits inside goal execution rather than finishing instantly.
* **The pre-kill events are already on disk.** ``EventStore.append`` opens the
  log, writes one JSON line, and closes it per event, so every event is durable
  (and readable from the parent process) the moment it is emitted — and
  ``goal.created`` is persisted *before* the bus dispatches it to the runtime.

Importing this module has no side effects; all work happens in :func:`main`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Bootstrap: make the project root importable when run directly, without needing
# PYTHONPATH set (project root is three levels up from this file).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Sleep granularity of the blocking/idle loops.
_STEP_S = 0.05
# Upper bound on the child's lifetime. The parent kills it long before this; the
# bound only guarantees the process cannot be orphaned forever if the parent dies.
_MAX_LIFETIME_S = 300.0


class _SlowOutcome:
    """Operator outcome shape consumed by ``GoalExecutionRuntime``."""

    completed = False
    summary = "child was not killed before its lifetime bound elapsed"
    created_files: tuple = ()


class _SlowOperator:
    """Offline stand-in for the real Operator: no LLM, no browser, just blocks.

    Blocking keeps the goal genuinely in progress so the parent's kill lands
    mid-flight, which is the whole point of the crash probe.
    """

    def __init__(self, deadline: float) -> None:
        self._deadline = deadline

    def run(self, goal_text: str) -> _SlowOutcome:
        while time.monotonic() < self._deadline:
            time.sleep(_STEP_S)
        return _SlowOutcome()


def main() -> int:
    """Submit one goal against a persisted event log, then idle until killed."""
    from scripts.kernel_validation.runner import _parse_flag_value

    store_path = _parse_flag_value("store")
    goal_text = _parse_flag_value("goal")
    if not store_path or not goal_text:
        print(
            "usage: python -m scripts.kernel_validation.child "
            "--store PATH --goal TEXT",
            file=sys.stderr,
        )
        return 2

    from friday.events.store import EventStore
    from friday.kernel.execution import GoalExecutionRuntime
    from friday.kernel.kernel import CognitiveKernel

    deadline = time.monotonic() + _MAX_LIFETIME_S
    kernel = CognitiveKernel(event_store=EventStore(store_path))
    kernel.register_runtime(GoalExecutionRuntime(lambda _text: _SlowOperator(deadline)))

    # Synchronous: persists goal.created, then blocks inside goal execution.
    kernel.submit_goal(goal_text)

    while time.monotonic() < deadline:
        time.sleep(_STEP_S)
    return 0


if __name__ == "__main__":  # pragma: no cover - separate-process entry point
    raise SystemExit(main())
