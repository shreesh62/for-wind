"""Ch 9 — Belief: a confidence-weighted, decaying statement about the world."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import List, Optional

from friday.temporal.aging import KnowledgeAging
from friday.world.provenance import (
    BeliefProvenance,
    RefreshPolicy,
    build_derivation_chain,
    derive_verification_status,
)


@dataclass
class Belief:
    """A probabilistic statement the operator holds about reality."""

    description: str
    confidence: float  # 0.0 to 1.0
    source: str  # which sensor/runtime produced this
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    observed_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None  # None = never expires
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    # M15 — World Model v2 additive fields (all defaulted; construction unaffected).
    half_life_seconds: float = 86400.0  # Req 1.7 — one day; <= 0 => instantly stale
    ttl_seconds: Optional[float] = None  # Req 2.1 — None = non-expiring
    refresh_policy: RefreshPolicy = RefreshPolicy.ON_STALE  # Req 2.3
    refresh_cost: float = 0.0  # Req 2.4 — clamped to [0.0, 1.0]
    high_impact: bool = False  # Req 4.3 — gates irreversible actions
    provenance: BeliefProvenance = field(default_factory=BeliefProvenance)  # Req 3.1

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))
        # Req 2.4 — refresh_cost is a dimensionless cost estimate in [0.0, 1.0].
        self.refresh_cost = max(0.0, min(1.0, self.refresh_cost))
        # Req 2.1 note / 4.7 — a non-None ttl_seconds <= 0 is retained as-is and
        # treated as "instantly stale" by is_stale (task 3.3); construction never raises.

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at

    def decay(self, rate: float = 0.01, now: Optional[float] = None) -> "Belief":
        """Return a new Belief with confidence reduced by temporal decay."""
        current = now if now is not None else time.time()
        dt = max(0.0, current - self.observed_at)
        new_conf = max(0.0, self.confidence - rate * dt)
        return replace(self, confidence=new_conf, last_updated=current)

    def reinforce(self, confidence: float, evidence_id: Optional[str] = None) -> "Belief":
        """Return a new Belief strengthened by a corroborating observation.

        Combined via noisy-OR: 1 - (1-a)(1-b) — two agreeing sources yield
        higher confidence than either alone.
        """
        combined = 1.0 - (1.0 - self.confidence) * (1.0 - max(0.0, min(1.0, confidence)))
        supporting = list(self.supporting_evidence)
        if evidence_id:
            supporting.append(evidence_id)
        now = time.time()
        return replace(
            self,
            confidence=combined,
            supporting_evidence=supporting,
            observed_at=now,
            last_updated=now,
        )

    def contradict(self, confidence: float, evidence_id: Optional[str] = None) -> "Belief":
        """Return a new Belief weakened by a contradicting observation."""
        reduced = self.confidence * (1.0 - max(0.0, min(1.0, confidence)))
        contradicting = list(self.contradicting_evidence)
        if evidence_id:
            contradicting.append(evidence_id)
        return replace(
            self,
            confidence=reduced,
            contradicting_evidence=contradicting,
            last_updated=time.time(),
        )

    def freshness(self, now: float) -> float:
        """Freshness in ``[0, 1]`` at ``now``, decaying by half-life from observation.

        Delegates to ``KnowledgeAging.freshness`` (M9) so there is exactly one
        implementation of the ``0.5 ** (age / half_life)`` decay curve in the codebase
        (Req 1.5). ``now`` is an explicit float argument; this method never reads a
        system clock, keeping freshness deterministic and replay-safe (Req 1.8).

        With ``half_life_seconds <= 0`` the belief is fresh only at the instant of
        observation (``1.0`` when ``now <= observed_at``, else ``0.0``); with
        ``now <= observed_at`` freshness clamps to ``1.0`` (Req 1.4, 1.7).
        """
        aging = KnowledgeAging(half_life_seconds=self.half_life_seconds)
        return aging.freshness(self.observed_at, now)

    def is_stale(self, now: float, staleness_threshold: float = 0.1) -> bool:
        """Whether the belief is stale at ``now`` by TTL or freshness decay.

        Stale when ``ttl_seconds`` is set and the age (``now - observed_at``) exceeds
        it (a non-positive ``ttl_seconds`` therefore makes the belief stale for any
        ``now > observed_at``), OR when ``freshness(now)`` has decayed below
        ``staleness_threshold`` (Req 2.2, 2.7, 4.7).

        Pure and replay-safe: ``now`` is explicit and no system clock is read. Hard
        expiry (``expires_at``) is intentionally not considered here — that
        precedence is resolved by the WorldModel (Req 2.8).
        """
        if self.ttl_seconds is not None and (now - self.observed_at) > self.ttl_seconds:
            return True
        return self.freshness(now) < staleness_threshold

    def add_supporting_observation(self, observation_id: str) -> "Belief":
        """Return a new Belief with ``observation_id`` recorded as supporting evidence.

        Appends the id to ``provenance.supporting_observations`` and mirrors it into
        the legacy ``supporting_evidence`` field (Req 3.9), then recomputes
        ``verification_status`` (Req 3.3). A brand-new ``BeliefProvenance`` is built
        with copied lists so the original belief and its provenance are never mutated.
        """
        new_supporting = list(self.provenance.supporting_observations)
        new_supporting.append(observation_id)
        new_contradicting = list(self.provenance.contradicting_observations)
        new_status = derive_verification_status(
            new_supporting, new_contradicting, self.provenance.verification_status
        )
        new_prov = BeliefProvenance(
            supporting_observations=new_supporting,
            contradicting_observations=new_contradicting,
            derivation_chain=list(self.provenance.derivation_chain),
            verification_status=new_status,
        )
        new_legacy = list(self.supporting_evidence)
        new_legacy.append(observation_id)
        return replace(self, provenance=new_prov, supporting_evidence=new_legacy)

    def add_contradicting_observation(self, observation_id: str) -> "Belief":
        """Return a new Belief with ``observation_id`` recorded as contradicting evidence.

        Symmetric to ``add_supporting_observation``: appends the id to
        ``provenance.contradicting_observations`` and mirrors it into the legacy
        ``contradicting_evidence`` field (Req 3.9, 3.4), then recomputes
        ``verification_status`` (Req 3.6). A new ``BeliefProvenance`` with copied
        lists is built so the original belief is never mutated.
        """
        new_contradicting = list(self.provenance.contradicting_observations)
        new_contradicting.append(observation_id)
        new_supporting = list(self.provenance.supporting_observations)
        new_status = derive_verification_status(
            new_supporting, new_contradicting, self.provenance.verification_status
        )
        new_prov = BeliefProvenance(
            supporting_observations=new_supporting,
            contradicting_observations=new_contradicting,
            derivation_chain=list(self.provenance.derivation_chain),
            verification_status=new_status,
        )
        new_legacy = list(self.contradicting_evidence)
        new_legacy.append(observation_id)
        return replace(self, provenance=new_prov, contradicting_evidence=new_legacy)

    def derive_from(self, parents: List["Belief"]) -> "Belief":
        """Return a new Belief recording ``parents`` as its derivation ancestry.

        Builds the ordered, de-duplicated, acyclic ``derivation_chain`` (root ->
        immediate parent) via ``build_derivation_chain``, which rejects self-reference
        and cycles and bounds the chain to ``MAX_DERIVATION_CHAIN`` entries (Req 3.1,
        3.2, 3.7, 3.8). A new ``BeliefProvenance`` copying the other fields is built so
        the original belief and its provenance are never mutated.
        """
        new_chain = build_derivation_chain(
            [(p.provenance.derivation_chain, p.id) for p in parents],
            self.id,
        )
        new_prov = BeliefProvenance(
            supporting_observations=list(self.provenance.supporting_observations),
            contradicting_observations=list(self.provenance.contradicting_observations),
            derivation_chain=new_chain,
            verification_status=self.provenance.verification_status,
        )
        return replace(self, provenance=new_prov)
