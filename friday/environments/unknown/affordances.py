"""Ch 66 — AffordanceInferrer: infer what can be done with an object, generically.

The inferrer maps a node's *generic* type and *generic* visible-text semantics
to candidate :class:`Affordance`s, each carrying a :class:`RiskLevel` and the
minimum node confidence required to attempt it.

CRITICAL (Axiom 15): every signal used here is generic. "button"/"textbox" are
universal control-type vocabulary, and destructive-word detection keys off
ordinary English text ("delete", "remove", "trash") — this is *text semantics*,
not application identity. There is no ``if app == ...`` branch and no per-app
handler anywhere.
"""

from __future__ import annotations

from typing import List

from friday.environments.unknown.object_graph import (
    Affordance,
    ObjectGraph,
    ObjectNode,
    RiskLevel,
)

# Generic English words that signal a destructive action. This is text
# semantics shared across all interfaces, not app identity.
_DESTRUCTIVE_WORDS = ("delete", "remove", "trash", "discard", "erase", "destroy")


class AffordanceInferrer:
    """Ch 66 — infer what can be done with an object, generically."""

    def infer(self, node: ObjectNode, graph: ObjectGraph) -> List[Affordance]:
        """Return candidate affordances for ``node`` from generic signals only."""
        affordances: List[Affordance] = []

        # Every object can always be observed and hovered — the safest rungs.
        affordances.append(
            Affordance(
                capability="observe",
                risk=RiskLevel.OBSERVE,
                expected_effect="reads the object's current state without changing it",
                min_confidence_required=0.0,
            )
        )
        affordances.append(
            Affordance(
                capability="hover",
                risk=RiskLevel.HOVER,
                expected_effect="reveals tooltips or hover state without committing",
                min_confidence_required=0.2,
            )
        )

        label = (node.label or "").lower()
        looks_destructive = any(word in label for word in _DESTRUCTIVE_WORDS)
        object_type = (node.object_type or "").lower()
        editable = object_type == "textbox"

        if looks_destructive:
            # Generic destructive-text semantics -> a high-risk click gate.
            affordances.append(
                Affordance(
                    capability="click",
                    risk=RiskLevel.DELETE,
                    expected_effect="may irreversibly remove or destroy data",
                    min_confidence_required=0.9,
                )
            )
        elif object_type == "button":
            affordances.append(
                Affordance(
                    capability="click",
                    risk=RiskLevel.CLICK,
                    expected_effect="activates the control and triggers its action",
                    min_confidence_required=0.5,
                )
            )

        if editable:
            affordances.append(
                Affordance(
                    capability="type",
                    risk=RiskLevel.MODIFY,
                    expected_effect="enters text, modifying the object's content",
                    min_confidence_required=0.75,
                )
            )

        return affordances
