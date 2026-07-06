"""Ch 34 — RecoveryEngine: the full failure→recovery loop.

Generalizes the existing RepairDiagnoser (``friday/planner/repair.py``) into the
full Ch 34.4 loop:

    Failure → Observe → Classify → Collect Evidence → Generate Alternatives →
    Estimate Utility → Execute Recovery → Verify → Continue.

It adds the Ch 34.3 failure taxonomy, the Ch 34.5 recovery-level ladder, and the
Ch 34.9 Action Rollback Contracts (Undo/Rollback/Compensation/None), where an
irreversible action raises the confidence required to attempt recovery.

The RepairDiagnoser is **wrapped, never rewritten**: this engine delegates
diagnosis to ``RepairDiagnoser.diagnose`` and maps the resulting ``RepairCause``
into the richer ``FailureClass`` taxonomy.

Recovery **preserves the goal id and changes strategy** (Ch 34.1): its output
references the same ``goal_id`` and proposes a different approach, published as a
``recovery.proposed`` kernel event for the Deliberator to re-enter.

This module MUST NOT import ``friday.memory.controller`` (Req 5.3): subsystems
communicate only through kernel events (Ch 52).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional

from friday.events.event import make_event
from friday.planner.repair import RepairCause, RepairDiagnoser, RepairDiagnosis


class FailureClass(str, Enum):
    """Ch 34.3 — the failure taxonomy (superset mapping ``RepairCause``)."""

    TRANSIENT = "transient"            # retry may succeed (timeouts, flakiness)
    PRECONDITION = "precondition"      # required state absent (no sources/content)
    CAPABILITY = "capability"          # capability not competent here
    ENVIRONMENTAL = "environmental"    # environment changed/unavailable
    BLOCKED = "blocked"                # captcha/verification/human wall
    IRRECOVERABLE = "irrecoverable"    # no viable alternative
    UNKNOWN = "unknown"


class RecoveryLevel(IntEnum):
    """Ch 34.5 — escalating recovery levels (lower tried first)."""

    MICRO = 0          # retry the same action
    LOCAL = 1          # different capability, same plan step
    ENVIRONMENTAL = 2  # change environment/session
    STRATEGIC = 3      # replan the approach (new strategy, same goal)
    HUMAN = 4          # request human help
    ARCHITECTURAL = 5  # capability/architecture gap — escalate


class RollbackKind(str, Enum):
    """Ch 34.9 — Action Rollback Contract kinds."""

    UNDO = "undo"                  # exact inverse exists
    ROLLBACK = "rollback"          # restore a prior checkpoint
    COMPENSATION = "compensation"  # semantically offset (no exact inverse)
    NONE = "none"                  # irreversible — nothing can undo it


@dataclass(frozen=True)
class RecoveryAlternative:
    """One candidate recovery approach, with an estimated utility."""

    level: RecoveryLevel
    description: str
    capability: str
    estimated_utility: float
    required_confidence: float     # raised for irreversible actions (Ch 34.9)


@dataclass(frozen=True)
class RecoveryPlan:
    """Ch 34 — the recovery decision for one failure (audit-grade, pure).

    ``goal_id`` is preserved verbatim from the input (Ch 34.1). When ``reversible``
    is False the chosen alternative's ``required_confidence`` is at least
    ``IRREVERSIBLE_CONFIDENCE_FLOOR``; otherwise ``chosen`` is None and ``level``
    is escalated.
    """

    goal_id: str                   # PRESERVED — same goal (Ch 34.1)
    failure_class: FailureClass
    level: RecoveryLevel
    rollback: RollbackKind
    alternatives: tuple            # ordered RecoveryAlternative by utility desc
    chosen: Optional[RecoveryAlternative]
    reversible: bool
    note: str = ""

    def to_payload(self) -> Dict[str, Any]:
        """Project into a JSON-serializable ``recovery.proposed`` payload."""
        floor = (
            RecoveryEngine.REVERSIBLE_CONFIDENCE_FLOOR
            if self.reversible
            else RecoveryEngine.IRREVERSIBLE_CONFIDENCE_FLOOR
        )
        required = self.chosen.required_confidence if self.chosen else floor
        return {
            "goal_id": self.goal_id,
            "failure_class": self.failure_class.value,
            "level": int(self.level),
            "rollback": self.rollback.value,
            "alternatives": [
                {
                    "level": int(alt.level),
                    "description": alt.description,
                    "capability": alt.capability,
                    "estimated_utility": alt.estimated_utility,
                    "required_confidence": alt.required_confidence,
                }
                for alt in self.alternatives
            ],
            "chosen": (
                {
                    "level": int(self.chosen.level),
                    "description": self.chosen.description,
                    "capability": self.chosen.capability,
                    "estimated_utility": self.chosen.estimated_utility,
                    "required_confidence": self.chosen.required_confidence,
                }
                if self.chosen
                else None
            ),
            "reversible": self.reversible,
            "required_confidence": required,
        }


class RecoveryEngine:
    """Kernel-driven recovery built on top of ``RepairDiagnoser``."""

    # Irreversible actions demand more confidence before we act (Ch 34.9).
    IRREVERSIBLE_CONFIDENCE_FLOOR: float = 0.85
    REVERSIBLE_CONFIDENCE_FLOOR: float = 0.3

    def __init__(self, diagnoser: Optional[RepairDiagnoser] = None) -> None:
        self._diagnoser = diagnoser or RepairDiagnoser()
        self._kernel: Any = None

    # --------------------------------------------------------- classification

    def _classify(self, diagnosis: RepairDiagnosis) -> FailureClass:
        """Map ``RepairCause`` → ``FailureClass`` (wrap, don't rewrite).

        If the diagnosis is not repairable and the cause is UNKNOWN, the failure
        is IRRECOVERABLE (no viable alternative).
        """
        cause = diagnosis.cause
        mapping = {
            RepairCause.NO_SOURCES: FailureClass.PRECONDITION,
            RepairCause.NO_CONTENT: FailureClass.PRECONDITION,
            RepairCause.FILE_NOT_WRITTEN: FailureClass.CAPABILITY,
            RepairCause.NOT_NAVIGATED: FailureClass.ENVIRONMENTAL,
            RepairCause.DELIVERY_UNCONFIRMED: FailureClass.BLOCKED,
            RepairCause.BLOCKED: FailureClass.BLOCKED,
            RepairCause.UNKNOWN: FailureClass.UNKNOWN,
        }
        failure_class = mapping.get(cause, FailureClass.UNKNOWN)
        if not diagnosis.repairable and cause == RepairCause.UNKNOWN:
            return FailureClass.IRRECOVERABLE
        return failure_class

    def _required_confidence(self, reversible: bool) -> float:
        """Confidence required to attempt recovery (irreversible ≥ reversible)."""
        return (
            self.REVERSIBLE_CONFIDENCE_FLOOR
            if reversible
            else self.IRREVERSIBLE_CONFIDENCE_FLOOR
        )

    # ------------------------------------------------------------- pure core

    def recover(
        self,
        *,
        goal_id: str,
        requirement: str,
        evidence: Any,
        reversible: bool = True,
        blocked: bool = False,
        competence: float = 1.0,
    ) -> RecoveryPlan:
        """Pure core: diagnose, classify, generate alternatives, choose one.

        Preserves ``goal_id`` verbatim (Ch 34.1). Irreversible failures require
        ``competence >= IRREVERSIBLE_CONFIDENCE_FLOOR`` before an alternative is
        chosen; otherwise recovery escalates to a higher ``RecoveryLevel`` (e.g.
        HUMAN).
        """
        diagnosis = self._diagnoser.diagnose(requirement, evidence, blocked=blocked)
        failure_class = self._classify(diagnosis)
        required = self._required_confidence(reversible)

        rollback = RollbackKind.UNDO if reversible else RollbackKind.NONE

        alternatives = self._build_alternatives(
            diagnosis, failure_class, required
        )

        # Choose the recovery level / alternative.
        chosen: Optional[RecoveryAlternative] = None
        if failure_class is FailureClass.BLOCKED:
            level = RecoveryLevel.HUMAN
        elif failure_class is FailureClass.IRRECOVERABLE:
            level = RecoveryLevel.ARCHITECTURAL
        elif (not reversible) and competence < self.IRREVERSIBLE_CONFIDENCE_FLOOR:
            # Req 4.2 — irreversible action we are not competent to attempt.
            level = RecoveryLevel.HUMAN
        else:
            # Highest-utility alternative whose required confidence we can meet.
            for alt in alternatives:
                if alt.required_confidence <= competence:
                    chosen = alt
                    break
            level = chosen.level if chosen else RecoveryLevel.HUMAN

        return RecoveryPlan(
            goal_id=goal_id,
            failure_class=failure_class,
            level=level,
            rollback=rollback,
            alternatives=tuple(alternatives),
            chosen=chosen,
            reversible=reversible,
            note=diagnosis.note,
        )

    def _build_alternatives(
        self,
        diagnosis: RepairDiagnosis,
        failure_class: FailureClass,
        required: float,
    ) -> List[RecoveryAlternative]:
        """Generate recovery alternatives ordered by estimated utility desc.

        Each ``RepairAction`` becomes one ``RecoveryAlternative`` at a
        ``RecoveryLevel`` that escalates slightly for later actions. A BLOCKED
        failure escalates to HUMAN; a TRANSIENT failure stays at MICRO.
        """
        alternatives: List[RecoveryAlternative] = []
        for index, action in enumerate(diagnosis.actions):
            level = self._alternative_level(failure_class, index)
            utility = max(0.0, 1.0 - 0.1 * index)
            alternatives.append(
                RecoveryAlternative(
                    level=level,
                    description=action.description,
                    capability=getattr(
                        action.capability, "value", str(action.capability)
                    ),
                    estimated_utility=utility,
                    required_confidence=required,
                )
            )
        # Already ordered by construction (utility decreasing), but sort to be safe.
        alternatives.sort(key=lambda a: a.estimated_utility, reverse=True)
        return alternatives

    def _alternative_level(
        self, failure_class: FailureClass, index: int
    ) -> RecoveryLevel:
        """Pick a ``RecoveryLevel`` for the ``index``-th alternative."""
        if failure_class is FailureClass.BLOCKED:
            return RecoveryLevel.HUMAN
        if failure_class is FailureClass.TRANSIENT:
            return RecoveryLevel.MICRO
        # First action stays LOCAL; later actions escalate slightly.
        if index <= 0:
            return RecoveryLevel.LOCAL
        if index == 1:
            return RecoveryLevel.ENVIRONMENTAL
        return RecoveryLevel.STRATEGIC

    # --------------------------------------------------------------- wiring

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``verification.completed`` (Ch 52 — kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("verification.completed", self._on_verification)

    def _on_verification(self, event: Any) -> None:
        """React to a failure event, run ``recover()``, publish ``recovery.proposed``.

        Reads payload fields defensively and never raises into the kernel tick
        loop. Only failures (falsy ``satisfied``) are acted on; a missing
        ``goal_id`` skips recovery entirely.
        """
        try:
            payload = getattr(event, "payload", {}) or {}

            # Only react to FAILURES.
            if payload.get("satisfied"):
                return

            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            requirement = payload.get("requirement") or payload.get("description") or ""

            evidence = payload.get("evidence")
            if evidence is None:
                # Local import to keep the module import graph clean.
                from friday.verification.evidence_law import ExecutionEvidence

                evidence = ExecutionEvidence()

            reversible = bool(payload.get("reversible", True))
            blocked = bool(payload.get("blocked", False))
            competence = float(payload.get("competence", 1.0))

            plan = self.recover(
                goal_id=goal_id,
                requirement=requirement,
                evidence=evidence,
                reversible=reversible,
                blocked=blocked,
                competence=competence,
            )

            if self._kernel is not None:
                tick = 0
                try:
                    tick = int(self._kernel.health().get("tick", 0))
                except Exception:  # noqa: BLE001 — health must never break the loop
                    tick = 0
                proposed = make_event(
                    event_type="recovery.proposed",
                    source="recovery",
                    logical_time=tick + 1,
                    payload=plan.to_payload(),
                )
                self._kernel.publish_event(proposed)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return
