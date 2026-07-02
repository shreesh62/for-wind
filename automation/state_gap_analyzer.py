"""State gap analyzer: Identify missing states between current world and goal.

This module performs rule-based analysis to determine what needs to change
in the WorldState to satisfy a Goal. No LLM, no guessing, only logic.
"""

from __future__ import annotations

from typing import List

from awareness.world_state import WorldState
from .goal_schema import Goal


def compute_missing_states(goal: Goal, world: WorldState) -> List[str]:
    """Compute what is missing to achieve the goal.
    
    This is a pure rule-based function that analyzes the gap between
    the current WorldState and the desired Goal.
    
    Args:
        goal: The desired end state
        world: The current observed state
        
    Returns:
        List of missing state identifiers (e.g., "browser_not_open", "login_required")
    """
    missing = []
    
    # Navigation goals
    if goal.intent == "navigate":
        if not world.browser_open:
            missing.append("browser_not_open")
        elif goal.target_entity:
            # Check if we're already on the target
            target_lower = goal.target_entity.lower()
            on_target = False
            
            if world.browser_url and target_lower in world.browser_url.lower():
                on_target = True
            elif world.browser_title and target_lower in world.browser_title.lower():
                on_target = True
            
            if not on_target:
                missing.append("navigation_not_performed")
            
            # Check for common blockers
            if world.possible_login_screen:
                missing.append("login_required")
            if world.possible_consent_dialog:
                missing.append("consent_dialog_present")
            if world.possible_error_dialog:
                missing.append("error_dialog_present")
    
    # Search goals
    elif goal.intent == "search":
        if not world.browser_open:
            missing.append("browser_not_open")
        else:
            # Check if search was performed
            search_performed = False
            if world.browser_url:
                search_indicators = ["search", "query", "q=", "results"]
                if any(ind in world.browser_url.lower() for ind in search_indicators):
                    search_performed = True
            
            if not search_performed:
                missing.append("search_not_performed")
            
            # Check for blockers
            if world.possible_login_screen:
                missing.append("login_required")
            if world.possible_consent_dialog:
                missing.append("consent_dialog_present")
    
    # Message sending goals
    elif goal.intent == "send_message":
        # Determine which app should be active
        if goal.target_app == "whatsapp":
            if "whatsapp" not in world.active_app.lower() and not (
                world.browser_open and world.browser_url and "whatsapp" in world.browser_url.lower()
            ):
                missing.append("whatsapp_not_open")
        elif goal.target_app == "instagram":
            if "instagram" not in world.active_app.lower() and not (
                world.browser_open and world.browser_url and "instagram" in world.browser_url.lower()
            ):
                missing.append("instagram_not_open")
        else:
            # Generic messaging
            if not world.browser_open:
                missing.append("messaging_app_not_open")
        
        # Check if recipient is selected
        if goal.target_entity:
            recipient_found = False
            target_lower = goal.target_entity.lower()
            
            # Check UI elements for recipient name
            for elem in world.ui_elements:
                if target_lower in elem.text.lower():
                    recipient_found = True
                    break
            
            # Check OCR for recipient name
            if not recipient_found:
                for word in world.ocr_words:
                    if target_lower in word.text.lower():
                        recipient_found = True
                        break
            
            if not recipient_found:
                missing.append("recipient_not_selected")
        
        # Check if message is typed
        if goal.message_content:
            # This is hard to verify without seeing the input field
            # We'll assume it needs to be typed
            missing.append("message_not_typed")
        
        # Check for blockers
        if world.possible_login_screen:
            missing.append("login_required")
    
    # Email composition goals
    elif goal.intent == "compose_email":
        # Check if email client is open
        email_open = False
        if world.browser_open and world.browser_url:
            if "mail.google.com" in world.browser_url.lower() or "gmail" in world.browser_url.lower():
                email_open = True
        
        if not email_open:
            missing.append("email_client_not_open")
        
        # Check if compose window is active
        compose_active = False
        for elem in world.ui_elements:
            if "compose" in elem.text.lower() or "new message" in elem.text.lower():
                compose_active = True
                break
        
        if not compose_active:
            missing.append("compose_window_not_open")
        
        if world.possible_login_screen:
            missing.append("login_required")
    
    # Click goals
    elif goal.intent == "click":
        if not goal.target_entity:
            missing.append("target_not_specified")
        else:
            # Check if target element is visible
            target_found = world.find_element_by_text(goal.target_entity)
            if not target_found:
                target_found = world.find_ocr_word(goal.target_entity)
            if not target_found:
                target_found = world.find_browser_element(goal.target_entity)
            
            if not target_found:
                missing.append("target_not_visible")
    
    # Type goals
    elif goal.intent == "type":
        # Check if there's a focused input element
        if not world.focused_element:
            missing.append("no_focused_input")
        elif world.focused_element.control_type not in ["Edit", "Document", "Text"]:
            missing.append("focused_element_not_input")
    
    # Focus goals
    elif goal.intent == "focus":
        if goal.target_app:
            target_lower = goal.target_app.lower()
            if target_lower not in world.active_app.lower() and target_lower not in world.active_window_title.lower():
                missing.append("target_app_not_focused")
    
    # Read content goals
    elif goal.intent == "read_content":
        # Check if there's visible content to read
        if not world.ui_elements and not world.ocr_words and not world.browser_elements:
            missing.append("no_visible_content")
    
    return missing


def is_goal_satisfied(goal: Goal, world: WorldState) -> bool:
    """Check if a goal is fully satisfied in the current world state.
    
    Args:
        goal: The goal to check
        world: The current world state
        
    Returns:
        True if goal is satisfied, False otherwise
    """
    missing = compute_missing_states(goal, world)
    return len(missing) == 0


def describe_missing_states(missing_states: List[str]) -> str:
    """Convert missing state identifiers into human-readable descriptions.
    
    Args:
        missing_states: List of missing state identifiers
        
    Returns:
        Human-readable description of what's missing
    """
    if not missing_states:
        return "Goal is satisfied."
    
    descriptions = {
        "browser_not_open": "Browser is not open",
        "navigation_not_performed": "Not on the target page",
        "login_required": "Login screen detected",
        "consent_dialog_present": "Consent dialog blocking",
        "error_dialog_present": "Error dialog present",
        "search_not_performed": "Search has not been performed",
        "whatsapp_not_open": "WhatsApp is not open",
        "instagram_not_open": "Instagram is not open",
        "messaging_app_not_open": "Messaging app is not open",
        "recipient_not_selected": "Recipient not selected",
        "message_not_typed": "Message not typed",
        "email_client_not_open": "Email client is not open",
        "compose_window_not_open": "Compose window is not open",
        "target_not_specified": "Click target not specified",
        "target_not_visible": "Target element is not visible",
        "no_focused_input": "No input field is focused",
        "focused_element_not_input": "Focused element is not an input field",
        "target_app_not_focused": "Target application is not focused",
        "no_visible_content": "No visible content to read",
    }
    
    result = []
    for state in missing_states:
        desc = descriptions.get(state, state)
        result.append(f"• {desc}")
    
    return "\n".join(result)
