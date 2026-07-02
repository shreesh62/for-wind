"""Operator Planner — cross-environment, capability-based goal planning.

Per ADR-020: The planner is the brain. It receives a goal + observes
the current environment + queries the tool registry + produces an
optimal execution plan that reuses existing state.

This replaces app-specific planning with environment-agnostic
capability-based planning.

Key behaviors:
- Observe BEFORE planning (what's already open/available?)
- Select tools by CAPABILITY, not by app name
- Reuse existing state (skip unnecessary work)
- Verify GOAL COMPLETION, not action execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.perception.environment import EnvironmentState
from friday.planner.decomposer import TaskPlan, TaskStep, TaskStatus
from friday.planner.goal_parser import Goal, GoalIntent, GoalParser
from friday.tools.registry import Tool, ToolCapability, ToolRegistry


@dataclass
class OperatorStep:
    """A single step in an operator plan.

    Unlike TaskStep, OperatorStep is tool-aware: it knows WHICH tool
    to use, what capability it needs, and whether existing state can
    be reused.
    """

    capability: ToolCapability
    tool_name: str
    target: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    can_skip: bool = False  # True if existing state satisfies this
    skip_reason: str = ""
    expected_outcome: str = ""
    status: TaskStatus = TaskStatus.PENDING
    order: int = 0


@dataclass
class OperatorPlan:
    """An environment-aware execution plan for a goal.

    The planner observes reality, then produces steps that:
    - Skip what's already done (app open, tab available)
    - Use the best available tool for each capability
    - Verify goal completion at the end
    """

    goal_text: str
    steps: List[OperatorStep] = field(default_factory=list)
    skipped_steps: int = 0
    environment_observations: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def actionable_steps(self) -> List[OperatorStep]:
        """Steps that actually need execution (not skipped)."""
        return [s for s in self.steps if not s.can_skip]

    @property
    def is_complete(self) -> bool:
        return all(
            s.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for s in self.steps
        )

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        done = sum(1 for s in self.steps if s.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED))
        return done / len(self.steps)

    def next_step(self) -> Optional[OperatorStep]:
        for s in self.steps:
            if s.status == TaskStatus.PENDING and not s.can_skip:
                return s
        return None


class OperatorPlanner:
    """Cross-environment planner for the General Operator.

    Uses LLM reasoning to decompose arbitrary goals into capability-based
    steps. No task-specific pipelines. The LLM thinks about requirements;
    the tool registry provides capabilities; the executor runs them.

    Usage:
        planner = OperatorPlanner(registry=tool_registry, model_router=router)
        plan = planner.plan("Research laptops and create a report", env_state=env)
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        model_router=None,
    ) -> None:
        self._registry = registry
        self._parser = GoalParser()
        self._model_router = model_router
        self._llm_decomposer = None
        if model_router:
            from friday.planner.llm_decomposer import LLMDecomposer
            self._llm_decomposer = LLMDecomposer(model_router=model_router)

    def plan(
        self,
        goal_text: str,
        env_state: Optional[EnvironmentState] = None,
    ) -> OperatorPlan:
        """Generate a requirements-driven plan for an arbitrary goal.

        Per ADR-021: Requirements Discovery → Capability Planning.
        Reason about WHAT must be true, then compose capabilities to satisfy it.
        No workflow templates. No task-type special cases.

        Args:
            goal_text: What the user wants to achieve
            env_state: Current environment (what's already running/open)

        Returns:
            OperatorPlan with capability-based steps
        """
        plan = OperatorPlan(goal_text=goal_text)

        if env_state:
            plan.environment_observations = {
                "foreground": env_state.foreground_window,
                "apps_running": [a.name for a in env_state.running_apps[:10]],
                "windows_open": [w.title for w in env_state.open_windows[:10]],
            }

        # PRIMARY PATH: LLM decomposes the goal into capability steps directly.
        # The LLM already reasons about requirements implicitly when decomposing.
        # (Requirements Discovery is available separately for verification.)
        capabilities_needed = self._goal_to_capabilities(self._parser.parse(goal_text), goal_text)

        # For each capability, find the best tool and check if skippable
        order = 0
        for cap, target, desc in capabilities_needed:
            tool = self._select_tool(cap, env_state)
            can_skip, skip_reason = self._check_skippable(cap, target, env_state)

            step = OperatorStep(
                capability=cap,
                tool_name=tool.name if tool else "unknown",
                target=target,
                description=desc,
                can_skip=can_skip,
                skip_reason=skip_reason,
                status=TaskStatus.SKIPPED if can_skip else TaskStatus.PENDING,
                order=order,
            )

            if can_skip:
                plan.skipped_steps += 1

            plan.steps.append(step)
            order += 1

        # Always add goal verification at the end
        verify_tool = self._select_tool(ToolCapability.VERIFY_GOAL, env_state)
        plan.steps.append(OperatorStep(
            capability=ToolCapability.VERIFY_GOAL,
            tool_name=verify_tool.name if verify_tool else "verification.check_goal",
            target=goal_text,
            description="Verify goal completion",
            order=order,
        ))

        return plan

    def _goal_to_capabilities(
        self, goal: Goal, goal_text: str = ""
    ) -> List[tuple]:
        """Convert a goal into required capabilities.

        PRIMARY: LLM decomposition (reasons about what the goal requires).
        FALLBACK: generic capability inference (only when LLM unavailable).

        Per ADR-021: no static workflow templates. The LLM reasons about
        requirements; the static path is a minimal generic fallback.
        """
        text = goal_text or goal.raw_text

        # PRIMARY: LLM-powered decomposition (requirements-aware)
        if self._llm_decomposer:
            try:
                result = self._llm_decomposer.decompose_sync(text)
                if result.from_llm and result.steps:
                    capabilities = []
                    for step in result.steps:
                        try:
                            cap = ToolCapability(step.capability)
                        except ValueError:
                            cap = ToolCapability.OPEN_APPLICATION
                        capabilities.append((cap, step.target, step.description))
                    return capabilities
            except Exception:
                pass

        # FALLBACK: generic capability inference (LLM unavailable only)
        return self._generic_capabilities(goal, text)

    def _generic_capabilities(self, goal: Goal, text: str) -> List[tuple]:
        """Minimal generic fallback — infers capabilities from goal shape.

        NOT a workflow library. This is a last-resort heuristic when the
        LLM is unavailable. It infers capabilities from what the goal
        structurally requires (gather info? produce content? save? send?).
        """
        from friday.planner.query_extractor import extract_search_query

        text_lower = text.lower()
        caps = []

        needs_info = any(kw in text_lower for kw in
                         ["research", "find", "search", "look up", "what", "who", "how"])
        needs_content = any(kw in text_lower for kw in
                            ["write", "create", "generate", "summary", "report", "compose", "draft",
                             "spreadsheet", "table", "list", "compare", "comparison"])
        needs_file = any(kw in text_lower for kw in
                         ["save", "file", "document", ".txt", ".docx", ".md",
                          "spreadsheet", ".csv", ".xlsx", "excel", "table"])
        needs_send = any(kw in text_lower for kw in ["email", "send", "message", "dm"])
        needs_nav = any(kw in text_lower for kw in
                        ["open", "go to", "navigate", "instagram", "youtube", "gmail"])

        if needs_info:
            # Search the TOPIC, not the whole instruction sentence.
            query = extract_search_query(text)
            caps.append((ToolCapability.SEARCH_WEB, query, f"Search: {query}"))
            caps.append((ToolCapability.EXTRACT_WEB_CONTENT, "results", "Extract relevant content"))
        if needs_nav and not needs_info:
            caps.append((ToolCapability.NAVIGATE_URL, goal.target or text, f"Navigate to {goal.target or 'target'}"))
        if needs_content:
            caps.append((ToolCapability.GENERATE_TEXT, text, "Produce content"))
        if needs_file:
            caps.append((ToolCapability.CREATE_FILE, text, "Save to file"))
        if needs_send:
            caps.append((ToolCapability.SEND_MESSAGE, goal.target or "recipient", "Deliver to recipient"))

        # If nothing matched, default to a single navigate/open
        if not caps:
            caps.append((ToolCapability.OPEN_APPLICATION, goal.target or text, text))

        return caps

    def _select_tool(
        self, capability: ToolCapability, env_state: Optional[EnvironmentState]
    ) -> Optional[Tool]:
        """Select the best tool for a capability given current environment."""
        if not self._registry:
            return None

        tools = self._registry.find_tools(capability)
        if not tools:
            return None

        # If environment state available, prefer tools matching what's open
        if env_state and len(tools) > 1:
            # If browser is open, prefer browser tools
            if env_state.is_app_running("chrome") or env_state.is_app_running("msedge"):
                browser_tools = [t for t in tools if t.environment == "browser"]
                if browser_tools:
                    return browser_tools[0]

        return tools[0]  # Highest priority

    def _check_skippable(
        self,
        capability: ToolCapability,
        target: str,
        env_state: Optional[EnvironmentState],
    ) -> tuple:
        """Check if a step can be skipped because state already satisfies it.

        Returns (can_skip: bool, reason: str)
        """
        if not env_state:
            return False, ""

        target_lower = target.lower()

        if capability == ToolCapability.OPEN_APPLICATION:
            # Check each known app keyword that appears in the target
            known_apps = ["chrome", "firefox", "edge", "notepad", "spotify",
                          "explorer", "terminal", "word", "excel", "vscode", "code"]
            for app in known_apps:
                if app in target_lower:
                    if env_state.is_app_running(app) or env_state.is_window_open(app):
                        return True, f"{app} already running"
            # Direct match on full target
            if env_state.is_app_running(target):
                return True, f"{target} already running"
            if env_state.is_window_open(target):
                return True, f"Window for {target} already open"

        elif capability == ToolCapability.NAVIGATE_URL:
            # Is the tab already open?
            if env_state.is_tab_open(target):
                return True, f"Tab for {target} already open"

        elif capability == ToolCapability.SWITCH_WINDOW:
            # Is it already the foreground?
            if env_state.foreground_window and target_lower in env_state.foreground_window.lower():
                return True, f"{target} already in foreground"

        return False, ""
