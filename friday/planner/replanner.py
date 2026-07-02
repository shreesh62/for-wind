"""Replanner — LLM-powered plan revision on action failure.

When a task step fails verification, the replanner:
1. Checks procedural memory for proven repair strategies
2. If no memory match, asks the model router (NVIDIA reasoning) to suggest alternatives
3. Produces revised TaskStep(s) that attempt a different approach

The replanner NEVER directly controls devices.
It outputs revised steps for the engine to execute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from friday.actions.result import ActionResult
from friday.memory.procedural import ProceduralMemory
from friday.perception.world_state import WorldState
from friday.planner.decomposer import TaskStep


@dataclass
class ReplanContext:
    """Context for the replanner to reason about."""

    failed_step: TaskStep
    failure_reason: str
    world_state_summary: Dict[str, Any]
    attempt_number: int = 1
    previous_repairs: List[str] = None
    perception_quality: Dict[str, Any] = None

    def __post_init__(self):
        if self.previous_repairs is None:
            self.previous_repairs = []
        if self.perception_quality is None:
            self.perception_quality = {}


@dataclass
class ReplanResult:
    """Output of the replanner."""

    revised_steps: List[TaskStep]
    strategy: str  # Name of the repair strategy used
    reasoning: str  # Why this approach was chosen
    confidence: float = 0.5
    from_memory: bool = False  # Was this from procedural memory?


class Replanner:
    """LLM-powered plan revision engine.

    Uses procedural memory first (proven strategies), then LLM reasoning
    when memory doesn't have a match.

    Usage:
        replanner = Replanner(memory=procedural_memory, model_router=router)

        context = ReplanContext(
            failed_step=step,
            failure_reason="Element not found",
            world_state_summary=world_state.to_summary(),
        )
        result = replanner.replan(context)
        # Execute result.revised_steps
    """

    def __init__(
        self,
        memory: Optional[ProceduralMemory] = None,
        model_router=None,
    ) -> None:
        self._memory = memory
        self._router = model_router

    def replan(self, context: ReplanContext) -> ReplanResult:
        """Generate a revised plan for a failed step.

        Strategy priority:
        1. Procedural memory (instant, proven)
        2. Pattern-based heuristics (common failures)
        3. LLM reasoning (expensive, flexible)
        """
        # 1. Check procedural memory
        if self._memory:
            memory_result = self._try_memory_strategy(context)
            if memory_result:
                return memory_result

        # 2. Pattern-based heuristics
        heuristic_result = self._try_heuristic(context)
        if heuristic_result:
            return heuristic_result

        # 3. LLM reasoning (would be async in production)
        # For now, use heuristic fallback since LLM call is async
        return self._default_repair(context)

    async def replan_with_llm(self, context: ReplanContext) -> ReplanResult:
        """Generate a revised plan using LLM reasoning (async).

        Only used for Level 3 complex goals where pattern-matching fails.
        """
        if not self._router:
            return self._default_repair(context)

        try:
            from friday.models.router import ModelCapability

            prompt = self._build_replan_prompt(context)
            response = await self._router.complete(
                prompt,
                capability=ModelCapability.REASONING,
                max_tokens=300,
                temperature=0.3,
                system_prompt=(
                    "You are a task planning assistant. When an action fails, "
                    "suggest alternative steps to achieve the same goal. "
                    "Respond in JSON format with a list of steps."
                ),
            )

            revised = self._parse_llm_response(response.text, context)
            if revised:
                return revised

        except Exception:
            pass

        return self._default_repair(context)

    def _try_memory_strategy(self, context: ReplanContext) -> Optional[ReplanResult]:
        """Try to find a proven repair from procedural memory."""
        failure_type = self._classify_failure(context.failure_reason)

        repair = self._memory.suggest_repair(
            failure_type, context.failed_step.action_type
        )
        if repair:
            steps = self._repair_to_steps(repair, context)
            return ReplanResult(
                revised_steps=steps,
                strategy=repair,
                reasoning=f"Procedural memory: '{repair}' worked for '{failure_type}' before",
                confidence=0.8,
                from_memory=True,
            )
        return None

    def _try_heuristic(self, context: ReplanContext) -> Optional[ReplanResult]:
        """Pattern-match common failures to known repairs."""
        reason = context.failure_reason.lower()
        step = context.failed_step

        # Element not found → scroll or wait
        if "not found" in reason or "no element" in reason:
            if "scroll" not in (context.previous_repairs or []):
                return ReplanResult(
                    revised_steps=[
                        TaskStep(
                            action_type="scroll",
                            target="down",
                            description="Scroll down to find element",
                            expected_postcondition=f"'{step.target}' becomes visible",
                        ),
                        TaskStep(
                            action_type=step.action_type,
                            target=step.target,
                            description=f"Retry: {step.description}",
                            parameters=step.parameters,
                        ),
                    ],
                    strategy="scroll_and_retry",
                    reasoning="Element not visible — scrolling to reveal it",
                    confidence=0.6,
                )

        # Navigation failed → check browser is open
        if "navigation" in reason or ("url" in reason and "unchanged" not in reason):
            return ReplanResult(
                revised_steps=[
                    TaskStep(
                        action_type="open_app",
                        target="chrome",
                        description="Ensure browser is open",
                    ),
                    TaskStep(
                        action_type=step.action_type,
                        target=step.target,
                        description=f"Retry navigation: {step.description}",
                        parameters=step.parameters,
                    ),
                ],
                strategy="ensure_browser_and_retry",
                reasoning="Navigation failed — ensuring browser is open first",
                confidence=0.6,
            )

        # State unchanged → retry with focus
        if "unchanged" in reason or "unverified" in reason:
            return ReplanResult(
                revised_steps=[
                    TaskStep(
                        action_type="focus",
                        target=step.target,
                        description="Focus the target element first",
                    ),
                    TaskStep(
                        action_type=step.action_type,
                        target=step.target,
                        description=f"Retry after focus: {step.description}",
                        parameters=step.parameters,
                    ),
                ],
                strategy="focus_and_retry",
                reasoning="State unchanged — focusing target before retry",
                confidence=0.5,
            )

        # Dialog blocking → dismiss
        if "blocked" in reason or "dialog" in reason or "modal" in reason:
            return ReplanResult(
                revised_steps=[
                    TaskStep(
                        action_type="dismiss_dialog",
                        target="modal",
                        description="Dismiss blocking dialog",
                    ),
                    TaskStep(
                        action_type=step.action_type,
                        target=step.target,
                        description=f"Retry after dismissal: {step.description}",
                        parameters=step.parameters,
                    ),
                ],
                strategy="dismiss_and_retry",
                reasoning="Dialog blocking the action — dismissing first",
                confidence=0.6,
            )

        return None

    def _default_repair(self, context: ReplanContext) -> ReplanResult:
        """Default: simple retry of the failed step."""
        return ReplanResult(
            revised_steps=[
                TaskStep(
                    action_type=context.failed_step.action_type,
                    target=context.failed_step.target,
                    description=f"Retry: {context.failed_step.description}",
                    parameters=context.failed_step.parameters,
                ),
            ],
            strategy="simple_retry",
            reasoning="No specific repair known — retrying the step",
            confidence=0.3,
        )

    def _classify_failure(self, reason: str) -> str:
        """Classify a failure reason into a category."""
        reason_lower = reason.lower()
        if "not found" in reason_lower:
            return "element_not_found"
        if "timeout" in reason_lower:
            return "timeout"
        if "blocked" in reason_lower or "dialog" in reason_lower:
            return "dialog_blocking"
        if "unchanged" in reason_lower:
            return "state_unchanged"
        if "focus" in reason_lower:
            return "focus_lost"
        if "navigation" in reason_lower or "url" in reason_lower:
            return "navigation_failed"
        return "unknown"

    def _repair_to_steps(self, repair_name: str, context: ReplanContext) -> List[TaskStep]:
        """Convert a named repair strategy to concrete steps."""
        step = context.failed_step
        if repair_name == "scroll_down":
            return [
                TaskStep(action_type="scroll", target="down", description="Scroll down"),
                TaskStep(action_type=step.action_type, target=step.target, description=f"Retry: {step.description}"),
            ]
        if repair_name == "dismiss_dialog":
            return [
                TaskStep(action_type="dismiss_dialog", target="dialog", description="Dismiss dialog"),
                TaskStep(action_type=step.action_type, target=step.target, description=f"Retry: {step.description}"),
            ]
        # Default
        return [
            TaskStep(action_type=step.action_type, target=step.target, description=f"Retry ({repair_name})"),
        ]

    def _build_replan_prompt(self, context: ReplanContext) -> str:
        """Build a prompt for LLM-based replanning."""
        ws = context.world_state_summary
        return (
            f"A task step failed and needs replanning.\n\n"
            f"Failed step: {context.failed_step.action_type} on '{context.failed_step.target}'\n"
            f"Failure reason: {context.failure_reason}\n"
            f"Current window: {ws.get('window', 'unknown')}\n"
            f"Browser URL: {ws.get('browser_url', 'none')}\n"
            f"Previous repairs tried: {context.previous_repairs}\n"
            f"Attempt number: {context.attempt_number}\n\n"
            f"Suggest 1-3 alternative steps to achieve the original goal. "
            f"Respond with a JSON array of objects with 'action_type', 'target', 'description'."
        )

    def _parse_llm_response(self, text: str, context: ReplanContext) -> Optional[ReplanResult]:
        """Parse LLM response into ReplanResult."""
        try:
            # Try to extract JSON array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                steps = [
                    TaskStep(
                        action_type=item.get("action_type", "generic"),
                        target=item.get("target", ""),
                        description=item.get("description", ""),
                    )
                    for item in data
                    if isinstance(item, dict)
                ]
                if steps:
                    return ReplanResult(
                        revised_steps=steps,
                        strategy="llm_reasoning",
                        reasoning="Generated by LLM reasoning model",
                        confidence=0.6,
                    )
        except (json.JSONDecodeError, ValueError):
            pass
        return None
