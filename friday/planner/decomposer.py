"""Task Decomposer — breaks Goals into executable task sequences.

The decomposer takes a parsed Goal and produces an ordered list of
TaskSteps that the action layer can execute sequentially. Each step
has a clear action type, target, and expected postcondition.

The planner NEVER directly controls devices. It outputs task graphs
that the engine executes and verifies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from friday.planner.goal_parser import Goal, GoalIntent


class TaskStatus(str, Enum):
    """Execution status of a task step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    """A single executable step in a task plan.

    Each step maps to one FridayEngine.execute_verified() call.
    The planner produces steps; the engine executes them.
    """

    action_type: str
    target: str
    description: str
    parameters: Dict[str, str] = field(default_factory=dict)
    expected_postcondition: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    depends_on: List[int] = field(default_factory=list)  # indices of prior steps
    order: int = 0

    @property
    def is_done(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)


@dataclass
class TaskPlan:
    """An ordered sequence of steps to achieve a goal."""

    goal: Goal
    steps: List[TaskStep] = field(default_factory=list)
    current_step: int = 0

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.is_done)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        return self.completed_steps / self.total_steps

    @property
    def is_complete(self) -> bool:
        return all(s.is_done for s in self.steps)

    @property
    def next_step(self) -> Optional[TaskStep]:
        for step in self.steps:
            if step.status == TaskStatus.PENDING:
                return step
        return None

    def advance(self) -> Optional[TaskStep]:
        """Move to next pending step."""
        step = self.next_step
        if step:
            step.status = TaskStatus.RUNNING
            self.current_step = step.order
        return step

    def complete_current(self, result: str = "") -> None:
        """Mark current running step as complete."""
        for step in self.steps:
            if step.status == TaskStatus.RUNNING:
                step.status = TaskStatus.COMPLETED
                step.result = result
                break

    def fail_current(self, reason: str = "") -> None:
        """Mark current running step as failed."""
        for step in self.steps:
            if step.status == TaskStatus.RUNNING:
                step.status = TaskStatus.FAILED
                step.result = reason
                break


