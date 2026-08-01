"""Preference Memory (M21 / A2.11) — persistent, queryable user preferences.

One of the two seventh-tier completions. It persists durable user preferences as
upsertable ``(key, value)`` records (with an optional description) so FRIDAY's
behavior can respect them across sessions — distinct from the volatile
working-memory context that clears between sessions.

Bus note (Axiom 15 — no invented event types):
    A grep of the kernel event stream (``event_type=`` emitters and ``kernel.subscribe``
    consumers) found NO preference/user-preference event type on the bus today. The
    only preference-shaped constructs in the codebase are non-bus: semantic-memory
    ``Fact(category="preference")`` and the ``CognitiveIdentity.preferences`` direct
    API — neither is a published kernel event. Therefore this tier does NOT invent an
    application-specific event type. It is driven by its direct ``record_preference``
    API and, when attached, stores the kernel handle but subscribes to nothing. If a
    real preference event type is later introduced on the bus, ``attach`` is the single
    place to wire it (via the defensive ``_on_preference`` handler already provided).

Design:
- Reuses the existing bounded ``JSONFileStore`` (auto-evicts oldest → bounded storage);
  no new persistence mechanism.
- Mirrors ``FailureMemory``: ``attach(kernel)``, defensive handler that never raises,
  a direct ``record_*`` API, ``get``/``all`` queries, and the uniform
  ``retrieve(query, top_k)`` surface for the M19 Retrieval Router.
- Upsert semantics: at most one record per key; a newer value supersedes the older.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class PreferenceRecord:
    """One remembered user preference (JSON-projectable).

    M25 additive fields (after existing ones) extend the record with contextual
    scope, confidence, lifecycle counters, and provenance. Existing callers that
    construct ``PreferenceRecord(key=..., value=...)`` continue to work — new
    fields have safe defaults that preserve prior behavior.
    """

    key: str
    value: Any
    description: str = ""
    timestamp: float = 0.0
    # --- M25 additive fields (safe defaults preserve prior behavior) ---
    context_scope: str = ""             # "goal:<id>", "env:<name>", "category:<cat>", or ""
    preference_class: str = "contextual"  # one-time | session | contextual | general | credential-ref
    confidence: float = 0.5             # empirical confidence [0, 1]
    reuse_count: int = 0                # how many times successfully reapplied
    last_verified: float = 0.0          # timestamp of last successful application
    corrections: int = 0                # how many times corrected
    superseded_by: str = ""             # key of the preference that superseded this one
    provenance: str = ""                # how this preference was learned (explicit/repeated/inferred)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_memory_entry(self) -> MemoryEntry:
        content = (
            f"Preference {self.key}={self.value}"
            + (f" ({self.description})" if self.description else "")
        )
        return MemoryEntry(
            content=content,
            tier=MemoryTier.PREFERENCE,
            timestamp=self.timestamp,
            tags=["preference", self.key],
            metadata={
                "key": self.key,
                "value": self.value,
                "description": self.description,
                "context_scope": self.context_scope,
                "preference_class": self.preference_class,
                "confidence": self.confidence,
                "reuse_count": self.reuse_count,
                "last_verified": self.last_verified,
                "corrections": self.corrections,
                "superseded_by": self.superseded_by,
                "provenance": self.provenance,
            },
        )


class PreferenceMemory:
    """Persistent, queryable, upsertable memory of user preferences."""

    def __init__(
        self,
        store_path: str = "friday_data/preference_memory.json",
        max_entries: int = 1000,
    ) -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=max_entries)
        self._kernel: Any = None

    # --------------------------------------------------------------- wiring

    def attach(self, kernel: Any) -> None:
        """Store the kernel handle.

        No preference event type exists on the bus today (see module docstring —
        Axiom 15: no invented event types), so this tier subscribes to nothing and
        is driven by its direct ``record_preference`` API. If a real preference
        event type is introduced later, subscribe to it here and route it through
        the defensive ``_on_preference`` handler below.
        """
        self._kernel = kernel

    def _on_preference(self, event: Any) -> None:
        """Defensive handler for a (future) preference event. Never raises into the bus.

        Reads ``key``/``value``/``description`` defensively from the event payload and
        upserts the preference. Currently unused (no such event type exists) but kept
        so wiring a real event type later is a one-line ``attach`` change.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            if not payload:
                return  # malformed / empty event — nothing to remember
            key = payload.get("key", "") or ""
            if not key or "value" not in payload:
                return  # a complete preference requires both a key and a value
            self.record_preference(
                key=str(key),
                value=payload["value"],
                description=str(payload.get("description", "") or ""),
            )
        except Exception:  # noqa: BLE001 — memory must never break the bus
            return

    # ---------------------------------------------------------------- record

    def record_preference(self, key: str, value: Any, description: str = "") -> str:
        """Record a preference; UPSERT by ``key`` (newer supersedes). Returns entry id.

        Deletes any existing store entry whose metadata ``key`` matches, then stores
        the new record — so at most one record per key survives and the latest value
        wins. Keys and descriptions are normalized to strings; JSON-projectable
        values are preserved exactly (including ``False``, ``0``, and ``None``).
        """
        key = str(key)
        description = str(description)
        # Remove any prior record for this key (upsert — newest supersedes).
        for entry in self._store.list_recent(limit=self._store.count() or 1):
            if str(entry.metadata.get("key", "")) == key:
                self._store.delete(entry.entry_id)
        record = PreferenceRecord(key=key, value=value, description=description)
        return self._store.store(record.to_memory_entry())

    # ----------------------------------------------------------------- query

    def get(self, key: str) -> Optional[PreferenceRecord]:
        """Return the current record for ``key`` or ``None``."""
        key = str(key)
        for entry in self._store.list_recent(limit=self._store.count() or 1):
            if str(entry.metadata.get("key", "")) == key:
                return self._entry_to_record(entry)
        return None

    def all(self) -> List[PreferenceRecord]:
        """Return all current preference records."""
        return [
            self._entry_to_record(entry)
            for entry in self._store.list_recent(limit=self._store.count() or 1)
        ]

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Uniform retrieval surface (for the Retrieval Router): relevance-ranked
        preference entries for ``query``. Delegates to the backing store."""
        return self._store.retrieve(query, top_k=top_k)

    @staticmethod
    def _entry_to_record(entry: MemoryEntry) -> PreferenceRecord:
        m = entry.metadata
        return PreferenceRecord(
            key=m.get("key", ""),
            value=m.get("value", ""),
            description=m.get("description", ""),
            timestamp=entry.timestamp,
            context_scope=m.get("context_scope", ""),
            preference_class=m.get("preference_class", "contextual"),
            confidence=float(m.get("confidence", 0.5)),
            reuse_count=int(m.get("reuse_count", 0)),
            last_verified=float(m.get("last_verified", 0.0)),
            corrections=int(m.get("corrections", 0)),
            superseded_by=m.get("superseded_by", ""),
            provenance=m.get("provenance", ""),
        )

    def clear(self) -> None:
        self._store.clear()
