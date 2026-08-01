"""Failure Memory (M21 / A2.11) — persistent, queryable memory of failures.

The seventh memory tier. It is a CONSUMER of the M24 failure→recovery loop: it
subscribes to `verification.completed` (failures) and `recovery.proposed`, records
a structured `FailureRecord` per failure, and annotates it with the recovery that
was proposed. Planning/deliberation can then ask "have we failed at this before,
and what happened?" so past failures inform future decisions instead of being
silently repeated.

Design:
- Reuses the existing bounded `JSONFileStore` (auto-evicts oldest → bounded storage,
  audit objective 10/11); no new persistence mechanism.
- Consumes M24 `StructuredFailure` directly via `record_structured(...)`, and the
  kernel event stream via `attach(kernel)` — no duplicate failure taxonomy.
- Kernel-driven and defensive: handlers never raise into the bus.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.stores import JSONFileStore


@dataclass
class FailureRecord:
    """One remembered failure (JSON-projectable)."""

    requirement: str
    domain: str = "unknown"
    category: str = ""
    capability: str = ""
    environment: str = ""
    goal_id: str = ""
    severity: int = 1
    message: str = ""
    recoverable: bool = True
    recovery_class: str = ""       # filled from a matching recovery.proposed
    recovery_actionable: bool = False
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_memory_entry(self) -> MemoryEntry:
        content = (
            f"Failure [{self.domain}] on '{self.requirement[:80]}' "
            f"(capability={self.capability or '-'}, env={self.environment or '-'})"
        )
        return MemoryEntry(
            content=content,
            tier=MemoryTier.FAILURE,
            timestamp=self.timestamp,
            tags=["failure", self.domain, self.capability or "", self.environment or ""],
            metadata={
                "requirement": self.requirement,
                "domain": self.domain,
                "category": self.category,
                "capability": self.capability,
                "environment": self.environment,
                "goal_id": self.goal_id,
                "severity": self.severity,
                "message": self.message,
                "recoverable": self.recoverable,
                "recovery_class": self.recovery_class,
                "recovery_actionable": self.recovery_actionable,
            },
        )


class FailureMemory:
    """Persistent, queryable memory of failures + their proposed recoveries."""

    def __init__(
        self,
        store_path: str = "friday_data/failure_memory.json",
        max_entries: int = 2000,
    ) -> None:
        self._store: MemoryStore = JSONFileStore(store_path, max_entries=max_entries)
        self._kernel: Any = None

    # --------------------------------------------------------------- wiring

    def attach(self, kernel: Any) -> None:
        """Subscribe to the M24 failure/recovery events (Ch 52 — kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("verification.completed", self._on_verification)
        kernel.subscribe("recovery.proposed", self._on_recovery)

    def _on_verification(self, event: Any) -> None:
        """Record an unmet verdict as a failure. Never raises into the bus."""
        try:
            payload = getattr(event, "payload", {}) or {}
            if not payload:
                return  # malformed / empty event — nothing to remember
            if payload.get("satisfied"):
                return  # only failures are remembered
            self.record_failure(
                requirement=payload.get("requirement", "") or "",
                # A verification-stage detection: an unmet requirement.
                domain="verification",
                category="verification_failed",
                capability=payload.get("capability", "") or "",
                environment=payload.get("environment", "") or "",
                goal_id=payload.get("goal_id", "") or "",
                message=payload.get("requirement", "") or "",
            )
        except Exception:  # noqa: BLE001 — memory must never break the bus
            return

    def _on_recovery(self, event: Any) -> None:
        """Annotate the most recent failure for this goal with the recovery proposal."""
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id", "") or ""
            if not goal_id:
                return
            self._annotate_recovery(
                goal_id=goal_id,
                recovery_class=str(payload.get("failure_class", "") or ""),
                actionable=payload.get("chosen") is not None,
            )
        except Exception:  # noqa: BLE001 — memory must never break the bus
            return

    # ---------------------------------------------------------------- record

    def record_failure(
        self,
        *,
        requirement: str,
        domain: str = "unknown",
        category: str = "",
        capability: str = "",
        environment: str = "",
        goal_id: str = "",
        severity: int = 1,
        message: str = "",
        recoverable: bool = True,
    ) -> str:
        """Record a failure; returns the stored entry id."""
        record = FailureRecord(
            requirement=requirement, domain=domain, category=category,
            capability=capability, environment=environment, goal_id=goal_id,
            severity=severity, message=message, recoverable=recoverable,
        )
        return self._store.store(record.to_memory_entry())

    def record_structured(self, failure: Any) -> str:
        """Record a first-class M24 ``StructuredFailure`` directly (richest path)."""
        return self.record_failure(
            requirement=getattr(failure, "requirement", "") or "",
            domain=getattr(getattr(failure, "domain", None), "value",
                           str(getattr(failure, "domain", "unknown"))),
            category=getattr(failure, "category", "") or "",
            capability=getattr(failure, "capability", "") or "",
            environment=getattr(failure, "environment", "") or "",
            goal_id=getattr(failure, "goal_id", "") or "",
            severity=int(getattr(failure, "severity", 1) or 1),
            message=getattr(failure, "message", "") or "",
            recoverable=bool(getattr(failure, "recoverable", True)),
        )

    def _annotate_recovery(
        self, *, goal_id: str, recovery_class: str, actionable: bool
    ) -> bool:
        """Update the newest failure entry for ``goal_id`` with recovery info."""
        for entry in self._store.list_recent(limit=200):
            if entry.metadata.get("goal_id") == goal_id:
                entry.metadata["recovery_class"] = recovery_class
                entry.metadata["recovery_actionable"] = actionable
                self._store.delete(entry.entry_id)
                self._store.store(entry)
                return True
        return False

    # ----------------------------------------------------------------- query

    def recall(
        self,
        *,
        capability: Optional[str] = None,
        environment: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> List[FailureRecord]:
        """Return recent failures filtered by capability/environment/domain."""
        out: List[FailureRecord] = []
        for entry in self._store.list_recent(limit=max(limit * 5, 50)):
            m = entry.metadata
            if capability is not None and m.get("capability") != capability:
                continue
            if environment is not None and m.get("environment") != environment:
                continue
            if domain is not None and m.get("domain") != domain:
                continue
            out.append(self._entry_to_record(entry))
            if len(out) >= limit:
                break
        return out

    def has_failed_before(
        self,
        requirement: str,
        *,
        capability: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> bool:
        """True if a matching failure was previously recorded."""
        req = (requirement or "").strip().lower()
        for entry in self._store.list_recent(limit=500):
            m = entry.metadata
            if capability is not None and m.get("capability") != capability:
                continue
            if environment is not None and m.get("environment") != environment:
                continue
            if req and req == str(m.get("requirement", "")).strip().lower():
                return True
        return False

    def failure_count(
        self,
        *,
        capability: Optional[str] = None,
        environment: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> int:
        """Count recorded failures matching the filters."""
        count = 0
        for entry in self._store.list_recent(limit=self._store.count() or 1):
            m = entry.metadata
            if capability is not None and m.get("capability") != capability:
                continue
            if environment is not None and m.get("environment") != environment:
                continue
            if domain is not None and m.get("domain") != domain:
                continue
            count += 1
        return count

    def statistics(self) -> Dict[str, Any]:
        """Aggregate stats: totals + distribution by domain."""
        by_domain: Dict[str, int] = {}
        recovered = 0
        recent = self._store.list_recent(limit=self._store.count() or 1)
        for entry in recent:
            dom = entry.metadata.get("domain", "unknown")
            by_domain[dom] = by_domain.get(dom, 0) + 1
            if entry.metadata.get("recovery_actionable"):
                recovered += 1
        return {
            "total_failures": self._store.count(),
            "by_domain": by_domain,
            "with_actionable_recovery": recovered,
        }

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Uniform retrieval surface (for the Retrieval Router): relevance-ranked
        failure entries for ``query``. Delegates to the backing store."""
        return self._store.retrieve(query, top_k=top_k)

    @staticmethod
    def _entry_to_record(entry: MemoryEntry) -> FailureRecord:
        m = entry.metadata
        return FailureRecord(
            requirement=m.get("requirement", ""),
            domain=m.get("domain", "unknown"),
            category=m.get("category", ""),
            capability=m.get("capability", ""),
            environment=m.get("environment", ""),
            goal_id=m.get("goal_id", ""),
            severity=int(m.get("severity", 1) or 1),
            message=m.get("message", ""),
            recoverable=bool(m.get("recoverable", True)),
            recovery_class=m.get("recovery_class", ""),
            recovery_actionable=bool(m.get("recovery_actionable", False)),
            timestamp=entry.timestamp,
        )

    def clear(self) -> None:
        self._store.clear()
