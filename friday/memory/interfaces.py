"""Memory interfaces — framework-agnostic contracts for memory layers.

Designed for future synchronization across harnesses (unified agentic memory).
Each memory tier implements a common protocol so backends can be swapped
(local JSON → SQLite → MongoDB → Supermemory) without changing business logic.

Inspired by Memory OS 6-layer architecture:
1. Working Memory — current task context
2. Episodic Memory — interaction history
3. Procedural Memory — learned action patterns
4. Semantic Memory — facts and knowledge
5. User Memory — preferences and profiles
6. Long-Term Consolidation — periodic review + compression
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class MemoryTier(str, Enum):
    """Memory tier identifiers."""

    WORKING = "working"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"
    USER = "user"
    FAILURE = "failure"        # M21 slice 1 — persistent failure memory (consumes M24 failures)
    CAPABILITY = "capability"  # M21 slice 2 — capability memory view (from competence.updated)
    PREFERENCE = "preference"  # M21 slice 2 — persistent user preferences


@dataclass
class MemoryEntry:
    """Universal memory entry that any tier can store/retrieve."""

    content: str
    tier: MemoryTier
    timestamp: float = 0.0
    relevance_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    entry_id: str = ""
    expires_at: Optional[float] = None  # None = never expires

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        import time
        return time.time() > self.expires_at


class MemoryStore(ABC):
    """Abstract interface for a memory storage backend.

    Any memory tier implements this. Backends can be swapped:
    - JSONFileStore (local, default)
    - SQLiteStore (local, structured)
    - MongoStore (cloud, future — GitHub Student Pack)
    - VectorStore (semantic search, future)
    """

    @abstractmethod
    def store(self, entry: MemoryEntry) -> str:
        """Store an entry. Returns entry_id."""
        ...

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Retrieve entries by relevance to query."""
        ...

    @abstractmethod
    def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a specific entry by ID."""
        ...

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """Delete an entry. Returns True if found and deleted."""
        ...

    @abstractmethod
    def list_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """List most recent entries."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total entries in this store."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries."""
        ...
