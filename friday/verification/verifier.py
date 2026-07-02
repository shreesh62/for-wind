"""Verifier — confirms action outcomes against perception.

Every action must be verified. The verifier takes:
- The action that was performed (type + target)
- WorldState before the action
- WorldState after the action
- Expected postconditions

And produces a verification verdict: VERIFIED, UNVERIFIED, or FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult, ActionStatus
from friday.perception.world_state import WorldState
from friday.verification.evidence import collect_evidence


class VerificationVerdict(str, Enum):
    """Result of verification."""

    VERIFIED = "verified"        # Action succeeded and evidence confirms it
    UNVERIFIED = "unverified"    # Action may have succeeded but no evidence
    FAILED = "failed"            # Evidence shows action did not achieve goal
    INCONCLUSIVE = "inconclusive"  # Cannot determine (perception unavailable)


@dataclass
class VerificationResult:
    """Detailed verification outcome."""

    verdict: VerificationVerdict
    evidence: ActionEvidence
    reason: str = ""
    confidence: float = 0.0  # 0-1 confidence in verdict
    repair_hints: List[str] = None

    def __post_init__(self):
        if self.repair_hints is None:
            self.repair_hints = []


class ActionVerifier:
    """Verifies action outcomes by comparing before/after WorldState.

    Registers verification strategies per action type.
    Falls back to generic hash-based verification when no
    specific strategy exists.

    Usage:
        verifier = ActionVerifier()
        result = verifier.verify(
            action_type="click",
            target="Submit button",
            before=world_state_before,
            after=world_state_after,
        )
        if result.verdict == VerificationVerdict.VERIFIED:
            # Action confirmed successful
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, Callable] = {
            "click": self._verify_click,
            "type": self._verify_type,
            "navigate": self._verify_navigate,
            "open_url": self._verify_navigate,
            "scroll": self._verify_scroll,
            "focus": self._verify_focus,
            "dismiss_dialog": self._verify_dismiss,
            "login": self._verify_login,
        }

    def register_strategy(
        self, action_type: str, strategy: Callable
    ) -> None:
        """Register a custom verification strategy for an action type."""
        self._strategies[action_type] = strategy

    def verify(
        self,
        action_type: str,
        target: str,
        before: WorldState,
        after: WorldState,
        expected: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify an action outcome.

        Args:
            action_type: Type of action performed (click, type, navigate, etc.)
            target: What the action was targeting
            before: WorldState before action
            after: WorldState after action
            expected: Optional expected postconditions

        Returns:
            VerificationResult with verdict and evidence
        """
        evidence = collect_evidence(before, after)

        # Use specific strategy if available
        strategy = self._strategies.get(action_type.lower())
        if strategy:
            return strategy(target, before, after, evidence, expected)

        # Fall back to generic verification
        return self._verify_generic(target, before, after, evidence, expected)

    def verify_action_result(
        self,
        result: ActionResult,
        before: WorldState,
        after: WorldState,
    ) -> ActionResult:
        """Enhance an ActionResult with verification evidence.

        Takes an existing ActionResult and upgrades it with
        before/after evidence. Returns a new ActionResult with
        the evidence attached.
        """
        evidence = collect_evidence(before, after)

        verification = self.verify(
            action_type=result.action_type,
            target=result.target,
            before=before,
            after=after,
        )

        # Update the result with verification data
        result.evidence = evidence
        if verification.verdict == VerificationVerdict.VERIFIED:
            result.status = ActionStatus.SUCCESS
        elif verification.verdict in (VerificationVerdict.FAILED, VerificationVerdict.UNVERIFIED):
            if result.status == ActionStatus.SUCCESS:
                result.status = ActionStatus.NEEDS_REPAIR
                result.error = verification.reason
                result.repair_hints = verification.repair_hints

        return result

    # --- Specific Verification Strategies ---

    def _verify_click(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a click action succeeded."""
        # A successful click should change something
        if evidence.state_changed:
            # Check if we see expected changes
            if evidence.url_changed or evidence.window_changed or evidence.focus_changed:
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason="Click produced observable state change",
                    confidence=0.85,
                )

            if evidence.text_appeared:
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason=f"New text appeared: {evidence.text_appeared[:50]}",
                    confidence=0.8,
                )

            # Hash changed but no specific signal — likely worked
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="State hash changed after click",
                confidence=0.6,
            )

        # No state change after click — suspicious
        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No observable state change after click",
            confidence=0.3,
            repair_hints=["retry_click", "check_element_exists", "scroll_to_element"],
        )

    def _verify_type(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a type/input action succeeded."""
        # Check if the typed text appears in the after state
        typed_text = (expected or {}).get("typed_text", "")

        if typed_text and after.contains_text(typed_text):
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason=f"Typed text '{typed_text[:30]}' found in state",
                confidence=0.9,
            )

        # Check for focus change (input field was focused)
        if evidence.focus_changed and evidence.state_changed:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="Focus changed and state updated after typing",
                confidence=0.7,
            )

        if evidence.state_changed:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="State changed after typing",
                confidence=0.6,
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No evidence that text was entered",
            confidence=0.2,
            repair_hints=["check_focus", "click_input_first", "retype"],
        )

    def _verify_navigate(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a navigation action succeeded."""
        target_url = (expected or {}).get("url", target)

        # Best case: URL changed to expected target
        if evidence.url_changed and after.browser_url:
            if target_url and target_url.lower() in after.browser_url.lower():
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason=f"URL changed to target: {after.browser_url}",
                    confidence=0.95,
                )
            # URL changed but not to expected — might be redirect
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason=f"URL changed to: {after.browser_url}",
                confidence=0.7,
            )

        # Window changed (maybe opened new browser)
        if evidence.window_changed:
            after_title = after.active_window.title if after.active_window else ""
            if "chrome" in after_title.lower() or "firefox" in after_title.lower() or "edge" in after_title.lower():
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason="Browser window now active",
                    confidence=0.6,
                )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No URL or window change detected after navigation",
            confidence=0.2,
            repair_hints=["check_browser_open", "retry_navigation", "wait_for_load"],
        )

    def _verify_scroll(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a scroll action succeeded."""
        # Scrolling should change the visible content
        if evidence.screenshot_changed or evidence.state_changed:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="Screen content changed after scroll",
                confidence=0.7,
            )

        # If target text is now visible, scroll worked
        if target and after.contains_text(target) and not before.contains_text(target):
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason=f"Target text '{target[:30]}' now visible after scroll",
                confidence=0.9,
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No visible content change after scroll",
            confidence=0.4,
            repair_hints=["scroll_more", "check_scrollable"],
        )

    def _verify_focus(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a focus/window-switch action succeeded."""
        if evidence.window_changed:
            after_title = after.active_window.title if after.active_window else ""
            if target and target.lower() in after_title.lower():
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason=f"Window focused: {after_title}",
                    confidence=0.95,
                )
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason=f"Window changed to: {after_title}",
                confidence=0.7,
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No window change detected after focus attempt",
            confidence=0.2,
            repair_hints=["retry_focus", "find_window", "alt_tab"],
        )

    def _verify_dismiss(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a dialog dismissal succeeded."""
        # Dialog should no longer show error/consent keywords
        if before.derived.possible_error_dialog and not after.derived.possible_error_dialog:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="Error dialog no longer detected",
                confidence=0.85,
            )

        if before.derived.possible_consent_dialog and not after.derived.possible_consent_dialog:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="Consent dialog no longer detected",
                confidence=0.85,
            )

        if evidence.state_changed and evidence.text_disappeared:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason=f"Dialog text disappeared: {evidence.text_disappeared[:40]}",
                confidence=0.75,
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="Dialog may still be present",
            confidence=0.3,
            repair_hints=["press_escape", "click_away", "find_close_button"],
        )

    def _verify_login(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Verify a login action succeeded."""
        # Login screen should disappear
        if before.derived.possible_login_screen and not after.derived.possible_login_screen:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="Login screen no longer detected",
                confidence=0.9,
            )

        # URL changed away from login page
        if evidence.url_changed and before.browser_url and after.browser_url:
            if "login" in before.browser_url.lower() and "login" not in after.browser_url.lower():
                return VerificationResult(
                    verdict=VerificationVerdict.VERIFIED,
                    evidence=evidence,
                    reason="Navigated away from login page",
                    confidence=0.85,
                )

        if after.derived.possible_error_dialog:
            return VerificationResult(
                verdict=VerificationVerdict.FAILED,
                evidence=evidence,
                reason="Error detected after login attempt",
                confidence=0.8,
                repair_hints=["check_credentials", "retry_login", "handle_captcha"],
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="Cannot confirm login success",
            confidence=0.3,
            repair_hints=["wait_for_redirect", "check_page_content"],
        )

    def _verify_generic(
        self,
        target: str,
        before: WorldState,
        after: WorldState,
        evidence: ActionEvidence,
        expected: Optional[Dict] = None,
    ) -> VerificationResult:
        """Generic verification based on state hash change."""
        if evidence.has_evidence:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=evidence,
                reason="State changed after action",
                confidence=0.5,
            )

        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=evidence,
            reason="No observable state change",
            confidence=0.2,
            repair_hints=["retry", "check_preconditions"],
        )
