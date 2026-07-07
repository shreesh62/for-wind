"""Ch 37/39/40/41 — domain data models for pure capability compositions.

Frozen value objects shared across the FRIDAY domain compositions (research,
communication, documents, and the deferred software domain). These models hold
no durable state and name no application or site (Axiom 15); domains thread them
as immutable inputs/outputs and store nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


def _clamp01(value: float) -> float:
    """Clamp a float to the inclusive range [0, 1]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


# ---- Research (Ch 37) ------------------------------------------------------


@dataclass(frozen=True)
class RankedSource:
    """A gathered source with a domain-agnostic credibility score in [0, 1]."""

    url: str
    authority_class: str  # "primary" | "reference" | "general" — NEVER a literal site name
    credibility: float  # clamped [0, 1]

    def __post_init__(self) -> None:
        object.__setattr__(self, "credibility", _clamp01(self.credibility))


@dataclass(frozen=True)
class Claim:
    """A lightweight assertion extracted from gathered text."""

    subject: str
    polarity: bool  # True = asserts, False = negates
    source_url: str = ""


@dataclass(frozen=True)
class Contradiction:
    """Two claims about the same subject with opposing polarity."""

    subject: str
    positive_source: str
    negative_source: str


@dataclass(frozen=True)
class HypothesisScore:
    """Support for a hypothesis in [0, 1] derived from gathered claims."""

    hypothesis: str
    support: float  # clamped [0, 1]
    supporting: int
    total: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "support", _clamp01(self.support))


@dataclass(frozen=True)
class ResearchFinding:
    """The full outcome of an investigation — derived purely from gathered evidence."""

    query: str
    sources_read: int
    ranked_sources: Tuple[RankedSource, ...] = ()
    hypotheses: Tuple[HypothesisScore, ...] = ()
    contradictions: Tuple[Contradiction, ...] = ()
    blocked: bool = False
    error: str = ""

    @property
    def success(self) -> bool:
        return self.sources_read > 0 and not self.blocked


# ---- Communication (Ch 39) -------------------------------------------------


class DeliveryStatus(str, Enum):
    CONFIRMED = "confirmed"  # real DELIVERY_CONFIRMATION artifact present
    FAILED = "failed"  # capability ran but delivery not confirmed
    UNAVAILABLE = "unavailable"  # no deliver-verb capability in the registry


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    logical_index: int


@dataclass(frozen=True)
class Conversation:
    """Immutable, caller-owned transcript. The domain returns updated copies; it stores nothing."""

    turns: Tuple[Turn, ...] = ()

    def with_turn(self, speaker: str, text: str) -> "Conversation":
        return Conversation(turns=self.turns + (Turn(speaker, text, len(self.turns)),))


@dataclass(frozen=True)
class DeliveryOutcome:
    recipient: str
    status: DeliveryStatus
    capability_id: str = ""
    detail: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status is DeliveryStatus.CONFIRMED


# ---- Documents (Ch 40) -----------------------------------------------------


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    PLAINTEXT = "plaintext"
    DOCX = "docx"
    PDF = "pdf"


@dataclass(frozen=True)
class Citation:
    marker: str  # e.g. "[1]"
    source_url: str


@dataclass(frozen=True)
class Block:
    text: str
    style: str = "body"  # "body" | "bullet" | "code"


@dataclass(frozen=True)
class Section:
    heading: str
    blocks: Tuple[Block, ...] = ()


@dataclass(frozen=True)
class SemanticDocument:
    title: str
    sections: Tuple[Section, ...] = ()
    citations: Tuple[Citation, ...] = ()


@dataclass(frozen=True)
class ExportOutcome:
    filename: str
    fmt: DocumentFormat
    bytes_written: int = 0
    success: bool = False
    error: str = ""


# ---- Software (Ch 41, deferred) --------------------------------------------


@dataclass(frozen=True)
class DeferredOutcome:
    domain: str
    reason: str
    would_compose: Tuple[str, ...] = ()  # abstract verbs a v2 SWE domain would use
    deferred: bool = True
