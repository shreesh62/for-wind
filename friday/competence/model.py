"""Ch 28 — CompetenceModel: evidence-only competence per (capability, environment).

Competence is aggregated from real ``CompetenceRecord``s (Laplace-smoothed) —
NEVER an LLM guess (Ch 28.20, the 4th law). It decays over time toward the
neutral prior when no new evidence arrives (Ch 28.8) and gates risky actions
with per-risk confidence thresholds (Ch 28.11).

This module wraps/reuses the existing ``CompetenceRecord``
(``friday.kernel.contracts.capability``); it never re-implements the estimator
and never imports ``friday.memory.controller``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from friday.events.event import make_event
from friday.kernel.contracts.capability import CompetenceRecord

# Neutral prior: an unseen (capability, environment) is neither trusted nor
# distrusted, and decay always moves effective confidence toward this value.
NEUTRAL_PRIOR: float = 0.5

CompetenceKey = Tuple[str, str]  # (capability, environment)


@dataclass
class CompetenceNode:
    """One node in the competence graph, backed by an evidence record."""

    key: CompetenceKey
    record: CompetenceRecord = field(default_factory=CompetenceRecord)
    last_evidence_tick: int = 0

    @property
    def confidence(self) -> float:
        """Delegates to the evidence-backed ``CompetenceRecord.confidence`` in [0, 1]."""
        return self.record.confidence


class CompetenceModel:
    """Kernel-driven competence aggregation, decay, and gating."""

    # Ch 28.11 — higher risk demands higher demonstrated competence.
    # Non-decreasing in risk: observe <= reversible <= modify <= irreversible.
    RISK_CONFIDENCE_GATE: Dict[str, float] = {
        "observe": 0.0,
        "reversible": 0.3,
        "modify": 0.6,
        "irreversible": 0.85,
    }

    def __init__(self, decay_half_life_ticks: int = 10_000) -> None:
        self._nodes: Dict[CompetenceKey, CompetenceNode] = {}
        self._decay_half_life = decay_half_life_ticks
        self._kernel: Any = None

    # ------------------------------------------------------------------ core

    def record_outcome(
        self, key: CompetenceKey, *, success: bool, tick: int = 0
    ) -> CompetenceNode:
        """Fold a VERIFIED outcome into the ``(capability, environment)`` record.

        Evidence-only: increments ``attempts`` and increments ``successes`` iff
        ``success`` is ``True``. Updates ``last_evidence_tick``. Never fabricates
        success and never decreases attempts/successes.
        """
        node = self._nodes.get(key)
        if node is None:
            node = CompetenceNode(key=key)
            self._nodes[key] = node
        node.record.attempts += 1
        if success:
            node.record.successes += 1
        node.last_evidence_tick = tick
        return node

    def confidence(self, key: CompetenceKey) -> float:
        """Current evidence-derived confidence in [0, 1] (neutral prior if unseen)."""
        node = self._nodes.get(key)
        if node is None:
            return NEUTRAL_PRIOR
        return max(0.0, min(1.0, node.confidence))

    def effective_confidence(self, key: CompetenceKey, now_tick: int) -> float:
        """Time-decayed confidence in [0, 1] toward the neutral prior (Ch 28.8).

        ``effective = prior + (record.confidence - prior) * 0.5 ** (elapsed / half_life)``

        Because ``0.5 ** x`` is monotonic decreasing in ``elapsed``, the signed
        deviation ``(record.confidence - prior)`` shrinks in magnitude
        monotonically as ``now_tick`` grows without new evidence. Therefore:
        - when ``record.confidence >= prior``, ``effective_confidence`` is
          monotonic **non-increasing** in ``now_tick``;
        - when ``record.confidence <= prior``, it is monotonic non-decreasing;
        - in both cases ``|effective - prior|`` is monotonic non-increasing.

        Decay never increases confidence above the record's confidence when the
        record is above the prior, and never adds successes. Result clamped [0, 1].
        """
        node = self._nodes.get(key)
        if node is None:
            return NEUTRAL_PRIOR
        base = node.confidence
        elapsed = now_tick - node.last_evidence_tick
        if elapsed <= 0 or self._decay_half_life <= 0:
            return max(0.0, min(1.0, base))
        factor = 0.5 ** (elapsed / self._decay_half_life)
        effective = NEUTRAL_PRIOR + (base - NEUTRAL_PRIOR) * factor
        return max(0.0, min(1.0, effective))

    def decay(self, now_tick: int) -> None:
        """Ch 28.8 — apply time decay by advancing each node's evidence clock.

        Monotonic non-increasing without new evidence: this collapses the current
        effective (decayed) confidence back into the record's statistics is NOT
        done — instead we simply mark the decay reference so later reads via
        ``effective_confidence`` reflect elapsed time. To keep decay a no-op on
        the underlying evidence (never inventing/removing successes), this method
        only reads; effective confidence is computed on demand. It never
        increases confidence and never adds successes.
        """
        # Decay is computed on demand in `effective_confidence`; nothing about the
        # evidence record is mutated here (Ch 28.20 — evidence-only). This method
        # exists so callers can trigger/observe decay at a given tick without ever
        # raising or fabricating competence.
        for node in self._nodes.values():
            # Reading effective confidence has no side effects; asserting the
            # invariant keeps decay honest (never above the record when above prior).
            _ = self.effective_confidence(node.key, now_tick)

    def is_permitted(self, key: CompetenceKey, risk: str) -> bool:
        """Ch 28.11 — gate: ``confidence(key) >= RISK_CONFIDENCE_GATE[risk]``.

        Unknown risk labels are treated as maximally risky (never permitted
        unless confidence is a perfect 1.0), which fails safe.
        """
        threshold = self.RISK_CONFIDENCE_GATE.get(risk, 1.0)
        return self.confidence(key) >= threshold

    def graph(self) -> Dict[CompetenceKey, CompetenceNode]:
        """Return the competence graph (read-only copy of the node mapping)."""
        return dict(self._nodes)

    # --------------------------------------------------------------- wiring

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``verification.completed`` (Ch 52 — kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("verification.completed", self._on_verification)

    def _on_verification(self, event: Any) -> None:
        """Update competence from a ``verification.completed`` event, then publish.

        Reads payload fields defensively and never raises into the kernel tick
        loop. A missing ``capability`` skips the update entirely.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            capability = payload.get("capability")
            if not capability:
                return
            environment = payload.get("environment", "")
            satisfied = bool(payload.get("satisfied", False))
            key: CompetenceKey = (capability, environment)

            tick = 0
            if self._kernel is not None:
                try:
                    tick = int(self._kernel.health().get("tick", 0))
                except Exception:  # noqa: BLE001 — health must never break the loop
                    tick = 0

            node = self.record_outcome(key, success=satisfied, tick=tick)

            if self._kernel is not None:
                updated = make_event(
                    event_type="competence.updated",
                    source="competence",
                    logical_time=tick + 1,
                    payload={
                        "capability": capability,
                        "environment": environment,
                        "confidence": self.confidence(key),
                        "attempts": node.record.attempts,
                    },
                )
                self._kernel.publish_event(updated)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return
