"""DesktopActionsAdapter — OS-level desktop control via pyautogui.

This adapter sits between DesktopAdapter (UIA, priority 80) and
VisionAdapter (OCR/pixel, priority 30). It handles cases where UIA
elements aren't available but we still need desktop control:

- Browser dialogs (file pickers, permission prompts)
- OS-level hotkeys (Ctrl+S, Alt+Tab, etc.)
- Explicit coordinate-based clicks
- Window management

Priority: 60
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pyautogui

from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import PerceptionSource
from friday.perception.world_state import WorldState


class DesktopActionsAdapter:
    """OS-level desktop interaction adapter.

    Handles keystrokes, pointer moves, and window management when
    UIA elements are not available. Uses pyautogui directly with
    explicit coordinates or OS-level hotkey dispatch.
    """

    @property
    def name(self) -> str:
        return "desktop_actions"

    @property
    def priority(self) -> int:
        return 60

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        """Return True when target has window_title, coordinates, or is OS-level.

        OS-level actions include hotkeys without a specific element target
        (e.g. Ctrl+S, Alt+Tab) — detected when target has no semantic hint
        and no coordinates but has a window_title, or when target only has
        coordinates.
        """
        # Explicit coordinates — we can always click there
        if target.coordinates is not None:
            return True

        # Window management target
        if target.window_title:
            return True

        # OS-level action: target has no semantic hint (text/role/selector/automation_id)
        # This means it's likely a hotkey or generic desktop action
        if not target.has_semantic_hint:
            return True

        return False

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        """Resolve target to a ResolvedElement for desktop actions.

        - If target has coordinates, create element at those coordinates.
        - If target has window_title, find the window and create element.
        - Otherwise return None.
        """
        # Coordinate-based resolution
        if target.coordinates is not None:
            x, y = target.coordinates
            return ResolvedElement(
                text=target.text or f"({x}, {y})",
                source=PerceptionSource.UIA,
                priority=60,
                confidence=1.0,
                clickable=True,
                bbox=(x, y, 1, 1),
                raw_element=None,
            )

        # Window title resolution
        if target.window_title:
            # Check if we can find the window in world state
            if (
                world_state.active_window
                and target.window_title.lower()
                in world_state.active_window.title.lower()
            ):
                return ResolvedElement(
                    text=world_state.active_window.title,
                    source=PerceptionSource.UIA,
                    priority=60,
                    confidence=0.9,
                    clickable=False,
                    bbox=None,
                    raw_element=None,
                )

            # Try to find via pyautogui (window may not be in world_state)
            try:
                windows = pyautogui.getWindowsWithTitle(target.window_title)
                if windows:
                    win = windows[0]
                    return ResolvedElement(
                        text=win.title,
                        source=PerceptionSource.UIA,
                        priority=60,
                        confidence=0.8,
                        clickable=False,
                        bbox=(win.left, win.top, win.width, win.height)
                        if hasattr(win, "left")
                        else None,
                        raw_element=None,
                    )
            except Exception:
                pass

            # Still return a placeholder element for window operations
            return ResolvedElement(
                text=target.window_title,
                source=PerceptionSource.UIA,
                priority=60,
                confidence=0.5,
                clickable=False,
                bbox=None,
                raw_element=None,
            )

        # OS-level action (no semantic hint, no coordinates, no window_title)
        # Return a generic element so hotkeys/keyboard can proceed
        if not target.has_semantic_hint:
            return ResolvedElement(
                text=target.text or "os_action",
                source=PerceptionSource.UIA,
                priority=60,
                confidence=0.7,
                clickable=False,
                bbox=None,
                raw_element=None,
            )

        return None

    # ------------------------------------------------------------------
    # Pointer actions
    # ------------------------------------------------------------------

    async def click(self, element: ResolvedElement) -> ActionResult:
        """Execute a single click at resolved coordinates."""
        try:
            x, y = self._get_coordinates(element)
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
                repair_hints=["retry", "re_resolve_target", "check_coordinates"],
            )

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a double click at resolved coordinates."""
        try:
            x, y = self._get_coordinates(element)
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
                repair_hints=["retry", "re_resolve_target", "check_coordinates"],
            )

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a right click at resolved coordinates."""
        try:
            x, y = self._get_coordinates(element)
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
                repair_hints=["retry", "re_resolve_target", "check_coordinates"],
            )

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        """Type text into whatever is currently focused."""
        try:
            await asyncio.to_thread(pyautogui.write, text)
            return ActionResult.success(
                action="type_text",
                target=text,
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="type_text",
                error=str(exc),
                target=text,
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
        """Press a key combination (e.g. ['ctrl', 's']).

        This is the primary use case for OS-level shortcuts.
        """
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

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------

    async def scroll(
        self,
        direction: str,
        amount: int,
        element: Optional[ResolvedElement] = None,
    ) -> ActionResult:
        """Scroll at coordinates or screen center."""
        try:
            # Determine scroll amount (positive = up, negative = down)
            scroll_amount = amount if direction == "up" else -amount

            if element and element.bbox:
                # Scroll at element coordinates
                x = element.bbox[0] + element.bbox[2] // 2
                y = element.bbox[1] + element.bbox[3] // 2
                await asyncio.to_thread(pyautogui.scroll, scroll_amount, x=x, y=y)
            else:
                # Scroll at screen center
                screen_w, screen_h = pyautogui.size()
                await asyncio.to_thread(
                    pyautogui.scroll,
                    scroll_amount,
                    x=screen_w // 2,
                    y=screen_h // 2,
                )

            return ActionResult.success(
                action="scroll",
                target=f"{direction} {amount}",
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="scroll",
                error=str(exc),
                target=f"{direction} {amount}",
                error_category="adapter_failed",
                repair_hints=["retry", "check_coordinates"],
            )

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        """Drag from source to destination using mouse down/move/up."""
        try:
            src_x, src_y = self._get_coordinates(source)
            dest_x, dest_y = self._get_coordinates(dest)

            await asyncio.to_thread(pyautogui.moveTo, src_x, src_y)
            await asyncio.to_thread(pyautogui.mouseDown)
            await asyncio.to_thread(pyautogui.moveTo, dest_x, dest_y, duration=0.3)
            await asyncio.to_thread(pyautogui.mouseUp)

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
                repair_hints=["retry", "re_resolve_target", "check_coordinates"],
            )

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    async def focus_window(self, target: Target) -> ActionResult:
        """Bring a window matching the target to the foreground."""
        try:
            windows = await asyncio.to_thread(
                pyautogui.getWindowsWithTitle, target.window_title
            )
            if not windows:
                return ActionResult.failed(
                    action="focus_window",
                    error=f"No window found with title: {target.window_title}",
                    target=target.window_title,
                    error_category="window_not_found",
                    repair_hints=[
                        "launch_application",
                        "check_window_title",
                        "list_windows",
                    ],
                )

            window = windows[0]
            # Activate the window
            await asyncio.to_thread(self._activate_window, window)

            return ActionResult.success(
                action="focus_window",
                target=target.window_title,
                evidence=ActionEvidence(
                    state_changed=True,
                    window_changed=True,
                ),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="focus_window",
                error=str(exc),
                target=target.window_title,
                error_category="adapter_failed",
                repair_hints=["retry", "check_window_title", "launch_application"],
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_coordinates(self, element: ResolvedElement) -> tuple:
        """Extract (x, y) click coordinates from a ResolvedElement.

        Uses bbox center if available, otherwise raises ValueError.
        """
        if element.bbox is not None:
            x, y, w, h = element.bbox
            return (x + w // 2, y + h // 2)
        raise ValueError(
            f"Cannot determine coordinates for element: {element.text}"
        )

    @staticmethod
    def _activate_window(window) -> None:
        """Activate a pyautogui window object.

        Handles minimized windows by restoring them first.
        """
        if hasattr(window, "isMinimized") and window.isMinimized:
            window.restore()
        if hasattr(window, "activate"):
            window.activate()
