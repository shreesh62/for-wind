"""Ch 16 — CapabilityContract: reusable, composable, evidence-tracked competence.

This module defines the full ``CapabilityContract`` ABC (all nine members) plus
the supporting data models it depends on:

- ``Condition``       — a predicate over the ObservedWorld that must hold pre/post.
- ``WorldStateDelta`` — the change a capability expects to produce.
- ``CompetenceRecord``— evidence-backed success statistics with a Laplace-smoothed
  confidence estimator clamped to ``[0.0, 1.0]``.

These types are importable from ``friday.kernel.contracts.capability``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from friday.actions.result import ActionResult
from friday.world.worlds import ObservedWorld, PredictedWorld

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


@dataclass(frozen=True)
class Condition:
    """Ch 16 — a predicate over the ObservedWorld that must hold pre/post.

    ``subject`` is a semantic descriptor (never an app name). ``holds`` uses a
    simple heuristic: the condition is satisfied when any active belief's
    description contains the subject text.
    """

    kind: str
    subject: str
    params: Dict[str, Any] = field(default_factory=dict)

    def holds(self, world: "ObservedWorld") -> bool:
        """True iff an active belief's description references the subject."""
        if not self.subject:
            return False
        needle = self.subject.lower()
        for belief in world.active_beliefs():
            if needle in belief.description.lower():
                return True
        return False


@dataclass(frozen=True)
class WorldStateDelta:
    """Ch 16 — the change a capability expects to produce (Predicted minus Observed).

    ``adds`` are belief descriptions expected to appear, ``removes`` are those
    expected to vanish. Convertible to a ``PredictedWorld`` for verification.
    """

    adds: List[str] = field(default_factory=list)
    removes: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def as_predicted_world(self) -> "PredictedWorld":
        """Project the expected additions into a PredictedWorld."""
        return PredictedWorld(expected=list(self.adds), confidence=self.confidence)


@dataclass
class CompetenceRecord:
    """Ch 16 — evidence-backed success statistics for one capability."""

    attempts: int = 0
    successes: int = 0

    @property
    def confidence(self) -> float:
        """Laplace-smoothed success rate ``(successes + 1) / (attempts + 2)``.

        The estimator is a pure function of ``(successes, attempts)`` and the
        result is clamped to ``[0.0, 1.0]``.
        """
        value = (self.successes + 1) / (self.attempts + 2)
        return max(0.0, min(1.0, value))


class CapabilityContract(ABC):
    """Ch 16 — a reusable, composable, evidence-tracked unit of competence."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def confidence(self) -> float:
        """Evidence-backed competence in ``[0, 1]``, updated after each run."""

    @abstractmethod
    def preconditions(self) -> List[Condition]:
        """Conditions that must hold in the ObservedWorld before ``execute()``."""

    @abstractmethod
    def expected_outcome(self) -> WorldStateDelta:
        """The predicted change; convertible to a PredictedWorld for verification."""

    @abstractmethod
    async def execute(self, params: Dict[str, Any], world: "ObservedWorld") -> ActionResult:
        """Perform the capability. MUST return an ActionResult with evidence."""

    @abstractmethod
    def verify(self, result: ActionResult, world: "ObservedWorld") -> bool:
        """True iff the expected_outcome is satisfied by the post-execution world."""

    @abstractmethod
    def recover(self, failure: ActionResult) -> Optional["CapabilityContract"]:
        """Return an alternative capability to try, or None if unrecoverable."""

    @abstractmethod
    def update_competence(self, result: ActionResult) -> None:
        """Fold this outcome into the competence record (moves confidence)."""
