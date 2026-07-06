"""Ch 25 — ExplorationEngine: make unknown software learnable via safe experimentation.

The engine is the heart of "general". It:

1. observes the environment and builds an :class:`ObjectGraph`,
2. infers generic :class:`Affordance`s for every node,
3. plans **risk-ordered** experiments,
4. executes only the *permitted* (confidence-gated) ones, in non-decreasing
   risk order, until it is confident enough or the budget is spent, and
5. optionally distils a :class:`CapabilityCandidate` from what it learned.

CRITICAL (Axiom 15 / FAS Ch 63): :meth:`explore` uses ONLY the abstract
:class:`EnvironmentContract` surface (``observe`` / ``interact``). It cannot
tell desktop from browser from stub — there is no environment-type branch
anywhere. That is precisely what proves generality.
"""

from __future__ import annotations

from typing import List, Optional

from friday.actions.result import ActionStatus
from friday.capabilities.registry import CapabilityRegistry
from friday.environments.contract import EnvironmentContract
from friday.environments.unknown.affordances import AffordanceInferrer
from friday.environments.unknown.demonstration import (
    DemonstrationRecording,
    extract_principles,
)
from friday.environments.unknown.experiment import SafeExperimentPlanner
from friday.environments.unknown.object_graph import (
    CapabilityCandidate,
    ExplorationResult,
    ObjectGraph,
    Procedure,
    RiskLevel,
)


class ExplorationEngine:
    """Ch 25/66 — makes unknown software learnable via safe experimentation."""

    def __init__(
        self,
        inferrer: AffordanceInferrer,
        planner: SafeExperimentPlanner,
        registry: CapabilityRegistry,
        max_experiments: int = 20,
        confidence_target: float = 0.75,
    ) -> None:
        self.inferrer = inferrer
        self.planner = planner
        self.registry = registry
        self.max_experiments = max_experiments
        self.confidence_target = confidence_target

    def explore(self, environment: EnvironmentContract) -> ExplorationResult:
        """Build understanding of ``environment`` through safe, risk-ordered probes.

        Uses only ``environment.observe()`` / ``environment.interact()`` — no
        environment-type branch. Experiments run in non-decreasing risk order;
        any experiment whose risk exceeds what the node's confidence allows is
        skipped (and recorded in ``notes``). Terminates at the confidence target
        or when the experiment budget is exhausted.
        """
        graph = ObjectGraph()
        notes: List[str] = []

        # 1. observe (Axiom 3) & 2. build the object graph
        for obs in environment.observe():
            graph.add_from_observation(obs)

        # 3. infer generic types and affordances
        graph.infer_types()
        for node in graph.nodes():
            node.affordances = self.inferrer.infer(node, graph)

        # 4. plan experiments ordered by ascending risk
        experiments = self.planner.plan(graph)

        # 5. execute the permitted experiments
        run = []
        for exp in experiments:
            if len(run) >= self.max_experiments:
                notes.append("experiment budget exhausted")
                break
            node_confidence = graph.confidence_for(exp.node_id)
            if not self.planner.is_permitted(exp, node_confidence):
                notes.append(
                    f"skipped {exp.action.capability} on node {exp.node_id}: "
                    f"risk {exp.risk.name} requires higher confidence than "
                    f"{node_confidence:.2f}"
                )
                continue
            result = environment.interact(exp.action)
            graph.update_from_result(exp, result)
            run.append(exp)
            if graph.overall_confidence() >= self.confidence_target:
                notes.append("confidence target reached")
                break

        return ExplorationResult(
            graph=graph,
            experiments_run=run,
            confidence=graph.overall_confidence(),
            budget_spent=len(run),
            notes=notes,
        )

    def learn_from_demonstration(
        self, recording: DemonstrationRecording
    ) -> List[Procedure]:
        """Distil a coordinate-free :class:`Procedure` from a demonstration.

        Delegates to :func:`extract_principles` and wraps the result in a single
        :class:`Procedure`.
        """
        principles = extract_principles(recording)
        if not principles:
            return []
        procedure = Procedure(name="learned_procedure", principles=principles)
        return [procedure]

    def generate_capability_candidate(
        self, exploration: ExplorationResult
    ) -> Optional[CapabilityCandidate]:
        """Distil a :class:`CapabilityCandidate` from a confident exploration.

        Returns ``None`` unless the exploration reached the confidence target and
        contains at least one successful, high-value experiment (a confirmed
        state-changing interaction). The candidate is built from the best such
        affordance.
        """
        if exploration.confidence < self.confidence_target:
            return None

        graph = exploration.graph
        best_affordance = None
        best_node_id = None
        best_risk = -1

        # A high-value, confirmed experiment: the node's confidence rose and its
        # affordance is state-changing (risk >= CLICK). Pick the highest-risk
        # such affordance among explored nodes as the most valuable capability.
        for exp in exploration.experiments_run:
            node = next((n for n in graph.nodes() if n.id == exp.node_id), None)
            if node is None:
                continue
            if int(exp.risk) < int(RiskLevel.CLICK):
                continue
            affordance = next(
                (a for a in node.affordances if a.capability == exp.action.capability),
                None,
            )
            if affordance is None:
                continue
            if int(exp.risk) > best_risk:
                best_risk = int(exp.risk)
                best_affordance = affordance
                best_node_id = node.id

        if best_affordance is None:
            return None

        return CapabilityCandidate(
            proposed_id=f"explored.{best_affordance.capability}.{best_node_id}",
            affordance=best_affordance,
            procedure=None,
            evidence_count=exploration.budget_spent,
            confidence=exploration.confidence,
        )
