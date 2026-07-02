"""Ch 9 — Belief: a confidence-weighted, decaying statement about the world."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import List, Optional


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

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, self.confidence))

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
