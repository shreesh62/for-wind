"""Semantic actions: High-level actions that operate on perceived world state.

This module defines the Action class and semantic action types that are
derived from world state analysis, not from keywords or site-specific logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Action:
    """Represents a single semantic action to be executed.
    
    An Action describes WHAT to do and WHAT should change, not HOW to do it.
    The execution engine figures out the HOW based on the current WorldState.
    """
    
    type: str
    target: Optional[str]
    expected_change: str
    
    # Additional parameters
    text_content: Optional[str] = None
    coordinates: Optional[tuple[int, int]] = None
    url: Optional[str] = None
    
    def __str__(self) -> str:
        """Human-readable representation of the action."""
        parts = [f"Action: {self.type}"]
        if self.target:
            parts.append(f"Target: {self.target}")
        if self.text_content:
            parts.append(f"Text: {self.text_content[:50]}")
        parts.append(f"Expected: {self.expected_change}")
        return " | ".join(parts)


# Semantic action types
class ActionType:
    """Constants for semantic action types."""
    
    # Application control
    OPEN_APPLICATION = "open_application"
    FOCUS_WINDOW = "focus_window"
    CLOSE_APPLICATION = "close_application"
    
    # Browser control
    OPEN_BROWSER = "open_browser"
    NAVIGATE_TO_URL = "navigate_to_url"
    REFRESH_PAGE = "refresh_page"
    GO_BACK = "go_back"
    
    # Element interaction
    CLICK_ELEMENT = "click_element"
    CLICK_COORDINATES = "click_coordinates"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    
    # Search and navigation
    SEARCH_WEB = "search_web"
    SEARCH_ON_PAGE = "search_on_page"
    
    # Dialog handling
    DISMISS_DIALOG = "dismiss_dialog"
    ACCEPT_CONSENT = "accept_consent"
    HANDLE_LOGIN = "handle_login"
    
    # Verification
    WAIT_FOR_CHANGE = "wait_for_change"
    VERIFY_STATE = "verify_state"
    CAPTURE_SCREENSHOT = "capture_screenshot"
    
    # Content extraction
    READ_SCREEN = "read_screen"
    EXTRACT_TEXT = "extract_text"


def create_open_browser_action() -> Action:
    """Create an action to open the browser."""
    return Action(
        type=ActionType.OPEN_BROWSER,
        target="browser",
        expected_change="browser_opened",
    )


def create_navigate_action(url: str) -> Action:
    """Create an action to navigate to a URL."""
    return Action(
        type=ActionType.NAVIGATE_TO_URL,
        target=url,
        expected_change="page_loaded",
        url=url,
    )


def create_click_element_action(element_text: str) -> Action:
    """Create an action to click an element by its text."""
    return Action(
        type=ActionType.CLICK_ELEMENT,
        target=element_text,
        expected_change="element_clicked",
    )


def create_click_coordinates_action(x: int, y: int, target_desc: str = "coordinates") -> Action:
    """Create an action to click at specific coordinates."""
    return Action(
        type=ActionType.CLICK_COORDINATES,
        target=target_desc,
        expected_change="location_clicked",
        coordinates=(x, y),
    )


def create_type_text_action(text: str) -> Action:
    """Create an action to type text."""
    return Action(
        type=ActionType.TYPE_TEXT,
        target="focused_input",
        expected_change="text_entered",
        text_content=text,
    )


def create_search_action(query: str) -> Action:
    """Create an action to perform a web search."""
    return Action(
        type=ActionType.SEARCH_WEB,
        target="search_engine",
        expected_change="search_results_visible",
        text_content=query,
    )


def create_dismiss_dialog_action() -> Action:
    """Create an action to dismiss a dialog."""
    return Action(
        type=ActionType.DISMISS_DIALOG,
        target="dialog",
        expected_change="dialog_closed",
    )


def create_accept_consent_action() -> Action:
    """Create an action to accept a consent dialog."""
    return Action(
        type=ActionType.ACCEPT_CONSENT,
        target="consent_dialog",
        expected_change="consent_accepted",
    )


def create_focus_window_action(app_name: str) -> Action:
    """Create an action to focus a window."""
    return Action(
        type=ActionType.FOCUS_WINDOW,
        target=app_name,
        expected_change="window_focused",
    )


def create_wait_action(expected_change: str, timeout: float = 5.0) -> Action:
    """Create an action to wait for a state change."""
    return Action(
        type=ActionType.WAIT_FOR_CHANGE,
        target=None,
        expected_change=expected_change,
    )


def create_verify_action(verification_target: str) -> Action:
    """Create an action to verify current state."""
    return Action(
        type=ActionType.VERIFY_STATE,
        target=verification_target,
        expected_change="state_verified",
    )


def create_read_screen_action() -> Action:
    """Create an action to read screen content."""
    return Action(
        type=ActionType.READ_SCREEN,
        target="screen",
        expected_change="content_extracted",
    )
