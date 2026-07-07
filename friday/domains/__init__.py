"""Ch 37 — domains as pure capability compositions over the CapabilityRegistry.

Domains own no durable state and hardcode no application or site name (Axiom 15).
Each domain is a leaf that composes capabilities discovered by abstract verb via
``CapabilityRegistry.find_for`` and records ``ExecutionEvidence``; nothing in the
M1–M9 substrate imports a domain, so deleting any domain module leaves every
capability and every other domain intact.
"""

from friday.domains.models import (
    Block,
    Citation,
    Claim,
    Contradiction,
    Conversation,
    DeferredOutcome,
    DeliveryOutcome,
    DeliveryStatus,
    DocumentFormat,
    ExportOutcome,
    HypothesisScore,
    RankedSource,
    ResearchFinding,
    Section,
    SemanticDocument,
    Turn,
)
from friday.domains.research import ResearchDomain
from friday.domains.communication import CommunicationDomain
from friday.domains.documents import DocumentDomain
from friday.domains.software import SoftwareDomain

__all__ = [
    # Domains (pure compositions)
    "ResearchDomain",
    "CommunicationDomain",
    "DocumentDomain",
    "SoftwareDomain",
    # Research (Ch 37) models
    "RankedSource",
    "Claim",
    "Contradiction",
    "HypothesisScore",
    "ResearchFinding",
    # Communication (Ch 39) models
    "DeliveryStatus",
    "DeliveryOutcome",
    "Turn",
    "Conversation",
    # Documents (Ch 40) models
    "DocumentFormat",
    "Citation",
    "Block",
    "Section",
    "SemanticDocument",
    "ExportOutcome",
    # Software (Ch 41, deferred) model
    "DeferredOutcome",
]
