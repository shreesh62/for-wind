"""WorldState: Single source of truth for machine perception.

This module defines the unified world model that represents everything
JARVIS knows about the current machine state at any given moment.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class UIElement:
    """Represents a UI element detected via Windows UI Automation."""
    
    text: str
    control_type: str
    bounding_box: Tuple[int, int, int, int]
    focused: bool
    enabled: bool
    confidence: float


@dataclass
class OCRWord:
    """Represents a word detected via OCR with spatial information."""
    
    text: str
    bbox: Tuple[int, int, int, int]
    confidence: float


@dataclass
class BrowserElement:
    """Represents a DOM element in the active browser tab."""
    
    tag: str
    text: str
    role: str
    clickable: bool
    bbox: Optional[Tuple[int, int, int, int]] = None


@dataclass
class WorldState:
    """Complete snapshot of the observable machine state.
    
    This is the single authoritative source of truth for all perception.
    No action should be taken without consulting the current WorldState.
    """
    
    timestamp: float
    
    # Desktop perception
    active_window_title: str
    active_app: str
    cursor_position: Tuple[int, int]
    focused_element: Optional[UIElement]
    ui_elements: List[UIElement] = field(default_factory=list)
    
    # Visual perception
    screenshot_hash: str = ""
    ocr_words: List[OCRWord] = field(default_factory=list)
    
    # Browser perception
    browser_open: bool = False
    browser_url: Optional[str] = None
    browser_title: Optional[str] = None
    browser_elements: List[BrowserElement] = field(default_factory=list)
    
    # Derived facts (computed from raw perception)
    possible_login_screen: bool = False
    possible_error_dialog: bool = False
    possible_profile_selection: bool = False
    possible_consent_dialog: bool = False
    
    def __post_init__(self):
        """Compute derived facts from raw perception data."""
        self._compute_derived_facts()
    
    def _compute_derived_facts(self) -> None:
        """Analyze raw perception to derive high-level facts."""
        # Login screen detection
        login_keywords = {"login", "sign in", "password", "username", "email"}
        self.possible_login_screen = self._contains_keywords(login_keywords)
        
        # Error dialog detection
        error_keywords = {"error", "failed", "unable", "cannot", "problem", "retry"}
        self.possible_error_dialog = self._contains_keywords(error_keywords)
        
        # Profile selection detection
        profile_keywords = {"profile", "account", "user", "select", "choose"}
        self.possible_profile_selection = self._contains_keywords(profile_keywords)
        
        # Consent dialog detection
        consent_keywords = {"accept", "consent", "agree", "cookies", "privacy", "terms"}
        self.possible_consent_dialog = self._contains_keywords(consent_keywords)
    
    def _contains_keywords(self, keywords: set) -> bool:
        """Check if any UI text or OCR text contains given keywords."""
        all_text = []
        
        # Collect UI element text
        for elem in self.ui_elements:
            if elem.text:
                all_text.append(elem.text.lower())
        
        # Collect OCR text
        for word in self.ocr_words:
            if word.text:
                all_text.append(word.text.lower())
        
        # Collect browser element text
        for elem in self.browser_elements:
            if elem.text:
                all_text.append(elem.text.lower())
        
        # Check for keyword presence
        combined = " ".join(all_text)
        return any(kw in combined for kw in keywords)
    
    def find_element_by_text(self, text: str, *, case_sensitive: bool = False) -> Optional[UIElement]:
        """Find a UI element by text match."""
        target = text if case_sensitive else text.lower()
        
        for elem in self.ui_elements:
            elem_text = elem.text if case_sensitive else elem.text.lower()
            if target in elem_text:
                return elem
        return None
    
    def find_ocr_word(self, text: str, *, case_sensitive: bool = False) -> Optional[OCRWord]:
        """Find an OCR word by text match."""
        target = text if case_sensitive else text.lower()
        
        for word in self.ocr_words:
            word_text = word.text if case_sensitive else word.text.lower()
            if target in word_text:
                return word
        return None
    
    def find_browser_element(self, text: str, *, case_sensitive: bool = False) -> Optional[BrowserElement]:
        """Find a browser element by text match."""
        target = text if case_sensitive else text.lower()
        
        for elem in self.browser_elements:
            elem_text = elem.text if case_sensitive else elem.text.lower()
            if target in elem_text:
                return elem
        return None
    
    def compute_hash(self) -> str:
        """Compute a hash representing this world state for change detection."""
        components = [
            self.active_window_title,
            self.active_app,
            self.screenshot_hash,
            self.browser_url or "",
            str(len(self.ui_elements)),
            str(len(self.ocr_words)),
        ]
        combined = "|".join(components)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """Convert WorldState to dictionary for serialization/logging."""
        return {
            "timestamp": self.timestamp,
            "active_window_title": self.active_window_title,
            "active_app": self.active_app,
            "cursor_position": self.cursor_position,
            "focused_element": {
                "text": self.focused_element.text,
                "control_type": self.focused_element.control_type,
            } if self.focused_element else None,
            "ui_elements_count": len(self.ui_elements),
            "screenshot_hash": self.screenshot_hash,
            "ocr_words_count": len(self.ocr_words),
            "browser_open": self.browser_open,
            "browser_url": self.browser_url,
            "browser_title": self.browser_title,
            "browser_elements_count": len(self.browser_elements),
            "derived_facts": {
                "possible_login_screen": self.possible_login_screen,
                "possible_error_dialog": self.possible_error_dialog,
                "possible_profile_selection": self.possible_profile_selection,
                "possible_consent_dialog": self.possible_consent_dialog,
            },
            "state_hash": self.compute_hash(),
        }
