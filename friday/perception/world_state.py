"""WorldState — Single source of truth for machine perception.

This is the authoritative snapshot of everything FRIDAY knows about
the current environment at a given moment. No action should be taken
without consulting a current WorldState.

Design principles:
- Immutable once built (use WorldStateBuilder to construct)
- Hash-based change detection for verification
- All perception sources feed into one unified object
- Derived facts are computed at build time
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from friday.perception.types import (
    BoundingBox,
    BrowserElement,
    OCRRegion,
    PerceptionSource,
    ScreenRegion,
    UIElement,
    WindowInfo,
)


@dataclass
class DerivedFacts:
    """High-level facts derived from raw perception data."""

    possible_login_screen: bool = False
    possible_error_dialog: bool = False
    possible_profile_selection: bool = False
    possible_consent_dialog: bool = False
    possible_loading: bool = False
    has_text_input_focused: bool = False
    has_modal_overlay: bool = False


@dataclass
class WorldState:
    """Complete snapshot of the observable machine state.

    This is the single authoritative source of truth for all perception.
    The cognitive loop must always build a fresh WorldState before planning.
    """

    # Metadata
    timestamp: float
    build_duration_ms: float = 0.0
    sources_used: List[PerceptionSource] = field(default_factory=list)

    # Desktop perception
    active_window: Optional[WindowInfo] = None
    cursor_position: Tuple[int, int] = (0, 0)
    focused_element: Optional[UIElement] = None
    ui_elements: List[UIElement] = field(default_factory=list)

    # Visual perception
    screenshot_hash: str = ""
    ocr_regions: List[OCRRegion] = field(default_factory=list)
    screen_regions: List[ScreenRegion] = field(default_factory=list)

    # Browser perception
    browser_url: Optional[str] = None
    browser_title: Optional[str] = None
    browser_elements: List[BrowserElement] = field(default_factory=list)
    browser_connected: bool = False

    # Derived facts (computed at build time)
    derived: DerivedFacts = field(default_factory=DerivedFacts)

    # State hash for change detection
    _hash: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self._hash:
            self._hash = self._compute_hash()

    @property
    def state_hash(self) -> str:
        """Stable hash representing this perception snapshot."""
        return self._hash

    @property
    def browser_open(self) -> bool:
        """Whether a browser tab is detected."""
        return self.browser_connected and self.browser_url is not None

    @property
    def all_text(self) -> str:
        """All perceivable text combined (for keyword searches)."""
        parts: List[str] = []
        for elem in self.ui_elements:
            if elem.text:
                parts.append(elem.text)
        for region in self.ocr_regions:
            if region.text:
                parts.append(region.text)
        for elem in self.browser_elements:
            if elem.text:
                parts.append(elem.text)
        return " ".join(parts)

    def find_ui_element(
        self, text: str, *, control_type: Optional[str] = None
    ) -> Optional[UIElement]:
        """Find a UI element by text match (case-insensitive)."""
        target = text.lower()
        for elem in self.ui_elements:
            if target in elem.text.lower():
                if control_type and elem.control_type.lower() != control_type.lower():
                    continue
                return elem
        return None

    def find_ocr_text(self, text: str) -> Optional[OCRRegion]:
        """Find an OCR region containing the given text."""
        target = text.lower()
        for region in self.ocr_regions:
            if target in region.text.lower():
                return region
        return None

    def find_browser_element(
        self, text: str, *, tag: Optional[str] = None, clickable_only: bool = False
    ) -> Optional[BrowserElement]:
        """Find a browser element by text match."""
        target = text.lower()
        for elem in self.browser_elements:
            if target in elem.text.lower():
                if tag and elem.tag.lower() != tag.lower():
                    continue
                if clickable_only and not elem.clickable:
                    continue
                return elem
        return None

    def contains_text(self, text: str) -> bool:
        """Check if any perception source contains the given text."""
        return text.lower() in self.all_text.lower()

    def diff_from(self, previous: "WorldState") -> Dict[str, bool]:
        """Compute what changed between two world states."""
        return {
            "window_changed": (
                (self.active_window and previous.active_window and
                 self.active_window.title != previous.active_window.title)
                or (self.active_window is None) != (previous.active_window is None)
            ),
            "url_changed": self.browser_url != previous.browser_url,
            "screenshot_changed": self.screenshot_hash != previous.screenshot_hash,
            "focus_changed": (
                (self.focused_element and previous.focused_element and
                 self.focused_element.text != previous.focused_element.text)
                or (self.focused_element is None) != (previous.focused_element is None)
            ),
            "element_count_changed": len(self.ui_elements) != len(previous.ui_elements),
            "hash_changed": self.state_hash != previous.state_hash,
        }

    def to_summary(self) -> Dict:
        """Compact summary for logging and LLM context."""
        return {
            "timestamp": self.timestamp,
            "window": self.active_window.title if self.active_window else None,
            "app": self.active_window.process_name if self.active_window else None,
            "cursor": self.cursor_position,
            "focused": self.focused_element.text if self.focused_element else None,
            "ui_elements": len(self.ui_elements),
            "ocr_regions": len(self.ocr_regions),
            "browser_url": self.browser_url,
            "browser_title": self.browser_title,
            "browser_elements": len(self.browser_elements),
            "derived": {
                "login": self.derived.possible_login_screen,
                "error": self.derived.possible_error_dialog,
                "loading": self.derived.possible_loading,
                "modal": self.derived.has_modal_overlay,
            },
            "state_hash": self.state_hash,
            "sources": [s.value for s in self.sources_used],
        }

    def _compute_hash(self) -> str:
        """Compute a stable hash for change detection."""
        components = [
            self.active_window.title if self.active_window else "",
            self.active_window.process_name if self.active_window else "",
            self.screenshot_hash,
            self.browser_url or "",
            self.browser_title or "",
            str(len(self.ui_elements)),
            str(len(self.ocr_regions)),
            str(len(self.browser_elements)),
        ]
        combined = "|".join(components)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


class WorldStateBuilder:
    """Constructs a WorldState from multiple perception sources.

    Usage:
        builder = WorldStateBuilder()
        builder.set_window_info(...)
        builder.add_ui_elements(...)
        builder.set_browser_state(...)
        builder.set_screenshot_hash(...)
        builder.add_ocr_regions(...)
        world_state = builder.build()
    """

    def __init__(self) -> None:
        self._start_time = time.perf_counter()
        self._sources: List[PerceptionSource] = []
        self._active_window: Optional[WindowInfo] = None
        self._cursor_position: Tuple[int, int] = (0, 0)
        self._focused_element: Optional[UIElement] = None
        self._ui_elements: List[UIElement] = []
        self._screenshot_hash: str = ""
        self._ocr_regions: List[OCRRegion] = []
        self._screen_regions: List[ScreenRegion] = []
        self._browser_url: Optional[str] = None
        self._browser_title: Optional[str] = None
        self._browser_elements: List[BrowserElement] = []
        self._browser_connected: bool = False

    def set_window_info(self, window: WindowInfo) -> "WorldStateBuilder":
        """Set active window information."""
        self._active_window = window
        if PerceptionSource.PROCESS not in self._sources:
            self._sources.append(PerceptionSource.PROCESS)
        return self

    def set_cursor_position(self, x: int, y: int) -> "WorldStateBuilder":
        """Set current cursor position."""
        self._cursor_position = (x, y)
        return self

    def set_focused_element(self, element: UIElement) -> "WorldStateBuilder":
        """Set the currently focused UI element."""
        self._focused_element = element
        return self

    def add_ui_elements(self, elements: List[UIElement]) -> "WorldStateBuilder":
        """Add UI elements from Windows UI Automation."""
        self._ui_elements.extend(elements)
        if PerceptionSource.UIA not in self._sources:
            self._sources.append(PerceptionSource.UIA)
        return self

    def set_screenshot_hash(self, hash_value: str) -> "WorldStateBuilder":
        """Set the hash of the current screenshot."""
        self._screenshot_hash = hash_value
        if PerceptionSource.SCREEN not in self._sources:
            self._sources.append(PerceptionSource.SCREEN)
        return self

    def add_ocr_regions(self, regions: List[OCRRegion]) -> "WorldStateBuilder":
        """Add OCR-detected text regions."""
        self._ocr_regions.extend(regions)
        if PerceptionSource.OCR not in self._sources:
            self._sources.append(PerceptionSource.OCR)
        return self

    def add_screen_regions(self, regions: List[ScreenRegion]) -> "WorldStateBuilder":
        """Add screen regions of interest."""
        self._screen_regions.extend(regions)
        return self

    def set_browser_state(
        self,
        url: Optional[str],
        title: Optional[str],
        elements: List[BrowserElement],
        connected: bool = True,
    ) -> "WorldStateBuilder":
        """Set browser perception state."""
        self._browser_url = url
        self._browser_title = title
        self._browser_elements = elements
        self._browser_connected = connected
        if PerceptionSource.BROWSER not in self._sources:
            self._sources.append(PerceptionSource.BROWSER)
        return self

    def build(self) -> WorldState:
        """Build the final WorldState with derived facts computed."""
        build_duration = (time.perf_counter() - self._start_time) * 1000

        state = WorldState(
            timestamp=time.time(),
            build_duration_ms=build_duration,
            sources_used=list(self._sources),
            active_window=self._active_window,
            cursor_position=self._cursor_position,
            focused_element=self._focused_element,
            ui_elements=self._ui_elements,
            screenshot_hash=self._screenshot_hash,
            ocr_regions=self._ocr_regions,
            screen_regions=self._screen_regions,
            browser_url=self._browser_url,
            browser_title=self._browser_title,
            browser_elements=self._browser_elements,
            browser_connected=self._browser_connected,
        )

        # Compute derived facts
        state.derived = self._compute_derived_facts(state)

        return state

    def _compute_derived_facts(self, state: WorldState) -> DerivedFacts:
        """Analyze raw perception to derive high-level facts."""
        all_text_lower = state.all_text.lower()

        login_keywords = {"login", "sign in", "password", "username", "log in"}
        error_keywords = {"error", "failed", "unable", "cannot", "problem", "retry", "exception"}
        profile_keywords = {"profile", "choose account", "select account", "which profile"}
        consent_keywords = {"accept", "consent", "agree", "cookies", "privacy policy", "terms"}
        loading_keywords = {"loading", "please wait", "spinner", "processing"}

        has_text_input = any(
            elem.control_type.lower() in ("edit", "textbox", "input", "textarea")
            and elem.focused
            for elem in state.ui_elements
        )

        return DerivedFacts(
            possible_login_screen=any(kw in all_text_lower for kw in login_keywords),
            possible_error_dialog=any(kw in all_text_lower for kw in error_keywords),
            possible_profile_selection=any(kw in all_text_lower for kw in profile_keywords),
            possible_consent_dialog=any(kw in all_text_lower for kw in consent_keywords),
            possible_loading=any(kw in all_text_lower for kw in loading_keywords),
            has_text_input_focused=has_text_input,
            has_modal_overlay=False,  # Requires visual analysis (future)
        )
