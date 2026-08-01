"""Ch 17/18/20 — GoalExecutionRuntime: execute kernel goals via the proven Operator.

The M1–M11 kernel could record a goal (``submit_goal`` → ``goal.created``) but
nothing executed it. This runtime is the missing link: it subscribes to
``goal.created`` and **delegates execution to the existing, proven Operator**
(injected as a factory), maps the ``OperatorOutcome`` into a
:class:`GoalExecutionRecord`, emits a single ``goal.completed`` / ``goal.failed``
lifecycle event, and records a completed-goal episode through an optional,
duck-typed memory sink.

Import boundary (Ch 52): this module imports ONLY ``friday.events``,
``friday.kernel.contracts``, and standard-library modules. It does NOT import
``friday.operator``, ``friday.memory``, ``friday.bridge``, or ``friday.executor``
— the Operator arrives as a factory and memory as a sink, injected by the wiring
layer. It contains no hardcoded application/site names or URLs (Axiom 15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract

RUNTIME_NAME = "goal_execution"


@dataclass(frozen=True)
class GoalExecutionRecord:
    """The outcome of executing one kernel goal via the Operator."""

    goal_id: str
    goal_text: str
    completed: bool
    summary: str = ""
    created_files: Tuple[str, ...] = ()
    error: str = ""


class GoalExecutionRuntime(RuntimeContract):
    """Ch 17/18/20 — executes kernel goals by delegating to the proven Operator."""

    def __init__(
        self,
        operator_factory: Callable[[str], Any],
        *,
        memory_sink: Optional[Any] = None,
    ) -> None:
        # operator_factory: goal_text -> object exposing .run(goal) -> OperatorOutcome.
        # memory_sink: duck-typed object exposing .record_episode(dict) -> bool.
        self._operator_factory = operator_factory
        self._memory_sink = memory_sink
        self._kernel: Any = None
        self._executed_count = 0
        self._degraded_reasons: List[str] = []

    # ------------------------------------------------------------------ core

    def execute_goal(self, goal_id: str, goal_text: str) -> GoalExecutionRecord:
        """Build an operator via the factory, run it, map the outcome.

        Never raises: a factory or ``.run`` failure is captured as a record with
        ``completed=False`` and the error text.
        """
        try:
            operator = self._operator_factory(goal_text)
            outcome = operator.run(goal_text)
        except Exception as exc:  # noqa: BLE001 — a failure is data, not a crash
            return GoalExecutionRecord(
                goal_id=goal_id,
                goal_text=goal_text,
                completed=False,
                error=str(exc),
            )

        completed = bool(getattr(outcome, "completed", False))
        summary = str(getattr(outcome, "summary", "") or "")
        created = getattr(outcome, "created_files", ()) or ()
        try:
            created_files = tuple(str(f) for f in created)
        except TypeError:
            created_files = ()

        return GoalExecutionRecord(
            goal_id=goal_id,
            goal_text=goal_text,
            completed=completed,
            summary=summary,
            created_files=created_files,
        )

    # --------------------------------------------------------------- wiring

    @property
    def name(self) -> str:
        return RUNTIME_NAME

    def initialize(self, kernel: Any) -> None:
        """Store the kernel and subscribe to ``goal.created`` (Ch 52)."""
        self._kernel = kernel
        try:
            kernel.subscribe("goal.created", self._on_goal_created)
        except Exception as exc:  # noqa: BLE001 — never break registration
            self._degraded_reasons.append(f"subscribe_failed: {exc}")

    def tick(self, logical_time: int) -> None:
        # Reactive runtime: all work is event-driven via _on_goal_created.
        return None

    def observe(self) -> List[Dict[str, Any]]:
        return []

    def receive(self, event: Event) -> None:
        # The kernel broadcasts every event to every runtime's receive(); this
        # runtime acts only on its explicit goal.created subscription, so
        # receive() is a no-op that never raises.
        return None

    def publish(self, event: Event) -> None:
        if self._kernel is not None:
            try:
                self._kernel.publish_event(event)
            except Exception as exc:  # noqa: BLE001
                self._degraded_reasons.append(f"publish_failed: {exc}")

    def checkpoint(self) -> Dict[str, Any]:
        return {"executed_count": self._executed_count}

    def restore(self, state: Dict[str, Any]) -> None:
        try:
            self._executed_count = int((state or {}).get("executed_count", 0))
        except (TypeError, ValueError):
            self._executed_count = 0

    def shutdown(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {
            "name": RUNTIME_NAME,
            "status": "degraded" if self._degraded_reasons else "ok",
            "executed_count": self._executed_count,
            "degraded_reasons": list(self._degraded_reasons),
        }

    # ---- event handler (never raises into the tick loop) -------------------

    def _on_goal_created(self, event: Any) -> None:
        """Reflect a ``goal.created`` event into execution + lifecycle emission."""
        try:
            payload = getattr(event, "payload", None) or {}
            goal_id = payload.get("goal_id")
            goal_text = payload.get("text")
            if not goal_id or not goal_text:
                return

            record = self.execute_goal(goal_id, goal_text)
            self._executed_count += 1

            # SUSPENSION CHECKPOINT — honor a cooperative interrupt before the
            # goal's lifecycle is finalized. The unit of work is already complete
            # here, so waiting loses nothing and repeats nothing; resuming simply
            # continues to the lifecycle emission.
            self._await_resume(goal_id)

            if record.completed:
                self._emit(
                    "goal.completed",
                    {
                        "goal_id": record.goal_id,
                        "summary": record.summary,
                        "created_files": list(record.created_files),
                        "completed": True,
                    },
                )
                self._record_episode(record)
            else:
                self._emit(
                    "goal.failed",
                    {"goal_id": record.goal_id, "error": record.error},
                )
        except Exception as exc:  # noqa: BLE001 — a handler must never break the loop
            self._degraded_reasons.append(f"on_goal_created_failed: {exc}")

    def _await_resume(self, goal_id: str, timeout: float = 300.0) -> bool:
        """Block while ``goal_id`` is suspended, up to ``timeout`` seconds.

        Duck-typed against the kernel's ``is_goal_suspended``: a kernel without the
        capability (or an error asking it) means "not suspended", so this is inert
        rather than fragile. Returns True if a suspension was actually waited out.

        The bound exists so a goal suspended and never resumed cannot pin a thread
        forever; hitting it is recorded as a degraded reason rather than ignored.
        """
        kernel = self._kernel
        if kernel is None:
            return False
        probe = getattr(kernel, "is_goal_suspended", None)
        if not callable(probe):
            return False

        import time

        waited = False
        deadline = time.monotonic() + timeout
        while True:
            try:
                suspended = bool(probe(goal_id))
            except Exception as exc:  # noqa: BLE001 — cannot ask ⇒ not suspended
                self._degraded_reasons.append(f"suspend_check_failed: {exc}")
                return waited
            if not suspended:
                return waited
            waited = True
            if time.monotonic() >= deadline:
                self._degraded_reasons.append(
                    f"suspend_wait_timeout: goal {goal_id} still suspended after "
                    f"{timeout:.0f}s"
                )
                return waited
            time.sleep(0.02)

    def _record_episode(self, record: GoalExecutionRecord) -> None:
        """Record a completed goal via the optional sink; never raises."""
        sink = self._memory_sink
        if sink is None:
            return
        try:
            sink.record_episode(
                {
                    "goal_id": record.goal_id,
                    "goal": record.goal_text,
                    "summary": record.summary,
                    "created_files": list(record.created_files),
                    "completed": record.completed,
                }
            )
        except Exception as exc:  # noqa: BLE001 — memory failures never break execution
            self._degraded_reasons.append(f"record_episode_failed: {exc}")

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a lifecycle event via the kernel; never raises into the loop."""
        if self._kernel is None:
            return
        try:
            self._kernel.publish_event(
                make_event(
                    event_type=event_type,
                    source=RUNTIME_NAME,
                    logical_time=self._next_logical_time(),
                    payload=payload,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._degraded_reasons.append(f"emit_failed: {exc}")

    def _next_logical_time(self) -> int:
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001
            return 1
