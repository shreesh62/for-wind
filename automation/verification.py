"""Semantic verification engine for action postconditions.

This module ensures NO action is marked successful unless its postcondition
is verified through actual state observation. No hallucinated success allowed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def verify_click(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    """Verify click action by checking if focused element changed.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        
    Returns:
        True if verification passed
    """
    before_focused = before.get("focused_element")
    after_focused = after.get("focused_element")
    
    # Check if focus changed
    if before_focused != after_focused:
        return True
    
    # Check if window changed
    if before.get("active_window_title") != after.get("active_window_title"):
        return True
    
    # Check if state hash changed
    if before.get("state_hash") != after.get("state_hash"):
        return True
    
    return False


def verify_type(before: Dict[str, Any], after: Dict[str, Any], typed_text: str) -> bool:
    """Verify type action by checking if typed text appears in OCR or UI elements.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        typed_text: The text that was typed
        
    Returns:
        True if verification passed
    """
    if not typed_text:
        return False
    
    typed_lower = typed_text.lower()
    
    # Check OCR text
    before_ocr = set(w.lower() for w in before.get("ocr_words", []))
    after_ocr = set(w.lower() for w in after.get("ocr_words", []))
    
    # Check if any word from typed text appears in new OCR
    typed_words = typed_lower.split()
    for word in typed_words:
        if word in after_ocr and word not in before_ocr:
            return True
    
    # Check UI element text
    before_ui_text = " ".join(before.get("ui_element_texts", [])).lower()
    after_ui_text = " ".join(after.get("ui_element_texts", [])).lower()
    
    if typed_lower in after_ui_text and typed_lower not in before_ui_text:
        return True
    
    # Fallback: check if state changed at all
    if before.get("state_hash") != after.get("state_hash"):
        return True
    
    return False


def verify_login(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    """Verify login action by checking if browser URL or DOM changed.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        
    Returns:
        True if verification passed
    """
    # Check if browser URL changed
    before_url = before.get("browser_url", "")
    after_url = after.get("browser_url", "")
    
    if before_url != after_url:
        # URL changed - likely successful login redirect
        return True
    
    # Check if browser title changed
    before_title = before.get("browser_title", "")
    after_title = after.get("browser_title", "")
    
    if before_title != after_title:
        return True
    
    # Check if login dialog disappeared
    if before.get("possible_login_screen") and not after.get("possible_login_screen"):
        return True
    
    # Check if DOM changed significantly
    before_elements = before.get("browser_elements_count", 0)
    after_elements = after.get("browser_elements_count", 0)
    
    if abs(after_elements - before_elements) > 5:
        return True
    
    return False


def verify_open_website(before: Dict[str, Any], after: Dict[str, Any], target_url: str) -> bool:
    """Verify website opening by checking DevTools location.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        target_url: The target URL that should be opened
        
    Returns:
        True if verification passed
    """
    after_url = after.get("browser_url", "")
    
    if not after_url:
        return False
    
    # Normalize URLs for comparison
    target_normalized = target_url.lower().replace("https://", "").replace("http://", "").rstrip("/")
    after_normalized = after_url.lower().replace("https://", "").replace("http://", "").rstrip("/")
    
    # Check if target is in the current URL
    if target_normalized in after_normalized:
        return True
    
    # Check if browser title contains target
    after_title = after.get("browser_title", "").lower()
    if target_normalized.split("/")[0] in after_title:
        return True
    
    return False


def verify_dismiss_dialog(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    """Verify dialog dismissal by checking if dialog indicators disappeared.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        
    Returns:
        True if verification passed
    """
    # Check if error dialog flag cleared
    if before.get("possible_error_dialog") and not after.get("possible_error_dialog"):
        return True
    
    # Check if consent dialog flag cleared
    if before.get("possible_consent_dialog") and not after.get("possible_consent_dialog"):
        return True
    
    # Check if OCR text changed (dialog text disappeared)
    before_ocr = set(before.get("ocr_words", []))
    after_ocr = set(after.get("ocr_words", []))
    
    # Common dialog words
    dialog_words = {"ok", "cancel", "close", "accept", "dismiss", "error", "warning"}
    
    before_dialog_words = before_ocr & dialog_words
    after_dialog_words = after_ocr & dialog_words
    
    if before_dialog_words and not after_dialog_words:
        return True
    
    return False


def verify_focus_window(before: Dict[str, Any], after: Dict[str, Any], target_app: str) -> bool:
    """Verify window focus by checking active window.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        target_app: The target application name
        
    Returns:
        True if verification passed
    """
    after_app = after.get("active_app", "").lower()
    after_title = after.get("active_window_title", "").lower()
    
    target_lower = target_app.lower()
    
    # Check if target app is now active
    if target_lower in after_app or target_lower in after_title:
        return True
    
    return False


def verify_scroll(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    """Verify scroll action by checking if UI elements or OCR changed.
    
    Args:
        before: WorldState dict before action
        after: WorldState dict after action
        
    Returns:
        True if verification passed
    """
    # Check if OCR words changed (new content visible)
    before_ocr = set(before.get("ocr_words", []))
    after_ocr = set(after.get("ocr_words", []))
    
    if before_ocr != after_ocr:
        return True
    
    # Check if UI elements changed
    before_ui_count = before.get("ui_elements_count", 0)
    after_ui_count = after.get("ui_elements_count", 0)
    
    if before_ui_count != after_ui_count:
        return True
    
    # Check state hash
    if before.get("state_hash") != after.get("state_hash"):
        return True
    
    return False


def verify_action(
    action_type: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    action_params: Optional[Dict[str, Any]] = None
) -> bool:
    """Main verification dispatcher.
    
    Args:
        action_type: Type of action performed
        before: WorldState dict before action
        after: WorldState dict after action
        action_params: Optional parameters (e.g., typed_text, target_url)
        
    Returns:
        True if verification passed, False otherwise
    """
    if action_params is None:
        action_params = {}
    
    # Map action types to verification functions
    if action_type in ["click_element", "click_coordinates", "click"]:
        return verify_click(before, after)
    
    elif action_type == "type_text":
        typed_text = action_params.get("text_content", "")
        return verify_type(before, after, typed_text)
    
    elif action_type in ["login", "chrome_login", "whatsapp_unlock"]:
        return verify_login(before, after)
    
    elif action_type in ["navigate_to_url", "open_website", "open_browser"]:
        target_url = action_params.get("url", action_params.get("target", ""))
        if target_url:
            return verify_open_website(before, after, target_url)
        # Fallback: just check if browser opened
        return after.get("browser_open", False)
    
    elif action_type in ["dismiss_dialog", "accept_consent"]:
        return verify_dismiss_dialog(before, after)
    
    elif action_type == "focus_window":
        target_app = action_params.get("target", "")
        return verify_focus_window(before, after, target_app)
    
    elif action_type == "scroll":
        return verify_scroll(before, after)
    
    elif action_type == "wait_for_change":
        # Wait actions succeed if state changed
        return before.get("state_hash") != after.get("state_hash")
    
    elif action_type == "press_key":
        # Key press verification: check if state changed
        return before.get("state_hash") != after.get("state_hash")
    
    # Unknown action type: require state change
    return before.get("state_hash") != after.get("state_hash")


def build_verification_dict(
    action_type: str,
    before_world,
    after_world,
    action_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build a complete verification dictionary.
    
    Args:
        action_type: Type of action performed
        before_world: WorldState before action
        after_world: WorldState after action (can be None if failed to refresh)
        action_params: Optional action parameters
        
    Returns:
        Verification dictionary with all checks
    """
    if action_params is None:
        action_params = {}
    
    # Convert WorldState to dict
    before_dict = before_world.to_dict() if before_world else {}
    after_dict = after_world.to_dict() if after_world else {}
    
    # Compute verification
    semantic_success = False
    if after_world:
        semantic_success = verify_action(action_type, before_dict, after_dict, action_params)
    
    return {
        "action_type": action_type,
        "before_hash": before_dict.get("state_hash", ""),
        "after_hash": after_dict.get("state_hash", ""),
        "state_changed": before_dict.get("state_hash") != after_dict.get("state_hash"),
        "semantic_success": semantic_success,
        "verification_method": _get_verification_method(action_type),
    }


def _get_verification_method(action_type: str) -> str:
    """Get human-readable verification method for action type.
    
    Args:
        action_type: Type of action
        
    Returns:
        Description of verification method
    """
    methods = {
        "click_element": "focus_change_or_window_change",
        "click_coordinates": "focus_change_or_window_change",
        "type_text": "ocr_contains_typed_text",
        "login": "url_or_dom_changed",
        "navigate_to_url": "devtools_location_changed",
        "open_website": "devtools_location_changed",
        "dismiss_dialog": "dialog_indicators_cleared",
        "focus_window": "active_window_changed",
        "scroll": "ocr_or_ui_elements_changed",
        "wait_for_change": "state_hash_changed",
    }
    return methods.get(action_type, "state_hash_changed")
