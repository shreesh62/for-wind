"""Repair strategy engine for self-repair system.

Maps diagnosed failures to concrete repair strategies that can be executed
to recover from failures and retry actions.
"""

from __future__ import annotations

from typing import List, Dict, Optional

from awareness.perception_snapshot import PerceptionSnapshot


class RepairStrategy:
    """Represents a single repair strategy."""
    
    def __init__(self, name: str, description: str, priority: int = 5):
        """Initialize repair strategy.
        
        Args:
            name: Strategy identifier
            description: Human-readable description
            priority: Priority (1=highest, 10=lowest)
        """
        self.name = name
        self.description = description
        self.priority = priority


class RepairStrategyEngine:
    """Determines which repair strategies to apply based on failure diagnosis."""
    
    # Strategy definitions with priorities
    STRATEGIES = {
        "dismiss_dialog": RepairStrategy(
            "dismiss_dialog",
            "Dismiss blocking dialog or modal",
            priority=1  # Highest priority - blocks everything
        ),
        "bring_browser_front": RepairStrategy(
            "bring_browser_front",
            "Bring Chrome browser to foreground",
            priority=2
        ),
        "refocus_window": RepairStrategy(
            "refocus_window",
            "Refocus the correct window",
            priority=3
        ),
        "retry_navigation": RepairStrategy(
            "retry_navigation",
            "Retry browser navigation",
            priority=4
        ),
        "refocus_and_retry": RepairStrategy(
            "refocus_and_retry",
            "Refocus element and retry action",
            priority=5
        ),
        "expand_search_scope": RepairStrategy(
            "expand_search_scope",
            "Expand element search with fuzzy matching",
            priority=6
        ),
        "retype": RepairStrategy(
            "retype",
            "Retype text input",
            priority=7
        ),
        "reexecute_with_delay": RepairStrategy(
            "reexecute_with_delay",
            "Wait for UI to settle and retry",
            priority=8
        ),
        "wait_for_network": RepairStrategy(
            "wait_for_network",
            "Wait for network request to complete",
            priority=9
        ),
    }
    
    def get_strategies(self, diagnosis: Dict[str, bool]) -> List[RepairStrategy]:
        """Get ordered list of repair strategies based on diagnosis.
        
        Args:
            diagnosis: Dict of failure conditions from FailureDiagnosis
            
        Returns:
            List of RepairStrategy objects, ordered by priority
        """
        strategies = []
        
        # Map diagnosis to strategies
        if diagnosis.get("blocked_by_dialog"):
            strategies.append(self.STRATEGIES["dismiss_dialog"])
        
        if diagnosis.get("browser_not_foreground"):
            strategies.append(self.STRATEGIES["bring_browser_front"])
        
        if diagnosis.get("wrong_window"):
            strategies.append(self.STRATEGIES["refocus_window"])
        
        if diagnosis.get("wrong_tab") or diagnosis.get("network_timeout"):
            strategies.append(self.STRATEGIES["retry_navigation"])
            strategies.append(self.STRATEGIES["wait_for_network"])
        
        if diagnosis.get("focus_lost"):
            strategies.append(self.STRATEGIES["refocus_and_retry"])
        
        if diagnosis.get("element_not_found"):
            strategies.append(self.STRATEGIES["expand_search_scope"])
            strategies.append(self.STRATEGIES["reexecute_with_delay"])
        
        if diagnosis.get("keyboard_input_missing") or diagnosis.get("ocr_expected_missing"):
            strategies.append(self.STRATEGIES["retype"])
        
        if diagnosis.get("state_unchanged"):
            strategies.append(self.STRATEGIES["reexecute_with_delay"])
        
        # Sort by priority (lower number = higher priority)
        strategies.sort(key=lambda s: s.priority)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_strategies = []
        for strategy in strategies:
            if strategy.name not in seen:
                seen.add(strategy.name)
                unique_strategies.append(strategy)
        
        return unique_strategies
    
    def get_strategy_description(self, diagnosis: Dict[str, bool]) -> str:
        """Get human-readable description of diagnosed failures.
        
        Args:
            diagnosis: Dict of failure conditions
            
        Returns:
            Human-readable failure description
        """
        failures = [key for key, value in diagnosis.items() if value]
        
        if not failures:
            return "Unknown failure"
        
        descriptions = {
            "element_not_found": "Target element not found in UI",
            "blocked_by_dialog": "Action blocked by modal dialog",
            "wrong_window": "Active window changed unexpectedly",
            "wrong_tab": "Browser tab/URL didn't change",
            "focus_lost": "UI focus was lost",
            "state_unchanged": "No observable state change occurred",
            "ocr_expected_missing": "Typed text not visible in OCR",
            "browser_not_foreground": "Chrome browser not in foreground",
            "keyboard_input_missing": "Keyboard input didn't register",
            "network_timeout": "Network request timed out",
        }
        
        failure_descriptions = [descriptions.get(f, f) for f in failures]
        return "; ".join(failure_descriptions)


def get_repair_strategies(diagnosis: Dict[str, bool]) -> List[RepairStrategy]:
    """Convenience function to get repair strategies.
    
    Args:
        diagnosis: Failure diagnosis dict
        
    Returns:
        List of repair strategies
    """
    engine = RepairStrategyEngine()
    return engine.get_strategies(diagnosis)


def describe_failure(diagnosis: Dict[str, bool]) -> str:
    """Convenience function to describe failure.
    
    Args:
        diagnosis: Failure diagnosis dict
        
    Returns:
        Human-readable failure description
    """
    engine = RepairStrategyEngine()
    return engine.get_strategy_description(diagnosis)
