"""M24 — VerificationEventPublisher (audit objective 4: recovery activation).

THE ROOT-CAUSE FIX. ``RecoveryEngine``, ``CompetenceModel``, and ``ReflectionEngine``
all subscribe to the ``verification.completed`` kernel event, but nothing in
``friday/`` publishes it — so the entire failure→recovery/competence/reflection loop
is DORMANT in production. This publisher is the missing producer: it emits
``verification.completed`` in the exact payload shape the existing subscribers read,
activating the loop.

Design invariants:
- Reuses the kernel event system (``make_event`` + ``kernel.publish_event``); it does
  NOT create a new event channel or bus.
- Additive & safe: without an attached kernel, publishing is a silent no-op. It never
  raises into the caller (the verdict path must not break because telemetry failed).
"""

from __future__ import annotations

from typing import Any, Optional

from friday.events.event import make_event
from friday.verification.evidence_law import ExecutionEvidence


def _summarize_evidence(evidence: Optional[ExecutionEvidence]) -> dict:
    """A JSON-safe summary of an evidence bundle (counts of real artifacts by kind).

    The live ``ExecutionEvidence`` object is deliberately NOT placed in the event
    payload: the append-only ``EventStore`` JSON-serializes every event, so the
    payload must stay JSON-safe to remain replay-compatible. Subscribers that need
    a working evidence object build an empty one when it is absent (which faithfully
    represents an unmet requirement — its demanded evidence is missing).
    """
    if evidence is None:
        return {"artifact_count": 0, "kinds": {}}
    kinds: dict = {}
    try:
        for art in getattr(evidence, "artifacts", []) or []:
            if getattr(art, "is_real", False):
                key = getattr(getattr(art, "kind", None), "value", str(getattr(art, "kind", "")))
                kinds[key] = kinds.get(key, 0) + 1
    except Exception:  # noqa: BLE001 - summary is best-effort, never raises
        return {"artifact_count": 0, "kinds": {}}
    return {"artifact_count": sum(kinds.values()), "kinds": kinds}


class VerificationEventPublisher:
    """Publishes ``verification.completed`` events to activate the recovery loop."""

    EVENT_TYPE = "verification.completed"
    SOURCE = "verification"

    def __init__(self, kernel: Any = None) -> None:
        self._kernel = kernel

    def attach(self, kernel: Any) -> None:
        """Attach a kernel; subsequent ``publish_verdict`` calls emit events."""
        self._kernel = kernel

    @property
    def active(self) -> bool:
        """True when a kernel is attached (events will be emitted)."""
        return self._kernel is not None

    def publish_verdict(
        self,
        *,
        goal_id: str,
        requirement: str,
        satisfied: bool,
        evidence: Optional[ExecutionEvidence] = None,
        capability: str = "",
        environment: str = "",
        reversible: bool = True,
        blocked: bool = False,
        competence: float = 1.0,
    ) -> bool:
        """Emit one ``verification.completed`` event for a requirement verdict.

        Returns True if an event was published, False on no-op (no kernel) or on a
        swallowed error. Never raises into the caller.

        The payload carries exactly the fields the existing subscribers read
        (``RecoveryEngine._on_verification`` / ``CompetenceModel._on_verification`` /
        the reflection engine): goal_id, satisfied, requirement, evidence, capability,
        environment, reversible, blocked, competence.
        """
        kernel = self._kernel
        if kernel is None:
            return False
        try:
            tick = 0
            try:
                tick = int(kernel.health().get("tick", 0))
            except Exception:  # noqa: BLE001 - health must never break publishing
                tick = 0
            event = make_event(
                event_type=self.EVENT_TYPE,
                source=self.SOURCE,
                logical_time=tick + 1,
                payload={
                    "goal_id": goal_id,
                    "satisfied": bool(satisfied),
                    "requirement": requirement,
                    # JSON-safe summary only (see _summarize_evidence). The live
                    # evidence object is intentionally omitted to keep events
                    # replay-serializable; subscribers build an empty bundle when
                    # a real one is absent.
                    "evidence": None,
                    "evidence_summary": _summarize_evidence(evidence),
                    "capability": capability,
                    "environment": environment,
                    "reversible": bool(reversible),
                    "blocked": bool(blocked),
                    "competence": float(competence),
                },
            )
            kernel.publish_event(event)
            return True
        except Exception:  # noqa: BLE001 - telemetry must never break the verdict path
            return False
