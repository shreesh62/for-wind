"""Failure detection and diagnosis engine for self-repair system.

This module analyzes before/after perception snapshots to determine
exactly why an action failed, enabling targeted repair strategies.
"""

from __future__ import annotations

from typing import Dict

from awareness.perception_snapshot import PerceptionSnapshot


class FailureDiagnosis:
    """Diagnoses why an action failed by comparing before/after snapshots."""
    
    def __init__(
        self,
        before: PerceptionSnapshot,
        after: PerceptionSnapshot,
        action,
        expected_target: str = None
    ):
        """Initialize failure diagnosis.
        
        Args:
            before: Perception snapshot before action
            after: Perception snapshot after action
            action: The action that was executed
            expected_target: Expected element text/target
        """
        self.before = before
        self.after = after
        self.action = action
        self.expected_target = expected_target or getattr(action, 'target', None)
    
    def diagnose(self) -> Dict[str, bool]:
        """Diagnose all possible failure conditions.
        
        Returns:
            Dict mapping failure types to boolean detection results
        """
        return {
            "element_not_found": self._detect_element_not_found(),
            "blocked_by_dialog": self._detect_blocked_by_dialog(),
            "wrong_window": self._detect_wrong_window(),
            "wrong_tab": self._detect_wrong_tab(),
            "focus_lost": self._detect_focus_lost(),
            "state_unchanged": self._detect_state_unchanged(),
            "ocr_expected_missing": self._detect_ocr_expected_missing(),
            "browser_not_foreground": self._detect_browser_not_foreground(),
            "keyboard_input_missing": self._detect_keyboard_input_missing(),
            "network_timeout": self._detect_network_timeout(),
        }
    
    def _detect_element_not_found(self) -> bool:
        """Detect if requested element was not found.
        
        Returns:
            True if element was requested but not found in after snapshot
        """
        if not self.expected_target:
            return False
        
        # REAL IMPLEMENTATION: Check if element exists in after snapshot
        elem = self.after.find_element_by_text(self.expected_target, fuzzy=True)
        if elem is not None:
            return False
        
        # Also check if ANY elements were found
        if len(self.after.elements) == 0:
            return True
        
        return True
    
    def _detect_blocked_by_dialog(self) -> bool:
        """Detect if a modal/dialog appeared and blocked the action.
        
        Returns:
            True if dialog/modal present in after but not before
        """
        # REAL IMPLEMENTATION: Check browser error flags
        if self.after.browser.has_error and not self.before.browser.has_error:
            return True
        
        # Check consent dialogs
        if self.after.browser.has_consent_dialog and not self.before.browser.has_consent_dialog:
            return True
        
        # Check for modal keywords appearing in OCR
        modal_keywords = {"ok", "cancel", "close", "dismiss", "error", "warning", "alert", "accept", "deny"}
        
        before_ocr = {e.text.lower() for e in self.before.elements if e.source == "ocr" and e.text}
        after_ocr = {e.text.lower() for e in self.after.elements if e.source == "ocr" and e.text}
        
        # New modal words that appeared
        new_modal_words = (after_ocr & modal_keywords) - (before_ocr & modal_keywords)
        
        # At least 2 modal keywords appeared = likely dialog
        return len(new_modal_words) >= 2
    
    def _detect_wrong_window(self) -> bool:
        """Detect if active window changed incorrectly.
        
        Returns:
            True if window changed but shouldn't have
        """
        # REAL IMPLEMENTATION: Compare actual window titles
        before_window = self.before.active_window_title
        after_window = self.after.active_window_title
        
        if before_window == after_window:
            return False
        
        # Action types that should NOT change window
        safe_actions = ["type_text", "click_element", "scroll", "click_coordinates"]
        action_type = getattr(self.action, 'type', '')
        
        # Window changed when it shouldn't have
        return any(safe in action_type for safe in safe_actions)
    
    def _detect_wrong_tab(self) -> bool:
        """Detect if browser URL didn't change when it should have.
        
        Returns:
            True if navigation action but URL unchanged
        """
        # REAL IMPLEMENTATION: Check actual browser URLs
        action_type = getattr(self.action, 'type', '')
        is_navigation = any(nav in action_type for nav in ["navigate", "open", "search", "url"])
        
        if not is_navigation:
            return False
        
        # Get actual URLs from snapshots
        before_url = self.before.browser.url or ""
        after_url = self.after.browser.url or ""
        
        # URL should have changed but didn't
        if before_url == after_url and self.before.browser.open:
            return True
        
        # Also check if browser title changed
        before_title = self.before.browser.title or ""
        after_title = self.after.browser.title or ""
        
        return before_title == after_title and self.before.browser.open
    
    def _detect_focus_lost(self) -> bool:
        """Detect if focused element was lost.
        
        Returns:
            True if focus was lost during action
        """
        # REAL IMPLEMENTATION: Compare focused elements from snapshots
        before_focused = self.before.find_focused_element()
        after_focused = self.after.find_focused_element()
        
        # Had focus before, lost it after
        if before_focused and not after_focused:
            return True
        
        # Focus changed unexpectedly for non-click actions
        if before_focused and after_focused:
            before_text = before_focused.text or ""
            after_text = after_focused.text or ""
            
            if before_text != after_text:
                action_type = getattr(self.action, 'type', '')
                # Click actions are expected to change focus
                if "click" not in action_type and "focus" not in action_type:
                    return True
        
        return False
    
    def _detect_state_unchanged(self) -> bool:
        """Detect if perception state didn't change at all.
        
        Returns:
            True if state hash identical before and after
        """
        return self.before.screen_hash == self.after.screen_hash
    
    def _detect_ocr_expected_missing(self) -> bool:
        """Detect if expected OCR text is missing after typing.
        
        Returns:
            True if typed text not found in OCR
        """
        action_type = getattr(self.action, 'type', '')
        if "type" not in action_type:
            return False
        
        # Get text that was typed
        typed_text = getattr(self.action, 'text_content', None)
        if not typed_text:
            return False
        
        # Check if any word from typed text appears in OCR
        typed_words = set(typed_text.lower().split())
        after_ocr = {e.text.lower() for e in self.after.elements if e.source == "ocr"}
        
        # At least one word should appear
        overlap = typed_words & after_ocr
        return len(overlap) == 0
    
    def _detect_browser_not_foreground(self) -> bool:
        """Detect if browser action attempted but Chrome not active.
        
        Returns:
            True if browser action but Chrome not foreground
        """
        # REAL IMPLEMENTATION: Check actual active app from snapshot
        action_type = getattr(self.action, 'type', '')
        is_browser_action = any(
            kw in action_type 
            for kw in ["navigate", "browser", "search", "url", "open_website"]
        )
        
        if not is_browser_action:
            return False
        
        # Get actual active app from after snapshot
        active_app = self.after.active_app.lower()
        active_window = self.after.active_window_title.lower()
        
        # Chrome should be active but isn't
        chrome_active = "chrome" in active_app or "chrome" in active_window
        
        return not chrome_active and self.after.browser.open
    
    def _detect_keyboard_input_missing(self) -> bool:
        """Detect if keyboard input didn't register.
        
        Returns:
            True if type action but no evidence of input
        """
        # REAL IMPLEMENTATION: Check if typed text appears in perception
        action_type = getattr(self.action, 'type', '')
        if "type" not in action_type:
            return False
        
        # Get the text that was typed
        typed_text = getattr(self.action, 'text_content', None)
        if not typed_text:
            return False
        
        # Check if typed text appears in OCR or UI elements
        typed_lower = typed_text.lower()
        
        # Check OCR words
        after_ocr = {e.text.lower() for e in self.after.elements if e.source == "ocr" and e.text}
        if any(word in after_ocr for word in typed_lower.split()):
            return False
        
        # Check UI element texts
        after_ui = {e.text.lower() for e in self.after.elements if e.source == "uia" and e.text}
        if any(word in after_ui for word in typed_lower.split()):
            return False
        
        # No evidence of typed text found
        return True
    
    def _detect_network_timeout(self) -> bool:
        """Detect if network request timed out.
        
        Returns:
            True if navigation action but no browser change
        """
        # REAL IMPLEMENTATION: Check for navigation timeout
        action_type = getattr(self.action, 'type', '')
        is_navigation = "navigate" in action_type or "url" in action_type or "open_website" in action_type
        
        if not is_navigation:
            return False
        
        # Get actual browser state from snapshots
        before_url = self.before.browser.url or ""
        after_url = self.after.browser.url or ""
        before_title = self.before.browser.title or ""
        after_title = self.after.browser.title or ""
        
        # No change in URL AND no change in title = likely timeout
        url_unchanged = before_url == after_url
        title_unchanged = before_title == after_title
        
        # Also check if browser has error flag
        has_error = self.after.browser.has_error
        
        return (url_unchanged and title_unchanged) or has_error


def diagnose_failure(
    before: PerceptionSnapshot,
    after: PerceptionSnapshot,
    action,
    expected_target: str = None
) -> Dict[str, bool]:
    """Convenience function to diagnose a failure.
    
    Args:
        before: Snapshot before action
        after: Snapshot after action
        action: Action that was executed
        expected_target: Expected element target
        
    Returns:
        Dict of failure conditions
    """
    diagnosis = FailureDiagnosis(before, after, action, expected_target)
    return diagnosis.diagnose()
