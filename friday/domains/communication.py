"""Ch 39 — environment-independent delivery + verification + conversation memory.

A ``CommunicationDomain`` is a pure composition leaf (HANDOFF Section 12/13,
Axiom 15): it discovers a delivery capability by the abstract verb ``"deliver"``
only, executes it, and confirms the outcome through the Evidence Law. It names
no application or site, subscribes to no kernel events, and owns no durable
cross-call state — conversation memory is a caller-owned immutable value the
domain merely returns updated copies of.
"""

from __future__ import annotations

from typing import Any

from friday.capabilities.registry import CapabilityRegistry
from friday.domains.models import (
    Conversation,
    DeliveryOutcome,
    DeliveryStatus,
)
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


class CommunicationDomain:
    """Ch 39 — environment-independent delivery + verification + conversation memory."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        # The registry is the ONLY instance attribute; the domain owns no other
        # mutable state and nothing durable survives a call.
        self.registry = registry

    async def deliver(
        self,
        recipient: str,
        message: str,
        evidence: ExecutionEvidence,
        world: Any = None,
    ) -> DeliveryOutcome:
        """Discover a deliver-verb capability, execute it, and confirm via the Evidence Law.

        Returns an ``UNAVAILABLE`` outcome (never raises) when the registry offers
        no delivery capability. Delivery is reported ``CONFIRMED`` only when a real
        ``DELIVERY_CONFIRMATION`` artifact is present in the evidence bundle;
        generated text alone never confirms delivery (Axiom 5 / Evidence Law).
        """
        caps = self.registry.find_for("deliver")
        if not caps:
            return DeliveryOutcome(
                recipient,
                DeliveryStatus.UNAVAILABLE,
                detail="no deliver capability",
            )

        # Highest-confidence capability (find_for returns descending confidence).
        cap = caps[0]
        result = await cap.execute({"recipient": recipient, "message": message}, world)

        if self.verify_delivery(evidence):
            return DeliveryOutcome(
                recipient,
                DeliveryStatus.CONFIRMED,
                capability_id=cap.id,
                detail=result.message if hasattr(result, "message") else "",
            )
        return DeliveryOutcome(
            recipient,
            DeliveryStatus.FAILED,
            capability_id=cap.id,
            detail="delivery not confirmed",
        )

    def verify_delivery(self, evidence: ExecutionEvidence) -> bool:
        """True iff the bundle carries a real ``DELIVERY_CONFIRMATION`` artifact (Evidence Law)."""
        return evidence.has(EvidenceKind.DELIVERY_CONFIRMATION)

    def append_turn(
        self, transcript: Conversation, speaker: str, text: str
    ) -> Conversation:
        """Return a NEW conversation with the turn appended.

        The transcript is caller-owned and immutable — the domain stores nothing.
        When no transcript is supplied, a fresh empty ``Conversation`` is used.
        """
        if transcript is None:
            transcript = Conversation()
        return transcript.with_turn(speaker, text)
