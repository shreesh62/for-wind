"""M13 — the interrupt/resume fault probe (C3).

This probe answers one question: **can a goal that is genuinely in flight be
suspended and then resumed, without losing or duplicating work?**

How it actuates that:

1. Build a real ``CognitiveKernel`` over a persisted ``EventStore`` and register a
   real ``GoalExecutionRuntime`` whose operator is slow and offline (no LLM, no
   network) and signals when it has actually entered ``run``.
2. Submit the goal on a **worker thread**. ``submit_goal`` is synchronous — it
   persists ``goal.created`` and then dispatches on the calling thread into the
   runtime, which calls ``operator.run(...)`` — so the submitting thread is *inside*
   goal execution. Interrupting from the probe's own thread while the worker blocks
   is the only way to have a real in-flight goal on this kernel design.
3. **Discover** the suspension capability at runtime rather than assuming one:
   probe the kernel object and the registered runtime for any of the candidate
   suspend/resume entry points below.
4. If a capability exists, actuate it for real and judge the result from the
   durable event log. If none exists, return ``fail`` naming precisely what is
   missing.

The discovery step matters: this probe is a regression detector, not a hardcoded
verdict. The moment a suspension API is added to the kernel, the probe will find
it, actuate it, and assert against it. Until then it reports the gap honestly,
which leaves criterion C3's interrupt component correctly UNPROVEN
(Requirement 4.3) instead of passing on a weakened assertion.

No application- or site-specific logic, and no failure is swallowed.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    ProbeContext,
    ProbeVerdict,
    register_probe,
)

PROBE_ID = "interrupt.pause_resume"

# Candidate suspension entry points, searched on the kernel and on the registered
# runtime. Naming is not assumed: whichever exists is the one actuated.
_SUSPEND_NAMES: Tuple[str, ...] = (
    "interrupt", "interrupt_goal",
    "suspend", "suspend_goal",
    "pause", "pause_goal",
)
_RESUME_NAMES: Tuple[str, ...] = (
    "resume", "resume_goal", "unpause", "continue_goal",
)

# Event types that would evidence a suspension having been recorded durably.
_SUSPENSION_EVENT_HINTS: Tuple[str, ...] = (
    "goal.suspended", "goal.interrupted", "goal.paused", "goal.state_changed",
    "interrupt.requested", "interrupt.received",
)

_ENTER_TIMEOUT_S = 20.0
_JOIN_TIMEOUT_S = 30.0
_STEP_S = 0.02


class _SlowOperator:
    """Offline operator that blocks inside ``run`` until explicitly released.

    ``entered`` lets the probe wait for a genuinely in-flight goal, and
    ``run_calls`` is the duplicated-work counter (Requirement 4.2c).
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.run_calls = 0
        self._lock = threading.Lock()

    def run(self, goal_text: str) -> Any:
        with self._lock:
            self.run_calls += 1
        self.entered.set()
        self.release.wait(timeout=_JOIN_TIMEOUT_S)

        class _Outcome:
            completed = True
            summary = "slow offline operator released"
            created_files: Tuple[str, ...] = ()

        return _Outcome()


