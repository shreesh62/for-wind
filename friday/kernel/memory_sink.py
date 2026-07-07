"""Ch 14 — MemorySink: a minimal, optional, fail-safe episode-recording seam.

Lets the :class:`~friday.kernel.execution.GoalExecutionRuntime` persist a
completed-goal episode WITHOUT the kernel package importing ``friday.memory``.
The concrete memory backend (e.g. ``FridayMemory``) is injected by the wiring
layer; this adapter calls it via duck typing and never raises.

- No backend ⇒ :meth:`record_episode` is a no-op returning ``False``.
- A backend present ⇒ the first available recording method
  (``record_episode`` / ``add_episode`` / ``record_turn``) is invoked.
- Any backend error is swallowed (returns ``False``) so memory can never break
  goal execution (the 12th law: cognition endures).

Import boundary: standard-library only. No hardcoded application/site names or
URLs (Axiom 15).
"""

from __future__ import annotations

from typing import Any, Dict


class MemorySink:
    """Ch 14 — duck-typed, fail-safe episode recorder (optional backend)."""

    # Recording methods tried in order on the injected backend.
    _CANDIDATE_METHODS = ("record_episode", "add_episode", "record_turn")

    def __init__(self, friday_memory: Any = None) -> None:
        self._backend = friday_memory

    def record_episode(self, episode: Dict[str, Any]) -> bool:
        """Record ``episode`` via the backend. Returns success; never raises."""
        backend = self._backend
        if backend is None:
            return False
        for method_name in self._CANDIDATE_METHODS:
            method = getattr(backend, method_name, None)
            if not callable(method):
                continue
            try:
                method(episode)
                return True
            except Exception:  # noqa: BLE001 — memory failures never propagate
                return False
        return False
