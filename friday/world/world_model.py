"""Ch 9 — WorldModel: the living belief store owned by the Kernel.

Updated exclusively through kernel events ("observation.received"); never
polled directly by other subsystems. This is a belief store, NOT the legacy
perception/world_state.py snapshot (which stays until M6).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from friday.events.event import Event, FrozenDict, make_event
from friday.perception.fusion import SensorFusion
from friday.perception.observation import Observation
from friday.world.belief import Belief
from friday.world.objects import Relationship, WorldObject
from friday.world.worlds import DesiredWorld, ObservedWorld


class WorldModel:
    """Probabilistic world representation fed by sensor events."""

    def __init__(self, decay_rate: float = 0.01, staleness_threshold: float = 0.1) -> None:
        self._lock = threading.RLock()
        self._fusion = SensorFusion()
        self._objects: Dict[str, WorldObject] = {}
        self._relationships: Dict[str, Relationship] = {}
        self._decay_rate = decay_rate
        # M15 — staleness sweep configuration + outbound kernel reference.
        # staleness_threshold has its own default so existing WorldModel(decay_rate=0.01)
        # behaviour is unchanged (Req 5.6). The kernel reference is captured in attach()
        # so the WorldModel can emit belief.stale_flagged events (Req 5.9).
        self._staleness_threshold = staleness_threshold
        self._kernel: Optional[Any] = None

    def attach(self, kernel: Any) -> None:
        """Subscribe to observation events on the kernel's bus."""
        # M15 — capture the kernel for outbound event emission (Req 5.9) before the
        # existing subscribe call, keeping the WorldModel a single instance per kernel
        # that talks to the outside world exclusively through kernel events.
        self._kernel = kernel
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

    def stale_beliefs(self, now: float) -> List[Belief]:
        """Return beliefs that are stale at ``now``, ordered deterministically.

        Scans the authoritative belief collection (``self._fusion.beliefs``) under the
        reentrant ``RLock`` for the entire read/recompute/collect/order sequence, so no
        concurrent mutation can produce an inconsistent view (Req 4.6, 6.1, 6.5).

        Classification precedence (Req 2.8): hard expiry outranks staleness. A belief
        whose ``expires_at`` is exceeded at ``now`` is treated as EXPIRED — it is neither
        returned nor flagged, regardless of TTL or freshness. Otherwise a belief is stale
        when its TTL is exceeded (``ttl_seconds`` non-None and age > ttl; a non-positive
        ``ttl_seconds`` therefore makes it stale for any ``now > observed_at``) OR when its
        freshness, recomputed fresh at ``now`` (never cached, Req 4.2), is strictly below
        the configured ``staleness_threshold``.

        The result is ordered by the stable key ``(observed_at, id)`` so repeated calls
        with the same beliefs and ``now`` return identical elements in identical order —
        idempotent and order-stable (Req 6.4). Returns ``[]`` when nothing is stale
        (Req 4.5). High-impact stale beliefs additionally emit a ``belief.stale_flagged``
        kernel event (Req 4.3), performed after ordering and swallowing any failure so the
        sweep result is never compromised.
        """
        with self._lock:
            stale: List[Belief] = []
            for belief in self._fusion.beliefs:
                # Req 2.8 — hard expiry outranks staleness; expired beliefs are dropped,
                # never flagged for refresh.
                if belief.expires_at is not None and now >= belief.expires_at:
                    continue
                ttl_exceeded = (
                    belief.ttl_seconds is not None
                    and (now - belief.observed_at) > belief.ttl_seconds
                )
                if ttl_exceeded or belief.freshness(now) < self._staleness_threshold:
                    stale.append(belief)
            stale.sort(key=lambda b: (b.observed_at, b.id))
            for belief in stale:
                if belief.high_impact:
                    self._publish_stale_flagged(belief, belief.freshness(now))
            return stale

    def _publish_stale_flagged(self, belief: Belief, freshness: float) -> None:
        """Emit a ``belief.stale_flagged`` kernel event for a high-impact stale belief.

        Builds a signed Event carrying ``{"belief_id", "freshness"}`` (Req 4.4) and routes
        it via the kernel's public ``publish_event`` so it flows through persistence and
        broadcast, matching the ``EnvironmentRuntime`` precedent. The event's logical time
        is a best-effort value from the public ``kernel.query_world()``; ``publish_event``
        merges it via the Lamport clock ``update``.

        No-op if no kernel is attached (detached/unit-test mode) so detection never depends
        on a live bus. Any failure — including a raising bus — is caught and swallowed so
        the sweep result is never compromised, mirroring the kernel's degrade-never-crash
        precedent. Never raises into the caller.
        """
        if self._kernel is None:
            return
        try:
            logical_time = int(self._kernel.query_world().get("logical_time", 0))
            event = make_event(
                event_type="belief.stale_flagged",
                source="world_model",
                logical_time=logical_time,
                payload={"belief_id": belief.id, "freshness": freshness},
            )
            self._kernel.publish_event(event)
        except Exception:  # noqa: BLE001 - degrade never crash; sweep must not fail
            pass

    @property
    def object_count(self) -> int:
        with self._lock:
            return len(self._objects)