def _read_event_types(path: Path) -> List[str]:
    """Event types from the JSON-lines log; a torn final line is skipped."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    types: List[str] = []
    for index, raw in enumerate(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            types.append(str(json.loads(raw).get("event_type", "")))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise
    return types


def _find_capability(
    targets: List[Tuple[str, Any]], names: Tuple[str, ...]
) -> Tuple[Optional[Callable[..., Any]], str]:
    """First callable among ``names`` on any target, with a human label."""
    for label, target in targets:
        for name in names:
            attr = getattr(target, name, None)
            if callable(attr):
                return attr, f"{label}.{name}"
    return None, ""


def _invoke_with_goal_id(fn: Callable[..., Any], goal_id: str) -> Tuple[bool, str]:
    """Call ``fn(goal_id)``, falling back to ``fn()`` for a no-arg API."""
    try:
        fn(goal_id)
        return True, ""
    except TypeError as exc:
        try:
            fn()
            return True, ""
        except Exception as inner:  # noqa: BLE001 — reported, not swallowed
            return False, f"{type(inner).__name__}: {inner} (after TypeError: {exc})"
    except Exception as exc:  # noqa: BLE001 — reported, not swallowed
        return False, f"{type(exc).__name__}: {exc}"


class InterruptResumeProbe:
    """Interrupts a genuinely in-flight goal and proves suspend/resume behavior."""

    probe_id = PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        if not context.workdir:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                error="probe requires context.workdir for the persisted event log",
            )

        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        store_path = Path(context.workdir) / "interrupt-ev.jsonl"
        goal_text = getattr(context.scenario, "goal_text", "") or ""
        assertions: List[str] = []

        operator = _SlowOperator()
        kernel = CognitiveKernel(event_store=EventStore(str(store_path)))
        runtime = GoalExecutionRuntime(lambda _text: operator)
        kernel.register_runtime(runtime)

        submitted: Dict[str, str] = {}
        submit_error: Dict[str, str] = {}

        def _submit() -> None:
            try:
                submitted["goal_id"] = kernel.submit_goal(goal_text)
            except Exception as exc:  # noqa: BLE001 — surfaced as a fail verdict
                submit_error["error"] = f"{type(exc).__name__}: {exc}"

        worker = threading.Thread(target=_submit, name="m13-interrupt-submit")
        worker.start()
        try:
            if not operator.entered.wait(timeout=_ENTER_TIMEOUT_S):
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "the goal never entered execution within "
                        f"{_ENTER_TIMEOUT_S:.0f}s, so no in-flight goal existed to "
                        "interrupt"
                        + (f"; submit failed: {submit_error['error']}"
                           if submit_error else "")
                    ),
                )
            assertions.append(
                "goal is genuinely in flight: the operator entered run() on the "
                "submitting thread and is blocked there"
            )

            in_flight_states = [
                f"{g.get('id')}={g.get('state')!r}" for g in kernel.query_goals()
            ]
            assertions.append(f"kernel goal states while in flight: {in_flight_states}")

            # submit_goal is synchronous and is still blocked inside execution, so
            # its return value is not available yet. Read the goal id from the
            # durable log instead — the same source a real interrupt would use.
            goal_id = self._goal_id_from_log(store_path)
            if not goal_id:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "no goal id was durably recorded, so no specific goal could "
                        "be interrupted"
                    ),
                )
            assertions.append(f"in-flight goal id from the durable log: {goal_id}")

            targets: List[Tuple[str, Any]] = [
                ("CognitiveKernel", kernel),
                ("GoalExecutionRuntime", runtime),
            ]
            suspend_fn, suspend_label = _find_capability(targets, _SUSPEND_NAMES)
            resume_fn, resume_label = _find_capability(targets, _RESUME_NAMES)

            if suspend_fn is None:
                return self._missing_capability_verdict(
                    kernel, runtime, operator, store_path, assertions
                )

            assertions.append(f"discovered suspension entry point: {suspend_label}")
            ok, why = _invoke_with_goal_id(suspend_fn, goal_id)
            if not ok:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=f"suspension via {suspend_label} raised: {why}",
                )

            suspended_types = _read_event_types(store_path)
            evidence = [t for t in suspended_types if t in _SUSPENSION_EVENT_HINTS]
            suspended_states = [
                str(g.get("state")) for g in kernel.query_goals()
            ]
            assertions.append(
                f"post-interrupt durable event types: {suspended_types}"
            )
            assertions.append(
                f"post-interrupt kernel goal states: {suspended_states}"
            )
            if not evidence and "suspended" not in suspended_states:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        f"{suspend_label} produced no observable suspension: no event "
                        f"among {list(_SUSPENSION_EVENT_HINTS)} was recorded and no "
                        "goal reached a suspended state"
                    ),
                )
            assertions.append(
                f"suspension observed durably: events={evidence}, "
                f"states={suspended_states}"
            )

            if resume_fn is None:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "a suspension entry point exists but no resume entry point "
                        f"was found among {list(_RESUME_NAMES)} on the kernel or the "
                        "runtime; a goal that cannot be resumed is not recovery"
                    ),
                )
            assertions.append(f"discovered resume entry point: {resume_label}")
            # Release the blocked unit of work FIRST so the runtime actually reaches
            # its suspension checkpoint and waits there. Otherwise resume could be
            # observed before anything had a chance to honor the suspension.
            operator.release.set()
            ok, why = _invoke_with_goal_id(resume_fn, goal_id)
            if not ok:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=f"resume via {resume_label} raised: {why}",
                )

            worker.join(timeout=_JOIN_TIMEOUT_S)
            final_types = _read_event_types(store_path)
            assertions.append(f"post-resume durable event types: {final_types}")
            terminal = next(
                (t for t in ("goal.completed", "goal.failed") if t in final_types),
                "",
            )
            if not terminal:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        "progress did not continue after resume: neither "
                        "goal.completed nor goal.failed was recorded"
                    ),
                )
            # Ordering is the evidence that the suspension was HONORED rather than
            # merely recorded: the goal must not have finalized before the resume.
            if "goal.resumed" not in final_types:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error="no goal.resumed event was recorded",
                )
            if final_types.index(terminal) < final_types.index("goal.resumed"):
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        f"the suspension was not honored: {terminal} was recorded "
                        "BEFORE goal.resumed, so the goal finalized while suspended"
                    ),
                )
            assertions.append(
                f"suspension was honored: {terminal} was recorded only AFTER "
                f"goal.resumed (order: {final_types})"
            )
            if operator.run_calls != 1:
                return ProbeVerdict(
                    probe_id=PROBE_ID, result=RESULT_FAIL,
                    assertions=tuple(assertions),
                    error=(
                        f"work was duplicated: operator.run was invoked "
                        f"{operator.run_calls} times for one goal"
                    ),
                )
            assertions.append(
                "no duplicated work: operator.run was invoked exactly once across "
                "interrupt and resume"
            )
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_PASS, assertions=tuple(assertions)
            )
        finally:
            operator.release.set()
            worker.join(timeout=_JOIN_TIMEOUT_S)

    # ------------------------------------------------------------------ steps

    @staticmethod
    def _goal_id_from_log(store_path: Path) -> str:
        """The goal id from the durable ``goal.created`` event, or ""."""
        if not store_path.exists():
            return ""
        for raw in store_path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "goal.created":
                return str((event.get("payload") or {}).get("goal_id", ""))
        return ""

    def _missing_capability_verdict(
        self,
        kernel: Any,
        runtime: Any,
        operator: _SlowOperator,
        store_path: Path,
        assertions: List[str],
    ) -> ProbeVerdict:
        """No suspension API exists — report the gap precisely, never a pass."""
        operator.release.set()
        # Let the in-flight goal finish so the "no duplicated work" observation is
        # still measured; it is evidence regardless of the verdict.
        deadline = time.monotonic() + _JOIN_TIMEOUT_S
        while time.monotonic() < deadline:
            if "goal.completed" in _read_event_types(store_path):
                break
            time.sleep(_STEP_S)

        kernel_public = sorted(
            n for n in dir(kernel) if not n.startswith("_") and callable(getattr(kernel, n, None))
        )
        runtime_public = sorted(
            n for n in dir(runtime)
            if not n.startswith("_") and callable(getattr(runtime, n, None))
        )
        assertions.append(
            f"uninterrupted run completed with operator.run invoked "
            f"{operator.run_calls} time(s): {_read_event_types(store_path)}"
        )
        assertions.append(f"CognitiveKernel public callables: {kernel_public}")
        assertions.append(f"GoalExecutionRuntime public callables: {runtime_public}")
        return ProbeVerdict(
            probe_id=PROBE_ID, result=RESULT_FAIL,
            assertions=tuple(assertions),
            error=(
                "MISSING CAPABILITY — no interrupt/suspend entry point exists on "
                f"CognitiveKernel or GoalExecutionRuntime (searched {list(_SUSPEND_NAMES)}). "
                "GoalExecutionRuntime._on_goal_created runs the operator to completion "
                "synchronously inside the goal.created handler with no cooperative "
                "cancellation point, and CognitiveKernel._apply_event only ever assigns "
                "the goal state 'created', so a kernel goal has no suspended state to "
                "reach. friday.goals.goal.GoalState.SUSPENDED and Goal.suspend()/resume() "
                "exist in the Goal Graph subsystem but are not wired into kernel goal "
                "execution. C3's interrupt/resume component is therefore UNPROVEN."
            ),
        )


register_probe(InterruptResumeProbe())
