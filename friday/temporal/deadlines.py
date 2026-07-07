"""Ch 49 — DeadlineTracker: classify goal deadlines; answer "can this finish?".

Tracks goal deadlines against the kernel clock and classifies each tracked goal
as ``ON_TRACK`` / ``APPROACHING`` / ``MISSED`` at a given wall time. Like every
temporal component, it reads time ONLY from values carried on Kernel_Events
(``logical_time`` / ``wall_time``, Ch 52) — ``evaluate`` and ``can_finish`` take
``now_wall`` as an argument and construct no clock of their own, so deadline
reasoning stays deterministic and replay-safe under ``FRIDAY_DRY_RUN=1``.

Classification uses two wall-time anchors captured at ``register`` time:
``total_window = deadline_wall - created_wall`` (the full runway) and
``remaining = deadline_wall - now_wall`` (the runway left at evaluation). A goal
is ``MISSED`` once ``now_wall`` passes ``deadline_wall``; it is ``APPROACHING``
when ``remaining`` has fallen to at most ``approach_fraction`` of the total
window and is not yet missed; otherwise it is ``ON_TRACK``. A non-positive
window (``deadline_wall <= created_wall``) is handled without dividing by zero:
such a goal is ``MISSED`` only when ``now_wall > deadline_wall`` and ``ON_TRACK``
otherwise. Goals without a deadline constraint are never registered, so they are
never tracked (Req 2.7). This is the classification core only; kernel wiring
(``attach`` + approaching/missed emissions) lives alongside it separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from friday.events.event import make_event


class DeadlineState(str, Enum):
    """Ch 49 — how a tracked goal stands against its deadline at a wall time."""

    ON_TRACK = "on_track"
    APPROACHING = "approaching"
    MISSED = "missed"


@dataclass(frozen=True)
class DeadlineStatus:
    """One tracked goal's classification at a given wall time."""

    goal_id: str
    state: DeadlineState
    remaining_seconds: float  # negative when missed
    deadline_wall: float


