"""Ch 67 — CognitiveStateManager: explicit model of the operator's own mind.

Distinct from the WorldModel (Ch 9), which models external reality, this module
tracks FRIDAY's own mind-state — current focus, attention, interruptibility,
thinking depth, reasoning budget, urgency, active goal, cognitive load,
background-cognition state, and mode (idle / exploration / execution /
conversation) — as first-class state any subsystem can query via ``snapshot()``
and consult via ``should_interrupt()`` / ``suggested_thinking_depth()``.

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
from typing import Any, Dict, Optional


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
    # --- M22 additive mind-state (appended AFTER the existing fields so the
    # field order / defaults / snapshot() contract of the original fields are
    # unchanged; Req 1.1 / 1.3) ---
    cognitive_load: float = 0.0            # 0..1 how heavily loaded the operator is
    background_active: bool = False        # background (non-foreground) cognition running

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe projection of the state (Req 1.2).

        Enum fields are emitted as their ``.value`` string, floats as floats,
        and optionals as ``None`` or ``str``. The result contains only
        JSON-serializable primitives so it can be attached to events / logs.
        """
        return {
            "mode": self.mode.value,
            "focus": self.focus,
            "attention": float(self.attention),
            "interruptible": bool(self.interruptible),
            "thinking_depth": self.thinking_depth.value,
            "reasoning_budget": float(self.reasoning_budget),
            "urgency": float(self.urgency),
            "active_goal": self.active_goal,
            "cognitive_load": float(self.cognitive_load),
            "background_active": bool(self.background_active),
        }


def _clamp01(value: float) -> float:
    """Clamp a float into the closed interval [0, 1]."""
    return max(0.0, min(1.0, float(value)))


