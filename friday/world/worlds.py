"""Ch 9 — The three worlds: Observed, Predicted, Desired."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from friday.world.belief import Belief


@dataclass
class ObservedWorld:
    """What the sensors say is true right now."""

    beliefs: Dict[str, Belief] = field(default_factory=dict)

    def active_beliefs(self, min_confidence: float = 0.0) -> List[Belief]:
        return [
            b
            for b in self.beliefs.values()
            if not b.expired and b.confidence >= min_confidence
        ]


@dataclass
class PredictedWorld:
    """What the operator expects to be true after the next action."""

    expected: List[str] = field(default_factory=list)  # belief descriptions
    confidence: float = 1.0


@dataclass
class DesiredWorld:
    """What must be true for a goal to be complete."""

    conditions: List[str] = field(default_factory=list)

    @classmethod
    def from_requirements(cls, requirements: Iterable) -> "DesiredWorld":
        """Build from a RequirementSet or any iterable of requirement-like items.

        Accepts strings, or objects exposing `.description` or `.text`.
        """
        conditions: List[str] = []
        items = getattr(requirements, "requirements", requirements)
        for req in items:
            if isinstance(req, str):
                conditions.append(req)
            else:
                text = getattr(req, "description", None) or getattr(req, "text", None)
                if text:
                    conditions.append(str(text))
        return cls(conditions=conditions)

    def unmet(self, observed: ObservedWorld, min_confidence: float = 0.5) -> List[str]:
        """Conditions not currently supported by a confident belief."""
        satisfied = {
            b.description for b in observed.active_beliefs(min_confidence=min_confidence)
        }
        return [c for c in self.conditions if c not in satisfied]
