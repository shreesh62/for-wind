"""UI pattern memory: Learn from successful UI interactions.

This module extends vector memory to store UI patterns, layouts, and
button-success mappings tagged with UI hashes for learning.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from awareness.world_state import WorldState


@dataclass
class UIPattern:
    """Represents a learned UI pattern."""
    
    ui_hash: str
    goal_intent: str
    successful_action: str
    element_text: str
    element_type: str
    timestamp: float
    success_count: int = 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "UIPattern":
        """Create from dictionary."""
        return cls(**data)


class UIPatternMemory:
    """Stores and retrieves learned UI interaction patterns."""
    
    def __init__(self, storage_path: str = "ui_patterns.json"):
        self.storage_path = Path(storage_path)
        self.patterns: List[UIPattern] = []
        self._load()
    
    def _load(self) -> None:
        """Load patterns from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, list):
                self.patterns = [UIPattern.from_dict(p) for p in data if isinstance(p, dict)]
        except Exception:
            self.patterns = []
    
    def _save(self) -> None:
        """Save patterns to disk."""
        try:
            data = [p.to_dict() for p in self.patterns]
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def record_success(
        self,
        world_state: WorldState,
        goal_intent: str,
        action_type: str,
        element_text: str,
        element_type: str
    ) -> None:
        """Record a successful UI interaction.
        
        Args:
            world_state: The WorldState when action succeeded
            goal_intent: The goal intent (e.g., "navigate", "search")
            action_type: The action type that succeeded
            element_text: The text of the element that was interacted with
            element_type: The type of element (button, link, etc.)
        """
        ui_hash = world_state.compute_hash()
        
        # Check if we already have this pattern
        for pattern in self.patterns:
            if (pattern.ui_hash == ui_hash and 
                pattern.goal_intent == goal_intent and
                pattern.element_text.lower() == element_text.lower()):
                # Increment success count
                pattern.success_count += 1
                pattern.timestamp = time.time()
                self._save()
                return
        
        # Create new pattern
        new_pattern = UIPattern(
            ui_hash=ui_hash,
            goal_intent=goal_intent,
            successful_action=action_type,
            element_text=element_text,
            element_type=element_type,
            timestamp=time.time(),
            success_count=1,
        )
        
        self.patterns.append(new_pattern)
        self._save()
    
    def find_similar_patterns(
        self,
        world_state: WorldState,
        goal_intent: str,
        top_k: int = 3
    ) -> List[UIPattern]:
        """Find similar successful patterns for the current state.
        
        Args:
            world_state: Current WorldState
            goal_intent: Current goal intent
            top_k: Number of patterns to return
            
        Returns:
            List of similar patterns, ranked by success count
        """
        ui_hash = world_state.compute_hash()
        
        # First, try exact hash match
        exact_matches = [
            p for p in self.patterns
            if p.ui_hash == ui_hash and p.goal_intent == goal_intent
        ]
        
        if exact_matches:
            # Sort by success count
            exact_matches.sort(key=lambda p: p.success_count, reverse=True)
            return exact_matches[:top_k]
        
        # Fallback: match by goal intent only
        intent_matches = [
            p for p in self.patterns
            if p.goal_intent == goal_intent
        ]
        
        if intent_matches:
            # Sort by success count and recency
            intent_matches.sort(
                key=lambda p: (p.success_count, p.timestamp),
                reverse=True
            )
            return intent_matches[:top_k]
        
        return []
    
    def suggest_action(
        self,
        world_state: WorldState,
        goal_intent: str
    ) -> Optional[tuple[str, str]]:
        """Suggest an action based on learned patterns.
        
        Args:
            world_state: Current WorldState
            goal_intent: Current goal intent
            
        Returns:
            Tuple of (action_type, element_text) if suggestion available, else None
        """
        patterns = self.find_similar_patterns(world_state, goal_intent, top_k=1)
        
        if patterns:
            best = patterns[0]
            return (best.successful_action, best.element_text)
        
        return None
    
    def get_statistics(self) -> dict:
        """Get statistics about learned patterns.
        
        Returns:
            Dictionary with pattern statistics
        """
        if not self.patterns:
            return {
                "total_patterns": 0,
                "unique_intents": 0,
                "total_successes": 0,
            }
        
        unique_intents = set(p.goal_intent for p in self.patterns)
        total_successes = sum(p.success_count for p in self.patterns)
        
        return {
            "total_patterns": len(self.patterns),
            "unique_intents": len(unique_intents),
            "total_successes": total_successes,
            "intents": list(unique_intents),
        }


# Global instance
_ui_pattern_memory: Optional[UIPatternMemory] = None


def get_ui_pattern_memory() -> UIPatternMemory:
    """Get the global UI pattern memory instance."""
    global _ui_pattern_memory
    if _ui_pattern_memory is None:
        _ui_pattern_memory = UIPatternMemory()
    return _ui_pattern_memory