# Documented terminal goal states that return the operator to IDLE (Req 3.3).
# Mirrors ``friday.goals.goal.GoalState`` terminal values (completed/failed/
# abandoned); "cancelled" is accepted defensively though not currently emitted.
_TERMINAL_GOAL_STATES = frozenset({"completed", "failed", "abandoned", "cancelled"})


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
        """Focus on a goal (also its active_goal); clamp attention to [0, 1].

        M22 additive side effect (Req 2.2): committing attention to a focus also
        raises ``cognitive_load`` — higher committed attention ⇒ higher load.
        The existing focus / active_goal / attention behavior is unchanged.
        """
        self._state.focus = goal_id
        self._state.active_goal = goal_id
        self._state.attention = _clamp01(attention)
        # load reflects committed attention (higher attention ⇒ higher load).
        self._state.cognitive_load = _clamp01(attention)

    def set_load(self, value: float) -> None:
        """Set cognitive_load, always clamped to [0, 1] (Req 2.1 / 2.3)."""
        self._state.cognitive_load = _clamp01(value)

    def adjust_load(self, delta: float) -> None:
        """Adjust cognitive_load by delta, always clamped to [0, 1] (Req 2.1 / 2.3)."""
        self._state.cognitive_load = _clamp01(self._state.cognitive_load + float(delta))

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

    # --- query surface: pure reads, deterministic, never mutate (Req 4) -----
    def should_interrupt(self, urgency: float) -> bool:
        """Whether an interruption of ``urgency`` should surface now (Req 4.1).

        Pure read. Returns ``True`` immediately when the operator is
        ``interruptible``. When NOT interruptible, an interruption surfaces only
        if its urgency clears a high-urgency bar that scales UP with current
        cognitive load: ``threshold = clamp01(0.5 + 0.5 * cognitive_load)``.
        So at zero load the bar is ``0.5`` and at full load it is ``1.0``
        (higher load ⇒ harder to interrupt).
        """
        if self._state.interruptible:
            return True
        threshold = _clamp01(0.5 + 0.5 * self._state.cognitive_load)
        return _clamp01(urgency) >= threshold

    def suggested_thinking_depth(self) -> ThinkingDepth:
        """Suggest a reasoning depth from budget / load (Req 4.2). Pure read.

        * ``SHALLOW`` when budget is low (< 0.3) OR load is high (> 0.7).
        * ``DEEP`` when budget is ample (> 0.7) AND load is low (< 0.3).
        * ``NORMAL`` otherwise.
        Deterministic for a given state; performs no mutation.
        """
        budget = self._state.reasoning_budget
        load = self._state.cognitive_load
        if budget < 0.3 or load > 0.7:
            return ThinkingDepth.SHALLOW
        if budget > 0.7 and load < 0.3:
            return ThinkingDepth.DEEP
        return ThinkingDepth.NORMAL

    def return_to_idle(self) -> None:
        """Return the operator to IDLE: clear focus/active_goal, drop attention and load.

        Used when foreground work completes (e.g. a focused goal reaches a
        terminal state; Req 3.3). Lowers ``cognitive_load`` toward 0.0.
        """
        self._state.mode = CognitiveMode.IDLE
        self._state.focus = None
        self._state.active_goal = None
        self._state.attention = 0.0
        self._state.cognitive_load = 0.0

    def attach(self, kernel: Any) -> None:
        """Subscribe to the kernel event stream to drive focus + mode.

        Existing subscriptions (preserved): ``goal.state_changed`` (focus /
        return-to-idle) and ``action.executed`` (EXECUTION). M22 additive
        subscriptions drive the remaining engagement modes purely from generic
        event types already present on the bus (Req 3.2):

        * ``observation.received`` — the closest real, generic exploration /
          environment-probing signal on the bus (published by the environment
          runtime / ``kernel.submit_observation``); it drives ``EXPLORATION``.
          No literal ``exploration.*`` event type exists in the codebase, so the
          closest generic signal is used rather than inventing one.
        * ``goal.created`` — a user request / goal entering the system (published
          by ``kernel.submit_goal``); the closest real conversation / user-input
          signal on the bus. It drives ``CONVERSATION``. No literal
          ``conversation.*`` / ``user_input.*`` event type exists.
        * ``reflection.completed`` — background (non-foreground) cognition
          (published by ``cognition/reflection.py``); while IDLE it marks
          ``background_active`` (Req 3.3). Foreground work clears it.
        """
        self._kernel = kernel
        kernel.subscribe("goal.state_changed", self._on_goal_state_changed)
        kernel.subscribe("action.executed", self._on_action_executed)
        kernel.subscribe("goal.created", self._on_conversation_signal)
        kernel.subscribe("observation.received", self._on_exploration_signal)
        kernel.subscribe("reflection.completed", self._on_background_signal)

    # --- event handlers: defensive, never raise into the tick loop ---------
    def _on_action_executed(self, event: Any) -> None:
        """Enter EXECUTION mode on action.executed (Req 3.1); never raises."""
        try:
            self.enter_mode(CognitiveMode.EXECUTION)
            # foreground work resumed → background cognition no longer active.
            self._state.background_active = False
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_exploration_signal(self, event: Any) -> None:
        """Enter EXPLORATION on an exploration/observation signal (Req 3.2); never raises."""
        try:
            self.enter_mode(CognitiveMode.EXPLORATION)
            self._state.background_active = False
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_conversation_signal(self, event: Any) -> None:
        """Enter CONVERSATION on a conversation/user-input signal (Req 3.2); never raises."""
        try:
            self.enter_mode(CognitiveMode.CONVERSATION)
            self._state.background_active = False
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_background_signal(self, event: Any) -> None:
        """Mark background cognition active when it runs while IDLE (Req 3.3); never raises."""
        try:
            if self._state.mode is CognitiveMode.IDLE:
                self._state.background_active = True
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_goal_state_changed(self, event: Any) -> None:
        """Focus a goal when active; return to IDLE on terminal state (Req 3.3).

        Preserves the existing focus-on-``active`` behavior. Additionally, when
        the payload ``state`` is a terminal state and the terminating goal is the
        current focus / active goal, the operator returns to IDLE (focus and
        active_goal cleared, attention and load lowered). If a *different* goal
        is active, the state is left untouched. Never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            state = payload.get("state")
            goal_id = payload.get("goal_id")
            if state == "active":
                if not goal_id:
                    return
                self.set_focus(goal_id)
                return
            if state in _TERMINAL_GOAL_STATES:
                # Only reset if the terminating goal is the one we are focused on
                # / holding active. A different active goal must not reset us.
                current = self._state.focus or self._state.active_goal
                if goal_id and current is not None and goal_id != current:
                    return
                self.return_to_idle()
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return
