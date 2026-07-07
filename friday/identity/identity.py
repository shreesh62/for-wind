"""Ch 51 — CognitiveIdentity: one continuous mind across many sessions.

Persists the operator's continuity — a stable identity id, user preferences,
and the durable references (goal ids + states, last checkpoint path) — so the
operator resumes rather than restarts (FAS Ch 51). Identity reuses the M3
``Goal`` serialization SHAPES (plain ``goal_id -> state`` dicts) and the kernel
checkpoint/restore semantics rather than rewriting them; it never imports the
``Goal`` class, goals/memory/kernel modules — only ``friday.events`` (when
emission is needed) and the standard library (Ch 52 isolation rule). Identity
is a passive continuity record: it subscribes to kernel events but publishes
none of its own.

``checkpoint``/``restore`` round-trip cleanly through JSON: ``restore`` is
defensive (a partial/truncated/non-dict state defaults missing fields and NEVER
invents goal ids), mirroring the M9 ``LongHorizonPlanner.restore`` pattern. All
kernel-attached handlers read payloads defensively via ``.get`` and are wrapped
in try/except so a malformed event is skipped WITHOUT raising into the kernel
tick loop (mirrors the M8/M9 convention).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CognitiveIdentity:
    """Ch 51 — one mind across many sessions.

    Tracks a stable ``identity_id``, a ``preferences`` mapping, a
    ``goal_states`` mapping (``goal_id -> state``), and the ``last_checkpoint``
    path. ``_kernel`` is an internal handle set by :meth:`attach`; it is kept
    out of ``repr`` so identity logs never leak the kernel object.
    """

    identity_id: str
    preferences: Dict[str, Any] = field(default_factory=dict)
    goal_states: Dict[str, str] = field(default_factory=dict)  # goal_id -> state
    last_checkpoint: Optional[str] = None
    _kernel: Any = field(default=None, repr=False)

    # --- pure core ---------------------------------------------------------

    def set_preference(self, key: str, value: Any) -> None:
        """Record a user preference under ``key`` (last write wins)."""
        self.preferences[key] = value

    def record_goal_state(self, goal_id: str, state: str) -> None:
        """Record ``goal_id -> state`` (reuses M3 Goal state shapes, not the class)."""
        self.goal_states[goal_id] = state

    def checkpoint(self) -> Dict[str, Any]:
        """Produce JSON-serializable identity state so the mind survives restarts.

        Returns a plain dict of ``{identity_id, preferences, goal_states,
        last_checkpoint}``. Preferences and goal states are copied so later
        mutation of the identity does not retroactively alter a taken snapshot.
        The result round-trips cleanly through JSON and is consumed by
        :meth:`restore`.
        """
        return {
            "identity_id": self.identity_id,
            "preferences": dict(self.preferences),
            "goal_states": dict(self.goal_states),
            "last_checkpoint": self.last_checkpoint,
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Rehydrate identity from checkpoint state (defensive; invents nothing).

        Mirrors the M9 ``LongHorizonPlanner.restore`` defensiveness: a
        non-dict/partial/truncated ``state`` keeps sensible defaults rather than
        raising, missing fields default, and NO goal id is ever invented — only
        what was explicitly serialized is rehydrated. The ``identity_id`` is
        preserved from the state when present (the same mind continues); when
        absent the existing id is kept.
        """
        if not isinstance(state, dict):
            # Non-dict state: keep current defaults, invent nothing.
            return

        identity_id = state.get("identity_id")
        if isinstance(identity_id, str) and identity_id:
            self.identity_id = identity_id

        raw_preferences = state.get("preferences")
        self.preferences = dict(raw_preferences) if isinstance(raw_preferences, dict) else {}

        raw_goal_states = state.get("goal_states")
        if isinstance(raw_goal_states, dict):
            # Never invent goal ids: only keep explicitly serialized entries.
            self.goal_states = {
                str(goal_id): str(gstate) for goal_id, gstate in raw_goal_states.items()
            }
        else:
            self.goal_states = {}

        last_checkpoint = state.get("last_checkpoint")
        self.last_checkpoint = last_checkpoint if isinstance(last_checkpoint, str) else None

    # --- kernel wiring (Ch 52 — kernel-driven) -----------------------------

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``goal.state_changed`` + ``kernel.checkpoint`` (Ch 52).

        Stores the kernel handle and subscribes so identity continuity is fed
        from the event stream: goal state transitions update ``goal_states`` and
        a kernel checkpoint records ``last_checkpoint``. Identity publishes no
        events of its own — it is a passive continuity record.
        """
        self._kernel = kernel
        kernel.subscribe("goal.state_changed", self._on_goal_state_changed)
        kernel.subscribe("kernel.checkpoint", self._on_kernel_checkpoint)

    def _on_goal_state_changed(self, event: Any) -> None:
        """Record ``goal_id -> state`` from a ``goal.state_changed`` event.

        Reads the payload defensively via ``.get``; skips when ``goal_id`` or
        ``state`` is absent, and never raises into the kernel tick loop.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            state = payload.get("state")
            if not goal_id or state is None:
                return
            self.record_goal_state(str(goal_id), str(state))
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_kernel_checkpoint(self, event: Any) -> None:
        """Record the checkpoint ``path`` from a ``kernel.checkpoint`` event.

        Reads the payload ``path`` defensively via ``.get``; skips when absent,
        and never raises into the kernel tick loop.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            path = payload.get("path")
            if not path:
                return
            self.last_checkpoint = str(path)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return