class TaskDecomposer:
    """Decomposes parsed Goals into executable TaskPlans.

    Uses pattern-based decomposition for known intents.
    Falls back to single-step plans for unknown intents.

    Usage:
        decomposer = TaskDecomposer()
        goal = goal_parser.parse("Open WhatsApp and send Om hello")
        plan = decomposer.decompose(goal)
        for step in plan.steps:
            print(f"{step.order}: {step.action_type} -> {step.target}")
    """

    def decompose(self, goal: Goal) -> TaskPlan:
        """Decompose a goal into a task plan.

        Args:
            goal: Parsed Goal object

        Returns:
            TaskPlan with ordered steps
        """
        if goal.is_multi_step:
            return self._decompose_multi(goal)

        return self._decompose_single(goal)

    def _decompose_single(self, goal: Goal) -> TaskPlan:
        """Decompose a single-step goal."""
        steps = self._intent_to_steps(goal)
        plan = TaskPlan(goal=goal, steps=steps)
        return plan

    def _decompose_multi(self, goal: Goal) -> TaskPlan:
        """Decompose a multi-step goal into sequential steps."""
        all_steps: List[TaskStep] = []
        order = 0

        for sub_goal in goal.sub_goals:
            sub_steps = self._intent_to_steps(sub_goal)
            for step in sub_steps:
                step.order = order
                if order > 0:
                    step.depends_on = [order - 1]
                all_steps.append(step)
                order += 1

        return TaskPlan(goal=goal, steps=all_steps)

    def _intent_to_steps(self, goal: Goal) -> List[TaskStep]:
        """Convert a goal intent to concrete steps."""

        if goal.intent == GoalIntent.NAVIGATE:
            return self._steps_for_navigate(goal)
        elif goal.intent == GoalIntent.COMMUNICATE:
            return self._steps_for_communicate(goal)
        elif goal.intent == GoalIntent.SEARCH:
            return self._steps_for_search(goal)
        elif goal.intent == GoalIntent.CREATE:
            return self._steps_for_create(goal)
        elif goal.intent == GoalIntent.CONTROL:
            return self._steps_for_control(goal)
        elif goal.intent == GoalIntent.RESEARCH:
            return self._steps_for_research(goal)
        else:
            return [TaskStep(
                action_type="generic",
                target=goal.target,
                description=goal.raw_text,
            )]

    def _steps_for_navigate(self, goal: Goal) -> List[TaskStep]:
        """Steps for navigation goals."""
        target = goal.target

        # Check if it's a URL or an app
        if any(target.startswith(p) for p in ["http", "www", "/"]):
            return [
                TaskStep(
                    action_type="navigate",
                    target=target,
                    description=f"Navigate to {target}",
                    expected_postcondition=f"Browser URL contains {target}",
                ),
            ]

        # It's an app
        return [
            TaskStep(
                action_type="open_app",
                target=target,
                description=f"Open {target}",
                expected_postcondition=f"Window titled {target} is active",
            ),
        ]

    def _steps_for_communicate(self, goal: Goal) -> List[TaskStep]:
        """Steps for communication goals."""
        recipient = goal.get_param("recipient") or goal.target
        message = goal.get_param("message") or ""

        steps = [
            TaskStep(
                action_type="open_app",
                target="messaging app",
                description=f"Open messaging app for {recipient}",
                parameters={"recipient": recipient},
                expected_postcondition="Messaging app is open",
            ),
            TaskStep(
                action_type="navigate",
                target=recipient,
                description=f"Find conversation with {recipient}",
                parameters={"recipient": recipient},
                expected_postcondition=f"Chat with {recipient} is visible",
            ),
        ]

        if message:
            steps.append(TaskStep(
                action_type="type",
                target="message input",
                description=f"Type message: {message[:50]}",
                parameters={"text": message},
                expected_postcondition="Message text is in input field",
            ))
            steps.append(TaskStep(
                action_type="click",
                target="send button",
                description="Send the message",
                expected_postcondition="Message sent confirmation",
            ))

        return steps

    def _steps_for_search(self, goal: Goal) -> List[TaskStep]:
        """Steps for search goals."""
        query = goal.get_param("query") or goal.target
        return [
            TaskStep(
                action_type="navigate",
                target="browser",
                description="Ensure browser is open",
                expected_postcondition="Browser window is active",
            ),
            TaskStep(
                action_type="type",
                target="search bar",
                description=f"Type search query: {query[:50]}",
                parameters={"text": query},
                expected_postcondition="Query text in search bar",
            ),
            TaskStep(
                action_type="click",
                target="search button",
                description="Execute search",
                expected_postcondition="Search results displayed",
            ),
        ]

    def _steps_for_create(self, goal: Goal) -> List[TaskStep]:
        """Steps for creation goals."""
        return [
            TaskStep(
                action_type="create",
                target=goal.target,
                description=f"Create {goal.target}",
                expected_postcondition=f"{goal.target} created",
            ),
        ]

    def _steps_for_control(self, goal: Goal) -> List[TaskStep]:
        """Steps for media/system control."""
        return [
            TaskStep(
                action_type="control",
                target=goal.target,
                description=goal.raw_text,
                expected_postcondition="Control action executed",
            ),
        ]

    def _steps_for_research(self, goal: Goal) -> List[TaskStep]:
        """Steps for research goals (complex, multi-source)."""
        return [
            TaskStep(
                action_type="navigate",
                target="browser",
                description="Open browser for research",
                expected_postcondition="Browser ready",
            ),
            TaskStep(
                action_type="search",
                target=goal.target,
                description=f"Search for: {goal.target[:50]}",
                expected_postcondition="Search results available",
            ),
            TaskStep(
                action_type="analyze",
                target="results",
                description="Analyze and summarize findings",
                expected_postcondition="Summary prepared",
            ),
        ]
