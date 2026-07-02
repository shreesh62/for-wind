"""Working Memory — current task context and active state.

The fastest memory tier. Holds:
- Current goal being pursued
- Active task plan steps
- Recent perception snapshots (last N)
- Conversation buffer (last N turns)
- Active constraints and preferences

Volatile: clears between sessions (or on explicit reset).
Capacity: small and focused (not a dumping ground).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


@dataclass
class ConversationTurn:
    """A single conversation exchange."""

    user: str
    assistant: str
    timestamp: float = 0.0
    mode: str = "jarvis"  # "jarvis" or "friday"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class ActiveGoal:
    """The currently active goal being pursued."""

    text: str
    intent: str = ""
    started_at: float = 0.0
    steps_total: int = 0
    steps_completed: int = 0
    status: str = "active"  # active, paused, completed, failed


class WorkingMemory:
    """Fast, volatile memory for current task context.

    This is the "RAM" of FRIDAY — holds everything needed for
    the current interaction without hitting disk.

    Usage:
        wm = WorkingMemory()
        wm.add_turn("Open Chrome", "Opening Chrome now.")
        wm.set_goal(ActiveGoal(text="Open Chrome and search"))
        context = wm.get_context_for_llm()
    """

    def __init__(self, max_turns: int = 10, max_snapshots: int = 3) -> None:
        self._max_turns = max_turns
        self._max_snapshots = max_snapshots
        self._turns: Deque[ConversationTurn] = deque(maxlen=max_turns)
        self._active_goal: Optional[ActiveGoal] = None
        self._state_snapshots: Deque[Dict] = deque(maxlen=max_snapshots)
        self._context_vars: Dict[str, Any] = {}
        self._session_start = time.time()

    @property
    def active_goal(self) -> Optional[ActiveGoal]:
        return self._active_goal

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def recent_turns(self) -> List[ConversationTurn]:
        return list(self._turns)

    def add_turn(self, user: str, assistant: str, mode: str = "jarvis") -> None:
        """Record a conversation turn."""
        self._turns.append(ConversationTurn(
            user=user,
            assistant=assistant,
            mode=mode,
        ))

    def set_goal(self, goal: ActiveGoal) -> None:
        """Set the current active goal."""
        if not goal.started_at:
            goal.started_at = time.time()
        self._active_goal = goal

    def clear_goal(self) -> None:
        """Clear the active goal (completed or abandoned)."""
        self._active_goal = None

    def add_state_snapshot(self, snapshot: Dict) -> None:
        """Store a perception snapshot for context."""
        self._state_snapshots.append({
            **snapshot,
            "_captured_at": time.time(),
        })

    def set_context(self, key: str, value: Any) -> None:
        """Set a context variable (preferences, constraints)."""
        self._context_vars[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self._context_vars.get(key, default)

    def get_context_for_llm(self, max_turns: int = 5) -> str:
        """Build context string suitable for LLM prompts.

        Includes recent conversation + goal + relevant state.
        Optimized for token efficiency.
        """
        parts: List[str] = []

        # Active goal
        if self._active_goal:
            parts.append(f"[Active Goal: {self._active_goal.text}]")
            if self._active_goal.steps_total > 0:
                parts.append(
                    f"[Progress: {self._active_goal.steps_completed}/{self._active_goal.steps_total}]"
                )

        # Recent conversation
        turns = list(self._turns)[-max_turns:]
        if turns:
            for turn in turns:
                parts.append(f"User: {turn.user}")
                parts.append(f"Assistant: {turn.assistant}")

        # Latest state snapshot (compact)
        if self._state_snapshots:
            latest = self._state_snapshots[-1]
            window = latest.get("window")
            url = latest.get("browser_url")
            if window:
                parts.append(f"[Window: {window}]")
            if url:
                parts.append(f"[URL: {url}]")

        return "\n".join(parts)

    def reset(self) -> None:
        """Full reset of working memory (new session)."""
        self._turns.clear()
        self._active_goal = None
        self._state_snapshots.clear()
        self._context_vars.clear()
        self._session_start = time.time()
