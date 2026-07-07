"""Ch 9.22/49 — KnowledgeAging: decay knowledge freshness; flag stale items.

Ages knowledge/belief freshness over time and flags items that have decayed
below a staleness threshold as candidates for refresh. Freshness decays with a
half-life, reusing the ``CompetenceModel`` decay precedent
(``0.5 ** (elapsed / half_life)``, see ``friday/competence/model.py``) rather
than re-implementing a decay curve.

Like every temporal component, ``KnowledgeAging`` reads time ONLY from values
carried on Kernel_Events (``logical_time`` / ``wall_time``, Ch 52) — it takes
``now`` and ``observed_at`` as arguments and constructs no clock of its own, so
freshness reasoning stays deterministic and replay-safe under ``FRIDAY_DRY_RUN=1``.

This half-life decay is distinct from the linear ttl-window freshness used by
``TemporalReasoner`` (Ch 49): a half-life expresses gradual, unbounded decay
while a ttl expresses a hard freshness window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class AgingItem:
    """One knowledge/belief item evaluated for staleness by ``KnowledgeAging``."""

    key: str  # belief/knowledge id or (capability, environment) key
    observed_at: float
    freshness: float  # in [0, 1] at last evaluation


class KnowledgeAging:
    """Ch 9.22/49 — decay knowledge freshness; flag stale items for refresh.

    Reuses the ``CompetenceModel`` decay precedent:
    ``factor = 0.5 ** (elapsed / half_life)``.
    """

    def __init__(
        self, *, half_life_seconds: float = 86_400.0, stale_threshold: float = 0.25
    ) -> None:
        self._half_life = half_life_seconds
        self._stale_threshold = stale_threshold

    def freshness(self, observed_at: float, now: float) -> float:
        """Freshness in ``[0, 1]``: ``0.5 ** ((now - observed_at) / half_life)``.

        - equals ``1.0`` when ``now == observed_at`` (or when ``now`` precedes it,
          which yields a value above ``1.0`` before clamping);
        - is monotonically non-increasing as ``now`` advances, because
          ``0.5 ** x`` decreases in ``x`` and elapsed time increases in ``now``;
        - stays within the closed interval ``[0, 1]`` after clamping.

        A non-positive ``half_life`` means knowledge is fresh only at the instant
        of observation: ``1.0`` when ``now <= observed_at``, else ``0.0`` (no
        divide by zero).
        """
        elapsed = now - observed_at
        if elapsed <= 0.0:
            return 1.0
        if self._half_life <= 0.0:
            return 0.0
        value = 0.5 ** (elapsed / self._half_life)
        if value <= 0.0:
            return 0.0
        if value >= 1.0:
            return 1.0
        return value

    def stale_items(self, items: List["AgingItem"], now: float) -> List["AgingItem"]:
        """Return every item whose freshness at ``now`` is below ``stale_threshold``.

        These are the candidates for refresh (Ch 9.22). Freshness is recomputed
        from each item's ``observed_at`` against ``now`` rather than trusting the
        item's last-evaluated ``freshness`` snapshot.
        """
        return [
            item
            for item in items
            if self.freshness(item.observed_at, now) < self._stale_threshold
        ]
