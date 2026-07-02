"""Semantic Memory — facts, knowledge, and embedding-based retrieval.

The semantic tier stores durable facts and knowledge with vector
embeddings for similarity search. Unlike episodic memory (events),
semantic memory holds generalized knowledge:
- User facts ("Shreesh prefers DOM over screenshots")
- Learned facts about apps/sites ("Gmail compose button is top-left")
- General knowledge the user wants remembered

Embeddings via NVIDIA nv-embed-v1 (with graceful fallback to lexical).

Inspired by Memory OS semantic layer + Supermemory retrieval patterns.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class Fact:
    """A semantic fact with optional embedding and temporal validity.

    Temporal edges (Memory OS pattern): facts carry valid_at/invalid_at
    timestamps instead of being overwritten. Updating a fact invalidates
    the old version rather than destroying history. Enables temporal
    reasoning ("what did I believe last week?") and clean knowledge updates.
    """

    content: str
    category: str = "general"  # general, user, app, site, preference
    confidence: float = 1.0
    embedding: Optional[List[float]] = None
    source: str = ""
    timestamp: float = 0.0
    access_count: int = 0
    valid_at: float = 0.0           # When this fact became valid
    invalid_at: Optional[float] = None  # When superseded/invalidated (None = still valid)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.valid_at:
            self.valid_at = self.timestamp

    @property
    def is_currently_valid(self) -> bool:
        """Whether this fact is currently valid (not invalidated)."""
        return self.invalid_at is None

    def to_memory_entry(self) -> MemoryEntry:
        return MemoryEntry(
            content=self.content,
            tier=MemoryTier.SEMANTIC,
            timestamp=self.timestamp,
            tags=[self.category],
            metadata={
                "category": self.category,
                "confidence": self.confidence,
                "embedding": self.embedding,
                "source": self.source,
                "access_count": self.access_count,
                "valid_at": self.valid_at,
                "invalid_at": self.invalid_at,
            },
        )


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticMemory:
    """Knowledge store with embedding-based semantic search.

    Uses NVIDIA nv-embed-v1 for embeddings when a provider is available,
    falls back to lexical (keyword) search otherwise.

    Usage:
        sem = SemanticMemory(embedding_provider=nvidia_provider)
        sem.add_fact(Fact(content="Shreesh prefers DOM over screenshots",
                          category="preference"))

        # Semantic retrieval
        results = sem.search("how should I perceive the screen?")
    """

    def __init__(
        self,
        store_path: str = "friday_data/semantic_memory.json",
        embedding_provider=None,
    ) -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=3000)
        self._embedding_provider = embedding_provider

    @property
    def has_embeddings(self) -> bool:
        """Whether embedding-based search is available."""
        return (
            self._embedding_provider is not None
            and getattr(self._embedding_provider, "available", False)
            and hasattr(self._embedding_provider, "embed")
        )

    def add_fact(self, fact: Fact) -> str:
        """Add a fact to semantic memory.

        Computes embedding if a provider is available.
        """
        if self.has_embeddings and fact.embedding is None:
            fact.embedding = self._compute_embedding(fact.content)

        return self._store.store(fact.to_memory_entry())

    def add_facts(self, facts: List[Fact]) -> List[str]:
        """Add multiple facts."""
        return [self.add_fact(f) for f in facts]

    def search(self, query: str, top_k: int = 5, include_invalid: bool = False) -> List[Fact]:
        """Search facts by semantic similarity (embeddings) or lexical fallback.

        Args:
            query: Search query
            top_k: Number of results
            include_invalid: If True, include invalidated (historical) facts

        Returns:
            List of relevant facts, ranked by similarity (valid facts only by default)
        """
        if self.has_embeddings:
            results = self._semantic_search(query, top_k * 2 if not include_invalid else top_k)
        else:
            results = self._lexical_search(query, top_k * 2 if not include_invalid else top_k)

        if not include_invalid:
            results = [f for f in results if f.is_currently_valid]

        return results[:top_k]

    def update_fact(self, old_content: str, new_content: str, category: str = "general") -> bool:
        """Update a fact via temporal edges: invalidate old, add new.

        Preserves history instead of overwriting (Memory OS pattern).

        Returns True if an old fact was found and invalidated.
        """
        invalidated = self.invalidate(old_content)
        self.add_fact(Fact(content=new_content, category=category))
        return invalidated

    def invalidate(self, content_substring: str) -> bool:
        """Mark matching facts as invalid (sets invalid_at) without deleting.

        Returns True if any fact was invalidated.
        """
        now = time.time()
        entries = self._store.list_recent(limit=3000)
        found = False
        for entry in entries:
            if (content_substring.lower() in entry.content.lower()
                    and entry.metadata.get("invalid_at") is None):
                entry.metadata["invalid_at"] = now
                self._store.delete(entry.entry_id)
                self._store.store(entry)
                found = True
        return found

    def get_facts_by_category(self, category: str) -> List[Fact]:
        """Get all facts in a category."""
        entries = self._store.list_recent(limit=1000)
        facts = []
        for entry in entries:
            if entry.metadata.get("category") == category:
                facts.append(self._entry_to_fact(entry))
        return facts

    def get_user_preferences(self) -> List[Fact]:
        """Get all user preference facts."""
        return self.get_facts_by_category("preference")

    @property
    def total_facts(self) -> int:
        return self._store.count()

    def clear(self) -> None:
        self._store.clear()

    def _semantic_search(self, query: str, top_k: int) -> List[Fact]:
        """Embedding-based similarity search."""
        query_embedding = self._compute_embedding(query)
        if not query_embedding:
            return self._lexical_search(query, top_k)

        entries = self._store.list_recent(limit=3000)
        scored: List[tuple] = []

        for entry in entries:
            emb = entry.metadata.get("embedding")
            if emb:
                sim = _cosine_similarity(query_embedding, emb)
                scored.append((sim, entry))
            else:
                # No embedding — lexical fallback score
                if query.lower() in entry.content.lower():
                    scored.append((0.5, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._entry_to_fact(e) for _, e in scored[:top_k]]

    def _lexical_search(self, query: str, top_k: int) -> List[Fact]:
        """Keyword-based fallback search."""
        entries = self._store.retrieve(query, top_k=top_k)
        return [self._entry_to_fact(e) for e in entries]

    def _compute_embedding(self, text: str) -> Optional[List[float]]:
        """Compute an embedding via the NVIDIA provider."""
        if not self.has_embeddings:
            return None
        try:
            # embed() is async; run it appropriately
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self._embedding_provider.embed(text)
                    )
                    return future.result(timeout=30)
            except RuntimeError:
                return asyncio.run(self._embedding_provider.embed(text))
        except Exception:
            return None

    def _entry_to_fact(self, entry: MemoryEntry) -> Fact:
        meta = entry.metadata
        return Fact(
            content=entry.content,
            category=meta.get("category", "general"),
            confidence=meta.get("confidence", 1.0),
            embedding=meta.get("embedding"),
            source=meta.get("source", ""),
            timestamp=entry.timestamp,
            access_count=meta.get("access_count", 0),
            valid_at=meta.get("valid_at", entry.timestamp),
            invalid_at=meta.get("invalid_at"),
        )
