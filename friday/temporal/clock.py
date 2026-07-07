"""Ch 49 — TemporalReasoner: freshness, staleness, and time-remaining.

Reasons about knowledge freshness and deadlines using the kernel clock carried
on every ``Event`` (``logical_time`` + ``wall_time``, Ch 52). It NEVER creates a
clock of its own — every method takes the current time as a value read from a
Kernel_Event, so temporal reasoning stays deterministic and replay-safe under
``FRIDAY_DRY_RUN=1``.

Freshness decay is linear against a time-to-live window: value ``1.0`` at the
moment of observation, decaying to ``0.0`` as age approaches (and never below
``0.0`` once age exceeds) the ttl. This is distinct from the half-life decay used
by ``KnowledgeAging`` (Ch 9.22) — a ttl expresses a hard freshness window while a
half-life expresses gradual, unbounded decay.
"""

from __future__ import annotations


class TemporalReasoner:
    """Ch 49 — temporal reasoning over the kernel clock (logical_time + wall_time)."""

    def freshness(self, observed_at: float, now: float, *, ttl_seconds: float) -> float:
        """Freshness in ``[0, 1]``: ``1.0`` at observation, decaying to ``0`` at ttl.

        Age is ``now - observed_at``. Freshness is ``1 - age / ttl_seconds`` clamped
        to ``[0, 1]``:

        - equals ``1.0`` when ``now == observed_at`` (or when ``now`` precedes it);
        - decreases linearly as ``now`` advances;
        - equals ``0.0`` once age reaches or exceeds ``ttl_seconds``.

        A non-positive ``ttl_seconds`` means knowledge is fresh only at the instant
        of observation: ``1.0`` when ``now <= observed_at``, else ``0.0`` (no divide
        by zero).
        """
        age = now - observed_at
        if age <= 0.0:
            return 1.0
        if ttl_seconds <= 0.0:
            return 0.0
        freshness = 1.0 - (age / ttl_seconds)
        if freshness <= 0.0:
            return 0.0
        if freshness >= 1.0:
            return 1.0
        return freshness

    def is_stale(self, observed_at: float, now: float, *, ttl_seconds: float) -> bool:
        """True once age (``now - observed_at``) exceeds ``ttl_seconds``.

        Knowledge is stale only strictly past its freshness window; at exactly the
        ttl boundary it is not yet stale. A non-positive ``ttl_seconds`` makes any
        elapsed time stale (fresh only when ``now <= observed_at``).
        """
        age = now - observed_at
        if age <= 0.0:
            return False
        if ttl_seconds <= 0.0:
            return True
        return age > ttl_seconds

    def time_remaining(self, deadline_wall: float, now: float) -> float:
        """Seconds until ``deadline_wall`` from ``now`` (negative once missed)."""
        return deadline_wall - now
