"""Ch 25 — SafeExperimentPlanner: order experiments up the risk ladder, gate by confidence.

The planner turns an :class:`ObjectGraph` into a list of :class:`Experiment`s
sorted by *ascending* risk (observe < hover < click < modify < delete) and
decides which are permitted given a node's current confidence.

The gate table :data:`RISK_CONFIDENCE_GATE` is **monotonic** in risk — a
higher-risk experiment requires strictly-or-equally higher confidence — which
encodes "high-risk actions require high confidence". A DELETE-risk experiment is
never permitted while node confidence is below ``0.9``.

CRITICAL (Axiom 15): planning keys off generic affordances/risk only. There is
no environment-type branch and no app-specific rule.
"""

from __future__ import annotations

from typing import List

from friday.actions.target import Target
from friday.environments.contract import Action
from friday.environments.unknown.object_graph import (
    Experiment,
    ObjectGraph,
    RiskLevel,
)

# Monotonic mapping: minimum node confidence required to run at each risk level.
RISK_CONFIDENCE_GATE = {
    RiskLevel.OBSERVE: 0.0,
    RiskLevel.HOVER: 0.2,
    RiskLevel.CLICK: 0.5,
    RiskLevel.MODIFY: 0.75,
    RiskLevel.DELETE: 0.9,
}


class SafeExperimentPlanner:
    """Ch 25 — orders experiments up the risk ladder; gates by confidence."""

    def plan(self, graph: ObjectGraph) -> List[Experiment]:
        """Return experiments sorted by ascending RiskLevel.

        For each node, for each of its affordances, build a reversible-aware
        :class:`Experiment` targeting that node. The resulting list is sorted by
        ascending risk (observe < hover < click < modify < delete).
        """
        experiments: List[Experiment] = []
        for node in graph.nodes():
            for affordance in node.affordances:
                target = Target(text=node.label) if node.label else None
                action = Action(
                    capability=affordance.capability,
                    target=target,
                    params={"node_id": node.id},
                )
                experiments.append(
                    Experiment(
                        node_id=node.id,
                        action=action,
                        risk=affordance.risk,
                        hypothesis=(
                            f"{affordance.capability} on '{node.label or node.id}' "
                            f"{affordance.expected_effect}"
                        ),
                        reversible=affordance.risk < RiskLevel.MODIFY,
                    )
                )
        experiments.sort(key=lambda exp: int(exp.risk))
        return experiments

    def is_permitted(self, experiment: Experiment, node_confidence: float) -> bool:
        """A higher-risk experiment requires higher confidence.

        Permitted iff ``node_confidence >= RISK_CONFIDENCE_GATE[experiment.risk]``.
        A DELETE-risk experiment is never permitted while confidence is < 0.9.
        """
        gate = RISK_CONFIDENCE_GATE[experiment.risk]
        return node_confidence >= gate
