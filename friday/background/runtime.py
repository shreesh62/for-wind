"""Ch 43 — BackgroundRuntime: opportunistic background cognition.

A pluggable kernel `RuntimeContract` that performs bounded, opportunistic work
ONLY while the foreground is idle and yields the instant foreground activity
arrives (Ch 43.4/43.5). Idleness is tracked event-driven — the runtime
subscribes to foreground-activity events (`goal.state_changed`,
`action.executed`) rather than busy-polling (Ch 43.3). Any foreground-activity
event resets the idle counter so foreground work always preempts background
work immediately.

Communication flows only through kernel-published events (Ch 52). This module
imports ONLY `friday.events`, `friday.kernel.contracts`, and standard-library
modules; it never reaches into learning, temporal, horizon, memory, or
competence internals.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract


def _is_dry_run() -> bool:
    """True when running under ``FRIDAY_DRY_RUN=1`` (Ch 43.6).

    Read from the environment at call-time (not import-time) so tests that set
    the flag before importing ``friday`` see it and the runtime performs bounded
    no-op-safe work while still emitting auditable events.
    """
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"

# Foreground-progress Kernel_Events whose arrival resets the idle counter
# (Ch 43.3). These are event-type namespaces only — no hardcoded application
# or site names (Axiom 15).
FOREGROUND_ACTIVITY_EVENTS: tuple[str, ...] = (
    "goal.state_changed",
    "action.executed",
)


class BackgroundRuntime(RuntimeContract):
    """Ch 43 — opportunistic background cognition; foreground always preempts."""

    def __init__(
        self,
        *,
        idle_ticks_required: int = 5,
        max_work_per_tick: int = 1,
    ) -> None:
        self._idle_ticks_required = int(idle_ticks_required)
        self._max_work_per_tick = int(max_work_per_tick)
        self._kernel: Any = None
        # Consecutive idle ticks observed since the last foreground activity.
        self._idle_ticks: int = 0
        # Total background work units performed (audit/health).
        self._work_done: int = 0
        # Degraded reason set by a failing work unit (8.2); empty when healthy.
        self._degraded_reason: str = ""
        # Round-robin cursor so successive idle ticks rotate through the work
        # units rather than always re-running the first one (Ch 43.4).
        self._work_cursor: int = 0

    # --- RuntimeContract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "background"

    def initialize(self, kernel: Any) -> None:
        """Subscribe to foreground-activity events rather than busy-polling.

        Every foreground-activity event resets the idle counter (Req 4.4/4.5),
        so foreground work preempts background work immediately.
        """
        self._kernel = kernel
        for event_type in FOREGROUND_ACTIVITY_EVENTS:
            try:
                kernel.subscribe(event_type, self._on_foreground_activity)
            except Exception:  # noqa: BLE001 - subscription must never crash init
                pass

    def tick(self, logical_time: int) -> None:
        """Do bounded work only while idle; otherwise yield (Ch 43.4/43.5).

        A tick with no intervening foreground activity counts toward idleness.
        Once at least `idle_ticks_required` consecutive idle ticks have elapsed,
        the runtime may perform up to `max_work_per_tick` bounded units. Never
        raises into the kernel tick loop (Ch 43.5).
        """
        try:
            # This tick observed no foreground activity (receive() would have
            # reset the counter first); count it toward the idle streak.
            self._idle_ticks += 1

            if self._idle_ticks < self._idle_ticks_required:
                return  # Not idle long enough — yield.

            # Idle long enough: perform bounded opportunistic work.
            self._perform_bounded_work(logical_time)
        except Exception:  # noqa: BLE001 - background work must never crash ticks
            self._degraded_reason = "tick_failed"

    def observe(self) -> List[Dict[str, Any]]:
        return []

    def receive(self, event: Event) -> None:
        """Any foreground-activity event resets the idle counter (Req 4.4).

        The kernel routes every event here (subscribed to `*`); only
        foreground-activity events preempt background work.
        """
        try:
            if getattr(event, "event_type", "") in FOREGROUND_ACTIVITY_EVENTS:
                self._idle_ticks = 0
        except Exception:  # noqa: BLE001
            pass

    def publish(self, event: Event) -> None:
        if self._kernel is not None:
            self._kernel.publish_event(event)

    def checkpoint(self) -> Dict[str, Any]:
        """JSON-serializable stats only."""
        return {
            "name": self.name,
            "idle_ticks": self._idle_ticks,
            "idle_ticks_required": self._idle_ticks_required,
            "max_work_per_tick": self._max_work_per_tick,
            "work_done": self._work_done,
            "work_cursor": self._work_cursor,
        }

    def restore(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._idle_ticks = int(state.get("idle_ticks", 0) or 0)
        self._idle_ticks_required = int(
            state.get("idle_ticks_required", self._idle_ticks_required) or 0
        )
        self._max_work_per_tick = int(
            state.get("max_work_per_tick", self._max_work_per_tick) or 0
        )
        self._work_done = int(state.get("work_done", 0) or 0)
        self._work_cursor = int(state.get("work_cursor", 0) or 0)

    def shutdown(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {
            "status": "degraded" if self._degraded_reason else "ok",
            "idle_ticks": self._idle_ticks,
            "work_done": self._work_done,
            "reason": self._degraded_reason,
        }

    # --- idle tracking helpers --------------------------------------------
    def _on_foreground_activity(self, event: Event) -> None:
        """Handler for subscribed foreground-activity events; resets idleness."""
        self._idle_ticks = 0

    def _is_idle(self) -> bool:
        """True when the idle streak has reached the required threshold."""
        return self._idle_ticks >= self._idle_ticks_required

    # --- background work (task 8.2) ---------------------------------------
    # The ordered roster of bounded Background_Work_Units. Each returns True
    # when it performed (and audited) a unit of work. The tick loop rotates a
    # round-robin cursor over this roster so no single unit starves the others.
    _WORK_UNIT_NAMES: tuple[str, ...] = (
        "consolidate_memory",
        "apply_competence_decay",
        "check_freshness",
        "advance_long_horizon",
    )

    def _perform_bounded_work(self, logical_time: int) -> None:
        """Run up to `max_work_per_tick` bounded units while idle (Ch 43.4).

        Units are attempted round-robin from `_work_cursor` so successive idle
        ticks rotate through the full roster instead of always re-running the
        first unit. Each unit is wrapped in `_guarded_unit`, which contains any
        exception, records a degraded reason surfaced by `health()`, and never
        re-raises into the kernel tick loop (Req 4.7).
        """
        units = (
            self._consolidate_memory,
            self._apply_competence_decay,
            self._check_freshness,
            self._advance_long_horizon,
        )
        total = len(units)
        if total == 0 or self._max_work_per_tick <= 0:
            return
        performed = 0
        for offset in range(total):
            if performed >= self._max_work_per_tick:
                break
            index = (self._work_cursor + offset) % total
            if self._guarded_unit(units[index], self._WORK_UNIT_NAMES[index], logical_time):
                performed += 1
        # Rotate the cursor by one so the next idle tick starts at a different
        # unit, giving every unit a fair turn over successive ticks.
        self._work_cursor = (self._work_cursor + 1) % total
        self._work_done += performed

    def _guarded_unit(self, unit: Any, unit_name: str, logical_time: int) -> bool:
        """Run one work unit under a guard (Req 4.7).

        Contains any exception raised by the unit, records a degraded reason
        that `health()` surfaces, and returns False rather than propagating —
        so a failing unit never crashes the kernel tick loop.
        """
        try:
            return bool(unit(logical_time))
        except Exception:  # noqa: BLE001 - a work unit must never crash the tick loop
            self._degraded_reason = f"work_unit_failed:{unit_name}"
            return False

    def _emit_work_done(self, unit: str, logical_time: int) -> None:
        """Publish an auditable `background.work_done` event (Req 4.6).

        The payload records which unit ran, the logical time, and whether the
        runtime is in DRY_RUN — emitted even under DRY_RUN so background work
        stays fully auditable (Req 4.8).
        """
        self.publish(
            make_event(
                event_type="background.work_done",
                source=self.name,
                logical_time=logical_time,
                payload={
                    "unit": unit,
                    "logical_time": logical_time,
                    "dry_run": _is_dry_run(),
                },
            )
        )

    def _consolidate_memory(self, logical_time: int) -> bool:
        """Propose a memory consolidation write via `memory.candidate` (Req 4.6).

        Background cognition NEVER writes memory directly (Ch 14.8); it only
        proposes a procedural-memory candidate and lets `MemoryRuntime` decide.
        The candidate carries `verified=True` and `kind="pattern"` so it flows
        through the same sanctioned path the ReflectionEngine/LearningEngine use.
        Bounded and DRY_RUN-safe: it constructs and publishes events only, with
        no I/O or direct store access.
        """
        # Propose the consolidation candidate ONLY through memory.candidate.
        self.publish(
            make_event(
                event_type="memory.candidate",
                source=self.name,
                logical_time=logical_time,
                payload={
                    "verified": True,
                    "kind": "pattern",
                    "origin": "background_consolidation",
                    "dry_run": _is_dry_run(),
                },
            )
        )
        self._emit_work_done("consolidate_memory", logical_time)
        return True

    def _apply_competence_decay(self, logical_time: int) -> bool:
        """Nudge a competence-decay sweep by emitting `background.work_done`.

        Never touches `friday.competence.*` directly (import boundary); it emits
        an auditable work-done event describing the decay sweep so the owning
        subsystem can act on it. Bounded and DRY_RUN-safe.
        """
        self._emit_work_done("apply_competence_decay", logical_time)
        return True

    def _check_freshness(self, logical_time: int) -> bool:
        """Flag a knowledge-freshness sweep via `background.work_done`.

        Emits an auditable event describing the freshness check without reaching
        into the temporal subsystem. Bounded and DRY_RUN-safe.
        """
        self._emit_work_done("check_freshness", logical_time)
        return True

    def _advance_long_horizon(self, logical_time: int) -> bool:
        """Nudge suspended long-horizon goals by EMITTING an event only.

        Must NOT import the planner (import boundary). It publishes a
        `background.work_done` event describing the long-horizon advance nudge;
        the LongHorizonPlanner, subscribed via the kernel bus, decides whether
        to advance. Bounded and DRY_RUN-safe.
        """
        self._emit_work_done("advance_long_horizon", logical_time)
        return True
