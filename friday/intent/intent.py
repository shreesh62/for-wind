"""Ch 7 — Intent: what the user actually wants, made explicit.

An Intent separates the raw utterance from the interpreted objective, and
makes every assumption explicit on a confidence spectrum so the operator
knows what to clarify versus what to safely assume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class Assumption:
    """One interpretation gap filled by the operator, on a confidence spectrum."""

    description: str
    confidence: float  # 1.0 = safe default, near 0.0 = wild guess
    critical: bool = False  # wrong guess would derail the goal

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))

    @property
    def needs_clarification(self) -> bool:
        return self.critical and self.confidence < 0.7


@dataclass(frozen=True)
class Intent:
    """The interpreted objective behind a raw request."""

    raw_text: str
    objective: str  # normalized statement of the desired outcome
    assumptions: Tuple[Assumption, ...] = ()
    complexity: float = 0.5  # 0 trivial .. 1 open-ended multi-step
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        object.__setattr__(self, "complexity", max(0.0, min(1.0, self.complexity)))

    @property
    def requires_clarification(self) -> bool:
        return any(a.needs_clarification for a in self.assumptions)

    @property
    def clarification_questions(self) -> Tuple[str, ...]:
        return tuple(
            a.description for a in self.assumptions if a.needs_clarification
        )

    def to_payload(self) -> Dict[str, Any]:
        return {
            "intent_id": self.id,
            "raw_text": self.raw_text,
            "objective": self.objective,
            "complexity": self.complexity,
            "assumptions": [
                {
                    "description": a.description,
                    "confidence": a.confidence,
                    "critical": a.critical,
                }
                for a in self.assumptions
            ],
            "requires_clarification": self.requires_clarification,
        }
