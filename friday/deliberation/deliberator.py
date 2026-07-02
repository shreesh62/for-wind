"""Ch 10/22 — Deliberator: choose among candidates and record the decision.

Every choice produces an immutable DecisionRecord published onto the kernel
event log, so any decision can later be audited: what was considered, what
was predicted, and why the winner won.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.deliberation.candidate import CandidateAction
from friday.deliberation.utility import UtilityFunction
from friday.events.event import make_event


@dataclass(frozen=True)
class DecisionRecord:
    """An auditable record of one deliberation."""

    goal_id: str
    chosen_id: Optional[str]  # None = deliberate inaction
    considered: tuple  # (candidate_id, utility) pairs
    reason: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decided_at: float = field(default_factory=time.time)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision_id": self.id,
            "goal_id": self.goal_id,
            "chosen_id": self.chosen_id or "",
            "considered": [list(pair) for pair in self.considered],
            "reason": self.reason,
        }


class Deliberator:
    """Ranks candidates with a UtilityFunction and records every decision."""

    def __init__(
        self,
        utility: Optional[UtilityFunction] = None,
        min_utility: float = 0.0,
    ) -> None:
        self._utility = utility or UtilityFunction()
        self._min_utility = min_utility
        self._kernel: Any = None
        self._decisions: List[DecisionRecord] = []

    @property
    def decisions(self) -> List[DecisionRecord]:
        return list(self._decisions)

    def attach(self, kernel: Any) -> None:
        self._kernel = kernel

    def decide(
        self, goal_id: str, candidates: List[CandidateAction]
    ) -> DecisionRecord:
        ranked = self._utility.rank(candidates)
        considered = tuple((c.id, round(u, 6)) for c, u in ranked)
        if not ranked:
            record = DecisionRecord(
                goal_id=goal_id,
                chosen_id=None,
                considered=(),
                reason="no candidates generated",
            )
        else:
            best, best_utility = ranked[0]
            if best_utility >= self._min_utility:
                record = DecisionRecord(
                    goal_id=goal_id,
                    chosen_id=best.id,
                    considered=considered,
                    reason=f"highest utility {best_utility:.3f}: {best.description}",
                )
            else:
                record = DecisionRecord(
                    goal_id=goal_id,
                    chosen_id=None,
                    considered=considered,
                    reason=(
                        f"best utility {best_utility:.3f} below threshold "
                        f"{self._min_utility:.3f}; choosing inaction"
                    ),
                )
        self._decisions.append(record)
        self._publish(record)
        return record

    def _publish(self, record: DecisionRecord) -> None:
        if self._kernel is None:
            return
        self._kernel.publish_event(
            make_event(
                event_type="deliberation.decision",
                source="deliberation",
                logical_time=self._kernel.health()["tick"] + 1,
                payload=record.to_payload(),
            )
        )
