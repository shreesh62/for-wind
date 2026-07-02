"""Goal schema: Formal representation of user intent.

This module defines the Goal dataclass that represents what the user
wants to achieve, independent of how it will be accomplished.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Goal:
    """Formal representation of user intent.
    
    A Goal describes WHAT the user wants, not HOW to achieve it.
    The system must figure out the HOW by analyzing the current WorldState.
    
    Examples:
        "Open GitHub" ->
            Goal(target_app="browser", target_entity="github.com",
                 intent="navigate", desired_effect="github_page_visible")
        
        "Send message to Rahul saying hello" ->
            Goal(target_app="messaging", target_entity="Rahul",
                 intent="send_message", desired_effect="message_delivered")
        
        "Find today's stock news" ->
            Goal(target_app="browser", target_entity="stock news",
                 intent="search", desired_effect="search_results_visible")
    """
    
    target_app: Optional[str]
    target_entity: Optional[str]
    intent: str
    desired_effect: str
    
    # Additional context
    message_content: Optional[str] = None
    search_query: Optional[str] = None
    
    def __str__(self) -> str:
        """Human-readable representation of the goal."""
        parts = [f"Intent: {self.intent}"]
        if self.target_app:
            parts.append(f"App: {self.target_app}")
        if self.target_entity:
            parts.append(f"Entity: {self.target_entity}")
        parts.append(f"Desired: {self.desired_effect}")
        return " | ".join(parts)
    
    def is_satisfied(self, world_state) -> bool:
        """Check if this goal is satisfied in the given world state.
        
        This is a high-level check. Detailed verification happens in
        the state gap analyzer.
        """
        from awareness.world_state import WorldState
        
        if not isinstance(world_state, WorldState):
            return False
        
        # Navigation goals
        if self.intent == "navigate" and self.target_entity:
            if not world_state.browser_open:
                return False
            if world_state.browser_url and self.target_entity.lower() in world_state.browser_url.lower():
                return True
            if world_state.browser_title and self.target_entity.lower() in world_state.browser_title.lower():
                return True
            return False
        
        # Search goals
        if self.intent == "search":
            if not world_state.browser_open:
                return False
            # Check if search results are visible (heuristic)
            if world_state.browser_url and "search" in world_state.browser_url.lower():
                return True
            return False
        
        # Message sending goals
        if self.intent == "send_message":
            # This would require more sophisticated verification
            # For now, we can't verify message delivery without explicit confirmation
            return False
        
        # Default: not satisfied
        return False
