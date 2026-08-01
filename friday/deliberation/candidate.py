"""Ch 10 — CandidateAction: an option under consideration, with its
predicted outcome. Axiom: every significant action has a predicted outcome
before it is taken.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.deliberation.recovery_contract import RecoveryContract


@dataclass(frozen=True)
class PredictedOutcome:
    """What the operator expects the world to look like after the action."""

    expected_beliefs: tuple  # descriptions expected to become true
    confidence: float  # 0..1 — how likely the prediction is
    reversible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "confidence", max(0.0, min(1.0, self.confidence))
        )


@dataclass(frozen=True)
class CandidateAction:
    """One option for advancing a goal."""

    description: str
    capability: str  # abstract capability name, never app-specific
    prediction: PredictedOutcome
    goal_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    expected_value: float = 1.0  # progress toward goal if prediction holds
    cost: float = 0.1  # time/resource estimate, same scale as value
    risk: float = 0.0  # 0..1 chance of harmful side effects
    # M16 — expanded-utility term inputs (evidence/estimates, never
    # self-asserted competence). All defaulted so construction + build(...)
    # are unaffected (Requirements 1.4, 2.4).
    information_gain: float = 0.0  # positive: knowledge the action yields
    future_optionality: float = 0.0  # positive: options it keeps open
    time_cost: float = 0.0  # negative: wall-clock estimate
    resource_cost: float = 0.0  # negative: resource estimate
    attention_cost: float = 0.0  # negative: attention/interruption estimate
    opportunity_cost: float = 0.0  # negative: value of the road not taken
    touches_protected: bool = False  # Ch 35 permission-boundary signal
    recovery_contract: Optional[RecoveryContract] = None  # walk-back plan
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def has_undo_path(self) -> bool:
        """A candidate has a declared undo path only when its prediction is
        reversible AND its recovery contract provides one; a missing contract
        means no declared undo path (conservative default — Requirement 1.3).
        """
        return self.prediction.reversible and (
            self.recovery_contract.has_undo_path
            if self.recovery_contract is not None
            else False
        )

    @staticmethod
    def build(
        description: str,
        capability: str,
        goal_id: str,
        expected_beliefs: List[str],
        confidence: float = 0.5,
        **kwargs: Any,
    ) -> "CandidateAction":
        return CandidateAction(
            description=description,
            capability=capability,
            goal_id=goal_id,
            prediction=PredictedOutcome(
                expected_beliefs=tuple(expected_beliefs), confidence=confidence
            ),
            **kwargs,
        )
