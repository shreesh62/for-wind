"""Ch 16 — CapabilityRegistry: executable capabilities, queryable & confidence-ranked.

The registry is the runtime index of everything FRIDAY *can do*. Unlike the
legacy ``friday.tools.registry.ToolRegistry`` (which stored planning metadata
only), every entry here is an executable :class:`CapabilityContract` carrying
evidence-backed confidence. Callers ask for an abstract verb (``"click"``,
``"type"``, ``"read"``) and receive the matching capabilities ranked by
descending confidence.

Matching convention (kept deliberately simple):
    A capability matches an abstract verb if the verb appears in the
    capability's ``id`` OR the capability exposes an optional ``verbs`` list
    that contains the verb. If ``verbs`` is absent, only the id substring test
    is used.

Legacy coexistence (TD-5 migration):
    ``import_tool_metadata`` adopts the metadata-only legacy ``Tool`` entries as
    low-confidence, *unwired* :class:`ToolDescriptorCapability` descriptors so
    the planner keeps seeing them while the real handlers are ported. Their
    ``execute`` returns a failed ``ActionResult`` ("descriptor only, no
    handler"). ``as_tool_view`` re-projects the registry into the same
    verb→[capability ids] shape as ``ToolRegistry.list_capabilities()``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from friday.actions.result import ActionResult
from friday.capabilities.contracts import BaseCapability
from friday.kernel.contracts.capability import (
    CapabilityContract,
    CompetenceRecord,
    Condition,
    WorldStateDelta,
)
from friday.tools.registry import ToolRegistry
from friday.world.worlds import ObservedWorld


class ToolDescriptorCapability(BaseCapability):
    """Ch 16 — a low-confidence, unwired descriptor adopted from a legacy Tool.

    These exist only so the planner keeps seeing legacy capabilities during the
    TD-5 migration. They are *unwired*: ``execute`` returns a failed
    ``ActionResult`` because no real handler has been ported yet.
    """

    def __init__(
        self,
        tool_id: str,
        verbs: List[str],
        description: str = "",
        competence: Optional[CompetenceRecord] = None,
    ) -> None:
        # Seed a low-confidence record: 0 successes over a few attempts keeps
        # the Laplace estimate low so wired capabilities outrank descriptors.
        super().__init__(competence or CompetenceRecord(attempts=8, successes=0))
        self._id = tool_id
        self._verbs = list(verbs)
        self._description = description

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> str:
        return "legacy"

    @property
    def verbs(self) -> List[str]:
        return list(self._verbs)

    def preconditions(self) -> List[Condition]:
        return []

    def expected_outcome(self) -> WorldStateDelta:
        return WorldStateDelta()

    async def execute(self, params: Dict[str, Any], world: ObservedWorld) -> ActionResult:
        return ActionResult.failed(
            action=self._id,
            error="descriptor only, no handler",
            target="",
            error_category="unwired_descriptor",
        )

    def verify(self, result: ActionResult, world: ObservedWorld) -> bool:
        return False

    def recover(self, failure: ActionResult) -> Optional[CapabilityContract]:
        return None


class PromotedCapability(BaseCapability):
    """Ch 16 — a generic executable capability distilled from exploration.

    Wraps a duck-typed ``CapabilityCandidate`` (``proposed_id``, ``affordance``,
    ``procedure``, ``confidence``). Concrete, domain-specific capability classes
    arrive in later tasks; until then this provides a minimal executable wrapper.
    If a ``handler`` (async callable ``(params, world) -> ActionResult``) is
    supplied it is delegated to; otherwise ``execute`` returns a success
    placeholder recording that the capability was promoted from exploration.
    """

    def __init__(self, candidate: Any, handler: Optional[Any] = None) -> None:
        seed_attempts, seed_successes = self._seed_from_confidence(
            getattr(candidate, "confidence", 0.5)
        )
        super().__init__(CompetenceRecord(attempts=seed_attempts, successes=seed_successes))
        self._candidate = candidate
        self._handler = handler
        self._id = getattr(candidate, "proposed_id", "promoted.capability")
        affordance = getattr(candidate, "affordance", None)
        verb = getattr(affordance, "capability", None)
        self._verbs = [verb] if verb else []

    @staticmethod
    def _seed_from_confidence(confidence: float) -> tuple[int, int]:
        """Seed a CompetenceRecord so its Laplace estimate approximates confidence.

        Uses a fixed prior weight so a candidate's declared confidence is
        reflected in the initial ranking without being taken as ground truth.
        """
        c = max(0.0, min(1.0, float(confidence)))
        attempts = 8
        # solve (successes + 1) / (attempts + 2) ~= c  =>  successes ~= c*(attempts+2) - 1
        successes = int(round(c * (attempts + 2) - 1))
        successes = max(0, min(attempts, successes))
        return attempts, successes

    @property
    def candidate(self) -> Any:
        return self._candidate

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> str:
        return "promoted"

    @property
    def verbs(self) -> List[str]:
        return list(self._verbs)

    def preconditions(self) -> List[Condition]:
        return []

    def expected_outcome(self) -> WorldStateDelta:
        affordance = getattr(self._candidate, "affordance", None)
        effect = getattr(affordance, "expected_effect", None)
        adds = [effect] if effect else []
        return WorldStateDelta(adds=adds, confidence=self.confidence)

    async def execute(self, params: Dict[str, Any], world: ObservedWorld) -> ActionResult:
        if self._handler is not None:
            return await self._handler(params, world)
        return ActionResult.success(
            action=self._id,
            message="promoted capability executed (placeholder)",
            metadata={"promoted": True},
        )

    def verify(self, result: ActionResult, world: ObservedWorld) -> bool:
        return result.is_success

    def recover(self, failure: ActionResult) -> Optional[CapabilityContract]:
        return None


class CapabilityRegistry:
    """Ch 16 — registry of executable capabilities, queryable and confidence-ranked."""

    def __init__(self) -> None:
        self._capabilities: Dict[str, CapabilityContract] = {}

    def register(self, capability: CapabilityContract) -> None:
        """Register (or replace) a capability keyed by its ``id``."""
        self._capabilities[capability.id] = capability

    def unregister(self, capability_id: str) -> None:
        """Remove a capability by id (no error if absent)."""
        self._capabilities.pop(capability_id, None)

    def get(self, capability_id: str) -> Optional[CapabilityContract]:
        """Return the capability with the given id, or ``None``."""
        return self._capabilities.get(capability_id)

    def find_for(
        self, abstract_verb: str, min_confidence: float = 0.0
    ) -> List[CapabilityContract]:
        """Return capabilities matching ``abstract_verb`` sorted by descending confidence.

        A capability matches if the verb appears in its ``id`` OR it exposes a
        ``verbs`` collection containing the verb. Capabilities below
        ``min_confidence`` are excluded.
        """
        matches = [
            cap
            for cap in self._capabilities.values()
            if self._matches(cap, abstract_verb) and cap.confidence >= min_confidence
        ]
        matches.sort(key=lambda cap: cap.confidence, reverse=True)
        return matches

    @staticmethod
    def _matches(capability: CapabilityContract, abstract_verb: str) -> bool:
        if not abstract_verb:
            return False
        verb = abstract_verb.lower()
        declared = getattr(capability, "verbs", None)
        if declared:
            if any(verb == str(v).lower() for v in declared):
                return True
        return verb in capability.id.lower()

    def record_outcome(self, capability_id: str, result: ActionResult) -> None:
        """Fold an outcome into the named capability's competence record."""
        capability = self._capabilities.get(capability_id)
        if capability is not None:
            capability.update_competence(result)

    def promote_candidate(self, candidate: Any) -> CapabilityContract:
        """Register an executable capability distilled from a CapabilityCandidate.

        ``candidate`` is duck-typed: it must expose ``proposed_id``,
        ``affordance``, ``procedure`` and ``confidence``. A generic
        :class:`PromotedCapability` wrapping the candidate is registered and
        returned.
        """
        capability = PromotedCapability(candidate)
        self.register(capability)
        return capability

    # --- Legacy coexistence (TD-5 migration) ------------------------------

    def import_tool_metadata(self, tool_registry: ToolRegistry) -> None:
        """Adopt legacy ``Tool`` entries as low-confidence, unwired descriptors.

        Each legacy tool becomes a :class:`ToolDescriptorCapability` with
        ``id = tool.name`` and ``verbs = tool.capability_names``. They register
        into the same index so the planner keeps seeing them, but they are
        unwired (``execute`` fails) until real handlers are ported.
        """
        for tool in tool_registry.list_all():
            descriptor = ToolDescriptorCapability(
                tool_id=tool.name,
                verbs=list(tool.capability_names),
                description=getattr(tool, "description", ""),
            )
            self.register(descriptor)

    def as_tool_view(self) -> Dict[str, List[str]]:
        """Return a verb→[capability ids] map shaped like ``ToolRegistry.list_capabilities()``."""
        view: Dict[str, List[str]] = {}
        for capability in self._capabilities.values():
            verbs = getattr(capability, "verbs", None) or []
            for verb in verbs:
                view.setdefault(str(verb), []).append(capability.id)
        return view

    @property
    def capability_count(self) -> int:
        return len(self._capabilities)