class DeadlineTracker:
    """Ch 49 — track goal deadlines; classify ON_TRACK / APPROACHING / MISSED."""

    def __init__(self, *, approach_fraction: float = 0.2) -> None:
        self._approach_fraction = approach_fraction
        # goal_id -> (deadline_wall, created_wall)
        self._deadlines: Dict[str, Tuple[float, float]] = {}
        self._kernel: Any = None
        # Track the last emitted state per goal so a MISSED/APPROACHING crossing
        # is announced once rather than on every re-evaluation of the same goal.
        self._last_emitted: Dict[str, DeadlineState] = {}

    # --- kernel wiring -----------------------------------------------------
    def attach(self, kernel: Any) -> None:
        """Subscribe to goal lifecycle events (Ch 52 — kernel-driven).

        Reads each deadline from the goal's ``constraints['deadline']`` field
        (wall-time epoch seconds). Goals without a deadline constraint are never
        registered and therefore never tracked (Req 2.7).
        """
        self._kernel = kernel
        kernel.subscribe("goal.created", self._on_goal_created)
        kernel.subscribe("goal.state_changed", self._on_goal_state_changed)

    def _on_goal_created(self, event: Any) -> None:
        """Register a deadline from a ``goal.created`` event; never raises.

        The deadline is read defensively from the event payload. It may live on
        a ``constraints`` mapping (``constraints['deadline']``) or directly on a
        ``deadline`` field. Goals with no deadline are skipped (Req 2.7).
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            deadline_wall = self._extract_deadline(payload)
            if deadline_wall is None:
                return  # no deadline constraint → never tracked (Req 2.7)

            created_wall = self._event_wall_time(event, payload)
            self.register(goal_id, deadline_wall, created_wall=created_wall)
            # Evaluate immediately so an already-approaching/missed goal is
            # announced at creation time.
            self._evaluate_and_emit(goal_id, created_wall)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_goal_state_changed(self, event: Any) -> None:
        """Re-classify a goal on ``goal.state_changed`` and emit crossings.

        Reads fields defensively; if the goal is not tracked (no deadline was
        registered) there is nothing to classify. Never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            # A payload may carry a deadline even on state changes; keep the
            # registration current if one is present.
            deadline_wall = self._extract_deadline(payload)
            now_wall = self._event_wall_time(event, payload)
            if deadline_wall is not None and goal_id not in self._deadlines:
                self.register(goal_id, deadline_wall, created_wall=now_wall)

            if goal_id not in self._deadlines:
                return

            self._evaluate_and_emit(goal_id, now_wall)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    # --- emission helpers --------------------------------------------------
    def _evaluate_and_emit(self, goal_id: str, now_wall: float) -> None:
        """Classify a single tracked goal at ``now_wall`` and publish crossings."""
        entry = self._deadlines.get(goal_id)
        if entry is None:
            return
        deadline_wall, created_wall = entry
        remaining = deadline_wall - now_wall
        total_window = deadline_wall - created_wall

        if now_wall > deadline_wall:
            state = DeadlineState.MISSED
        elif total_window > 0.0 and remaining <= self._approach_fraction * total_window:
            state = DeadlineState.APPROACHING
        else:
            state = DeadlineState.ON_TRACK

        # Only emit on a change into APPROACHING / MISSED (avoid duplicate spam).
        if self._last_emitted.get(goal_id) == state:
            return
        self._last_emitted[goal_id] = state

        if state is DeadlineState.APPROACHING:
            self._emit(
                "temporal.deadline_approaching",
                {
                    "goal_id": goal_id,
                    "remaining_seconds": remaining,
                    "deadline_wall": deadline_wall,
                },
            )
        elif state is DeadlineState.MISSED:
            self._emit(
                "temporal.deadline_missed",
                {
                    "goal_id": goal_id,
                    "overrun_seconds": now_wall - deadline_wall,
                    "deadline_wall": deadline_wall,
                },
            )

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a temporal event via the kernel; never raises."""
        if self._kernel is None:
            return
        event = make_event(
            event_type=event_type,
            source="temporal",
            logical_time=self._next_tick(),
            payload=payload,
        )
        self._kernel.publish_event(event)

    @staticmethod
    def _extract_deadline(payload: Dict[str, Any]) -> Optional[float]:
        """Read a deadline (epoch seconds) from a payload, defensively.

        Accepts either a ``constraints`` mapping carrying a ``deadline`` key or a
        top-level ``deadline`` field. Returns ``None`` when no usable numeric
        deadline is present.
        """
        raw: Any = None
        constraints = payload.get("constraints")
        if isinstance(constraints, dict):
            raw = constraints.get("deadline")
        if raw is None:
            raw = payload.get("deadline")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _event_wall_time(event: Any, payload: Dict[str, Any]) -> float:
        """Best-effort wall time for classification (Ch 52 — clock on the event)."""
        wall = payload.get("now_wall")
        if wall is None:
            wall = getattr(event, "wall_time", None)
        try:
            return float(wall) if wall is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1

    def register(
        self, goal_id: str, deadline_wall: float, *, created_wall: float
    ) -> None:
        """Record a deadline for a goal.

        The deadline is taken from the goal's ``constraints['deadline']`` by the
        kernel wiring; goals without a deadline constraint are never registered
        and therefore never tracked (Req 2.7).
        """
        self._deadlines[goal_id] = (deadline_wall, created_wall)

    def evaluate(self, now_wall: float) -> List[DeadlineStatus]:
        """Classify each tracked goal against its deadline at ``now_wall``.

        - ``MISSED`` when ``now_wall > deadline_wall`` (the goal is assumed
          non-terminal while tracked; terminal goals are dropped by the wiring);
        - ``APPROACHING`` when not missed and ``remaining`` has fallen to at most
          ``approach_fraction * total_window``;
        - ``ON_TRACK`` otherwise.

        A non-positive ``total_window`` never divides by zero: such a goal is
        ``MISSED`` only when ``now_wall > deadline_wall``, else ``ON_TRACK``.
        """
        statuses: List[DeadlineStatus] = []
        for goal_id, (deadline_wall, created_wall) in self._deadlines.items():
            remaining = deadline_wall - now_wall
            total_window = deadline_wall - created_wall

            if now_wall > deadline_wall:
                state = DeadlineState.MISSED
            elif total_window > 0.0 and remaining <= self._approach_fraction * total_window:
                state = DeadlineState.APPROACHING
            else:
                state = DeadlineState.ON_TRACK

            statuses.append(
                DeadlineStatus(
                    goal_id=goal_id,
                    state=state,
                    remaining_seconds=remaining,
                    deadline_wall=deadline_wall,
                )
            )
        return statuses

    def can_finish(self, goal_id: str, now_wall: float, *, est_seconds: float) -> bool:
        """True iff the time remaining until the deadline is at least ``est_seconds``.

        Feasibility check reusing ``time_remaining`` semantics
        (``deadline_wall - now_wall``). An untracked goal cannot be judged
        feasible and returns ``False``.
        """
        entry: Optional[Tuple[float, float]] = self._deadlines.get(goal_id)
        if entry is None:
            return False
        deadline_wall, _created_wall = entry
        return (deadline_wall - now_wall) >= est_seconds
