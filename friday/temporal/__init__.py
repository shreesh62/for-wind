"""Ch 49 — Temporal package: reason about time over the kernel clock.

Re-exports the public temporal surface. Every component here reads time ONLY
from the ``logical_time`` / ``wall_time`` carried on Kernel_Events (Ch 52) and
constructs no clock of its own.
"""

from __future__ import annotations

from friday.temporal.aging import AgingItem, KnowledgeAging
from friday.temporal.clock import TemporalReasoner
from friday.temporal.deadlines import DeadlineState, DeadlineStatus, DeadlineTracker

__all__ = [
    "AgingItem",
    "KnowledgeAging",
    "TemporalReasoner",
    "DeadlineTracker",
    "DeadlineState",
    "DeadlineStatus",
]
