"""Perception priority — semantic-first element resolution.

Enforces the core principle: prefer semantic information over visual.

Priority order (highest to lowest):
1. Browser DOM (Playwright/DevTools)
2. Windows UI Automation (UIA)
3. OCR (text extraction/verification)
4. Vision Models (page type, app ID, anomalies)
5. Raw pixel analysis

The planner reasons on WorldState. This module decides WHICH perception
source to trust when multiple sources report the same region/element.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Union

from friday.perception.types import (
    BrowserElement,
    OCRRegion,
    PerceptionSource,
    UIElement,
)
from friday.perception.world_state import WorldState


class SourcePriority(IntEnum):
    """Numeric priority for perception sources (higher = more trusted)."""

    BROWSER_DOM = 100
    UIA = 80
    OCR = 50
    VISION = 30
    PIXEL = 10
    UNKNOWN = 0


# Map perception sources to priority
_SOURCE_PRIORITY = {
    PerceptionSource.BROWSER: SourcePriority.BROWSER_DOM,
    PerceptionSource.UIA: SourcePriority.UIA,
    PerceptionSource.OCR: SourcePriority.OCR,
    PerceptionSource.VISION: SourcePriority.VISION,
    PerceptionSource.SCREEN: SourcePriority.PIXEL,
    PerceptionSource.PROCESS: SourcePriority.UIA,  # window info is semantic
}


@dataclass
class ResolvedElement:
    """An element resolved from the highest-priority available source."""

    text: str
    source: PerceptionSource
    priority: int
    confidence: float
    clickable: bool = False
    bbox: Optional[tuple] = None
    raw_element: Union[UIElement, BrowserElement, OCRRegion, None] = None

    @property
    def is_semantic(self) -> bool:
        """Whether this came from a semantic source (DOM or UIA)."""
        return self.source in (PerceptionSource.BROWSER, PerceptionSource.UIA)


class PerceptionResolver:
    """Resolves elements using semantic-first priority.

    When asked to find an element, searches sources in priority order
    and returns the highest-priority match. This ensures FRIDAY uses
    DOM/UIA before falling back to OCR/Vision.

    Usage:
        resolver = PerceptionResolver()

        # Find a clickable element by text — prefers DOM, then UIA, then OCR
        element = resolver.find_element(world_state, "Submit")
        if element and element.is_semantic:
            # High confidence — came from DOM or UIA
            click_at(element.bbox)
    """

    def find_element(
        self,
        world_state: WorldState,
        text: str,
        *,
        clickable_only: bool = False,
        prefer_browser: Optional[bool] = None,
    ) -> Optional[ResolvedElement]:
        """Find the best element matching text, semantic-first.

        Args:
            world_state: Current perception snapshot
            text: Text to match
            clickable_only: Only return clickable elements
            prefer_browser: Force browser-first (auto-detected if None)

        Returns:
            ResolvedElement from highest-priority source, or None
        """
        candidates: List[ResolvedElement] = []

        # 1. Browser DOM (highest priority)
        browser_elem = world_state.find_browser_element(
            text, clickable_only=clickable_only
        )
        if browser_elem:
            candidates.append(ResolvedElement(
                text=browser_elem.text,
                source=PerceptionSource.BROWSER,
                priority=int(SourcePriority.BROWSER_DOM),
                confidence=0.95,
                clickable=browser_elem.clickable,
                bbox=self._bbox_tuple(browser_elem.bbox),
                raw_element=browser_elem,
            ))

        # 2. Windows UI Automation
        ui_elem = world_state.find_ui_element(text)
        if ui_elem and (not clickable_only or self._is_clickable_control(ui_elem)):
            candidates.append(ResolvedElement(
                text=ui_elem.text,
                source=PerceptionSource.UIA,
                priority=int(SourcePriority.UIA),
                confidence=ui_elem.confidence,
                clickable=self._is_clickable_control(ui_elem),
                bbox=self._bbox_tuple(ui_elem.bbox),
                raw_element=ui_elem,
            ))

        # 3. OCR (text extraction — lower priority, not clickable-reliable)
        if not clickable_only:
            ocr_region = world_state.find_ocr_text(text)
            if ocr_region:
                candidates.append(ResolvedElement(
                    text=ocr_region.text,
                    source=PerceptionSource.OCR,
                    priority=int(SourcePriority.OCR),
                    confidence=ocr_region.confidence,
                    clickable=False,  # OCR can't confirm clickability
                    bbox=self._bbox_tuple(ocr_region.bbox),
                    raw_element=ocr_region,
                ))

        if not candidates:
            return None

        # Return highest priority, breaking ties by confidence
        candidates.sort(key=lambda c: (c.priority, c.confidence), reverse=True)
        return candidates[0]

    def read_text(self, world_state: WorldState, region_hint: str = "") -> str:
        """Read text using semantic-first priority.

        For reading content, prefer DOM/UIA text, fall back to OCR.

        Args:
            world_state: Current perception snapshot
            region_hint: Optional text to locate the region

        Returns:
            Best available text
        """
        # Browser DOM text first
        if world_state.browser_elements:
            dom_text = " ".join(
                e.text for e in world_state.browser_elements if e.text
            )
            if dom_text.strip():
                return dom_text

        # UIA element text
        if world_state.ui_elements:
            uia_text = " ".join(
                e.text for e in world_state.ui_elements if e.text
            )
            if uia_text.strip():
                return uia_text

        # OCR fallback
        if world_state.ocr_regions:
            return " ".join(r.text for r in world_state.ocr_regions if r.text)

        return ""

    def determine_page_type(self, world_state: WorldState) -> str:
        """Determine page/screen type using derived facts (semantic) first.

        Vision would supplement this, but we use derived facts from
        DOM/UIA keywords first.
        """
        d = world_state.derived
        if d.possible_login_screen:
            return "login"
        if d.possible_error_dialog:
            return "error"
        if d.possible_consent_dialog:
            return "consent"
        if d.possible_profile_selection:
            return "profile_selection"
        if d.possible_loading:
            return "loading"
        if world_state.browser_open:
            return "browser_page"
        if world_state.active_window:
            return "desktop_app"
        return "unknown"

    def get_perception_quality(self, world_state: WorldState) -> dict:
        """Report the quality/source distribution of current perception.

        Helps the planner know how much to trust the WorldState.
        """
        return {
            "has_browser_dom": len(world_state.browser_elements) > 0,
            "has_uia": len(world_state.ui_elements) > 0,
            "has_ocr": len(world_state.ocr_regions) > 0,
            "best_source": self._best_available_source(world_state).name,
            "semantic_coverage": self._semantic_coverage(world_state),
            "sources_used": [s.value for s in world_state.sources_used],
        }

    def _best_available_source(self, world_state: WorldState) -> SourcePriority:
        """Determine the highest-priority source with data."""
        if world_state.browser_elements:
            return SourcePriority.BROWSER_DOM
        if world_state.ui_elements:
            return SourcePriority.UIA
        if world_state.ocr_regions:
            return SourcePriority.OCR
        if world_state.screenshot_hash:
            return SourcePriority.PIXEL
        return SourcePriority.UNKNOWN

    def _semantic_coverage(self, world_state: WorldState) -> float:
        """Fraction of perception that is semantic (DOM/UIA) vs visual.

        1.0 = fully semantic, 0.0 = only pixels.
        """
        semantic = len(world_state.browser_elements) + len(world_state.ui_elements)
        visual = len(world_state.ocr_regions)
        total = semantic + visual
        if total == 0:
            return 0.0
        return semantic / total

    def _is_clickable_control(self, elem: UIElement) -> bool:
        """Determine if a UIA control type is clickable."""
        clickable_types = {
            "button", "hyperlink", "link", "menuitem", "tabitem",
            "listitem", "checkbox", "radiobutton", "splitbutton",
        }
        return elem.control_type.lower() in clickable_types

    def _bbox_tuple(self, bbox) -> Optional[tuple]:
        """Convert a BoundingBox to a tuple, or None."""
        if bbox is None:
            return None
        return (bbox.x, bbox.y, bbox.width, bbox.height)
