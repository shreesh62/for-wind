"""Ch 12 — SensorFusion: merge observations from many sensors into beliefs.

Agreeing observations of the same object combine via noisy-OR (confidence
rises); contradicting observations reduce confidence. Beliefs are keyed by
the observed object identity so repeated sightings update, not duplicate.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from friday.perception.observation import Observation
from friday.world.belief import Belief


class SensorFusion:
    """Combines uniform Observations into confidence-weighted Beliefs."""

    def __init__(self) -> None:
        self._beliefs_by_key: Dict[str, Belief] = {}

    @property
    def beliefs(self) -> List[Belief]:
        return list(self._beliefs_by_key.values())

    def ingest(self, observations: Iterable[Observation]) -> List[Belief]:
        """Fuse a batch of observations; returns the updated beliefs."""
        touched: List[Belief] = []
        for obs in observations:
            key = obs.object_key()
            description = self._describe(obs)
            existing = self._beliefs_by_key.get(key)
            if existing is None:
                belief = Belief(
                    description=description,
                    confidence=obs.confidence,
                    source=obs.sensor,
                    supporting_evidence=[obs.id],
                )
            elif self._contradicts(existing, obs):
                belief = existing.contradict(obs.confidence, evidence_id=obs.id)
            else:
                belief = existing.reinforce(obs.confidence, evidence_id=obs.id)
                if obs.sensor not in belief.source.split("+"):
                    belief.source = f"{belief.source}+{obs.sensor}"
            self._beliefs_by_key[key] = belief
            touched.append(belief)
        return touched

    @staticmethod
    def _describe(obs: Observation) -> str:
        name = obs.attributes.get("name") or obs.attributes.get("text") or "unknown"
        return f"{obs.object_type} '{name}' exists in {obs.environment}"

    @staticmethod
    def _contradicts(belief: Belief, obs: Observation) -> bool:
        return bool(obs.attributes.get("absent"))
