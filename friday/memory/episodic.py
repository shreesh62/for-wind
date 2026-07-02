"""Episodic Memory — interaction history and session logs.

Stores past interactions for:
- Long-term context (what happened before)
- Pattern recognition (repeated requests)
- User preference inference
- Debugging (what went wrong)

Persistent: survives restarts. Grows over time with consolidation.
Backend: JSONFileStore (upgradeable to SQLite/MongoDB).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class Episode:
    """A recorded interaction episode."""

    user_text: str
    assistant_response: str
    mode: str = "jarvis"  # jarvis or friday
    timestamp: float = 0.0
    action_type: Optional[str] = None
    action_success: Optional[bool] = None
    complexity_level: int = 0
    duration_ms: float = 0.0
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_memory_entry(self) -> MemoryEntry:
        """Convert to generic MemoryEntry for storage."""
        content = f"User: {self.user_text}\nAssistant: {self.assistant_response}"
        return MemoryEntry(
            content=content,
            tier=MemoryTier.EPISODIC,
            timestamp=self.timestamp,
            tags=self.tags + [self.mode],
            metadata={
                "user_text": self.user_text,
                "assistant_response": self.assistant_response,
                "mode": self.mode,
                "action_type": self.action_type,
                "action_success": self.action_success,
                "complexity": self.complexity_level,
                "duration_ms": self.duration_ms,
            },
        )


class EpisodicMemory:
    """Manages interaction history with retrieval and analysis.

    Usage:
        episodic = EpisodicMemory()
        episodic.record(Episode(
            user_text="Open Chrome",
            assistant_response="Chrome opened.",
            mode="friday",
            action_success=True,
        ))

        # Later, retrieve relevant past interactions
        relevant = episodic.recall("chrome")
    """

    def __init__(self, store_path: str = "friday_data/episodic_memory.json") -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=5000)

    def record(self, episode: Episode) -> str:
        """Record an interaction episode."""
        entry = episode.to_memory_entry()
        return self._store.store(entry)

    def recall(self, query: str, top_k: int = 5) -> List[Episode]:
        """Recall past episodes relevant to a query."""
        entries = self._store.retrieve(query, top_k=top_k)
        return [self._entry_to_episode(e) for e in entries]

    def recent(self, limit: int = 10) -> List[Episode]:
        """Get most recent episodes."""
        entries = self._store.list_recent(limit=limit)
        return [self._entry_to_episode(e) for e in entries]

    def get_success_rate(self, action_type: Optional[str] = None) -> float:
        """Calculate success rate for actions (overall or by type)."""
        entries = self._store.list_recent(limit=100)
        relevant = []
        for e in entries:
            meta = e.metadata
            if meta.get("action_success") is not None:
                if action_type is None or meta.get("action_type") == action_type:
                    relevant.append(meta["action_success"])

        if not relevant:
            return 0.0
        return sum(1 for s in relevant if s) / len(relevant)

    def get_frequent_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most frequently used commands."""
        entries = self._store.list_recent(limit=500)
        command_counts: Dict[str, int] = {}
        for e in entries:
            user_text = e.metadata.get("user_text", "")
            if user_text:
                key = user_text.lower().strip()
                command_counts[key] = command_counts.get(key, 0) + 1

        sorted_commands = sorted(command_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"command": cmd, "count": count} for cmd, count in sorted_commands[:limit]]

    @property
    def total_episodes(self) -> int:
        return self._store.count()

    def clear(self) -> None:
        """Clear all episodic memory."""
        self._store.clear()

    def _entry_to_episode(self, entry: MemoryEntry) -> Episode:
        """Convert MemoryEntry back to Episode."""
        meta = entry.metadata
        return Episode(
            user_text=meta.get("user_text", ""),
            assistant_response=meta.get("assistant_response", ""),
            mode=meta.get("mode", "jarvis"),
            timestamp=entry.timestamp,
            action_type=meta.get("action_type"),
            action_success=meta.get("action_success"),
            complexity_level=meta.get("complexity", 0),
            duration_ms=meta.get("duration_ms", 0),
            tags=entry.tags,
        )
