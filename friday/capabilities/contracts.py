"""Ch 16 — BaseCapability: a helper that implements confidence + competence tracking.

Concrete capabilities usually only differ in their domain-specific behaviour
(``id``, ``version``, ``preconditions``, ``expected_outcome``, ``execute``,
``verify``, ``recover``). The evidence-backed confidence machinery is identical
for all of them, so ``BaseCapability`` provides it once on top of a
``CompetenceRecord``:

- ``confidence`` reads the Laplace-smoothed estimate from the internal record.
- ``update_competence`` increments ``attempts`` on every outcome and ``successes``
  only when the ``ActionResult`` reports success.

Because the estimator is monotonic in its inputs, folding in a success never
lowers confidence below the prior value and folding in a failure never raises it
above the prior value (see ``update_competence``).
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional

from friday.actions.result import ActionResult
from friday.kernel.contracts.capability import (
    CapabilityContract,
    CompetenceRecord,
    Condition,
    WorldStateDelta,
)
from friday.world.worlds import ObservedWorld


class BaseCapability(CapabilityContract):
    """Ch 16 — capability base implementing confidence + competence tracking.

    Subclasses implement the domain-specific abstract members
    (``id``, ``version``, ``preconditions``, ``expected_outcome``, ``execute``,
    ``verify``, ``recover``); ``confidence`` and ``update_competence`` are
    provided here.
    """

    def __init__(self, competence: Optional[CompetenceRecord] = None) -> None:
        self._competence: CompetenceRecord = competence or CompetenceRecord()

    @property
    def competence(self) -> CompetenceRecord:
        """The internal evidence-backed competence record."""
        return self._competence

    @property
    def confidence(self) -> float:
        """Evidence-backed competence in ``[0, 1]`` from the CompetenceRecord."""
        return self._competence.confidence

    def update_competence(self, result: ActionResult) -> None:
        """Fold an outcome into the competence record.

        ``attempts`` always increments. ``successes`` increments only on a
        successful result. Because the Laplace estimator
        ``(successes + 1) / (attempts + 2)`` is monotonic, a success never
        decreases confidence and a failure never increases it.
        """
        self._competence.attempts += 1
        if result.is_success:
            self._competence.successes += 1

    # --- Domain-specific members left abstract for subclasses --------------

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def preconditions(self) -> List[Condition]: ...

    @abstractmethod
    def expected_outcome(self) -> WorldStateDelta: ...

    @abstractmethod
    async def execute(self, params: Dict[str, Any], world: ObservedWorld) -> ActionResult: ...

    @abstractmethod
    def verify(self, result: ActionResult, world: ObservedWorld) -> bool: ...

    @abstractmethod
    def recover(self, failure: ActionResult) -> Optional[CapabilityContract]: ...
