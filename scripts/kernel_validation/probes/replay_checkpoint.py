"""M13 — replay and checkpoint probes (C4 determinism).

These are kernel-internal operations — replaying an event log and restoring from a
checkpoint — that cannot be meaningfully tested by asking an LLM to plan steps for
"replay the durable event log." They exercise the kernel's own replay/restore
machinery directly, using the same assertions the kernel unit tests do, but against
a real goal lifecycle (not a synthetic one-liner).

The old approach asked the Operator to accomplish these as natural-language goals.
That only ever passed because the LLM produced garbage requirements that were
trivially satisfied, not because replay was verified. Now they are probes: direct,
deterministic, and honest.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Tuple

from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    ProbeContext,
    ProbeVerdict,
    register_probe,
)

_REPLAY_PROBE_ID = "replay.event_log"
_CHECKPOINT_PROBE_ID = "checkpoint.restore_state"


class ReplayProbe:
    """Execute a goal, then replay the durable log and assert event order."""

    probe_id = _REPLAY_PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        assertions: List[str] = []
        workdir = context.workdir or tempfile.mkdtemp(prefix="m13-replay-")
        store_path = os.path.join(workdir, "replay-ev.jsonl")

        # 1. Execute a real goal through the kernel.
        store = EventStore(store_path)
        kernel = CognitiveKernel(event_store=store)

        class _QuickOutcome:
            completed = True
            summary = "done"
            created_files: Tuple[str, ...] = ()

        kernel.register_runtime(GoalExecutionRuntime(lambda _t: _QuickOutcome()))
        goal_id = kernel.submit_goal("probe replay test goal")
        assertions.append(f"goal submitted and executed: {goal_id}")

        # 2. Read the event types from the live run.
        live_events = [e.event_type for e in store.replay()]
        if not live_events:
            return ProbeVerdict(
                probe_id=self.probe_id, result=RESULT_FAIL,
                error="no events were recorded during goal execution",
            )
        assertions.append(f"live event types: {live_events}")

        # 3. Replay from the same store and assert identical order.
        replayed = [e.event_type for e in store.replay()]
        assertions.append(f"replayed event types: {replayed}")

        if replayed != live_events:
            return ProbeVerdict(
                probe_id=self.probe_id, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"replay does not match live run: live={live_events}, "
                    f"replayed={replayed}"
                ),
            )
        assertions.append(
            "replay yields identical ordered event types as the live run"
        )
        # Goal lifecycle must be present.
        if "goal.created" not in replayed:
            return ProbeVerdict(
                probe_id=self.probe_id, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error="no goal.created in the replay — goal lifecycle not recorded",
            )
        assertions.append("goal.created present in the replay")
        return ProbeVerdict(
            probe_id=self.probe_id, result=RESULT_PASS, assertions=tuple(assertions)
        )


class CheckpointRestoreProbe:
    """Checkpoint mid-goal, restore into a fresh kernel, assert state matches."""

    probe_id = _CHECKPOINT_PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        from friday.events.store import EventStore
        from friday.kernel.kernel import CognitiveKernel

        assertions: List[str] = []
        workdir = context.workdir or tempfile.mkdtemp(prefix="m13-cp-")
        store_path = os.path.join(workdir, "cp-ev.jsonl")

        store = EventStore(store_path)
        kernel = CognitiveKernel(event_store=store)

        # Submit several goals so state is non-trivial.
        ids = []
        for i in range(3):
            ids.append(kernel.submit_goal(f"checkpoint probe goal {i}"))
        assertions.append(f"submitted {len(ids)} goals: {ids}")

        # Checkpoint.
        cp_path = kernel.checkpoint()
        assertions.append(f"checkpoint taken at: {cp_path}")

        # Submit more goals AFTER the checkpoint.
        for i in range(3, 5):
            ids.append(kernel.submit_goal(f"checkpoint probe goal {i}"))
        assertions.append(f"post-checkpoint goals: {ids[3:]}")

        original_goals = sorted(g["id"] for g in kernel.query_goals())
        assertions.append(f"original kernel has {len(original_goals)} goals")

        # Restore into a FRESH kernel.
        fresh_store = EventStore(store_path)
        fresh = CognitiveKernel(event_store=fresh_store)
        fresh.restore(cp_path)

        restored_goals = sorted(g["id"] for g in fresh.query_goals())
        assertions.append(f"restored kernel has {len(restored_goals)} goals")

        if restored_goals != original_goals:
            return ProbeVerdict(
                probe_id=self.probe_id, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"restored goals do not match original: "
                    f"original={original_goals}, restored={restored_goals}"
                ),
            )
        assertions.append(
            "restored goal ids match original (checkpoint + post-checkpoint replay)"
        )
        return ProbeVerdict(
            probe_id=self.probe_id, result=RESULT_PASS, assertions=tuple(assertions)
        )


register_probe(ReplayProbe())
register_probe(CheckpointRestoreProbe())
