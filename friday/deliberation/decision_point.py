"""M25 — DecisionPoint: a first-class, immutable representation of a recurring choice.

A ``DecisionPoint`` is a frozen (immutable) dataclass that captures everything the
preference resolution pipeline needs to determine how to resolve a recurring choice:
an identity key, goal/environment context, available options, risk estimate,
reversibility flag, candidate preferences from memory, and generic metadata.

Design invariants:
- NO application-specific fields (Axiom 15): no ``app_name``, ``dialog_id``,
  ``site_url``, or window title. The ``decision_id`` is a semantic key
  (e.g. ``"default_browser_profile"``, ``"download_directory"``).
- Frozen (immutable) and JSON-projectable (``to_dict()``).
- Imports only stdlib + ``friday.events.event.FrozenDict``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from friday.events.event import FrozenDict


def _clamp01(value: float) -> float:
    """Clamp a float into [0.0, 1.0]."""
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class DecisionPoint:
    """An immutable representation of a recurring choice requiring resolution.

    Fields
    ------
    decision_id : str
        Semantic key identifying the type of decision (e.g. ``"download_directory"``).
    goal_context : str
        Goal identifier or description providing the purpose context.
    environment : str
        Environment fingerprint or name where the decision arises.
    options : tuple
        Available choices (tuple of strings for hashability/immutability).
    risk : float
        Estimated risk in [0, 1] (clamped on construction).
    reversible : bool
        Whether the choice can be easily undone.
    category : str
        Generic task/object category (never application-specific).
    candidates : tuple
        Candidate preferences retrieved from memory (may be empty).
    metadata : dict
        Additional JSON-safe context.
    """

    decision_id: str
    goal_context: str
    environment: str
    options: Tuple[str, ...]
    risk: float
    reversible: bool
    category: str
    candidates: Tuple[Any, ...]
    metadata: dict

    def __init__(
        self,
        *,
        decision_id: str = "",
        goal_context: str = "",
        environment: str = "",
        options: Any = (),
        risk: float = 0.0,
        reversible: bool = True,
        category: str = "",
        candidates: Any = (),
        metadata: Any = None,
    ) -> None:
        # Use object.__setattr__ because the dataclass is frozen.
        object.__setattr__(self, "decision_id", str(decision_id))
        object.__setattr__(self, "goal_context", str(goal_context))
        object.__setattr__(self, "environment", str(environment))
        object.__setattr__(self, "options", tuple(str(o) for o in (options or ())))
        object.__setattr__(self, "risk", _clamp01(risk))
        object.__setattr__(self, "reversible", bool(reversible))
        object.__setattr__(self, "category", str(category))
        object.__setattr__(self, "candidates", tuple(candidates or ()))
        # Ensure metadata is a dict (mutable allowed since frozen-ness prevents reassignment).
        if metadata is None:
            object.__setattr__(self, "metadata", {})
        elif isinstance(metadata, dict):
            object.__setattr__(self, "metadata", dict(metadata))
        else:
            object.__setattr__(self, "metadata", dict(metadata))
        # Fail-fast validation (Requirement 1.4).
        if not self.decision_id:
            raise ValueError("DecisionPoint requires a non-empty decision_id")
        if not self.options:
            raise ValueError("DecisionPoint requires at least one option")

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe projection of this DecisionPoint."""
        return {
            "decision_id": self.decision_id,
            "goal_context": self.goal_context,
            "environment": self.environment,
            "options": list(self.options),
            "risk": self.risk,
            "reversible": self.reversible,
            "category": self.category,
            "candidates": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in self.candidates
            ],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionPoint":
        """Reconstruct a DecisionPoint from a JSON-safe dict (best-effort)."""
        return cls(
            decision_id=data.get("decision_id", ""),
            goal_context=data.get("goal_context", ""),
            environment=data.get("environment", ""),
            options=tuple(data.get("options", ())),
            risk=float(data.get("risk", 0.0)),
            reversible=bool(data.get("reversible", True)),
            category=data.get("category", ""),
            candidates=tuple(data.get("candidates", ())),
            metadata=data.get("metadata"),
        )
