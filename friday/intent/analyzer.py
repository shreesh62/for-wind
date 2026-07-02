"""Ch 7/8 — IntentAnalyzer: kernel-attached intent + classification pipeline.

Listens for goal.created events, produces an Intent and a Classification
for each goal, and publishes them back onto the event log
(intent.analyzed, goal.classified) so deliberation can consume them.
Heuristic-only in M5; an LLM analyzer can replace the heuristics later
behind the same interface.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from friday.events.event import Event, make_event
from friday.intent.classifier import Classification, ProblemClassifier
from friday.intent.intent import Assumption, Intent

_VAGUE_MARKERS = ("something", "somehow", "stuff", "things", "whatever", "etc")
_MULTI_STEP_MARKERS = (" and ", " then ", " after ", ";", " also ")


class IntentAnalyzer:
    """Builds Intents and Classifications for kernel goals."""

    def __init__(self, classifier: Optional[ProblemClassifier] = None) -> None:
        self._classifier = classifier or ProblemClassifier()
        self._kernel: Any = None
        self._lock = threading.RLock()
        self._by_goal: Dict[str, Tuple[Intent, Classification]] = {}

    def attach(self, kernel: Any) -> None:
        self._kernel = kernel
        kernel.subscribe("goal.created", self._on_goal_created)

    def for_goal(self, goal_id: str) -> Optional[Tuple[Intent, Classification]]:
        with self._lock:
            return self._by_goal.get(goal_id)

    def analyze(self, raw_text: str) -> Intent:
        objective = " ".join(raw_text.strip().split())
        assumptions = self._find_assumptions(objective)
        return Intent(
            raw_text=raw_text,
            objective=objective,
            assumptions=tuple(assumptions),
            complexity=self._estimate_complexity(objective),
        )

    def _find_assumptions(self, objective: str) -> List[Assumption]:
        text = objective.lower()
        assumptions: List[Assumption] = []
        for marker in _VAGUE_MARKERS:
            if marker in text:
                assumptions.append(
                    Assumption(
                        description=f"Interpretation of vague term '{marker}'",
                        confidence=0.4,
                        critical=True,
                    )
                )
        if not any(ch.isdigit() for ch in text) and (
            "every" in text or "each" in text
        ):
            assumptions.append(
                Assumption(
                    description="Unbounded scope ('every'/'each') taken literally",
                    confidence=0.6,
                    critical=False,
                )
            )
        return assumptions

    def _estimate_complexity(self, objective: str) -> float:
        text = objective.lower()
        score = min(1.0, len(text.split()) / 40.0)
        for marker in _MULTI_STEP_MARKERS:
            if marker in text:
                score = min(1.0, score + 0.2)
        return round(score, 4)

    # Kernel wiring -----------------------------------------------------------

    def _on_goal_created(self, event: Event) -> None:
        goal_id = event.payload.get("goal_id")
        text = event.payload.get("text", "")
        if not goal_id:
            return
        intent = self.analyze(text)
        classification = self._classifier.classify(intent.objective)
        with self._lock:
            self._by_goal[goal_id] = (intent, classification)
        self._publish("intent.analyzed", {"goal_id": goal_id, **intent.to_payload()}, event)
        self._publish(
            "goal.classified", {"goal_id": goal_id, **classification.to_payload()}, event
        )

    def _publish(self, event_type: str, payload: Dict[str, Any], cause: Event) -> None:
        if self._kernel is None:
            return
        self._kernel.publish_event(
            make_event(
                event_type=event_type,
                source="intent",
                logical_time=cause.logical_time + 1,
                payload=payload,
                correlation_id=cause.correlation_id,
                parent_id=cause.id,
            )
        )
