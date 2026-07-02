"""VisionAdapter — Coordinate-based fallback using OCR/pixel bounding boxes.

This is the LAST-RESORT adapter. It only activates when Browser, DesktopUIA,
and DesktopActions adapters all cannot handle the target. It resolves targets
via OCR text regions or raw coordinates and executes actions through pyautogui.

Priority: 30 (lowest among all adapters)
Sources: PerceptionSource.OCR (text match), PerceptionSource.SCREEN (coordinates)
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pyautogui

from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BoundingBox, OCRRegion, PerceptionSource
from friday.perception.world_state import WorldState


class VisionAdapter:
    """Coordinate-based fallback adapter using OCR regions and raw coordinates.

    Resolution strategy:
      1. Search world_state.ocr_regions for a case-insensitive text match
      2. If not found but target has explicit coordinates, use those
      3. Otherwise, cannot handle

    All pyautogui calls are dispatched via asyncio.to_thread to avoid
    blocking the event loop.
    """

    @property
    def name(self) -> str:
        return "vision"

    @property
    def priority(self) -> int:
        return 30

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        """Return True when OCR regions contain a text match or target has coordinates."""
        if target.text:
            for region in world_state.ocr_regions:
                if target.text.lower() in region.text.lower():
                    return True
        if target.coordinates is not None:
            return True
        return False

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        """Resolve target to a ResolvedElement from OCR or raw coordinates."""
        # Try OCR text match first
        if target.text:
            for region in world_state.ocr_regions:
                if target.text.lower() in region.text.lower():
                    return ResolvedElement(
                        text=region.text,
                        source=PerceptionSource.OCR,
                        priority=30,
                        confidence=region.confidence,
                        clickable=False,
                        bbox=(region.bbox.x, region.bbox.y, region.bbox.width, region.bbox.height),
                        raw_element=region,
                    )

        # Fallback to explicit coordinates
        if target.coordinates is not None:
            x, y = target.coordinates
            return ResolvedElement(
                text=target.text or f"({x}, {y})",
                source=PerceptionSource.SCREEN,
                priority=10,
                confidence=1.0,
                clickable=False,
                bbox=(x, y, 1, 1),
                raw_element=None,
            )

        return None

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _get_click_point(self, element: ResolvedElement) -> tuple[int, int]:
        """Extract the center click point from a resolved element."""
        if element.raw_element is not None and isinstance(element.raw_element, OCRRegion):
            return element.raw_element.bbox.center
        # For coordinate-based elements, bbox is (x, y, w, h)
        if element.bbox:
            bx, by, bw, bh = element.bbox
            return (bx + bw // 2, by + bh // 2)
        raise ValueError("Element has no positional information")

    # ------------------------------------------------------------------
    # Async action methods
    # ------------------------------------------------------------------

    async def click(self, element: ResolvedElement) -> ActionResult:
        """Execute a single click at the resolved element's center."""
        try:
            x, y = self._get_click_point(element)
            await asyncio.to_thread(pyautogui.click, x, y)
            return ActionResult.success(
                action="click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="click",
                target=element.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a double click at the resolved element's center."""
        try:
            x, y = self._get_click_point(element)
            await asyncio.to_thread(pyautogui.doubleClick, x, y)
            return ActionResult.success(
                action="double_click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="double_click",
                target=element.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a right click at the resolved element's center."""
        try:
            x, y = self._get_click_point(element)
            await asyncio.to_thread(pyautogui.rightClick, x, y)
            return ActionResult.success(
                action="right_click",
                target=element.text,
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="right_click",
                target=element.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        """Type text into the currently focused element."""
        try:
            await asyncio.to_thread(pyautogui.write, text)
            return ActionResult.success(
                action="type_text",
                target=text,
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="type_text",
                target=text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "click_target_first"],
            )

    async def press_key(self, key: str) -> ActionResult:
        """Press a single key."""
        try:
            await asyncio.to_thread(pyautogui.press, key)
            return ActionResult.success(
                action="press_key",
                target=key,
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_key",
                target=key,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry"],
            )

    async def press_hotkey(self, keys: List[str]) -> ActionResult:
        """Press a key combination (e.g. ['ctrl', 's'])."""
        try:
            await asyncio.to_thread(pyautogui.hotkey, *keys)
            return ActionResult.success(
                action="press_hotkey",
                target="+".join(keys),
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="press_hotkey",
                target="+".join(keys),
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry"],
            )

    async def scroll(
        self,
        direction: str,
        amount: int,
        element: Optional[ResolvedElement] = None,
    ) -> ActionResult:
        """Scroll at the OCR region center (or screen center if no element)."""
        try:
            # Determine scroll amount sign based on direction
            scroll_amount = amount if direction == "up" else -amount

            if element is not None:
                x, y = self._get_click_point(element)
                await asyncio.to_thread(pyautogui.scroll, scroll_amount, x, y)
            else:
                await asyncio.to_thread(pyautogui.scroll, scroll_amount)

            return ActionResult.success(
                action="scroll",
                target=f"{direction} {amount}",
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="scroll",
                target=f"{direction} {amount}",
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry"],
            )

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        """Drag from source element to destination element via coordinates."""
        try:
            sx, sy = self._get_click_point(source)
            dx, dy = self._get_click_point(dest)
            await asyncio.to_thread(pyautogui.moveTo, sx, sy)
            await asyncio.to_thread(pyautogui.drag, dx - sx, dy - sy, duration=0.5)
            return ActionResult.success(
                action="drag",
                target=f"{source.text} -> {dest.text}",
                evidence=ActionEvidence(state_changed=True, screenshot_changed=True),
            )
        except Exception as exc:
            return ActionResult.failed(
                action="drag",
                target=f"{source.text} -> {dest.text}",
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target"],
            )

    async def focus_window(self, target: Target) -> ActionResult:
        """Vision adapter cannot switch windows semantically — always fails."""
        return ActionResult.failed(
            action="focus_window",
            target=target.text or target.window_title or "",
            error="Vision adapter cannot switch windows semantically",
            error_category="adapter_failed",
            repair_hints=["try_alternative_adapter", "use_desktop_adapter"],
        )
