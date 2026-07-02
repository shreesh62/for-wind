"""Dynamic task graph for intent-driven action planning.

Expands user intent into action graphs without hardcoded workflows.
Adapts to UI changes and failures dynamically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set

from awareness.perception_snapshot import PerceptionSnapshot
from automation.semantic_actions import Action, ActionType


class TaskStatus(Enum):
    """Status of a task node."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskNode:
    """A single task in the execution graph."""
    
    task_id: str
    action: Action
    status: TaskStatus = TaskStatus.PENDING
    dependencies: Set[str] = field(default_factory=set)  # Task IDs that must complete first
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    
    def can_execute(self, completed_tasks: Set[str]) -> bool:
        """Check if all dependencies are satisfied.
        
        Args:
            completed_tasks: Set of completed task IDs
            
        Returns:
            True if task can be executed
        """
        return self.dependencies.issubset(completed_tasks)
    
    def should_retry(self) -> bool:
        """Check if task should be retried after failure.
        
        Returns:
            True if retry is allowed
        """
        return self.status == TaskStatus.FAILED and self.retry_count < self.max_retries


@dataclass
class TaskGraph:
    """Dynamic task execution graph.
    
    Represents a plan as a DAG of tasks with dependencies.
    Supports dynamic modification based on execution results.
    """
    
    goal_description: str
    nodes: List[TaskNode] = field(default_factory=list)
    completed_tasks: Set[str] = field(default_factory=set)
    
    def add_task(
        self,
        task_id: str,
        action: Action,
        dependencies: Optional[Set[str]] = None
    ) -> TaskNode:
        """Add a task to the graph.
        
        Args:
            task_id: Unique task identifier
            action: Action to execute
            dependencies: Set of task IDs that must complete first
            
        Returns:
            Created TaskNode
        """
        node = TaskNode(
            task_id=task_id,
            action=action,
            dependencies=dependencies or set()
        )
        self.nodes.append(node)
        return node
    
    def get_executable_tasks(self) -> List[TaskNode]:
        """Get all tasks ready for execution.
        
        Returns:
            List of tasks with satisfied dependencies
        """
        return [
            node for node in self.nodes
            if node.status == TaskStatus.PENDING
            and node.can_execute(self.completed_tasks)
        ]
    
    def mark_completed(self, task_id: str) -> None:
        """Mark a task as completed.
        
        Args:
            task_id: Task identifier
        """
        self.completed_tasks.add(task_id)
        for node in self.nodes:
            if node.task_id == task_id:
                node.status = TaskStatus.COMPLETED
                break
    
    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed.
        
        Args:
            task_id: Task identifier
            error: Error message
        """
        for node in self.nodes:
            if node.task_id == task_id:
                node.status = TaskStatus.FAILED
                node.error_message = error
                node.retry_count += 1
                break
    
    def is_complete(self) -> bool:
        """Check if all tasks are completed or failed.
        
        Returns:
            True if graph execution is complete
        """
        return all(
            node.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for node in self.nodes
        )
    
    def get_failed_tasks(self) -> List[TaskNode]:
        """Get all failed tasks.
        
        Returns:
            List of failed task nodes
        """
        return [node for node in self.nodes if node.status == TaskStatus.FAILED]


class TaskGraphBuilder:
    """Builds task graphs from user intent and perception state."""
    
    def build_from_goal(
        self,
        goal_description: str,
        snapshot: PerceptionSnapshot
    ) -> TaskGraph:
        """Build task graph from goal description.
        
        Args:
            goal_description: Natural language goal
            snapshot: Current perception snapshot
            
        Returns:
            TaskGraph ready for execution
        """
        graph = TaskGraph(goal_description=goal_description)
        
        # Parse intent from goal
        intent = self._parse_intent(goal_description)
        
        # Build task sequence based on intent
        if intent == "navigate":
            self._build_navigation_graph(graph, goal_description, snapshot)
        elif intent == "search":
            self._build_search_graph(graph, goal_description, snapshot)
        elif intent == "click":
            self._build_click_graph(graph, goal_description, snapshot)
        elif intent == "type":
            self._build_type_graph(graph, goal_description, snapshot)
        else:
            # Generic fallback
            self._build_generic_graph(graph, goal_description, snapshot)
        
        return graph
    
    def _parse_intent(self, goal: str) -> str:
        """Parse primary intent from goal description.
        
        Args:
            goal: Goal description
            
        Returns:
            Intent type
        """
        goal_lower = goal.lower()
        
        if any(kw in goal_lower for kw in ["open", "go to", "visit", "navigate"]):
            return "navigate"
        elif any(kw in goal_lower for kw in ["search", "find", "look for"]):
            return "search"
        elif any(kw in goal_lower for kw in ["click", "press", "tap"]):
            return "click"
        elif any(kw in goal_lower for kw in ["type", "enter", "input"]):
            return "type"
        
        return "generic"
    
    def _build_navigation_graph(
        self,
        graph: TaskGraph,
        goal: str,
        snapshot: PerceptionSnapshot
    ) -> None:
        """Build graph for navigation intent.
        
        Args:
            graph: Task graph to populate
            goal: Goal description
            snapshot: Current snapshot
        """
        # Task 1: Open browser if needed
        if not snapshot.browser.open:
            from automation.semantic_actions import create_open_browser_action
            graph.add_task("open_browser", create_open_browser_action())
        
        # Task 2: Handle blockers (consent, login)
        deps = {"open_browser"} if not snapshot.browser.open else set()
        
        if snapshot.browser.has_consent_dialog:
            from automation.semantic_actions import create_accept_consent_action
            graph.add_task("accept_consent", create_accept_consent_action(), deps)
            deps = {"accept_consent"}
        
        # Task 3: Navigate to target
        from automation.semantic_actions import create_navigate_action
        target = self._extract_target(goal)
        graph.add_task("navigate", create_navigate_action(target), deps)
    
    def _build_search_graph(
        self,
        graph: TaskGraph,
        goal: str,
        snapshot: PerceptionSnapshot
    ) -> None:
        """Build graph for search intent.
        
        Args:
            graph: Task graph to populate
            goal: Goal description
            snapshot: Current snapshot
        """
        # Task 1: Ensure browser open
        if not snapshot.browser.open:
            from automation.semantic_actions import create_open_browser_action
            graph.add_task("open_browser", create_open_browser_action())
        
        # Task 2: Navigate to search engine if not already there
        deps = {"open_browser"} if not snapshot.browser.open else set()
        
        # Task 3: Perform search
        from automation.semantic_actions import create_search_action
        query = self._extract_search_query(goal)
        graph.add_task("search", create_search_action(query), deps)
    
    def _build_click_graph(
        self,
        graph: TaskGraph,
        goal: str,
        snapshot: PerceptionSnapshot
    ) -> None:
        """Build graph for click intent.
        
        Args:
            graph: Task graph to populate
            goal: Goal description
            snapshot: Current snapshot
        """
        # Task 1: Click target element
        from automation.semantic_actions import create_click_element_action
        target = self._extract_target(goal)
        graph.add_task("click", create_click_element_action(target))
    
    def _build_type_graph(
        self,
        graph: TaskGraph,
        goal: str,
        snapshot: PerceptionSnapshot
    ) -> None:
        """Build graph for type intent.
        
        Args:
            graph: Task graph to populate
            goal: Goal description
            snapshot: Current snapshot
        """
        # Task 1: Type text
        from automation.semantic_actions import create_type_text_action
        text = self._extract_text_content(goal)
        graph.add_task("type", create_type_text_action(text))
    
    def _build_generic_graph(
        self,
        graph: TaskGraph,
        goal: str,
        snapshot: PerceptionSnapshot
    ) -> None:
        """Build generic fallback graph.
        
        Args:
            graph: Task graph to populate
            goal: Goal description
            snapshot: Current snapshot
        """
        # Fallback: try to parse as click action
        from automation.semantic_actions import create_click_element_action
        graph.add_task("generic_action", create_click_element_action(goal))
    
    def _extract_target(self, goal: str) -> str:
        """Extract target entity from goal.
        
        Args:
            goal: Goal description
            
        Returns:
            Target entity
        """
        # Remove common prefixes
        for prefix in ["open ", "go to ", "visit ", "navigate to ", "click "]:
            if goal.lower().startswith(prefix):
                return goal[len(prefix):].strip()
        
        return goal
    
    def _extract_search_query(self, goal: str) -> str:
        """Extract search query from goal.
        
        Args:
            goal: Goal description
            
        Returns:
            Search query
        """
        for prefix in ["search for ", "search ", "find ", "look for "]:
            if goal.lower().startswith(prefix):
                return goal[len(prefix):].strip()
        
        return goal
    
    def _extract_text_content(self, goal: str) -> str:
        """Extract text content from goal.
        
        Args:
            goal: Goal description
            
        Returns:
            Text to type
        """
        for prefix in ["type ", "enter ", "input "]:
            if goal.lower().startswith(prefix):
                return goal[len(prefix):].strip()
        
        return goal


def build_task_graph(goal: str, snapshot: PerceptionSnapshot) -> TaskGraph:
    """Build a task graph from goal and snapshot.
    
    Args:
        goal: Natural language goal
        snapshot: Current perception snapshot
        
    Returns:
        TaskGraph ready for execution
    """
    builder = TaskGraphBuilder()
    return builder.build_from_goal(goal, snapshot)
