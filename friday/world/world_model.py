"""Ch 9 — WorldModel: the living belief store owned by the Kernel.

Updated exclusively through kernel events ("observation.received"); never
polled directly by other subsystems. This is a belief store, NOT the legacy
perception/world_state.py snapshot (which stays until M6).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from friday.events.event import Event, FrozenDict
from friday.perception.fusion import SensorFusion
from friday.perception.observation import Observation
from friday.world.belief import Belief
from friday.world.objects import Relationship, WorldObject
from friday.world.worlds import DesiredWorld, ObservedWorld


class WorldModel:
    """Probabilistic world representation fed by sensor events."""

    def __init__(self, decay_rate: float = 0.01) -> None:
        self._lock = threading.RLock()
        self._fusion = SensorFusion()
        self._objects: Dict[str, WorldObject] = {}
        self._relationships: Dict[str, Relationship] = {}
        self._decay_rate = decay_rate

    def attach(self, kernel: Any) -> None:
        """Subscribe to observation events on the kernel's bus."""
        kernel.subscribe("observation.received", self._on_observation_event)

    def _on_observation_event(self, event: Event) -> None:
        payload = dict(event.payload)
        observation = Observation(
            sensor=str(payload.get("sensor", "unknown")),
            environment=str(payload.get("environment", "unknown")),
            object_type=str(payload.get("object_type", "unknown")),
            attributes=FrozenDict(payload.get("attributes") or {}),
            confidence=float(payload.get("confidence", 1.0)),
        )
        self.ingest([observation])

    def ingest(self, observations: List[Observation]) -> List[Belief]:
        with self._lock:
            beliefs = self._fusion.ingest(observations)
            for obs in observations:
                key = obs.object_key()
                obj = self._objects.get(key)
                if obj is None:
                    self._objects[key] = WorldObject(
                        object_type=obs.object_type,
                        attributes=dict(obs.attributes),
                    )
                else:
                    obj.last_seen = time.time()
                    obj.attributes.update(dict(obs.attributes))
            return beliefs

    def relate(self, source_key: str, target_key: str, relation: str) -> Optional[Relationship]:
        with self._lock:
            if source_key not in self._objects or target_key not in self._objects:
                return None
            source = self._objects[source_key]
            target = self._objects[target_key]
            rel = Relationship(source_id=source.id, target_id=target.id, relation=relation)
            self._relationships[rel.id] = rel
            return rel

    def observed_world(self, apply_decay: bool = True) -> ObservedWorld:
        with self._lock:
            beliefs = {}
            for belief in self._fusion.beliefs:
                if apply_decay:
                    belief = belief.decay(rate=self._decay_rate)
                beliefs[belief.id] = belief
            return ObservedWorld(beliefs=beliefs)

    def unmet_conditions(self, desired: DesiredWorld, min_confidence: float = 0.5) -> List[str]:
        return desired.unmet(self.observed_world(), min_confidence=min_confidence)

    @property
    def object_count(self) -> int:
        with self._lock:
            return len(self._objects)
