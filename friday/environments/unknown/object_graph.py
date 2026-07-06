"""Ch 66 — ObjectGraph & shared exploration data models (Ch 25 risk concepts).

This module holds the shared data structures the Exploration Engine is built on.
Two FAS chapters meet here:

- **Ch 66** — the interface :class:`ObjectGraph` and its :class:`ObjectNode` /
  :class:`Affordance` nodes: a generic, app-agnostic model of *what objects an
  interface exposes and what can be done with them*.
- **Ch 25** — the safety ladder (:class:`RiskLevel`) and the exploration
  bookkeeping types (:class:`Experiment`, :class:`ExplorationResult`,
  :class:`Principle`, :class:`Procedure`, :class:`CapabilityCandidate`).

CRITICAL (Axiom 15 / FAS Ch 63): nothing in this module knows about a concrete
environment. Type inference is **generic** — it keys off the observation's
``object_type`` / ``attributes`` (control type, editability, role), never off an
application name or a hardcoded rule such as ``if app == "notepad"``. This is
what lets the same graph model work against desktop, browser, and never-seen
software identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from friday.actions.result import ActionResult, ActionStatus
from friday.environments.contract import Action
from friday.perception.observation import Observation
from friday.perception.types import BoundingBox, PerceptionSource


class RiskLevel(int, Enum):
    """Ch 25 — the safety ladder. Lower ordinal = safer. Order is the contract."""

    OBSERVE = 0
    HOVER = 1
    CLICK = 2
    MODIFY = 3
    DELETE = 4


@dataclass(frozen=True)
class Affordance:
    """Ch 66 — a possible interaction and its risk + expected effect."""

    capability: str                  # abstract verb: "click", "type", "toggle"
    risk: RiskLevel
    expected_effect: str             # human-readable prediction
    min_confidence_required: float   # gate: only attempt if node confidence >= this


@dataclass
class ObjectNode:
    """Ch 66 — a node in the interface ObjectGraph."""

    id: str
    object_type: str                 # inferred: "button", "textbox", "menu", "unknown"
    label: str                       # visible text/name
    bbox: Optional[BoundingBox] = None
    affordances: List[Affordance] = field(default_factory=list)
    confidence: float = 0.5          # grows as experiments confirm inferences
    source: PerceptionSource = PerceptionSource.UIA


@dataclass
class Experiment:
    """Ch 25 — one safe probe against an object."""

    node_id: str
    action: Action
    risk: RiskLevel
    hypothesis: str
    reversible: bool


@dataclass
class ExplorationResult:
    """Ch 25 — the outcome of an exploration session."""

    graph: "ObjectGraph"
    experiments_run: List[Experiment]
    confidence: float                # overall understanding of the interface
    budget_spent: int
    notes: List[str] = field(default_factory=list)


@dataclass
class Principle:
    """Ch 25 — a coordinate-free description extracted from demonstration."""

    step_index: int
    capability: str                  # "click" | "type" | "scroll"
    target_descriptor: str           # "the prominent primary button in the top-right region"
    value: Optional[str] = None      # typed text pattern, if any (parameterizable)


@dataclass
class Procedure:
    """Ch 25 — an ordered, reusable, coordinate-free plan learned from a demo."""

    name: str
    principles: List[Principle]


@dataclass
class CapabilityCandidate:
    """Ch 16/66 — a proposed new capability distilled from successful exploration."""

    proposed_id: str
    affordance: Affordance
    procedure: Optional[Procedure]
    evidence_count: int
    confidence: float


# --- Generic type-inference signals (NOT app rules) -----------------------
#
# These sets describe *generic* control-type / role vocabulary shared across
# interfaces. They map raw observation hints to a small, universal type
# vocabulary. There is no application identity anywhere here.

_BUTTON_HINTS = {"button", "btn", "menuitem", "link", "hyperlink", "tab"}
_TEXTBOX_HINTS = {"textbox", "edit", "input", "textarea", "field", "combobox", "searchbox"}


def _clamp(value: float) -> float:
    """Clamp a confidence value into ``[0.0, 1.0]``."""
    return max(0.0, min(1.0, float(value)))


class ObjectGraph:
    """Ch 66 — a generic graph of inferred interface objects.

    Built from any environment's :class:`Observation` stream. Type inference and
    confidence bookkeeping are entirely app-agnostic: the graph never learns
    whether it is describing a desktop app, a web page, or a stub.
    """

    def __init__(self) -> None:
        self._nodes: List[ObjectNode] = []
        self._index: dict[str, ObjectNode] = {}

    # -- construction -------------------------------------------------------

    def add_from_observation(self, obs: Observation) -> ObjectNode:
        """Add (or refresh) a node from a single uniform Observation."""
        bbox = self._bbox_from_observation(obs)
        label = self._label_from_observation(obs)
        source = self._source_from_observation(obs)
        node = ObjectNode(
            id=obs.id,
            object_type=obs.object_type or "unknown",
            label=label,
            bbox=bbox,
            confidence=_clamp(obs.confidence * 0.5),  # unconfirmed inference starts low
            source=source,
        )
        if node.id in self._index:
            # Refresh in place, preserving affordances/confidence gains.
            existing = self._index[node.id]
            existing.object_type = node.object_type
            existing.label = node.label
            existing.bbox = node.bbox
            existing.source = node.source
            return existing
        self._nodes.append(node)
        self._index[node.id] = node
        return node

    @staticmethod
    def _bbox_from_observation(obs: Observation) -> Optional[BoundingBox]:
        raw = obs.bbox
        if raw is None:
            return None
        if isinstance(raw, BoundingBox):
            return raw
        try:
            x, y, w, h = raw
        except (TypeError, ValueError):
            return None
        return BoundingBox(x=int(x), y=int(y), width=int(w), height=int(h))

    @staticmethod
    def _label_from_observation(obs: Observation) -> str:
        attrs = obs.attributes
        for key in ("name", "text", "label", "title", "value"):
            val = attrs.get(key) if attrs is not None else None
            if val:
                return str(val)
        return ""

    @staticmethod
    def _source_from_observation(obs: Observation) -> PerceptionSource:
        sensor = (obs.sensor or "").lower()
        for source in PerceptionSource:
            if source.value == sensor:
                return source
        return PerceptionSource.UIA

    # -- inference ----------------------------------------------------------

    def infer_types(self) -> None:
        """Infer a generic object type for every node from generic signals only.

        Uses the observation's declared ``object_type`` plus editability and
        role hints. NO application-specific rules: a role/control-type in the
        generic button vocabulary -> "button"; editable / textbox vocabulary ->
        "textbox"; otherwise "unknown".
        """
        for node in self._nodes:
            node.object_type = self._infer_one(node)

    def _infer_one(self, node: ObjectNode) -> str:
        raw = (node.object_type or "").lower()
        if raw in _TEXTBOX_HINTS or any(hint in raw for hint in _TEXTBOX_HINTS):
            return "textbox"
        if raw in _BUTTON_HINTS or any(hint in raw for hint in _BUTTON_HINTS):
            return "button"
        return "unknown"

    # -- confidence ---------------------------------------------------------

    def confidence_for(self, node_id: str) -> float:
        """Return current confidence for a node id (0.0 if unknown)."""
        node = self._index.get(node_id)
        return node.confidence if node is not None else 0.0

    def update_from_result(self, experiment: Experiment, result: ActionResult) -> None:
        """Fold an experiment outcome into the target node's confidence.

        A confirmed (successful, evidence-backed) experiment raises the node's
        confidence; a denied (failed) experiment lowers it. Confidence stays
        clamped to ``[0, 1]``.
        """
        node = self._index.get(experiment.node_id)
        if node is None:
            return
        confirmed = result.status == ActionStatus.SUCCESS
        if confirmed:
            # Move a fraction of the remaining distance toward 1.0.
            node.confidence = _clamp(node.confidence + (1.0 - node.confidence) * 0.5)
        else:
            node.confidence = _clamp(node.confidence * 0.5)

    def overall_confidence(self) -> float:
        """Mean node confidence in ``[0, 1]`` (0.0 for an empty graph)."""
        if not self._nodes:
            return 0.0
        return _clamp(sum(n.confidence for n in self._nodes) / len(self._nodes))

    # -- access -------------------------------------------------------------

    def nodes(self) -> List[ObjectNode]:
        """Return the graph's nodes (insertion order)."""
        return list(self._nodes)
