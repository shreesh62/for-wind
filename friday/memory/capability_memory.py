"""Capability Memory (M21 slice 2 / A2.11) — persistent, queryable capability view.

The fifth of the seven FAS §A2.11.1 tiers. It is a memory VIEW, **not** an
authority: the evidence-only ``CompetenceModel`` (Ch 28) remains the sole
authority on competence. This tier merely subscribes to ``competence.updated``
and records what the authority *reported* — a queryable, reflective memory of
capability outcomes keyed by ``(capability, environment)`` — so planning /
deliberation can ask "what do we know about capability X in environment Y" and
have past outcomes inform future decisions.

Memory-not-authority (Requirement 2.3): this module performs NO competence math,
never recomputes or overrides the ``CompetenceModel``, exposes no gate /
confidence-authority method, and deliberately does NOT import
``friday.competence``. It stores only the values carried on the event.

Design:
- Reuses the existing bounded ``JSONFileStore`` (auto-evicts oldest → bounded
  storage); no new persistence mechanism.
- Kernel-driven and defensive: handlers never raise into the bus.
- Upserts by ``(capability, environment)`` so there is at most one current record
  per key (no unbounded duplicates).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class CapabilityRecord:
    """One remembered capability outcome (JSON-projectable)."""

    capability: str
    environment: str = ""
    confidence: float = 0.0
    attempts: int = 0
    summary: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_memory_entry(self) -> MemoryEntry:
        content = (
            f"Capability '{self.capability}' in env='{self.environment or '-'}' "
            f"(confidence={self.confidence:.2f}, attempts={self.attempts})"
        )
        return MemoryEntry(
            content=content,
            tier=MemoryTier.CAPABILITY,
            timestamp=self.timestamp,
            tags=["capability", self.capability or "", self.environment or ""],
            metadata={
                "capability": self.capability,
                "environment": self.environment,
                "confidence": self.confidence,
                "attempts": self.attempts,
                "summary": self.summary,
            },
        )


class CapabilityMemory:
    """Persistent, queryable memory VIEW of capability outcomes.

    NOT a competence authority: the ``CompetenceModel`` (Ch 28) remains the sole
    authority on competence. This tier records only what ``competence.updated``
    reported and performs no competence computation of its own.
    """

    def __init__(
        self,
        store_path: str = "friday_data/capability_memory.json",
        max_entries: int = 2000,
    ) -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=max_entries)
        self._kernel: Any = None

    # --------------------------------------------------------------- wiring

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``competence.updated`` (Ch 52 — kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("competence.updated", self._on_competence)

    def _on_competence(self, event: Any) -> None:
        """Record/update the capability memory from a ``competence.updated`` event.

        Reads the payload defensively and never raises into the bus. Records only
        what the authority reported (memory-not-authority); a missing/empty
        ``capability`` skips the update entirely.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            capability = payload.get("capability") or ""
            if not capability:
                return  # malformed / empty event — nothing to remember
            self.record_capability(
                capability=capability,
                environment=payload.get("environment", "") or "",
                confidence=float(payload.get("confidence", 0.0) or 0.0),
                attempts=int(payload.get("attempts", 0) or 0),
                summary=str(payload.get("summary", "") or ""),
            )
        except Exception:  # noqa: BLE001 — memory must never break the bus
            # Narrow degrade-to-no-op: a memory view must never propagate into the
            # kernel tick loop. BaseException (e.g. KeyboardInterrupt) still escapes.
            return

    # ---------------------------------------------------------------- record

    def record_capability(
        self,
        *,
        capability: str,
        environment: str = "",
        confidence: float = 0.0,
        attempts: int = 0,
        summary: str = "",
    ) -> str:
        """Record a capability outcome, upserting by ``(capability, environment)``.

        Returns the stored entry id. Any prior record for the same key is deleted
        first so there is at most one current record per key (no unbounded
        duplicates). Stores only the reported values — no competence math.
        """
        self._delete_existing(capability, environment)
        record = CapabilityRecord(
            capability=capability,
            environment=environment,
            confidence=confidence,
            attempts=attempts,
            summary=summary,
        )
        return self._store.store(record.to_memory_entry())

    def _delete_existing(self, capability: str, environment: str) -> None:
        """Delete the newest existing entry matching ``(capability, environment)``."""
        for entry in self._store.list_recent(limit=self._store.count() or 1):
            m = entry.metadata
            if m.get("capability") == capability and m.get("environment") == environment:
                self._store.delete(entry.entry_id)
                return

    # ----------------------------------------------------------------- query

    def recall(
        self,
        *,
        capability: Optional[str] = None,
        environment: Optional[str] = None,
        limit: int = 10,
    ) -> List[CapabilityRecord]:
        """Return recent capability records filtered by capability/environment."""
        out: List[CapabilityRecord] = []
        for entry in self._store.list_recent(limit=max(limit * 5, 50)):
            m = entry.metadata
            if capability is not None and m.get("capability") != capability:
                continue
            if environment is not None and m.get("environment") != environment:
                continue
            out.append(self._entry_to_record(entry))
            if len(out) >= limit:
                break
        return out

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Uniform retrieval surface (for the M19 Retrieval Router): relevance-
        ranked capability entries for ``query``. Delegates to the backing store."""
        return self._store.retrieve(query, top_k=top_k)

    @staticmethod
    def _entry_to_record(entry: MemoryEntry) -> CapabilityRecord:
        m = entry.metadata
        return CapabilityRecord(
            capability=m.get("capability", ""),
            environment=m.get("environment", ""),
            confidence=float(m.get("confidence", 0.0) or 0.0),
            attempts=int(m.get("attempts", 0) or 0),
            summary=m.get("summary", ""),
            timestamp=entry.timestamp,
        )

    def clear(self) -> None:
        self._store.clear()
