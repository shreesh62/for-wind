"""Ch 15 — learning data models: the immutable records of the learning pipeline.

These frozen dataclasses are the pure vocabulary the M9 Learning subsystem folds
one verified experience through: a ``VerifiedExperience`` is discovered into a
``DiscoveredPattern`` (repeated verified evidence), generalized into a transferable
``Principle`` (Ch 15.6/15.9), and validated into a ``ValidationResult``; a
``LearningStep`` is the audit record of one ``ingest()``.

Isolation (Property 1 / Req 5.2): this module holds only plain data — it MUST NOT
import ``friday.memory.controller``, ``friday.memory.runtime``, or any
``friday.competence`` module, and MUST NOT reference ``FridayMemory``/``MemoryStore``.
No literal application name, site name, or URL appears here (Axiom 15).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# The (capability, environment) tuple keying competence evidence (mirrors the M8
# CompetenceModel precedent without importing it).
CompetenceKey = Tuple[str, str]


@dataclass(frozen=True)
class VerifiedExperience:
    """Ch 15.19 — one unit of experience the learner may consume.

    Only records whose ``verified`` field is ``True`` may enter the learning
    pipeline (the hard gate of Ch 15.19).
    """

    goal_id: str
    capability: str
    environment: str
    outcome_signature: str      # stable hash of the observed outcome (repetition key)
    prediction_error: float     # 0..1 from the M8 reflection
    verified: bool              # HARD GATE — must be True to be learned from
    competence_delta: float     # signed nudge carried from reflection
    logical_time: int
    wall_time: float


@dataclass(frozen=True)
class DiscoveredPattern:
    """A pattern backed by repeated verified experience (support >= min_repetitions)."""

    signature: str
    capability: str
    environment: str
    support: int                # count of verified repetitions (>= min_repetitions)
    mean_prediction_error: float


@dataclass(frozen=True)
class Principle:
    """A generalized, transferable learning lifted from one or more patterns (Ch 15.6/15.9).

    ``applicability`` and ``source_signatures`` are tuples so the record stays
    immutable and hashable; ``statement`` carries no literal app/site name (Axiom 15).
    ``confidence`` is clamped to ``[0, 1]`` on construction and derived monotonically
    from accumulated support.
    """

    id: str
    statement: str                    # human-readable, NO literal app/site names (Axiom 15)
    applicability: Tuple[str, ...]    # capability/environment classes it transfers to
    source_signatures: Tuple[str, ...]
    support: int
    confidence: float                 # in [0, 1], monotonically derived from support

    def __post_init__(self) -> None:
        # Clamp confidence into [0, 1] (data-model validation, Req 1.4/5.4).
        object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))


class ValidationStatus(str, Enum):
    """Ch 15.4 — the outcome of validating a Principle before promotion."""

    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ValidationResult:
    """The audited result of one validation: status plus the signed improvement delta."""

    status: ValidationStatus
    principle_id: str
    improvement: float          # signed observed - baseline
    reason: str


@dataclass(frozen=True)
class LearningStep:
    """Audit record of one ingest(): what the pipeline did with a single experience."""

    discovered: Optional[DiscoveredPattern]
    generalized: Optional[Principle]
    validation: Optional[ValidationResult]
