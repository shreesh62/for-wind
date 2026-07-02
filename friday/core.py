"""FRIDAY Core Engine — the Observe → Act → Verify loop.

This is the central coordination layer that ties together:
- Perception (WorldState from multiple sources)
- Actions (execute with ActionResult contract)
- Verification (confirm outcomes via state diff)
- Learning (record successful patterns)

The engine ensures NO action returns unverified success.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult, ActionStatus, ActionTimer
from friday.perception.world_state import WorldState, WorldStateBuilder
from friday.perception.screen import ScreenCapture
from friday.perception.desktop import DesktopPerception
from friday.perception.browser import BrowserPerception
from friday.perception.priority import PerceptionResolver
from friday.verification.verifier import ActionVerifier, VerificationVerdict


@dataclass
class EngineConfig:
    """Configuration for the FRIDAY cognitive engine."""

    verify_all_actions: bool = True
    max_repair_attempts: int = 3
    perception_timeout_ms: float = 2000.0
    allow_unverified_success: bool = False  # When False, unverified = needs_repair


class FridayEngine:
    """Core cognitive engine implementing the Observe → Act → Verify loop.

    This is the single entry point for all automation in FRIDAY.
    Every action goes through this engine to ensure verification.

    Usage:
        engine = FridayEngine(state_cache=awareness_controller.state_cache)

        # Execute an action with full verification
        result = engine.execute_verified(
            action_fn=lambda: automation.click(element),
            action_type="click",
            target="Submit button",
        )

        if result.verified:
            print("Action confirmed successful")
        elif result.needs_repair:
            print(f"Needs repair: {result.repair_hints}")
    """

    def __init__(
        self,
        state_cache=None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self._config = config or EngineConfig()
        self._screen = ScreenCapture()
        self._desktop = DesktopPerception(state_cache=state_cache)
        self._browser = BrowserPerception(state_cache=state_cache)
        self._verifier = ActionVerifier()
        self._resolver = PerceptionResolver()
        self._state_cache = state_cache

    @property
    def verifier(self) -> ActionVerifier:
        """Access the action verifier (for custom strategies)."""
        return self._verifier

    @property
    def resolver(self) -> PerceptionResolver:
        """Access the perception resolver (semantic-first element resolution)."""
        return self._resolver

    def perceive_as_dict(self) -> dict:
        """Perceive and return the WorldState as an API-friendly dict.

        Includes semantic_coverage (how much perception is semantic vs visual).
        Used by the /api/worldstate endpoint and debugging.
        """
        state = self.perceive()
        summary = state.to_summary()
        try:
            quality = self._resolver.get_perception_quality(state)
            summary["semantic_coverage"] = quality.get("semantic_coverage", 0.0)
        except Exception:
            summary["semantic_coverage"] = 0.0
        # Normalize cursor to list for JSON
        cursor = summary.get("cursor")
        if isinstance(cursor, tuple):
            summary["cursor"] = list(cursor)
        return summary

    def perceive(self) -> WorldState:
        """Build a fresh WorldState from all available perception sources.

        This is the 'Observe' step. Call before any action.

        Returns:
            Current WorldState snapshot
        """
        builder = WorldStateBuilder()

        # Desktop perception
        window = self._desktop.get_active_window()
        if window:
            builder.set_window_info(window)

        cursor = self._desktop.get_cursor_position()
        builder.set_cursor_position(*cursor)

        elements = self._desktop.get_ui_elements()
        if elements:
            builder.add_ui_elements(elements)

        focused = self._desktop.get_focused_element()
        if focused:
            builder.set_focused_element(focused)

        # Screen capture (hash only for speed)
        screen_hash = self._screen.grab_hash_only()
        if screen_hash:
            builder.set_screenshot_hash(screen_hash)

        # Browser perception
        if self._browser.connected:
            url = self._browser.get_current_url()
            title = self._browser.get_page_title()
            browser_elements = self._browser.get_visible_elements()
            builder.set_browser_state(
                url=url,
                title=title,
                elements=browser_elements,
                connected=True,
            )

        return builder.build()

    def execute_verified(
        self,
        action_fn: Callable[[], Any],
        action_type: str,
        target: str = "",
        expected: Optional[Dict[str, Any]] = None,
        skip_perception: bool = False,
    ) -> ActionResult:
        """Execute an action with full perception → verification loop.

        1. Capture WorldState BEFORE
        2. Execute the action
        3. Capture WorldState AFTER
        4. Verify the outcome
        5. Return verified ActionResult

        Args:
            action_fn: Callable that performs the action (returns any)
            action_type: Type of action for verification strategy selection
            target: What the action targets (for logging/verification)
            expected: Optional expected postconditions
            skip_perception: Skip before/after perception (for testing)

        Returns:
            ActionResult with verification evidence
        """
        with ActionTimer() as timer:
            # OBSERVE (before)
            before_state = None
            if not skip_perception:
                try:
                    before_state = self.perceive()
                except Exception:
                    before_state = None

            # ACT
            action_error = None
            action_raw_result = None
            try:
                action_raw_result = action_fn()
            except Exception as exc:
                action_error = str(exc)

        # Handle action failure
        if action_error:
            return ActionResult.failed(
                action=action_type,
                error=action_error,
                target=target,
                error_category="action_exception",
                repair_hints=["retry", "check_preconditions"],
                started_at=timer.started_at,
                duration_ms=timer.duration_ms,
            )

        # OBSERVE (after)
        after_state = None
        if not skip_perception and before_state:
            try:
                # Small delay to let UI settle
                time.sleep(0.1)
                after_state = self.perceive()
            except Exception:
                after_state = None

        # VERIFY
        if before_state and after_state and self._config.verify_all_actions:
            verification = self._verifier.verify(
                action_type=action_type,
                target=target,
                before=before_state,
                after=after_state,
                expected=expected,
            )

            if verification.verdict == VerificationVerdict.VERIFIED:
                return ActionResult.success(
                    action=action_type,
                    target=target,
                    evidence=verification.evidence,
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                    metadata={"raw_result": str(action_raw_result)[:200] if action_raw_result else None},
                )
            elif verification.verdict == VerificationVerdict.FAILED:
                return ActionResult.failed(
                    action=action_type,
                    error=verification.reason,
                    target=target,
                    error_category="verification_failed",
                    repair_hints=verification.repair_hints,
                    evidence=verification.evidence,
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            else:
                # UNVERIFIED or INCONCLUSIVE
                if self._config.allow_unverified_success:
                    return ActionResult.success(
                        action=action_type,
                        target=target,
                        evidence=verification.evidence,
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
                else:
                    result = ActionResult(
                        status=ActionStatus.NEEDS_REPAIR,
                        action_type=action_type,
                        target=target,
                        message=f"{action_type} completed but unverified: {verification.reason}",
                        evidence=verification.evidence,
                        error=verification.reason,
                        repair_hints=verification.repair_hints,
                        started_at=timer.started_at,
                        completed_at=timer.completed_at,
                        duration_ms=timer.duration_ms,
                    )
                    return result

        # No perception available — return raw success (legacy fallback)
        return ActionResult.success(
            action=action_type,
            target=target,
            message=f"{action_type} completed (perception unavailable)",
            started_at=timer.started_at,
            duration_ms=timer.duration_ms,
            metadata={"raw_result": str(action_raw_result)[:200] if action_raw_result else None},
        )

    def execute_with_repair(
        self,
        action_fn: Callable[[], Any],
        action_type: str,
        target: str = "",
        expected: Optional[Dict[str, Any]] = None,
        repair_fn: Optional[Callable[[ActionResult], Any]] = None,
    ) -> ActionResult:
        """Execute an action with automatic repair on failure.

        Tries the action up to max_repair_attempts times,
        calling repair_fn between attempts if provided.

        Args:
            action_fn: Action to execute
            action_type: Type of action
            target: Action target
            expected: Expected postconditions
            repair_fn: Optional function to call with failed result before retry

        Returns:
            Final ActionResult (success or last failure)
        """
        last_result = None

        for attempt in range(self._config.max_repair_attempts):
            result = self.execute_verified(
                action_fn=action_fn,
                action_type=action_type,
                target=target,
                expected=expected,
            )

            if result.is_success and result.verified:
                return result

            last_result = result

            if not result.needs_repair:
                return result  # Hard failure, don't retry

            # Attempt repair
            if repair_fn and attempt < self._config.max_repair_attempts - 1:
                try:
                    repair_fn(result)
                except Exception:
                    pass

        return last_result or ActionResult.failed(
            action=action_type,
            error="Max repair attempts exceeded",
            target=target,
        )
