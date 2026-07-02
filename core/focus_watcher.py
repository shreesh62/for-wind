"""Focus-triggered passive capture system for training mode.

Replaces ENTER-based prompts with automatic window/screen detection.
"""

from __future__ import annotations

import time
from typing import Optional

from awareness.state_cache import StateCache
from awareness.perception_snapshot import PerceptionSnapshot


class FocusWatcher:
    """Passively watches for window focus and screen changes without terminal interaction."""
    
    def __init__(self, awareness_state: StateCache):
        """Initialize focus watcher.
        
        Args:
            awareness_state: StateCache for accessing perception data
        """
        self.awareness_state = awareness_state
        self.poll_interval = 0.2  # 200ms polling
    
    def wait_for_window(self, exe_contains: str, timeout: float = 30.0) -> bool:
        """Wait for a specific window to become focused.
        
        Args:
            exe_contains: Substring to match in process name (e.g., "chrome.exe")
            timeout: Maximum seconds to wait
            
        Returns:
            True if window was detected, False if timeout
            
        Raises:
            RuntimeError: If window never appears within timeout
        """
        start_time = time.time()
        exe_lower = exe_contains.lower()
        
        while time.time() - start_time < timeout:
            try:
                snapshot = self.awareness_state.get_snapshot()
                
                if snapshot and snapshot.get("active_window"):
                    active_window = snapshot.get("active_window", {})
                    app_exe = active_window.get("app_exe", "").lower()
                    
                    if exe_lower in app_exe:
                        return True
                
            except Exception:
                # Ignore perception errors during polling
                pass
            
            time.sleep(self.poll_interval)
        
        raise RuntimeError(
            f"{exe_contains} was never detected within {timeout}s. Training aborted."
        )
    
    def wait_for_screen_change(
        self,
        baseline_hash: str,
        timeout: float = 15.0,
        min_change_threshold: int = 5
    ) -> bool:
        """Wait for screen state to change from baseline.
        
        Args:
            baseline_hash: Initial screen hash to compare against
            timeout: Maximum seconds to wait
            min_change_threshold: Minimum hash difference to consider changed
            
        Returns:
            True if screen changed, False if timeout
            
        Raises:
            RuntimeError: If screen never changes within timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                world = self.awareness_state.build_world_state()
                if world:
                    snapshot = PerceptionSnapshot.from_world_state(world)
                    current_hash = snapshot.screen_hash
                    
                    # Check if hash changed significantly
                    if current_hash != baseline_hash:
                        # Simple hash difference check
                        if len(current_hash) != len(baseline_hash):
                            return True
                        
                        # Count differing characters
                        diff_count = sum(
                            c1 != c2 
                            for c1, c2 in zip(current_hash, baseline_hash)
                        )
                        
                        if diff_count >= min_change_threshold:
                            return True
                
            except Exception:
                # Ignore perception errors during polling
                pass
            
            time.sleep(self.poll_interval)
        
        raise RuntimeError(
            f"Screen did not change within {timeout}s. Unlock was not detected. Training aborted."
        )
    
    def get_current_snapshot(self) -> Optional[PerceptionSnapshot]:
        """Get current perception snapshot.
        
        Returns:
            PerceptionSnapshot or None if unavailable
        """
        try:
            world = self.awareness_state.build_world_state()
            if world:
                return PerceptionSnapshot.from_world_state(world)
        except Exception:
            pass
        
        return None
    
    def is_window_focused(self, exe_contains: str) -> bool:
        """Check if a specific window is currently focused.
        
        Args:
            exe_contains: Substring to match in process name
            
        Returns:
            True if window is focused
        """
        try:
            snapshot = self.awareness_state.get_snapshot()
            
            if snapshot and snapshot.get("active_window"):
                active_window = snapshot.get("active_window", {})
                app_exe = active_window.get("app_exe", "").lower()
                
                return exe_contains.lower() in app_exe
        except Exception:
            pass
        
        return False
