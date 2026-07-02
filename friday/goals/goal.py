"""Ch 18 — Goal: first-class object with an explicit lifecycle state machine.

Axiom: the goal (desired outcome) is immutable; strategies to achieve it are
disposable. Goal text and constraints therefore cannot change after creation —
only the lifecycle state moves, and only along legal transitions.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class GoalState(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


_TERMINAL = {GoalState.COMPLETED, GoalState.FAILED, GoalState.ABANDONED}

_LEGAL_TRANSITIONS: Dict[GoalState, set] = {
    GoalState.CREATED: {GoalState.ACTIVE, GoalState.ABANDONED},
    GoalState.ACTIVE: {
        GoalState.SUSPENDED,
        GoalState.BLOCKED,
        GoalState.COMPLETED,
        GoalState.FAILED,
        GoalState.ABANDONED,
    },
    GoalState.SUSPENDED: {GoalState.ACTIVE, GoalState.ABANDONED},
    GoalState.BLOCKED: {GoalState.ACTIVE, GoalState.FAILED, GoalState.ABANDONED},
    GoalState.COMPLETED: set(),
    GoalState.FAILED: set(),
    GoalState.ABANDONED: set(),
}


class IllegalTransition(Exception):
    """Raised when a goal is asked to move along a non-existent edge."""


class Goal:
    """A desired outcome. Text/constraints frozen at creation; state machine on top."""

    def __init__(
        self,
        text: str,
        constraints: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> None:
        self._id = goal_id or str(uuid.uuid4())
        self._text = text
        self._constraints = dict(constraints or {})
        self._parent_id = parent_id
        self._state = GoalState.CREATED
        self._created_at = time.time()
        self._history: List[Tuple[str, str, float]] = []  # (from, to, when)
        self._failure_reason: Optional[str] = None

    # Immutable identity -------------------------------------------------

    @property
    def id(self) -> str:
        return self._id

    @property
    def text(self) -> str:
        return self._text

    @property
    def constraints(self) -> Dict[str, Any]:
        return dict(self._constraints)

    @property
    def parent_id(self) -> Optional[str]:
        return self._parent_id

    # Lifecycle ----------------------------------------------------------

    @property
    def state(self) -> GoalState:
        return self._state

    @property
    def terminal(self) -> bool:
        return self._state in _TERMINAL

    @property
    def history(self) -> List[Tuple[str, str, float]]:
        return list(self._history)

    @property
    def failure_reason(self) -> Optional[str]:
        return self._failure_reason

    def transition(self, to: GoalState, reason: Optional[str] = None) -> None:
        if to not in _LEGAL_TRANSITIONS[self._state]:
            raise IllegalTransition(f"{self._state.value} -> {to.value}")
        self._history.append((self._state.value, to.value, time.time()))
        self._state = to
        if to is GoalState.FAILED:
            self._failure_reason = reason

    def activate(self) -> None:
        self.transition(GoalState.ACTIVE)

    def suspend(self) -> None:
        self.transition(GoalState.SUSPENDED)

    def resume(self) -> None:
        self.transition(GoalState.ACTIVE)

    def block(self) -> None:
        self.transition(GoalState.BLOCKED)

    def complete(self) -> None:
        self.transition(GoalState.COMPLETED)

    def fail(self, reason: Optional[str] = None) -> None:
        self.transition(GoalState.FAILED, reason=reason)

    def abandon(self) -> None:
        self.transition(GoalState.ABANDONED)

    # Persistence ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._id,
            "text": self._text,
            "constraints": dict(self._constraints),
            "parent_id": self._parent_id,
            "state": self._state.value,
            "created_at": self._created_at,
            "history": [list(h) for h in self._history],
            "failure_reason": self._failure_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        goal = cls(
            text=data["text"],
            constraints=data.get("constraints"),
            goal_id=data["id"],
            parent_id=data.get("parent_id"),
        )
        goal._state = GoalState(data.get("state", "created"))
        goal._created_at = float(data.get("created_at", time.time()))
        goal._history = [tuple(h) for h in data.get("history", [])]
        goal._failure_reason = data.get("failure_reason")
        return goal
