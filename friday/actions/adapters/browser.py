"""BrowserAdapter — Executes primitives via BrowserController's Playwright session.

Wraps the existing BrowserController (persistent Playwright on a dedicated
event loop) to implement AdapterProtocol. Priority 100 — highest fidelity
source for in-browser interactions.

All async methods are thin wrappers: BrowserController already provides
synchronous methods that internally submit coroutines to its dedicated loop.
The adapter wraps those sync calls in async methods to satisfy the protocol.
"""

from __future__ import annotations

from typing import List, Optional

from friday.actions.adapters.base import AdapterProtocol
from friday.actions.browser_controller import BrowserController
from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BrowserElement, PerceptionSource
from friday.perception.world_state import WorldState


class BrowserAdapter:
    """Environment adapter for browser interactions via BrowserController.

    Priority: 100 (Browser DOM — highest fidelity semantic source).

    Delegates execution to BrowserController which manages a persistent
    Playwright session on a dedicated event loop thread.
    """

    def __init__(self, controller: BrowserController) -> None:
        self._controller = controller

    @property
    def name(self) -> str:
        return "browser"

    @property
    def priority(self) -> int:
        return 100

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        """Return True when browser is connected and target has text, selector, or role."""
        if not world_state.browser_connected:
            return False
        return bool(target.text or target.selector or target.role)

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        """Search world_state.browser_elements for a matching element.

        Match order: selector (exact), text (case-insensitive), role (exact).
        """
        match: Optional[BrowserElement] = None

        # 1. Selector exact match
        if target.selector:
            for elem in world_state.browser_elements:
                if elem.selector == target.selector:
                    match = elem
                    break

        # 2. Text case-insensitive match
        if match is None and target.text:
            target_lower = target.text.lower()
            for elem in world_state.browser_elements:
                if target_lower in elem.text.lower():
                    match = elem
                    break

        # 3. Role exact match
        if match is None and target.role:
            for elem in world_state.browser_elements:
                if elem.role == target.role:
                    match = elem
                    break

        if match is None:
            return None

        bbox_tuple = None
        if match.bbox is not None:
            bbox_tuple = (match.bbox.x, match.bbox.y, match.bbox.width, match.bbox.height)

        return ResolvedElement(
            text=match.text,
            source=PerceptionSource.BROWSER,
            priority=100,
            confidence=0.95,
            clickable=match.clickable,
            bbox=bbox_tuple,
            raw_element=match,
        )

    # ------------------------------------------------------------------
    # Helper: get page URL safely
    # ------------------------------------------------------------------

    def _get_current_url(self) -> str:
        """Get the current page URL, returning empty string on failure."""
        try:
            return self._controller.current_url()
        except Exception:
            return ""

    def _build_evidence(self, before_url: str, after_url: str) -> ActionEvidence:
        """Build ActionEvidence using page URL as before/after hash."""
        return ActionEvidence(
            before_hash=before_url,
            after_hash=after_url,
            state_changed=before_url != after_url,
            url_changed=before_url != after_url,
        )

    # ------------------------------------------------------------------
    # Action methods
    # ------------------------------------------------------------------

    async def click(self, element: ResolvedElement) -> ActionResult:
        """Execute a single click on the resolved element."""
        try:
            before_url = self._get_current_url()
            result = self._controller.click(element.text)
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            if result.get("ok"):
                return ActionResult.success(
                    action="click",
                    target=element.text,
                    message=f"Clicked '{element.text}' in browser",
                    evidence=evidence,
                )
            else:
                return ActionResult.failed(
                    action="click",
                    target=element.text,
                    error=result.get("error", "Click failed"),
                    error_category="adapter_failed",
                    repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
                    evidence=evidence,
                )
        except Exception as exc:
            return ActionResult.failed(
                action="click",
                target=element.text,
                error=str(exc),
                error_category="browser_unavailable",
                repair_hints=["retry", "check_browser_connection", "try_alternative_adapter"],
            )

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a double click via Playwright dblclick."""
        try:
            before_url = self._get_current_url()

            async def _dblclick():
                locator = self._controller._page.get_by_text(element.text, exact=False).first
                await locator.dblclick(timeout=10000)
                await self._controller._page.wait_for_timeout(800)

            self._controller._submit(_dblclick())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            return ActionResult.success(
                action="double_click",
                target=element.text,
                message=f"Double-clicked '{element.text}' in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="double_click",
                target=element.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
            )

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a right click (context menu) via Playwright."""
        try:
            before_url = self._get_current_url()

            async def _right_click():
                locator = self._controller._page.get_by_text(element.text, exact=False).first
                await locator.click(button="right", timeout=10000)
                await self._controller._page.wait_for_timeout(800)

            self._controller._submit(_right_click())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            return ActionResult.success(
                action="right_click",
                target=element.text,
                message=f"Right-clicked '{element.text}' in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="right_click",
                target=element.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
            )

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        """Type text into a field. Delegates to BrowserController.type_text."""
        try:
            before_url = self._get_current_url()
            selector = None
            target_name = "focused element"

            if element and element.raw_element:
                raw: BrowserElement = element.raw_element
                if raw.selector:
                    selector = raw.selector
                target_name = element.text or selector or "focused element"

            result = self._controller.type_text(text, selector)
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            if result.get("ok"):
                return ActionResult.success(
                    action="type_text",
                    target=target_name,
                    message=f"Typed text into '{target_name}' in browser",
                    evidence=evidence,
                )
            else:
                return ActionResult.failed(
                    action="type_text",
                    target=target_name,
                    error=result.get("error", "Type failed"),
                    error_category="adapter_failed",
                    repair_hints=["retry", "click_target_first", "focus_input"],
                    evidence=evidence,
                )
        except Exception as exc:
            return ActionResult.failed(
                action="type_text",
                target=text[:50],
                error=str(exc),
                error_category="browser_unavailable",
                repair_hints=["retry", "check_browser_connection", "try_alternative_adapter"],
            )

    async def press_key(self, key: str) -> ActionResult:
        """Press a single key via Playwright keyboard.press()."""
        try:
            before_url = self._get_current_url()

            async def _press():
                await self._controller._page.keyboard.press(key)

            self._controller._submit(_press())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            return ActionResult.success(
                action="press_key",
                target=key,
                message=f"Pressed key '{key}' in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_key",
                target=key,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "check_browser_connection"],
            )

    async def press_hotkey(self, keys: List[str]) -> ActionResult:
        """Press a key combination via Playwright keyboard.press() with '+' joined keys."""
        try:
            before_url = self._get_current_url()
            combo = "+".join(keys)

            async def _hotkey():
                await self._controller._page.keyboard.press(combo)

            self._controller._submit(_hotkey())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)

            return ActionResult.success(
                action="press_hotkey",
                target=combo,
                message=f"Pressed hotkey '{combo}' in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_hotkey",
                target="+".join(keys),
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "check_browser_connection"],
            )

    async def scroll(
        self,
        direction: str,
        amount: int,
        element: Optional[ResolvedElement] = None,
    ) -> ActionResult:
        """Scroll using page.mouse.wheel() via _submit()."""
        try:
            before_url = self._get_current_url()

            # Convert direction to delta_x, delta_y
            delta_x = 0
            delta_y = 0
            if direction in ("down", "d"):
                delta_y = amount * 100
            elif direction in ("up", "u"):
                delta_y = -(amount * 100)
            elif direction in ("right", "r"):
                delta_x = amount * 100
            elif direction in ("left", "l"):
                delta_x = -(amount * 100)

            async def _scroll():
                await self._controller._page.mouse.wheel(delta_x, delta_y)
                await self._controller._page.wait_for_timeout(300)

            self._controller._submit(_scroll())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)
            # Scrolling always changes state even if URL doesn't change
            evidence.state_changed = True

            return ActionResult.success(
                action="scroll",
                target=f"{direction} x{amount}",
                message=f"Scrolled {direction} by {amount} in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="scroll",
                target=f"{direction} x{amount}",
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "check_browser_connection"],
            )

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        """Drag from source element to destination element using Playwright."""
        try:
            before_url = self._get_current_url()

            # Get bounding box centers for source and destination
            src_x, src_y = self._get_element_center(source)
            dst_x, dst_y = self._get_element_center(dest)

            async def _drag():
                page = self._controller._page
                await page.mouse.move(src_x, src_y)
                await page.mouse.down()
                await page.mouse.move(dst_x, dst_y, steps=10)
                await page.mouse.up()
                await page.wait_for_timeout(500)

            self._controller._submit(_drag())
            after_url = self._get_current_url()
            evidence = self._build_evidence(before_url, after_url)
            evidence.state_changed = True

            return ActionResult.success(
                action="drag",
                target=f"{source.text} -> {dest.text}",
                message=f"Dragged '{source.text}' to '{dest.text}' in browser",
                evidence=evidence,
            )
        except Exception as exc:
            return ActionResult.failed(
                action="drag",
                target=f"{source.text} -> {dest.text}",
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
            )

    async def focus_window(self, target: Target) -> ActionResult:
        """Browser adapter cannot switch OS windows — always returns failed."""
        return ActionResult.failed(
            action="focus_window",
            target=target.window_title or target.text,
            error="Browser adapter cannot switch OS windows",
            error_category="adapter_failed",
            repair_hints=["try_alternative_adapter", "use_desktop_adapter"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_element_center(self, element: ResolvedElement) -> tuple:
        """Extract center coordinates from a resolved element's bbox."""
        if element.bbox:
            x, y, w, h = element.bbox
            return (x + w // 2, y + h // 2)
        # Fallback: use page center if no bbox available
        return (960, 540)
