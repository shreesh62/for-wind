"""Ch 19 — GoalGraph: decomposition and dependency graph over Goals.

Two edge types:
- parent/child (decomposition): a parent completes only when all blocking
  children complete.
- depends_on (ordering): a goal is ready only when its dependencies are
  terminal-successful.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Set

from friday.goals.goal import Goal, GoalState


class GoalGraph:
    """Thread-safe graph of goals with decomposition and dependencies."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._goals: Dict[str, Goal] = {}
        self._children: Dict[str, List[str]] = {}
        self._depends_on: Dict[str, Set[str]] = {}

    # Structure ------------------------------------------------------------

    def add(self, goal: Goal) -> None:
        with self._lock:
            if goal.id in self._goals:
                raise ValueError(f"Goal already in graph: {goal.id}")
            self._goals[goal.id] = goal
            if goal.parent_id:
                if goal.parent_id not in self._goals:
                    raise ValueError(f"Unknown parent: {goal.parent_id}")
                self._children.setdefault(goal.parent_id, []).append(goal.id)

    def get(self, goal_id: str) -> Optional[Goal]:
        with self._lock:
            return self._goals.get(goal_id)

    def children(self, goal_id: str) -> List[Goal]:
        with self._lock:
            return [self._goals[c] for c in self._children.get(goal_id, [])]

    def add_dependency(self, goal_id: str, depends_on_id: str) -> None:
        with self._lock:
            if goal_id not in self._goals or depends_on_id not in self._goals:
                raise ValueError("Both goals must be in the graph")
            if self._would_cycle(goal_id, depends_on_id):
                raise ValueError(f"Dependency cycle: {goal_id} -> {depends_on_id}")
            self._depends_on.setdefault(goal_id, set()).add(depends_on_id)

    def _would_cycle(self, goal_id: str, depends_on_id: str) -> bool:
        # Adding goal_id -> depends_on_id cycles iff depends_on_id (transitively)
        # depends on goal_id already.
        stack = [depends_on_id]
        seen: Set[str] = set()
        while stack:
            current = stack.pop()
            if current == goal_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self._depends_on.get(current, ()))
        return False

    # Queries ---------------------------------------------------------------

    def ready(self) -> List[Goal]:
        """Non-terminal goals whose dependencies are all completed."""
        with self._lock:
            result = []
            for goal in self._goals.values():
                if goal.terminal or goal.state is GoalState.SUSPENDED:
                    continue
                deps = self._depends_on.get(goal.id, set())
                if all(self._goals[d].state is GoalState.COMPLETED for d in deps):
                    result.append(goal)
            return result

    def decomposition_complete(self, goal_id: str) -> bool:
        """True when every child is completed (leaf goals: trivially true)."""
        with self._lock:
            return all(
                self._goals[c].state is GoalState.COMPLETED
                for c in self._children.get(goal_id, [])
            )

    def roots(self) -> List[Goal]:
        with self._lock:
            return [g for g in self._goals.values() if g.parent_id is None]

    def all_goals(self) -> List[Goal]:
        with self._lock:
            return list(self._goals.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._goals)

    # Persistence -------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "goals": [g.to_dict() for g in self._goals.values()],
                "depends_on": {k: sorted(v) for k, v in self._depends_on.items()},
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalGraph":
        graph = cls()
        goals = [Goal.from_dict(g) for g in data.get("goals", [])]
        by_id = {g.id: g for g in goals}
        placed: Set[str] = set()

        def place(goal: Goal) -> None:
            if goal.id in placed:
                return
            if goal.parent_id and goal.parent_id in by_id:
                place(by_id[goal.parent_id])
            graph.add(goal)
            placed.add(goal.id)

        for goal in goals:
            place(goal)
        for goal_id, deps in data.get("depends_on", {}).items():
            for dep in deps:
                graph._depends_on.setdefault(goal_id, set()).add(dep)
        return graph
