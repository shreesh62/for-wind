"""Retrieval Router (M19 / A2.7, Ch 14.13) — one general way to retrieve memory.

The router unifies retrieval across memory tiers. Callers describe WHAT they want
(a query, optionally which tiers) and the router fans out to the registered sources,
normalizes their results into uniform ``RetrievedItem``s, merges, ranks, de-duplicates,
and returns a single provenance-carrying list. Callers never hardcode which tier to
hit — that is the point of a router.

Design (no duplicate systems):
- Works over the existing uniform surface: any source exposing
  ``retrieve(query, top_k) -> List[MemoryEntry]`` (every ``MemoryStore``, and
  ``FailureMemory`` via its ``retrieve``). No tier internals are touched.
- Ranking is RANK-based per source (best-first position → score), then scaled by an
  optional per-source weight. This is robust regardless of each backend's internal
  scoring scheme, and keeps the router backend-agnostic (Axiom 15 — no per-tier or
  app-specific logic; tier selection is data).
- Never raises: a source that errors is skipped; the router degrades, never crashes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from friday.memory.interfaces import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


@dataclass
class RetrievedItem:
    """A uniform, ranked retrieval result with provenance."""

    content: str
    tier: str
    score: float
    source: str
    entry_id: str = ""
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "tier": self.tier,
            "score": round(self.score, 6),
            "source": self.source,
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass
class _Source:
    tier: MemoryTier
    source: Any        # exposes retrieve(query, top_k) -> List[MemoryEntry]
    weight: float


class RetrievalRouter:
    """Routes a retrieval query across registered memory sources; merges + ranks."""

    def __init__(self) -> None:
        self._sources: Dict[str, _Source] = {}
        # Observable degradation record: maps a source name to the repr of the last
        # exception it raised during `route`. Reset at the start of each `route` call
        # so it reflects the most recent routing pass (see the degradation boundary
        # in `route`; A2.14.2 / Requirement 5.3 — failures are recorded, not swallowed).
        self._last_errors: Dict[str, str] = {}

    # --------------------------------------------------------------- registry

    def register_source(
        self, name: str, tier: MemoryTier, source: Any, *, weight: float = 1.0
    ) -> None:
        """Register a retrievable source under ``name``.

        ``source`` must expose ``retrieve(query, top_k) -> List[MemoryEntry]``
        (every ``MemoryStore`` and ``FailureMemory`` qualifies). ``weight`` scales
        this source's contribution to the merged ranking (>= 0).
        """
        if not callable(getattr(source, "retrieve", None)):
            raise TypeError(
                f"source {name!r} must expose a callable retrieve(query, top_k) method"
            )
        # Registering an existing name replaces the prior registration (Requirement 1.4).
        self._sources[name] = _Source(tier=tier, source=source, weight=max(0.0, float(weight)))

    def unregister(self, name: str) -> bool:
        return self._sources.pop(name, None) is not None

    @property
    def last_errors(self) -> Dict[str, str]:
        """Source-name → last-exception repr, recorded during the most recent ``route``.

        Empty when the last routing pass had no failing sources. Exposed so callers /
        operators can observe degraded sources rather than have failures silently
        swallowed (A2.14.2 / Requirement 5.3).
        """
        return dict(self._last_errors)

    @property
    def source_count(self) -> int:
        return len(self._sources)

    def tiers(self) -> List[MemoryTier]:
        """Distinct tiers currently registered."""
        seen: List[MemoryTier] = []
        for s in self._sources.values():
            if s.tier not in seen:
                seen.append(s.tier)
        return seen

    # ----------------------------------------------------------------- route

    def route(
        self,
        query: str,
        *,
        tiers: Optional[Iterable[MemoryTier]] = None,
        top_k: int = 10,
        per_source_k: int = 10,
    ) -> List[RetrievedItem]:
        """Retrieve across sources (optionally tier-filtered); merged + ranked.

        - When ``tiers`` is None, every registered source is queried; otherwise only
          sources whose tier is in ``tiers``.
        - Each source's results are scored by rank (1.0 for the top hit, decreasing),
          scaled by the source weight; results merge, sort by score desc,
          de-duplicate (by entry_id, else tier+content), and cap at ``top_k``.
        - Never raises; a failing source is skipped.
        """
        wanted = set(tiers) if tiers is not None else None
        # Bound the request/return sizes (Requirement 2.4): never ask a source for a
        # negative count, and never let a negative `top_k` slice from the end.
        per_source_k = max(0, per_source_k)
        top_k = max(0, top_k)
        collected: List[RetrievedItem] = []
        # Reset per-call so `last_errors` reflects only this routing pass.
        self._last_errors = {}

        for name, s in self._sources.items():
            if wanted is not None and s.tier not in wanted:
                continue
            try:
                entries = s.source.retrieve(query, per_source_k) or []
            except Exception as exc:  # noqa: BLE001
                # DEGRADATION BOUNDARY (A2.14.2 / Requirements 5.1, 5.2, 5.3):
                # a single misbehaving source must not break routing for the rest.
                # This broad catch is deliberate and NOT a silent swallow — the
                # failure is recorded (observable via `last_errors`) and logged with
                # structured context before we continue with the healthy sources.
                # BaseException (KeyboardInterrupt/SystemExit) intentionally propagates.
                self._last_errors[name] = repr(exc)
                logger.warning(
                    "retrieval_router: source %r (tier=%s) raised during retrieve; "
                    "skipping this source and continuing",
                    name,
                    getattr(s.tier, "value", s.tier),
                    exc_info=exc,
                )
                continue
            n = len(entries)
            for i, entry in enumerate(entries):
                # Rank-based score in (0, 1]: top hit = 1.0, decreasing by position.
                rank_score = 1.0 - (i / n) if n > 0 else 0.0
                collected.append(
                    RetrievedItem(
                        content=getattr(entry, "content", ""),
                        tier=getattr(getattr(entry, "tier", s.tier), "value", str(s.tier.value)),
                        score=rank_score * s.weight,
                        source=name,
                        entry_id=getattr(entry, "entry_id", "") or "",
                        timestamp=getattr(entry, "timestamp", 0.0) or 0.0,
                        metadata=dict(getattr(entry, "metadata", {}) or {}),
                    )
                )

        collected.sort(key=lambda it: it.score, reverse=True)
        return self._dedupe(collected)[:top_k]

    @staticmethod
    def _dedupe(items: List[RetrievedItem]) -> List[RetrievedItem]:
        """Drop duplicates, keeping the highest-scored occurrence (stable)."""
        seen: set = set()
        out: List[RetrievedItem] = []
        for it in items:
            key = it.entry_id or f"{it.tier}:{it.content}"
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out
