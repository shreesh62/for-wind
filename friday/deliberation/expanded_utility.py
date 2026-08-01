"""M16 — Expanded utility (FAS §A2.3.1–A2.3.3).

The :class:`ExpandedUtilityFunction` scores a candidate from the nine
§A2.3.1 terms plus an explicit action-safety penalty and an irreversibility
penalty, and gates no-undo actions behind a raised confidence requirement.

All scoring is a **pure, deterministic** function of the candidate and the
configured :class:`UtilityWeights` — no model calls, no clock, no network, no
randomness (the 4th law). The existing simple ``UtilityFunction`` and its
three-term scoring are left untouched; this scorer is opt-in and additive.
Carries no application-specific logic (Axiom 15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from friday.deliberation.candidate import CandidateAction

# Documented bound for every policy weight. Weights are policy, not evidence:
# clamping each contributor to this non-negative range means no single term
# can dominate the score by construction (Requirement 2.2) — the largest a
# term's weight can be is shared by every other term.
WEIGHT_MIN: float = 0.0
WEIGHT_MAX: float = 10.0


def _clamp_weight(value: float) -> float:
    """Clamp a policy weight to the documented ``[WEIGHT_MIN, WEIGHT_MAX]``
    non-negative range so no single term dominates by construction."""
    return max(WEIGHT_MIN, min(WEIGHT_MAX, value))


@dataclass(frozen=True)
class UtilityWeights:
    """Bounded per-term policy weights for :class:`ExpandedUtilityFunction`.

    Weights are **policy**, not evidence. Each is clamped in ``__post_init__``
    to the documented non-negative range ``[WEIGHT_MIN, WEIGHT_MAX]`` so that
    no single term can dominate the score by construction (Requirement 2.2).
    All default to ``1.0`` so the terms contribute on an equal footing.
    """

    # Positive contributors.
    w_goal_progress: float = 1.0
    w_information_gain: float = 1.0
    w_future_optionality: float = 1.0
    # Negative contributors.
    w_risk: float = 1.0
    w_time: float = 1.0
    w_resource: float = 1.0
    w_attention: float = 1.0
    w_opportunity: float = 1.0
    # Penalties (applied when the corresponding signal is set).
    safety_penalty: float = 1.0
    irreversibility_penalty: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "w_goal_progress",
            "w_information_gain",
            "w_future_optionality",
            "w_risk",
            "w_time",
            "w_resource",
            "w_attention",
            "w_opportunity",
            "safety_penalty",
            "irreversibility_penalty",
        ):
            object.__setattr__(
                self, name, _clamp_weight(getattr(self, name))
            )


class ExpandedUtilityFunction:
    """Nine-term expanded utility with safety/irreversibility penalties and a
    no-undo confidence gate. Pure and deterministic; no model calls.

    Duck-compatible with the simple ``UtilityFunction``: it exposes ``rank``
    and ``best`` with the same signatures so the ``Deliberator`` can use it
    interchangeably (it does not subclass ``UtilityFunction``).
    """

    def __init__(
        self,
        weights: UtilityWeights = UtilityWeights(),
        *,
        baseline_min_confidence: float = 0.5,
        no_undo_confidence_floor: float = 0.8,
    ) -> None:
        self._weights = weights
        self._baseline_min_confidence = baseline_min_confidence
        self._no_undo_confidence_floor = no_undo_confidence_floor

    def score(self, candidate: CandidateAction) -> float:
        """Expanded utility of a candidate (Requirements 2.1, 2.3).

        Pure/deterministic — a function of the candidate's fields and the
        configured weights only. Note: ``candidate.cost`` is the *legacy*
        simple-utility field and is intentionally NOT read here; the expanded
        scorer uses the explicit ``time_cost`` / ``resource_cost`` /
        ``attention_cost`` / ``opportunity_cost`` terms instead, so cost is
        never double-counted.
        """
        w = self._weights
        irreversibility = (
            w.irreversibility_penalty if not candidate.has_undo_path else 0.0
        )
        safety = w.safety_penalty if candidate.touches_protected else 0.0
        return (
            w.w_goal_progress
            * (candidate.prediction.confidence * candidate.expected_value)
            + w.w_information_gain * candidate.information_gain
            + w.w_future_optionality * candidate.future_optionality
            - w.w_risk * candidate.risk
            - w.w_time * candidate.time_cost
            - w.w_resource * candidate.resource_cost
            - w.w_attention * candidate.attention_cost
            - w.w_opportunity * candidate.opportunity_cost
            - irreversibility
            - safety
        )

    def required_confidence(self, candidate: CandidateAction) -> float:
        """Minimum prediction confidence a candidate must clear to be chosen
        (Requirement 4.1). Raised to the no-undo floor when the candidate has
        no declared undo path, otherwise the baseline."""
        if not candidate.has_undo_path:
            return max(
                self._baseline_min_confidence, self._no_undo_confidence_floor
            )
        return self._baseline_min_confidence

    def requires_human_confirmation(self, candidate: CandidateAction) -> bool:
        """True when a candidate has no undo path AND touches a protected /
        irreversible surface (no-undo + high impact — Requirement 4.3)."""
        return not candidate.has_undo_path and candidate.touches_protected

    def rank(
        self, candidates: List[CandidateAction]
    ) -> List[Tuple[CandidateAction, float]]:
        """Candidates paired with their score, sorted by score descending
        (stable)."""
        scored = [(c, self.score(c)) for c in candidates]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def best(
        self, candidates: List[CandidateAction], min_utility: float = 0.0
    ) -> Optional[CandidateAction]:
        """Highest-scoring *eligible* candidate, or None (Requirements 4.2,
        4.4).

        A candidate is eligible only if its score clears ``min_utility`` AND
        its prediction confidence meets its per-candidate
        ``required_confidence``. A no-undo candidate whose confidence is below
        its raised requirement is excluded even if it has the top raw score,
        so an irreversible action that fails its raised confidence is never
        auto-approved.
        """
        eligible = [
            (c, s)
            for c, s in self.rank(candidates)
            if s >= min_utility
            and c.prediction.confidence >= self.required_confidence(c)
        ]
        if not eligible:
            return None
        # rank() already sorted by score descending, so the first eligible
        # pair is the highest-scoring eligible candidate.
        return eligible[0][0]
