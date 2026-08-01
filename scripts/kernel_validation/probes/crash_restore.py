"""M13 — the crash-restore fault probe (C3).

What this probe actuates, in order:

1. Launch ``scripts.kernel_validation.child`` as a **real separate OS process**
   that builds a real ``CognitiveKernel`` over a **persisted** ``EventStore`` file
   and submits the scenario's goal.
2. Poll that file (``EventStore.append`` closes the log per event, so events are
   durable and cross-process readable immediately) until a goal-lifecycle event
   appears, bounded by a timeout.
3. Confirm the child is still alive — it is blocked inside goal execution — then
   ``kill()`` it. No graceful shutdown, no signal handler, no flush hook.
4. Build a **fresh** kernel over the **same** log and run the kernel's own
   ``CognitiveKernel.restore`` path, asserting the goal comes back with the same
   goal id and a legal state.

On the restore anchor: ``CognitiveKernel.restore(path)`` takes a checkpoint path,
loads that snapshot, then replays every stored event after it through
``_apply_event``. The crashed child never checkpointed (that is what a crash means),
so the probe anchors the replay at logical time 0 with an **empty** snapshot. All
restored goal state therefore comes from the durable event log alone — the anchor
contributes no goals — and the code path exercised is the kernel's real one.

No application- or site-specific logic, and no failure is swallowed: a timeout,
an early child exit, or a missing goal returns ``fail`` with the reason.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    ProbeContext,
    ProbeVerdict,
    register_probe,
)

PROBE_ID = "crash.restart_restore"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Goal-lifecycle event types. `goal.created` is emitted (and persisted) first, so
# seeing any of these means the goal was accepted by the crashed process.
_GOAL_LIFECYCLE: Tuple[str, ...] = ("goal.created", "goal.completed", "goal.failed")

# The observed time-to-first-event is ~0.4s; the bound is generous but finite.
_POLL_TIMEOUT_S = 30.0
_POLL_STEP_S = 0.05
_KILL_WAIT_S = 10.0

# The only state the kernel's goal model assigns (`submit_goal` and `_apply_event`
# in friday/kernel/kernel.py). A restored goal outside this set is not a legal
# state and must fail rather than be waved through.
_LEGAL_GOAL_STATES: Tuple[str, ...] = ("created",)


def _read_events(path: Path) -> List[Dict[str, Any]]:
    """Parse the JSON-lines event log.

    A partially written **final** line is skipped: the child can be killed
    mid-write. Any other malformed line is a real corruption and raises.
    """
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: List[Dict[str, Any]] = []
    for index, raw in enumerate(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise
    return events


def _event_types(events: List[Dict[str, Any]]) -> List[str]:
    return [str(e.get("event_type", "")) for e in events]


def _log_tail(path: Path, limit: int = 400) -> str:
    """Last bytes of the child's captured output, for a fail reason."""
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[-limit:]


