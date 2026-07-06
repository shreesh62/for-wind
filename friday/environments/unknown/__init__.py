"""Ch 25/66 — Exploration Engine: understanding & operating never-before-seen software.

This package makes FRIDAY *general*. It builds an :class:`ObjectGraph` from any
environment's observations, infers generic :class:`Affordance`s, plans
risk-ordered experiments, safely probes the interface to confirm inferences, and
learns coordinate-free :class:`Principle`s from human demonstration.

CRITICAL (Axiom 15 / FAS Ch 63): every module here imports ONLY the abstract
``friday.environments.contract`` surface. Nothing imports ``DesktopEnvironment``
or ``BrowserEnvironment``, and there is no ``isinstance(env, ...)`` branch and no
app-specific code. That is what proves the engine is truly general.
"""

from friday.environments.unknown.affordances import AffordanceInferrer
from friday.environments.unknown.demonstration import (
    DemonstrationRecorder,
    DemonstrationRecording,
    extract_principles,
)
from friday.environments.unknown.experiment import (
    RISK_CONFIDENCE_GATE,
    SafeExperimentPlanner,
)
from friday.environments.unknown.exploration import ExplorationEngine
from friday.environments.unknown.object_graph import (
    Affordance,
    CapabilityCandidate,
    Experiment,
    ExplorationResult,
    ObjectGraph,
    ObjectNode,
    Principle,
    Procedure,
    RiskLevel,
)

__all__ = [
    # engine + helpers
    "ExplorationEngine",
    "AffordanceInferrer",
    "SafeExperimentPlanner",
    "DemonstrationRecorder",
    "DemonstrationRecording",
    "extract_principles",
    "RISK_CONFIDENCE_GATE",
    # data models
    "RiskLevel",
    "ObjectGraph",
    "ObjectNode",
    "Affordance",
    "Experiment",
    "ExplorationResult",
    "Principle",
    "Procedure",
    "CapabilityCandidate",
]
