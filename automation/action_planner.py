"""Action planner: Generate semantic action plans from state gaps.

This module converts missing states into concrete action sequences
without any site-specific knowledge. Everything is derived from WorldState.
"""

from __future__ import annotations

from typing import List

from awareness.world_state import WorldState
from .semantic_actions import (
    Action,
    ActionType,
    create_open_browser_action,
    create_navigate_action,
    create_click_element_action,
    create_type_text_action,
    create_search_action,
    create_dismiss_dialog_action,
    create_accept_consent_action,
    create_focus_window_action,
    create_wait_action,
)
from .ui_pattern_memory import get_ui_pattern_memory


def build_action_plan(missing_states: List[str], world_state: WorldState, goal_intent: str = None) -> List[Action]:
    """Build a sequence of actions to resolve missing states.
    
    This is a rule-based planner that generates actions based purely on
    what's missing and what's currently visible in the world state.
    Enhanced with learned pattern suggestions when available.
    
    Args:
        missing_states: List of missing state identifiers
        world_state: Current observed world state
        goal_intent: Optional goal intent for pattern matching
        
    Returns:
        Ordered list of actions to execute
    """
    plan = []
    
    # Try to use learned patterns first
    if goal_intent:
        ui_memory = get_ui_pattern_memory()
        suggested = ui_memory.suggest_action(world_state, goal_intent)
        if suggested:
            action_type, element_text = suggested
            plan.append(Action(
                type=action_type,
                target=element_text,
                expected_change=f"{goal_intent}_via_pattern",
            ))
    
    # Handle blockers first (dialogs, errors)
    if "error_dialog_present" in missing_states:
        plan.append(create_dismiss_dialog_action())
        plan.append(create_wait_action("dialog_dismissed", timeout=2.0))
    
    if "consent_dialog_present" in missing_states:
        plan.append(create_accept_consent_action())
        plan.append(create_wait_action("consent_accepted", timeout=2.0))
    
    if "login_required" in missing_states:
        # We can't automatically handle login - this requires user intervention
        # For now, we'll just note it and continue
        pass
    
    # Handle application/browser opening
    if "browser_not_open" in missing_states:
        plan.append(create_open_browser_action())
        plan.append(create_wait_action("browser_opened", timeout=3.0))
    
    if "whatsapp_not_open" in missing_states:
        # Open WhatsApp web
        plan.append(create_open_browser_action())
        plan.append(create_navigate_action("https://web.whatsapp.com"))
        plan.append(create_wait_action("whatsapp_loaded", timeout=5.0))
    
    if "instagram_not_open" in missing_states:
        # Open Instagram web
        plan.append(create_open_browser_action())
        plan.append(create_navigate_action("https://www.instagram.com"))
        plan.append(create_wait_action("instagram_loaded", timeout=5.0))
    
    if "email_client_not_open" in missing_states:
        # Open Gmail
        plan.append(create_open_browser_action())
        plan.append(create_navigate_action("https://mail.google.com"))
        plan.append(create_wait_action("gmail_loaded", timeout=5.0))
    
    # Handle navigation
    if "navigation_not_performed" in missing_states:
        # We need to navigate, but we need the target URL
        # This should be derived from the goal's target_entity
        # For now, we'll create a placeholder that the execution engine will fill
        plan.append(Action(
            type=ActionType.NAVIGATE_TO_URL,
            target="goal_target",
            expected_change="page_loaded",
        ))
        plan.append(create_wait_action("navigation_complete", timeout=5.0))
    
    # Handle search
    if "search_not_performed" in missing_states:
        # Look for a search box in the current world state
        search_box_found = False
        for elem in world_state.ui_elements:
            if "search" in elem.text.lower() or elem.control_type == "Edit":
                search_box_found = True
                break
        
        if search_box_found:
            # Click search box, then type query
            plan.append(create_click_element_action("search"))
            plan.append(Action(
                type=ActionType.TYPE_TEXT,
                target="search_box",
                expected_change="query_entered",
                text_content="goal_search_query",  # Placeholder
            ))
            plan.append(Action(
                type=ActionType.PRESS_KEY,
                target="Enter",
                expected_change="search_submitted",
            ))
        else:
            # Navigate to a search engine first
            plan.append(create_navigate_action("https://www.google.com"))
            plan.append(create_wait_action("google_loaded", timeout=3.0))
            plan.append(create_search_action("goal_search_query"))  # Placeholder
    
    # Handle recipient selection
    if "recipient_not_selected" in missing_states:
        # Look for a contact search or new message button
        new_message_found = False
        for elem in world_state.ui_elements:
            if "new" in elem.text.lower() and ("message" in elem.text.lower() or "chat" in elem.text.lower()):
                new_message_found = True
                plan.append(create_click_element_action(elem.text))
                break
        
        if not new_message_found:
            # Try OCR
            for word in world_state.ocr_words:
                if "new" in word.text.lower():
                    new_message_found = True
                    plan.append(Action(
                        type=ActionType.CLICK_COORDINATES,
                        target="new_message",
                        expected_change="compose_opened",
                        coordinates=(word.bbox[0], word.bbox[1]),
                    ))
                    break
        
        # Type recipient name
        plan.append(Action(
            type=ActionType.TYPE_TEXT,
            target="recipient_field",
            expected_change="recipient_entered",
            text_content="goal_recipient",  # Placeholder
        ))
        plan.append(create_wait_action("recipient_selected", timeout=2.0))
    
    # Handle message typing
    if "message_not_typed" in missing_states:
        # Find message input field
        message_field_found = False
        for elem in world_state.ui_elements:
            if elem.focused and elem.control_type in ["Edit", "Document"]:
                message_field_found = True
                break
        
        if not message_field_found:
            # Try to find and click message field
            for elem in world_state.ui_elements:
                if "message" in elem.text.lower() or "type" in elem.text.lower():
                    plan.append(create_click_element_action(elem.text))
                    break
        
        plan.append(Action(
            type=ActionType.TYPE_TEXT,
            target="message_field",
            expected_change="message_typed",
            text_content="goal_message_content",  # Placeholder
        ))
        
        # Send message (look for send button)
        for elem in world_state.ui_elements:
            if "send" in elem.text.lower():
                plan.append(create_click_element_action(elem.text))
                break
    
    # Handle compose window
    if "compose_window_not_open" in missing_states:
        # Look for compose button
        for elem in world_state.ui_elements:
            if "compose" in elem.text.lower():
                plan.append(create_click_element_action(elem.text))
                plan.append(create_wait_action("compose_opened", timeout=2.0))
                break
    
    # Handle click targets
    if "target_not_visible" in missing_states:
        # Target element is not visible - might need to scroll or navigate
        # For now, we'll just note this as a failure condition
        pass
    
    # Handle focus
    if "target_app_not_focused" in missing_states:
        plan.append(Action(
            type=ActionType.FOCUS_WINDOW,
            target="goal_target_app",  # Placeholder
            expected_change="window_focused",
        ))
    
    # Handle input focus
    if "no_focused_input" in missing_states:
        # Try to find and click an input field
        for elem in world_state.ui_elements:
            if elem.control_type in ["Edit", "Document"]:
                plan.append(create_click_element_action(elem.text or "input_field"))
                break
    
    return plan


