"""Ch 67 — CognitiveStateManager: explicit model of the operator's own mind.

Distinct from the WorldModel (Ch 9), which models external reality, this module
tracks FRIDAY's own mind-state — current focus, attention, interruptibility,
thinking depth, reasoning budget, urgency, active goal, and mode (idle /
exploration / execution / conversation) — as first-class state any subsystem can
query via ``snapshot()``.

Isolation (Req 6.2): this module imports ONLY ``friday.events`` and standard
library. It never imports goals/world/deliberation modules and never calls other
subsystems directly — it is updated purely from the kernel event stream (Ch 52).
Kernel-attached handlers read payloads defensively and never raise into the tick
loop (Req 5.5), and ``reasoning_budget`` is always clamped to ``[0, 1]``
(Req 5.4).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class CognitiveMode(str, Enum):
    """Ch 67 — the operator's current mode of engagement."""

    IDLE = "idle"
    EXPLORATION = "exploration"
    EXECUTION = "execution"
    CONVERSATION = "conversation"


class ThinkingDepth(str, Enum):
    """Ch 67 — how deeply the operator is currently reasoning."""

    SHALLOW = "shallow"
    NORMAL = "normal"
    DEEP = "deep"


@dataclass
class CognitiveState:
    """Ch 67 — a snapshot of the operator's own mind-state (mutable by design)."""

    mode: CognitiveMode = CognitiveMode.IDLE
    focus: Optional[str] = None            # goal_id currently attended to
    attention: float = 0.0                 # 0..1 committed reasoning capacity
    interruptible: bool = True
    thinking_depth: ThinkingDepth = ThinkingDepth.NORMAL
    reasoning_budget: float = 1.0          # 0..1 remaining budget
    urgency: float = 0.0                   # 0..1 (separate from importance)
    active_goal: Optional[str] = None


def _clamp01(value: float) -> float:
    """Clamp a float into the closed interval [0, 1]."""
    return max(0.0, min(1.0, float(value)))


class CognitiveStateManager:
    """Ch 67 — track focus/attention/mode; queryable by any subsystem."""

    def __init__(self) -> None:
        self._state = CognitiveState()
        self._kernel: Any = None

    def snapshot(self) -> CognitiveState:
        """Return a copy of the current state so callers can't mutate internals."""
        return dataclasses.replace(self._state)

    def enter_mode(self, mode: CognitiveMode) -> None:
        """Set the current cognitive mode."""
        self._state.mode = mode

    def set_focus(self, goal_id: Optional[str], *, attention: float = 1.0) -> None:
        """Focus on a goal (also its active_goal); clamp attention to [0, 1]."""
        self._state.focus = goal_id
        self._state.active_goal = goal_id
        self._state.attention = _clamp01(attention)

    def set_interruptible(self, value: bool) -> None:
        """Set whether the operator may currently be interrupted."""
        self._state.interruptible = bool(value)

    def set_thinking_depth(self, depth: ThinkingDepth) -> None:
        """Set the current thinking depth."""
        self._state.thinking_depth = depth

    def consume_budget(self, amount: float) -> float:
        """Subtract amount from reasoning budget; clamp to [0, 1]; return remaining.

        Never returns negative and never exceeds 1 (Req 5.4 / Property 9).
        """
        self._state.reasoning_budget = _clamp01(self._state.reasoning_budget - float(amount))
        return self._state.reasoning_budget

    def reset_budget(self) -> None:
        """Reset the reasoning budget back to its full value of 1.0."""
        self._state.reasoning_budget = 1.0

    def attach(self, kernel: Any) -> None:
        """Subscribe to goal.state_changed / action.executed to update focus + mode."""
        self._kernel = kernel
        kernel.subscribe("goal.state_changed", self._on_goal_state_changed)
        kernel.subscribe("action.executed", self._on_action_executed)

    # --- event handlers: defensive, never raise into the tick loop ---------
    def _on_action_executed(self, event: Any) -> None:
        """Enter EXECUTION mode on action.executed (Req 5.2); never raises."""
        try:
            self.enter_mode(CognitiveMode.EXECUTION)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_goal_state_changed(self, event: Any) -> None:
        """Focus a goal when its state becomes ``active`` (Req 5.3); never raises."""
        try:
            payload = getattr(event, "payload", {}) or {}
            state = payload.get("state")
            if state != "active":
                return
            goal_id = payload.get("goal_id")
            if not goal_id:
                return
            self.set_focus(goal_id)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return
