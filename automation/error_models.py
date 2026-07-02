"""Error models: Classification and handling of action failures.

This module defines error types and provides classification logic
for understanding why actions fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorType(Enum):
    """Classification of action failure types."""
    
    # Element/target errors
    ELEMENT_NOT_FOUND = "element_not_found"
    TARGET_NOT_VISIBLE = "target_not_visible"
    TARGET_NOT_CLICKABLE = "target_not_clickable"
    
    # Focus/window errors
    FOCUS_LOST = "focus_lost"
    WINDOW_NOT_FOUND = "window_not_found"
    WRONG_WINDOW_ACTIVE = "wrong_window_active"
    
    # Authentication/permission errors
    PASSWORD_REJECTED = "password_rejected"
    LOGIN_REQUIRED = "login_required"
    PERMISSION_DENIED = "permission_denied"
    
    # Network/loading errors
    PAGE_NOT_LOADED = "page_not_loaded"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    
    # State errors
    UNEXPECTED_STATE = "unexpected_state"
    DIALOG_BLOCKING = "dialog_blocking"
    CONSENT_REQUIRED = "consent_required"
    
    # Execution errors
    ACTION_FAILED = "action_failed"
    VERIFICATION_FAILED = "verification_failed"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ActionError:
    """Represents a classified action failure."""
    
    error_type: ErrorType
    message: str
    action_type: Optional[str] = None
    target: Optional[str] = None
    recoverable: bool = True
    suggested_recovery: Optional[str] = None


def classify_error(
    action_type: str,
    error_message: str,
    world_state=None,
    verification: dict = None
) -> ActionError:
    """Classify an action failure into an ErrorType.
    
    Args:
        action_type: The type of action that failed
        error_message: The error message from execution
        world_state: Optional WorldState for context
        verification: Optional verification dict
        
    Returns:
        ActionError with classification and recovery suggestion
    """
    msg_lower = error_message.lower()
    
    # Element not found errors
    if "not found" in msg_lower or "not visible" in msg_lower:
        if world_state and (world_state.possible_error_dialog or world_state.possible_consent_dialog):
            return ActionError(
                error_type=ErrorType.DIALOG_BLOCKING,
                message=error_message,
                action_type=action_type,
                recoverable=True,
                suggested_recovery="dismiss_dialog_or_accept_consent",
            )
        return ActionError(
            error_type=ErrorType.ELEMENT_NOT_FOUND,
            message=error_message,
            action_type=action_type,
            recoverable=True,
            suggested_recovery="wait_and_retry_or_ocr_fallback",
        )
    
    # Focus errors
    if "focus" in msg_lower or "window" in msg_lower:
        return ActionError(
            error_type=ErrorType.FOCUS_LOST,
            message=error_message,
            action_type=action_type,
            recoverable=True,
            suggested_recovery="refocus_window",
        )
    
    # Login/auth errors
    if any(kw in msg_lower for kw in ["login", "password", "auth", "credential"]):
        if world_state and world_state.possible_login_screen:
            return ActionError(
                error_type=ErrorType.LOGIN_REQUIRED,
                message=error_message,
                action_type=action_type,
                recoverable=False,
                suggested_recovery="user_intervention_required",
            )
        return ActionError(
            error_type=ErrorType.PASSWORD_REJECTED,
            message=error_message,
            action_type=action_type,
            recoverable=False,
            suggested_recovery="user_intervention_required",
        )
    
    # Network/loading errors
    if any(kw in msg_lower for kw in ["network", "connection", "timeout", "load"]):
        return ActionError(
            error_type=ErrorType.PAGE_NOT_LOADED,
            message=error_message,
            action_type=action_type,
            recoverable=True,
            suggested_recovery="wait_and_retry",
        )
    
    # Consent/dialog errors
    if world_state and world_state.possible_consent_dialog:
        return ActionError(
            error_type=ErrorType.CONSENT_REQUIRED,
            message=error_message,
            action_type=action_type,
            recoverable=True,
            suggested_recovery="accept_consent",
        )
    
    # Verification failures
    if verification and not verification.get("state_changed"):
        return ActionError(
            error_type=ErrorType.VERIFICATION_FAILED,
            message="Action executed but expected state change did not occur",
            action_type=action_type,
            recoverable=True,
            suggested_recovery="verify_and_retry",
        )
    
    # Default: unknown error
    return ActionError(
        error_type=ErrorType.UNKNOWN_ERROR,
        message=error_message,
        action_type=action_type,
        recoverable=True,
        suggested_recovery="retry_or_skip",
    )


def should_retry(error: ActionError, retry_count: int = 0) -> bool:
    """Determine if an action should be retried given an error.
    
    Args:
        error: The classified error
        retry_count: Number of retries already attempted
        
    Returns:
        True if retry is recommended, False otherwise
    """
    if not error.recoverable:
        return False
    
    if retry_count >= 3:
        return False
    
    # Don't retry login/auth errors
    if error.error_type in [ErrorType.LOGIN_REQUIRED, ErrorType.PASSWORD_REJECTED]:
        return False
    
    # Retry most other errors
    if error.error_type in [
        ErrorType.ELEMENT_NOT_FOUND,
        ErrorType.FOCUS_LOST,
        ErrorType.PAGE_NOT_LOADED,
        ErrorType.TIMEOUT,
        ErrorType.VERIFICATION_FAILED,
    ]:
        return True
    
    return False


def get_recovery_action(error: ActionError):
    """Get a recovery action for an error.
    
    Args:
        error: The classified error
        
    Returns:
        Action or None if no recovery possible
    """
    from .semantic_actions import (
        create_wait_action,
        create_dismiss_dialog_action,
        create_accept_consent_action,
        create_focus_window_action,
    )
    
    if error.suggested_recovery == "dismiss_dialog_or_accept_consent":
        if "consent" in error.message.lower():
            return create_accept_consent_action()
        return create_dismiss_dialog_action()
    
    if error.suggested_recovery == "wait_and_retry":
        return create_wait_action("recovery_wait", timeout=2.0)
    
    if error.suggested_recovery == "refocus_window":
        return create_focus_window_action("active_window")
    
    if error.suggested_recovery == "accept_consent":
        return create_accept_consent_action()
    
    return None
