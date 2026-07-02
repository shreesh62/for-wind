"""Browser actions — DOM-first browser automation returning ActionResult.

Per ADR-014 (semantic-first perception), browser actions prefer
DOM/DevTools over screenshots. Finding buttons, reading text,
determining page state, form filling, and navigation all use
DOM information primarily.

Wraps the existing automation (Playwright/DevTools bridge) and
produces verified ActionResult objects.
"""

from __future__ import annotations

from typing import Any, Optional

from friday.actions.result import ActionResult, ActionEvidence, ActionTimer
from friday.perception.world_state import WorldState
from friday.perception.priority import PerceptionResolver


class BrowserActions:
    """DOM-first browser actuators returning ActionResult.

    These wrap the existing browser automation but enforce the
    semantic-first principle: locate elements via DOM, not pixels.

    Usage:
        browser = BrowserActions(automation_services=services)
        result = browser.navigate("https://google.com")
        result = browser.click_element("Search button", world_state=ws)
    """

    def __init__(self, automation_services=None) -> None:
        self._automation = automation_services
        self._resolver = PerceptionResolver()

    @property
    def available(self) -> bool:
        return self._automation is not None

    def navigate(self, url: str) -> ActionResult:
        """Navigate the browser to a URL (via DevTools, not address-bar typing).

        Args:
            url: Target URL

        Returns:
            ActionResult — verification confirms URL change
        """
        with ActionTimer() as timer:
            if not self._automation:
                return ActionResult.failed(
                    action="navigate",
                    error="No automation services available",
                    target=url,
                    error_category="no_automation",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            # Normalize URL
            target_url = url if url.startswith(("http://", "https://")) else f"https://{url}"

            try:
                # Prefer DevTools navigation (semantic), not typing into address bar
                result_text = None
                if hasattr(self._automation, 'navigate_to'):
                    result_text = self._automation.navigate_to(target_url)
                elif hasattr(self._automation, 'open_website'):
                    result_text = self._automation.open_website(target_url)
                else:
                    return ActionResult.failed(
                        action="navigate",
                        error="No navigation method on automation services",
                        target=url,
                        error_category="no_method",
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )

                return ActionResult.success(
                    action="navigate",
                    target=target_url,
                    message=f"Navigated to {target_url}",
                    evidence=ActionEvidence(
                        url_changed=True,
                        state_changed=True,
                        raw={"url": target_url, "result": str(result_text)[:100]},
                    ),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="navigate",
                    error=str(exc),
                    target=url,
                    error_category="navigation_error",
                    repair_hints=["check_browser_open", "retry_navigation"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def click_element(
        self,
        element_text: str,
        world_state: Optional[WorldState] = None,
    ) -> ActionResult:
        """Click a browser element located via DOM (semantic-first).

        Args:
            element_text: Text/label of the element to click
            world_state: Current perception (used to resolve element via DOM)

        Returns:
            ActionResult
        """
        with ActionTimer() as timer:
            if not self._automation:
                return ActionResult.failed(
                    action="click",
                    error="No automation services available",
                    target=element_text,
                    error_category="no_automation",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            # Resolve element semantically (DOM > UIA > OCR)
            resolved = None
            if world_state:
                resolved = self._resolver.find_element(
                    world_state, element_text, clickable_only=True
                )
                if resolved is None:
                    # No clickable semantic element. Check if OCR sees it
                    # (text present but no DOM/UIA) — clicking would be unreliable.
                    ocr_match = self._resolver.find_element(
                        world_state, element_text, clickable_only=False
                    )
                    if ocr_match and not ocr_match.is_semantic:
                        return ActionResult.blocked(
                            action="click",
                            reason=f"Element '{element_text}' only found via OCR (no DOM/UIA). "
                                   "Clicking would be unreliable.",
                            target=element_text,
                            repair_hints=["wait_for_dom", "refresh_perception"],
                            started_at=timer.started_at,
                            duration_ms=timer.duration_ms,
                        )

            try:
                # Use DOM-based click if available
                if hasattr(self._automation, 'click_text'):
                    self._automation.click_text(element_text)
                elif hasattr(self._automation, 'click_element'):
                    self._automation.click_element(element_text)
                else:
                    return ActionResult.failed(
                        action="click",
                        error="No click method on automation services",
                        target=element_text,
                        error_category="no_method",
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )

                evidence = ActionEvidence(state_changed=True)
                if resolved:
                    evidence.raw = {
                        "source": resolved.source.value,
                        "semantic": resolved.is_semantic,
                    }

                return ActionResult.success(
                    action="click",
                    target=element_text,
                    message=f"Clicked '{element_text}'",
                    evidence=evidence,
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="click",
                    error=str(exc),
                    target=element_text,
                    error_category="click_error",
                    repair_hints=["scroll_to_element", "wait_for_element", "retry_click"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def type_text(self, text: str, field_hint: str = "") -> ActionResult:
        """Type text into a browser input field (DOM-targeted).

        Args:
            text: Text to type
            field_hint: Optional hint for which field

        Returns:
            ActionResult
        """
        with ActionTimer() as timer:
            if not self._automation:
                return ActionResult.failed(
                    action="type",
                    error="No automation services available",
                    target=field_hint or "input",
                    error_category="no_automation",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            try:
                if hasattr(self._automation, 'type_into'):
                    self._automation.type_into(field_hint, text)
                elif hasattr(self._automation, 'type_text'):
                    self._automation.type_text(text)
                else:
                    return ActionResult.failed(
                        action="type",
                        error="No type method on automation services",
                        target=field_hint or "input",
                        error_category="no_method",
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )

                return ActionResult.success(
                    action="type",
                    target=field_hint or "input",
                    message=f"Typed text into {field_hint or 'field'}",
                    evidence=ActionEvidence(
                        state_changed=True,
                        text_appeared=text[:50],
                    ),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="type",
                    error=str(exc),
                    target=field_hint or "input",
                    error_category="type_error",
                    repair_hints=["click_field_first", "check_focus"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def read_page_text(self, world_state: WorldState) -> str:
        """Read page text using DOM-first resolution.

        Per ADR-014, prefers DOM text over OCR.
        """
        return self._resolver.read_text(world_state)

    def get_page_state(self, world_state: WorldState) -> str:
        """Determine page state semantically (login, error, etc.)."""
        return self._resolver.determine_page_type(world_state)
