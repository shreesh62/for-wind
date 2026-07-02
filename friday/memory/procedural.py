"""Procedural Memory — learned action patterns and repair strategies.

Stores successful UI interaction patterns and repair outcomes so
FRIDAY can learn from experience. When a similar situation is
encountered, procedural memory suggests proven strategies.

Bridges the existing ui_pattern_memory.py (wraps, doesn't replace).

Inspired by Memory OS procedural layer + Supermemory retrieval patterns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class ActionPattern:
    """A learned pattern for successful action execution."""

    action_type: str
    target_description: str
    context_hash: str  # WorldState hash when this pattern worked
    steps: List[str]  # Ordered steps that succeeded
    success_count: int = 1
    last_used: float = 0.0
    avg_duration_ms: float = 0.0
    repair_strategy: Optional[str] = None  # What repair worked if initial failed
    tags: List[str] = field(default_factory=list)

    def to_memory_entry(self) -> MemoryEntry:
        content = f"Pattern: {self.action_type} on {self.target_description} ({self.success_count} successes)"
        return MemoryEntry(
            content=content,
            tier=MemoryTier.PROCEDURAL,
            timestamp=self.last_used or time.time(),
            tags=self.tags + [self.action_type],
            metadata={
                "action_type": self.action_type,
                "target": self.target_description,
                "context_hash": self.context_hash,
                "steps": self.steps,
                "success_count": self.success_count,
                "avg_duration_ms": self.avg_duration_ms,
                "repair_strategy": self.repair_strategy,
            },
        )


@dataclass
class RepairOutcome:
    """Record of a repair attempt and its outcome."""

    failure_type: str
    repair_strategy: str
    succeeded: bool
    action_type: str
    context_description: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class ProceduralMemory:
    """Manages learned action patterns and repair strategies.

    Usage:
        proc = ProceduralMemory()

        # Record a successful pattern
        proc.record_success(ActionPattern(
            action_type="click",
            target_description="Submit button on login form",
            context_hash="abc123",
            steps=["focus_window", "find_element", "click"],
        ))

        # Later, suggest a strategy for similar situation
        suggestion = proc.suggest_strategy("click", "abc123")
    """

    def __init__(self, store_path: str = "friday_data/procedural_memory.json") -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=2000)
        self._repair_log: List[RepairOutcome] = []

    def record_success(self, pattern: ActionPattern) -> None:
        """Record a successful action pattern."""
        # Check if we already have this pattern (update count)
        existing = self._find_matching_pattern(
            pattern.action_type, pattern.context_hash
        )
        if existing:
            # Update existing
            meta = existing.metadata
            meta["success_count"] = meta.get("success_count", 0) + 1
            meta["avg_duration_ms"] = (
                (meta.get("avg_duration_ms", 0) + pattern.avg_duration_ms) / 2
            )
            existing.timestamp = time.time()
            # Re-store (update in place via delete+store)
            self._store.delete(existing.entry_id)
            self._store.store(existing)
        else:
            pattern.last_used = time.time()
            self._store.store(pattern.to_memory_entry())

    def record_repair(self, outcome: RepairOutcome) -> None:
        """Record a repair attempt outcome."""
        self._repair_log.append(outcome)
        # Also store as memory entry for retrieval
        entry = MemoryEntry(
            content=f"Repair: {outcome.repair_strategy} for {outcome.failure_type} -> {'success' if outcome.succeeded else 'failed'}",
            tier=MemoryTier.PROCEDURAL,
            timestamp=outcome.timestamp,
            tags=["repair", outcome.failure_type, outcome.action_type],
            metadata={
                "failure_type": outcome.failure_type,
                "repair_strategy": outcome.repair_strategy,
                "succeeded": outcome.succeeded,
                "action_type": outcome.action_type,
                "context": outcome.context_description,
            },
        )
        self._store.store(entry)

    def suggest_strategy(
        self, action_type: str, context_hash: str
    ) -> Optional[List[str]]:
        """Suggest a proven strategy for an action in this context.

        Returns ordered steps that previously succeeded, or None.
        """
        match = self._find_matching_pattern(action_type, context_hash)
        if match and match.metadata.get("success_count", 0) >= 1:
            return match.metadata.get("steps", [])
        return None

    def suggest_repair(self, failure_type: str, action_type: str) -> Optional[str]:
        """Suggest a repair strategy based on past outcomes.

        Returns the most successful repair strategy for this failure type.
        """
        # Check repair log for successful repairs
        successful_repairs: Dict[str, int] = {}
        for outcome in self._repair_log:
            if outcome.failure_type == failure_type and outcome.succeeded:
                key = outcome.repair_strategy
                successful_repairs[key] = successful_repairs.get(key, 0) + 1

        if successful_repairs:
            return max(successful_repairs, key=successful_repairs.get)

        # Fall back to stored memory
        entries = self._store.retrieve(f"repair {failure_type}", top_k=5)
        for entry in entries:
            if entry.metadata.get("succeeded") and entry.metadata.get("failure_type") == failure_type:
                return entry.metadata.get("repair_strategy")

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get procedural memory statistics."""
        total = self._store.count()
        recent = self._store.list_recent(limit=50)

        action_types: Dict[str, int] = {}
        total_successes = 0
        for entry in recent:
            atype = entry.metadata.get("action_type", "unknown")
            action_types[atype] = action_types.get(atype, 0) + 1
            total_successes += entry.metadata.get("success_count", 0)

        return {
            "total_patterns": total,
            "total_successes": total_successes,
            "action_types": action_types,
            "repair_outcomes": len(self._repair_log),
        }

    def _find_matching_pattern(
        self, action_type: str, context_hash: str
    ) -> Optional[MemoryEntry]:
        """Find a stored pattern matching action type and context."""
        entries = self._store.retrieve(action_type, top_k=20)
        for entry in entries:
            if (entry.metadata.get("action_type") == action_type and
                entry.metadata.get("context_hash") == context_hash):
                return entry
        return None

    def clear(self) -> None:
        """Clear all procedural memory."""
        self._store.clear()
        self._repair_log.clear()