class CrashRestoreProbe:
    """Kills a real process mid-goal and proves the goal is recoverable."""

    probe_id = PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        if not context.workdir:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                error="probe requires context.workdir for the persisted event log",
            )

        workdir = Path(context.workdir)
        store_path = workdir / "crash-ev.jsonl"
        child_log_path = workdir / "child.log"
        goal_text = getattr(context.scenario, "goal_text", "") or ""
        assertions: List[str] = []
        proc = None
        child_log = None

        try:
            child_log = child_log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "scripts.kernel_validation.child",
                    "--store", str(store_path), "--goal", goal_text,
                ],
                cwd=str(_PROJECT_ROOT),
                stdout=child_log,
                stderr=subprocess.STDOUT,
            )
            assertions.append(
                f"launched real child process pid {proc.pid} over persisted log "
                f"{store_path.name}"
            )

            pre_kill = self._poll_for_lifecycle(proc, store_path)
            if not pre_kill:
                exited = proc.poll()
                reason = (
                    f"child exited early with code {exited}"
                    if exited is not None
                    else f"no goal-lifecycle event within {_POLL_TIMEOUT_S:.0f}s"
                )
                tail = _log_tail(child_log_path)
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "pre-kill log contained no goal-lifecycle events "
                        f"({reason}); nothing was proven"
                        + (f"; child output: {tail}" if tail else "")
                    ),
                )

            pre_kill_types = _event_types(pre_kill)
            goal_id = ""
            for event in pre_kill:
                if event.get("event_type") == "goal.created":
                    goal_id = str((event.get("payload") or {}).get("goal_id", ""))
                    break
            if not goal_id:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "pre-kill log carried no goal.created goal_id; "
                        f"observed event types {pre_kill_types}"
                    ),
                )
            assertions.append(f"pre-kill log event types: {pre_kill_types}")
            assertions.append(f"pre-kill goal id from durable log: {goal_id}")

            if proc.poll() is not None:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        f"child exited on its own (code {proc.returncode}) before the "
                        "kill; no crash was actuated"
                    ),
                )
            assertions.append(
                f"child pid {proc.pid} was still alive mid-goal (blocked inside goal "
                "execution) immediately before the kill"
            )

            proc.kill()
            try:
                exit_code = proc.wait(timeout=_KILL_WAIT_S)
            except subprocess.TimeoutExpired:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        f"child pid {proc.pid} survived kill() for "
                        f"{_KILL_WAIT_S:.0f}s"
                    ),
                )
            assertions.append(
                f"child pid {proc.pid} killed hard with no graceful shutdown; "
                f"process gone (exit code {exit_code})"
            )

            return self._restore_and_assert(store_path, goal_id, assertions)
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=_KILL_WAIT_S)
            if child_log is not None:
                # Close the handle so the runner can remove the workdir on Windows.
                child_log.close()

    # ------------------------------------------------------------------ steps

    def _poll_for_lifecycle(
        self, proc: "subprocess.Popen[bytes]", store_path: Path
    ) -> List[Dict[str, Any]]:
        """Poll the durable log until a goal-lifecycle event lands (or time out)."""
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            events = _read_events(store_path)
            if any(e.get("event_type") in _GOAL_LIFECYCLE for e in events):
                return events
            if proc.poll() is not None:
                return []
            time.sleep(_POLL_STEP_S)
        return []

    def _restore_and_assert(
        self, store_path: Path, goal_id: str, assertions: List[str]
    ) -> ProbeVerdict:
        """Fresh kernel over the same log; run the kernel's real restore path."""
        from friday.events.store import EventStore
        from friday.kernel.kernel import CognitiveKernel

        store = EventStore(str(store_path))
        # Empty snapshot anchored at logical time 0: restore() replays every stored
        # event through the kernel's own _apply_event, so all restored goal state
        # comes from the durable log, not from the anchor.
        anchor = store.checkpoint({}, 0)
        kernel = CognitiveKernel(event_store=store)
        kernel.restore(anchor)

        post_types = _event_types(_read_events(store_path))
        assertions.append(f"post-restore replayed event types: {post_types}")

        goals = kernel.query_goals()
        restored = [g for g in goals if g.get("id") == goal_id]
        if not restored:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"fresh kernel restored goal ids {[g.get('id') for g in goals]}; "
                    f"pre-kill goal id {goal_id} was not among them"
                ),
            )

        state = str(restored[0].get("state", ""))
        if state not in _LEGAL_GOAL_STATES:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    f"restored goal {goal_id} has illegal state {state!r}; "
                    f"legal states are {list(_LEGAL_GOAL_STATES)}"
                ),
            )

        assertions.append(
            f"post-restore goal id matched pre-kill id: {goal_id}"
        )
        assertions.append(
            f"restored goal state is legal: {state!r} (of {list(_LEGAL_GOAL_STATES)})"
        )
        assertions.append(
            f"restored goal text preserved: {str(restored[0].get('text', ''))!r}"
        )
        return ProbeVerdict(
            probe_id=PROBE_ID, result=RESULT_PASS, assertions=tuple(assertions)
        )


register_probe(CrashRestoreProbe())
