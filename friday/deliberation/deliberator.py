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
    # M16 — optional additive flags, populated only when the expanded scorer
    # is used (feature-detected). They stay False on the simple default path,
    # so existing construction and `to_payload()` gain two extra keys with
    # False values but are otherwise unchanged (Requirement 4.3, 5.1).
    elevated_confidence_required: bool = False
    requires_human_confirmation: bool = False

    def to_payload(self) -> Dict[str, Any]:
        return {
            "decision_id": self.id,
            "goal_id": self.goal_id,
            "chosen_id": self.chosen_id or "",
            "considered": [list(pair) for pair in self.considered],
            "reason": self.reason,
            "elevated_confidence_required": self.elevated_confidence_required,
            "requires_human_confirmation": self.requires_human_confirmation,
        }


class Deliberator:
    """Ranks candidates with a UtilityFunction and records every decision."""

    def __init__(
        self,
        utility: Optional[object] = None,
        min_utility: float = 0.0,
    ) -> None:
        # ``utility`` may be the simple ``UtilityFunction`` (default) or any
        # duck-compatible scorer exposing ``rank``/``best`` — notably the M16
        # ``ExpandedUtilityFunction``, which additionally exposes
        # ``required_confidence``/``requires_human_confirmation`` and gates
        # no-undo actions behind a raised confidence bar. Kept as ``object``
        # to avoid coupling this seam to the expanded module (Requirement 5.1).
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
        elif self._uses_confidence_gate():
            # Expanded scorer: select the winner via the confidence-aware gate
            # (equivalent to ExpandedUtilityFunction.best), while keeping the
            # auditable ``considered`` list ranked by raw score as before.
            record = self._decide_with_gate(goal_id, ranked, considered)
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

    def _uses_confidence_gate(self) -> bool:
        """True when the injected scorer exposes the expanded no-undo
        confidence gate (feature-detected — Requirement 5.1). The simple
        ``UtilityFunction`` lacks ``required_confidence`` and so keeps the
        exact legacy ``ranked[0]`` + ``min_utility`` behavior."""
        return hasattr(self._utility, "required_confidence") and hasattr(
            self._utility, "best"
        )

    def _decide_with_gate(
        self,
        goal_id: str,
        ranked: List,
        considered: tuple,
    ) -> "DecisionRecord":
        """Gate-aware winner selection for the expanded scorer.

        The winner is the highest-scoring candidate that is ELIGIBLE — its
        score clears ``min_utility`` AND its prediction confidence meets its
        per-candidate ``required_confidence`` (raised for no-undo actions).
        ``ranked`` is already sorted by score descending, so the first
        eligible pair is the winner (equivalent to the expanded ``best``).
        """
        eligible = [
            (candidate, utility)
            for candidate, utility in ranked
            if utility >= self._min_utility
            and candidate.prediction.confidence
            >= self._utility.required_confidence(candidate)
        ]
        top_candidate, top_utility = ranked[0]
        if not eligible:
            gated_out = any(
                utility >= self._min_utility
                and candidate.prediction.confidence
                < self._utility.required_confidence(candidate)
                for candidate, utility in ranked
            )
            if gated_out:
                reason = (
                    "no eligible candidate: higher-scoring candidate withheld "
                    "(confidence below required for no-undo action); "
                    "choosing inaction"
                )
            else:
                reason = (
                    f"best utility {top_utility:.3f} below threshold "
                    f"{self._min_utility:.3f}; choosing inaction"
                )
            return DecisionRecord(
                goal_id=goal_id,
                chosen_id=None,
                considered=considered,
                reason=reason,
            )
        winner, winner_utility = eligible[0]
        elevated = not winner.has_undo_path
        requires_human = (
            bool(self._utility.requires_human_confirmation(winner))
            if hasattr(self._utility, "requires_human_confirmation")
            else False
        )
        reason = (
            f"highest eligible utility {winner_utility:.3f}: "
            f"{winner.description}"
        )
        if winner.id != top_candidate.id:
            reason += (
                " (higher-scoring candidate withheld: confidence below "
                "required for no-undo action)"
            )
        return DecisionRecord(
            goal_id=goal_id,
            chosen_id=winner.id,
            considered=considered,
            reason=reason,
            elevated_confidence_required=elevated,
            requires_human_confirmation=requires_human,
        )

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
