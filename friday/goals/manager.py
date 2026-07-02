"""Ch 18/19 — GoalManager: kernel-attached owner of the GoalGraph.

Mirrors kernel goal events into the graph and publishes lifecycle events
back through the kernel, so every state change is on the causal event log.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from friday.events.event import Event, make_event
from friday.goals.goal import Goal, GoalState
from friday.goals.graph import GoalGraph


class GoalManager:
    """Owns the GoalGraph; driven by and reporting through kernel events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._graph = GoalGraph()
        self._kernel: Any = None

    @property
    def graph(self) -> GoalGraph:
        return self._graph

    def attach(self, kernel: Any) -> None:
        self._kernel = kernel
        kernel.subscribe("goal.created", self._on_goal_created)

    def _on_goal_created(self, event: Event) -> None:
        goal_id = event.payload.get("goal_id")
        text = event.payload.get("text", "")
        if not goal_id:
            return
        with self._lock:
            if self._graph.get(goal_id) is None:
                self._graph.add(Goal(text=text, goal_id=goal_id))

    # Lifecycle operations ---------------------------------------------------

    def decompose(self, parent_id: str, subgoal_texts: List[str]) -> List[str]:
        """Create child goals under a parent; children are eventful too."""
        parent = self._graph.get(parent_id)
        if parent is None:
            raise ValueError(f"Unknown goal: {parent_id}")
        child_ids = []
        with self._lock:
            for text in subgoal_texts:
                child = Goal(text=text, parent_id=parent_id)
                self._graph.add(child)
                child_ids.append(child.id)
                self._publish(
                    "goal.decomposed",
                    {"goal_id": child.id, "parent_id": parent_id, "text": text},
                )
        return child_ids

    def set_state(
        self, goal_id: str, state: GoalState, reason: Optional[str] = None
    ) -> None:
        goal = self._graph.get(goal_id)
        if goal is None:
            raise ValueError(f"Unknown goal: {goal_id}")
        goal.transition(state, reason=reason)
        self._publish(
            "goal.state_changed",
            {"goal_id": goal_id, "state": state.value, "reason": reason or ""},
        )
        if state is GoalState.COMPLETED and goal.parent_id:
            self._maybe_complete_parent(goal.parent_id)

    def _maybe_complete_parent(self, parent_id: str) -> None:
        parent = self._graph.get(parent_id)
        if (
            parent is not None
            and not parent.terminal
            and self._graph.decomposition_complete(parent_id)
        ):
            if parent.state is GoalState.CREATED:
                parent.activate()
            self.set_state(parent_id, GoalState.COMPLETED)

    def ready_goals(self) -> List[Goal]:
        return self._graph.ready()

    # Persistence --------------------------------------------------------------

    def checkpoint(self) -> Dict[str, Any]:
        with self._lock:
            return self._graph.to_dict()

    def restore(self, state: Dict[str, Any]) -> None:
        with self._lock:
            self._graph = GoalGraph.from_dict(state)

    def _publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self._kernel is None:
            return
        self._kernel.publish_event(
            make_event(
                event_type=event_type,
                source="goals",
                logical_time=self._kernel.health()["tick"] + 1,
                payload=payload,
            )
        )
