"""Unified perception snapshot for cognitive system.

This replaces dict-based snapshots with a structured object that serves as
the single source of truth for all perception data.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PerceptionElement:
    """A single UI element detected via UIA, OCR, or browser DOM."""
    
    text: str
    element_type: str  # "Button", "Edit", "Link", "OCRWord", etc.
    bounding_box: Optional[Tuple[int, int, int, int]]  # (left, top, right, bottom)
    confidence: float  # 0.0-1.0
    source: str  # "uia", "ocr", "browser"
    focused: bool = False
    enabled: bool = True
    visible: bool = True
    
    def center(self) -> Optional[Tuple[int, int]]:
        """Get center coordinates of bounding box."""
        if not self.bounding_box:
            return None
        l, t, r, b = self.bounding_box
        return ((l + r) // 2, (t + b) // 2)
    
    def area(self) -> int:
        """Get area of bounding box in pixels."""
        if not self.bounding_box:
            return 0
        l, t, r, b = self.bounding_box
        return max(0, (r - l) * (b - t))


@dataclass
class BrowserState:
    """Browser-specific perception data."""
    
    open: bool = False
    url: Optional[str] = None
    title: Optional[str] = None
    elements: List[PerceptionElement] = field(default_factory=list)
    has_login_form: bool = False
    has_error: bool = False
    has_consent_dialog: bool = False


@dataclass
class PerceptionSnapshot:
    """Unified perception snapshot - single source of truth for cognitive system.
    
    This object replaces dict-based snapshots and provides structured access
    to all perception data with semantic queries.
    """
    
    timestamp: float
    
    # Window context
    active_window_title: str
    active_app: str
    active_window_pid: Optional[int] = None
    active_window_bounds: Optional[Tuple[int, int, int, int]] = None
    
    # Cursor
    cursor_position: Tuple[int, int] = (0, 0)
    
    # All detected elements (unified from UIA + OCR + Browser)
    elements: List[PerceptionElement] = field(default_factory=list)
    
    # Browser state
    browser: BrowserState = field(default_factory=BrowserState)
    
    # Screen hash for change detection
    screen_hash: str = ""
    
    # Metadata
    source_flags: dict = field(default_factory=dict)  # {uia: True, ocr: True, browser: False}
    
    def __post_init__(self):
        """Compute screen hash if not provided."""
        if not self.screen_hash:
            self.screen_hash = self.compute_hash()
    
    def compute_hash(self) -> str:
        """Compute hash of current perception state for change detection."""
        components = [
            self.active_window_title,
            self.active_app,
            str(self.cursor_position),
            str(len(self.elements)),
            self.browser.url or "",
            self.browser.title or "",
        ]
        
        # Include element texts (sorted for stability)
        element_texts = sorted([e.text for e in self.elements if e.text])
        components.extend(element_texts[:50])  # Limit to prevent huge hashes
        
        combined = "|".join(components)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def find_element_by_text(self, text: str, fuzzy: bool = False) -> Optional[PerceptionElement]:
        """Find element by text match.
        
        Args:
            text: Text to search for
            fuzzy: If True, use case-insensitive substring match
            
        Returns:
            First matching element or None
        """
        text_lower = text.lower()
        
        for elem in self.elements:
            if not elem.text:
                continue
            
            if fuzzy:
                if text_lower in elem.text.lower():
                    return elem
            else:
                if elem.text == text:
                    return elem
        
        return None
    
    def find_elements_by_type(self, element_type: str) -> List[PerceptionElement]:
        """Find all elements of a specific type.
        
        Args:
            element_type: Type to filter by (e.g., "Button", "Edit")
            
        Returns:
            List of matching elements
        """
        return [e for e in self.elements if e.element_type == element_type]
    
    def find_focused_element(self) -> Optional[PerceptionElement]:
        """Get currently focused element."""
        for elem in self.elements:
            if elem.focused:
                return elem
        return None
    
    def find_clickable_elements(self) -> List[PerceptionElement]:
        """Get all clickable elements with bounding boxes."""
        return [
            e for e in self.elements
            if e.bounding_box and e.enabled and e.visible
            and e.element_type in ("Button", "Link", "MenuItem", "TabItem")
        ]
    
    def find_text_inputs(self) -> List[PerceptionElement]:
        """Get all text input fields."""
        return [
            e for e in self.elements
            if e.element_type in ("Edit", "Document", "Text")
            and e.enabled and e.visible
        ]
    
    def to_dict(self) -> dict:
        """Convert to dict for backward compatibility."""
        return {
            "timestamp": self.timestamp,
            "active_window_title": self.active_window_title,
            "active_app": self.active_app,
            "active_window_pid": self.active_window_pid,
            "cursor_position": self.cursor_position,
            "browser_open": self.browser.open,
            "browser_url": self.browser.url,
            "browser_title": self.browser.title,
            "screen_hash": self.screen_hash,
            "element_count": len(self.elements),
            "source_flags": self.source_flags,
            "has_login_form": self.browser.has_login_form,
            "has_error": self.browser.has_error,
            "has_consent_dialog": self.browser.has_consent_dialog,
        }
    
    @classmethod
    def from_world_state(cls, world_state) -> "PerceptionSnapshot":
        """Create PerceptionSnapshot from existing WorldState object.
        
        Args:
            world_state: WorldState object from world_state.py
            
        Returns:
            PerceptionSnapshot instance
        """
        elements = []
        
        # Convert UIA elements
        for ui_elem in getattr(world_state, "ui_elements", []):
            elements.append(PerceptionElement(
                text=ui_elem.text,
                element_type=ui_elem.control_type,
                bounding_box=ui_elem.bounding_box,
                confidence=ui_elem.confidence,
                source="uia",
                focused=ui_elem.focused,
                enabled=ui_elem.enabled,
            ))
        
        # Convert OCR words
        for ocr_word in getattr(world_state, "ocr_words", []):
            elements.append(PerceptionElement(
                text=ocr_word.text,
                element_type="OCRWord",
                bounding_box=ocr_word.bbox,
                confidence=ocr_word.confidence,
                source="ocr",
            ))
        
        # Convert browser elements
        browser_elements = []
        for browser_elem in getattr(world_state, "browser_elements", []):
            pe = PerceptionElement(
                text=browser_elem.text,
                element_type=browser_elem.tag,
                bounding_box=browser_elem.bbox,
                confidence=0.95,
                source="browser",
                enabled=browser_elem.clickable,
            )
            elements.append(pe)
            browser_elements.append(pe)
        
        browser_state = BrowserState(
            open=getattr(world_state, "browser_open", False),
            url=getattr(world_state, "browser_url", None),
            title=getattr(world_state, "browser_title", None),
            elements=browser_elements,
            has_login_form=getattr(world_state, "possible_login_screen", False),
            has_error=getattr(world_state, "possible_error_dialog", False),
            has_consent_dialog=getattr(world_state, "possible_consent_dialog", False),
        )
        
        return cls(
            timestamp=getattr(world_state, "timestamp", time.time()),
            active_window_title=getattr(world_state, "active_window_title", ""),
            active_app=getattr(world_state, "active_app", ""),
            active_window_pid=None,
            cursor_position=getattr(world_state, "cursor_position", (0, 0)),
            elements=elements,
            browser=browser_state,
            screen_hash=getattr(world_state, "screenshot_hash", ""),
            source_flags={
                "uia": len([e for e in elements if e.source == "uia"]) > 0,
                "ocr": len([e for e in elements if e.source == "ocr"]) > 0,
                "browser": browser_state.open,
            },
        )
