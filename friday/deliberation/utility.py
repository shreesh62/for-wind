"""Ch 22 — UtilityFunction: scores candidate actions.

utility = confidence * expected_value - cost - risk_weight * risk
Irreversible actions carry an extra penalty: mistakes that cannot be
undone must clear a higher bar.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from friday.deliberation.candidate import CandidateAction


class UtilityFunction:
    """Deterministic scoring of candidates; no model calls."""

    def __init__(
        self,
        risk_weight: float = 1.0,
        irreversibility_penalty: float = 0.5,
    ) -> None:
        self._risk_weight = risk_weight
        self._irreversibility_penalty = irreversibility_penalty

    def score(self, candidate: CandidateAction) -> float:
        utility = (
            candidate.prediction.confidence * candidate.expected_value
            - candidate.cost
            - self._risk_weight * candidate.risk
        )
        if not candidate.prediction.reversible:
            utility -= self._irreversibility_penalty
        return utility

    def rank(
        self, candidates: List[CandidateAction]
    ) -> List[Tuple[CandidateAction, float]]:
        scored = [(c, self.score(c)) for c in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def best(
        self, candidates: List[CandidateAction], min_utility: float = 0.0
    ) -> Optional[CandidateAction]:
        """Highest-utility candidate, or None if nothing clears the bar."""
        ranked = self.rank(candidates)
        if not ranked:
            return None
        candidate, utility = ranked[0]
        return candidate if utility >= min_utility else None
