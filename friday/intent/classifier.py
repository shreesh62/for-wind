"""Ch 8 — Problem classification: what KIND of problem is this goal?

Deterministic keyword/structure heuristics (no LLM in M5); a goal can
belong to several classes with weights, and classification is revisable
as new evidence arrives (reclassify()).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple


class ProblemClass(str, Enum):
    INFORMATION_GATHERING = "information_gathering"
    CREATION = "creation"
    TRANSFORMATION = "transformation"
    COMMUNICATION = "communication"
    NAVIGATION = "navigation"
    MONITORING = "monitoring"
    AUTOMATION = "automation"
    UNKNOWN = "unknown"


_SIGNALS: Dict[ProblemClass, Tuple[str, ...]] = {
    ProblemClass.INFORMATION_GATHERING: (
        "find", "search", "research", "look up", "lookup", "what is", "who is",
        "gather", "compare", "learn", "investigate", "check",
    ),
    ProblemClass.CREATION: (
        "create", "write", "draft", "make", "build", "generate", "compose",
        "produce", "new file", "new document",
    ),
    ProblemClass.TRANSFORMATION: (
        "convert", "transform", "translate", "summarize", "format", "rename",
        "resize", "merge", "split", "edit", "update", "fix",
    ),
    ProblemClass.COMMUNICATION: (
        "send", "email", "message", "reply", "notify", "share", "post", "dm",
        "tell", "inform",
    ),
    ProblemClass.NAVIGATION: (
        "open", "go to", "navigate", "visit", "launch", "switch to", "close",
    ),
    ProblemClass.MONITORING: (
        "watch", "monitor", "track", "alert", "when", "whenever", "every time",
        "keep an eye",
    ),
    ProblemClass.AUTOMATION: (
        "automate", "schedule", "recurring", "daily", "weekly", "every day",
        "every week", "routinely",
    ),
}


@dataclass(frozen=True)
class Classification:
    """Weighted problem-class assignment for a goal; revisable."""

    weights: Tuple[Tuple[str, float], ...]  # (class value, weight) descending
    revision: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def primary(self) -> ProblemClass:
        if not self.weights:
            return ProblemClass.UNKNOWN
        return ProblemClass(self.weights[0][0])

    @property
    def classes(self) -> Tuple[ProblemClass, ...]:
        return tuple(ProblemClass(c) for c, _ in self.weights)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "classification_id": self.id,
            "primary": self.primary.value,
            "weights": [list(pair) for pair in self.weights],
            "revision": self.revision,
        }


class ProblemClassifier:
    """Keyword-signal classifier; general-purpose, never app-specific."""

    def classify(self, objective: str) -> Classification:
        text = objective.lower()
        scores: Dict[ProblemClass, float] = {}
        for problem_class, signals in _SIGNALS.items():
            hits = sum(
                1
                for signal in signals
                if re.search(rf"\b{re.escape(signal)}\b", text)
            )
            if hits:
                scores[problem_class] = float(hits)
        if not scores:
            return Classification(weights=((ProblemClass.UNKNOWN.value, 1.0),))
        total = sum(scores.values())
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return Classification(
            weights=tuple((cls.value, round(score / total, 4)) for cls, score in ordered)
        )

    def reclassify(
        self, previous: Classification, objective: str
    ) -> Classification:
        """Re-run classification as understanding evolves; bumps revision."""
        fresh = self.classify(objective)
        return Classification(weights=fresh.weights, revision=previous.revision + 1)
