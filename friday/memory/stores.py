"""Memory stores — concrete backend implementations.

Local-first. JSON for simplicity, with path to SQLite and cloud.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier


class JSONFileStore(MemoryStore):
    """JSON file-backed memory store. Simple, local, human-readable.

    Good for: development, small datasets, debugging.
    Scales to: ~10k entries comfortably.
    Future upgrade path: SQLite or MongoDB Atlas (Student Pack).
    """

    def __init__(self, file_path: str, max_entries: int = 5000) -> None:
        self._path = Path(file_path)
        self._max_entries = max_entries
        self._entries: List[MemoryEntry] = []
        self._load()

    def store(self, entry: MemoryEntry) -> str:
        """Store an entry. Auto-generates ID if empty."""
        if not entry.entry_id:
            entry.entry_id = str(uuid.uuid4())[:8]
        if not entry.timestamp:
            entry.timestamp = time.time()

        self._entries.append(entry)

        # Bounded growth — remove oldest when at capacity
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._save()
        return entry.entry_id

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Retrieve entries by text similarity (basic keyword matching).

        For production, upgrade to embedding-based retrieval via
        NVIDIA nv-embed-v1 or local sentence-transformers.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored: List[tuple] = []
        for entry in self._entries:
            if entry.expired:
                continue
            # Simple scoring: word overlap + recency bonus
            content_lower = entry.content.lower()
            content_words = set(content_lower.split())
            overlap = len(query_words & content_words)
            if overlap == 0 and query_lower not in content_lower:
                continue

            # Score: overlap + substring bonus + recency
            score = overlap * 2.0
            if query_lower in content_lower:
                score += 5.0
            # Recency bonus (decays over 30 days)
            age_days = (time.time() - entry.timestamp) / 86400
            recency = max(0, 1.0 - age_days / 30)
            score += recency

            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def delete(self, entry_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def list_recent(self, limit: int = 10) -> List[MemoryEntry]:
        valid = [(i, e) for i, e in enumerate(self._entries) if not e.expired]
        ordered = sorted(valid, key=lambda pair: (pair[1].timestamp, pair[0]), reverse=True)
        return [e for _, e in ordered[:limit]]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._entries = [
                    MemoryEntry(
                        content=item.get("content", ""),
                        tier=MemoryTier(item.get("tier", "working")),
                        timestamp=item.get("timestamp", 0),
                        relevance_score=item.get("relevance_score", 0),
                        tags=item.get("tags", []),
                        metadata=item.get("metadata", {}),
                        entry_id=item.get("entry_id", ""),
                        expires_at=item.get("expires_at"),
                    )
                    for item in data
                    if isinstance(item, dict)
                ]
        except Exception:
            self._entries = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "content": e.content,
                "tier": e.tier.value,
                "timestamp": e.timestamp,
                "relevance_score": e.relevance_score,
                "tags": e.tags,
                "metadata": e.metadata,
                "entry_id": e.entry_id,
                "expires_at": e.expires_at,
            }
            for e in self._entries
        ]
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