def simplify_plan(plan: List[Action]) -> List[Action]:
    """Remove redundant actions from a plan.
    
    Args:
        plan: Original action plan
        
    Returns:
        Simplified plan with redundancies removed
    """
    if not plan:
        return plan
    
    simplified = []
    seen_types = set()
    
    for action in plan:
        # Skip duplicate wait actions
        if action.type == ActionType.WAIT_FOR_CHANGE:
            if "wait" in seen_types:
                continue
            seen_types.add("wait")
        
        # Skip duplicate browser open actions
        if action.type == ActionType.OPEN_BROWSER:
            if ActionType.OPEN_BROWSER in seen_types:
                continue
            seen_types.add(ActionType.OPEN_BROWSER)
        
        simplified.append(action)
    
    return simplified


def validate_plan(plan: List[Action], world_state: WorldState) -> bool:
    """Validate that a plan is executable given the current world state.
    
    Args:
        plan: Action plan to validate
        world_state: Current world state
        
    Returns:
        True if plan appears executable, False otherwise
    """
    if not plan:
        return False
    
    # Check first action is feasible
    first_action = plan[0]
    
    # Can't click if nothing is visible
    if first_action.type == ActionType.CLICK_ELEMENT:
        if not world_state.ui_elements and not world_state.ocr_words:
            return False
    
    # Can't type if no input is available
    if first_action.type == ActionType.TYPE_TEXT:
        if not world_state.focused_element:
            # Check if there's at least one input element
            has_input = any(
                elem.control_type in ["Edit", "Document"]
                for elem in world_state.ui_elements
            )
            if not has_input:
                return False
    
    return True
