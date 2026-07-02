"""DesktopAdapter — Windows UIA-based desktop interaction adapter.

Executes primitives against Windows desktop applications using element
coordinates from Windows UI Automation, dispatching actions through
pyautogui. Priority 80 (SourcePriority.UIA).

All async methods use `asyncio.to_thread()` to run blocking pyautogui
calls off the event loop.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pyautogui

from friday.actions.adapters.base import AdapterProtocol
from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BoundingBox, PerceptionSource, UIElement
from friday.perception.world_state import WorldState


class DesktopAdapter:
    """Adapter for Windows desktop interaction via UIA element coordinates.

    Uses pyautogui to perform mouse/keyboard actions at coordinates
    resolved from UIElement bounding boxes in the WorldState.
    """

    @property
    def name(self) -> str:
        return "desktop"

    @property
    def priority(self) -> int:
        return 80

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        """Return True when world_state.ui_elements contains a match for target."""
        return self._find_matching_element(target, world_state) is not None

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        """Search world_state.ui_elements for a match and return ResolvedElement."""
        element = self._find_matching_element(target, world_state)
        if element is None:
            return None

        bbox = element.bbox
        return ResolvedElement(
            text=element.text,
            source=PerceptionSource.UIA,
            priority=80,
            confidence=element.confidence,
            clickable=element.control_type.lower() in (
                "button", "hyperlink", "link", "menuitem", "tabitem",
                "listitem", "checkbox", "radiobutton", "splitbutton",
            ),
            bbox=(bbox.x, bbox.y, bbox.width, bbox.height),
            raw_element=element,
        )

    async def click(self, element: ResolvedElement) -> ActionResult:
        """Execute a single click at the resolved element's center."""
        try:
            ui_elem: UIElement = element.raw_element
            x, y = ui_elem.bbox.center
            await asyncio.to_thread(pyautogui.click, x, y)
            return ActionResult.success(
                action="click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="click",
                error=str(exc),
                target=element.text,
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a double click at the resolved element's center."""
        try:
            ui_elem: UIElement = element.raw_element
            x, y = ui_elem.bbox.center
            await asyncio.to_thread(pyautogui.doubleClick, x, y)
            return ActionResult.success(
                action="double_click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="double_click",
                error=str(exc),
                target=element.text,
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a right click at the resolved element's center."""
        try:
            ui_elem: UIElement = element.raw_element
            x, y = ui_elem.bbox.center
            await asyncio.to_thread(pyautogui.rightClick, x, y)
            return ActionResult.success(
                action="right_click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="right_click",
                error=str(exc),
                target=element.text,
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        """Type text using pyautogui. Handles Unicode via pyperclip + Ctrl+V."""
        try:
            # Check if text is pure ASCII
            if all(ord(c) < 128 for c in text):
                await asyncio.to_thread(pyautogui.write, text, interval=0.02)
            else:
                # Unicode: use clipboard paste
                import pyperclip
                await asyncio.to_thread(pyperclip.copy, text)
                await asyncio.to_thread(pyautogui.hotkey, "ctrl", "v")

            target_text = element.text if element else "focused_element"
            return ActionResult.success(
                action="type_text",
                target=target_text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            target_text = element.text if element else "focused_element"
            return ActionResult.failed(
                action="type_text",
                error=str(exc),
                target=target_text,
                error_category="adapter_failed",
                repair_hints=["retry", "click_target_first", "focus_input"],
            )

    async def press_key(self, key: str) -> ActionResult:
        """Press a single key."""
        try:
            await asyncio.to_thread(pyautogui.press, key)
            return ActionResult.success(
                action="press_key",
                target=key,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_key",
                error=str(exc),
                target=key,
                error_category="adapter_failed",
                repair_hints=["retry", "check_key_name"],
            )

    async def press_hotkey(self, keys: List[str]) -> ActionResult:
        """Press a key combination."""
        try:
            await asyncio.to_thread(pyautogui.hotkey, *keys)
            return ActionResult.success(
                action="press_hotkey",
                target="+".join(keys),
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_hotkey",
                error=str(exc),
                target="+".join(keys),
                error_category="adapter_failed",
                repair_hints=["retry", "check_key_names"],
            )

    async def scroll(
        self,
        direction: str,
        amount: int,
        element: Optional[ResolvedElement] = None,
    ) -> ActionResult:
        """Scroll at element center or screen center.

        Positive amount scrolls up, negative scrolls down.
        Direction 'down' negates the amount.
        """
        try:
            # Determine scroll position
            if element and element.raw_element:
                ui_elem: UIElement = element.raw_element
                x, y = ui_elem.bbox.center
            else:
                # Screen center fallback
                screen_w, screen_h = pyautogui.size()
                x, y = screen_w // 2, screen_h // 2

            # Negate for down direction
            scroll_amount = -amount if direction.lower() == "down" else amount
            await asyncio.to_thread(pyautogui.scroll, scroll_amount, x=x, y=y)

            target_text = element.text if element else "screen_center"
            return ActionResult.success(
                action="scroll",
                target=target_text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            target_text = element.text if element else "screen_center"
            return ActionResult.failed(
                action="scroll",
                error=str(exc),
                target=target_text,
                error_category="adapter_failed",
                repair_hints=["retry"],
            )

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        """Drag from source element to destination element."""
        try:
            src_elem: UIElement = source.raw_element
            dst_elem: UIElement = dest.raw_element
            src_x, src_y = src_elem.bbox.center
            dst_x, dst_y = dst_elem.bbox.center

            dx = dst_x - src_x
            dy = dst_y - src_y

            await asyncio.to_thread(pyautogui.moveTo, src_x, src_y)
            await asyncio.to_thread(pyautogui.drag, dx, dy, duration=0.5)

            return ActionResult.success(
                action="drag",
                target=f"{source.text} -> {dest.text}",
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="drag",
                error=str(exc),
                target=f"{source.text} -> {dest.text}",
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def focus_window(self, target: Target) -> ActionResult:
        """Bring a window matching target.window_title to the foreground."""
        try:
            windows = await asyncio.to_thread(
                pyautogui.getWindowsWithTitle, target.window_title
            )
            if not windows:
                return ActionResult.failed(
                    action="focus_window",
                    error=f"No window matching '{target.window_title}'",
                    target=target.window_title,
                    error_category="window_not_found",
                    repair_hints=["launch_application", "check_window_title", "list_windows"],
                )

            window = windows[0]
            if window.isMinimized:
                await asyncio.to_thread(window.restore)
            await asyncio.to_thread(window.activate)

            return ActionResult.success(
                action="focus_window",
                target=target.window_title,
                message=f"Focused window: {window.title}",
                evidence=ActionEvidence(
                    state_changed=True,
                    window_changed=True,
                    raw={"window_title": window.title},
                ),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="focus_window",
                error=str(exc),
                target=target.window_title,
                error_category="adapter_failed",
                repair_hints=["retry", "launch_application", "check_window_title"],
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_matching_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[UIElement]:
        """Search world_state.ui_elements for a match by text, role, or automation_id."""
        matches: List[UIElement] = []

        for elem in world_state.ui_elements:
            if self._element_matches(elem, target):
                matches.append(elem)

        if not matches:
            return None

        # Apply index disambiguation
        if target.index < len(matches):
            return matches[target.index]
        return matches[0]

    def _element_matches(self, elem: UIElement, target: Target) -> bool:
        """Check if a UIElement matches the target criteria."""
        # Match by text (case-insensitive substring)
        if target.text and target.text.lower() in elem.text.lower():
            # If role is also specified, both must match
            if target.role:
                return elem.control_type.lower() == target.role.lower()
            return True

        # Match by role (control_type) alone
        if target.role and not target.text:
            if elem.control_type.lower() == target.role.lower():
                return True

        # Match by automation_id
        if target.automation_id and elem.automation_id:
            if target.automation_id.lower() == elem.automation_id.lower():
                return True

        return False
