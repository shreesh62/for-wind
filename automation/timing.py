"""State-based timing utilities for cognitive loop.

This module replaces fixed time.sleep() calls with state-based polling.
Actions wait for actual state changes, not arbitrary time periods.
"""

from __future__ import annotations

import time
from typing import Callable, Optional


def wait_until(
    condition: Callable[[], bool],
    timeout: float = 6.0,
    poll_interval: float = 0.2,
    description: str = "condition"
) -> bool:
    """Wait until a condition becomes true or timeout occurs.
    
    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum seconds to wait
        poll_interval: Seconds between condition checks
        description: Human-readable description for logging
        
    Returns:
        True if condition met, False if timeout
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if condition():
                return True
        except Exception:
            pass
        
        time.sleep(poll_interval)
    
    return False


def wait_for_state_change(
    get_state_hash: Callable[[], str],
    timeout: float = 6.0,
    poll_interval: float = 0.3
) -> bool:
    """Wait for state hash to change.
    
    Args:
        get_state_hash: Callable that returns current state hash
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if state changed, False if timeout
    """
    try:
        initial_hash = get_state_hash()
    except Exception:
        return False
    
    def state_changed():
        try:
            current_hash = get_state_hash()
            return current_hash != initial_hash
        except Exception:
            return False
    
    return wait_until(state_changed, timeout, poll_interval, "state_change")


def wait_for_browser_navigation(
    get_browser_url: Callable[[], Optional[str]],
    timeout: float = 8.0,
    poll_interval: float = 0.4
) -> bool:
    """Wait for browser URL to change.
    
    Args:
        get_browser_url: Callable that returns current browser URL
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if URL changed, False if timeout
    """
    try:
        initial_url = get_browser_url()
    except Exception:
        return False
    
    def url_changed():
        try:
            current_url = get_browser_url()
            return current_url != initial_url
        except Exception:
            return False
    
    return wait_until(url_changed, timeout, poll_interval, "browser_navigation")


def wait_for_element_visible(
    find_element: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.2
) -> bool:
    """Wait for an element to become visible.
    
    Args:
        find_element: Callable that returns True if element found
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if element found, False if timeout
    """
    return wait_until(find_element, timeout, poll_interval, "element_visible")


def wait_for_focus_change(
    get_focused_element: Callable[[], Optional[str]],
    timeout: float = 3.0,
    poll_interval: float = 0.15
) -> bool:
    """Wait for focused element to change.
    
    Args:
        get_focused_element: Callable that returns focused element identifier
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if focus changed, False if timeout
    """
    try:
        initial_focus = get_focused_element()
    except Exception:
        return False
    
    def focus_changed():
        try:
            current_focus = get_focused_element()
            return current_focus != initial_focus
        except Exception:
            return False
    
    return wait_until(focus_changed, timeout, poll_interval, "focus_change")


def wait_for_window_change(
    get_active_window: Callable[[], str],
    timeout: float = 4.0,
    poll_interval: float = 0.2
) -> bool:
    """Wait for active window to change.
    
    Args:
        get_active_window: Callable that returns active window title
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if window changed, False if timeout
    """
    try:
        initial_window = get_active_window()
    except Exception:
        return False
    
    def window_changed():
        try:
            current_window = get_active_window()
            return current_window != initial_window
        except Exception:
            return False
    
    return wait_until(window_changed, timeout, poll_interval, "window_change")


def wait_for_dialog_dismissed(
    check_dialog_present: Callable[[], bool],
    timeout: float = 3.0,
    poll_interval: float = 0.2
) -> bool:
    """Wait for dialog to be dismissed.
    
    Args:
        check_dialog_present: Callable that returns True if dialog still present
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks
        
    Returns:
        True if dialog dismissed, False if timeout
    """
    def dialog_gone():
        try:
            return not check_dialog_present()
        except Exception:
            return False
    
    return wait_until(dialog_gone, timeout, poll_interval, "dialog_dismissed")
