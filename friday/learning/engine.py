"""Ch 15 — the LearningEngine: orchestrate discover → generalize → validate over verified experience.

The :class:`LearningEngine` is the kernel-attached orchestrator of the M9 learning pipeline. It folds
one :class:`VerifiedExperience` at a time through :class:`PatternDiscovery` (patterns emerge from
*repeated* verified experience, never a single success — Ch 15.5), :class:`Generalizer` (lift a
specific pattern into a transferable :class:`Principle` — Ch 15.6/15.9), and
:class:`LearningValidator` (promote only after measurable, verified improvement — Ch 15.4/15.19),
returning a :class:`LearningStep` audit record of what the pipeline did.

This module implements the *pure core* of that orchestration: :meth:`LearningEngine.ingest` is
deterministic and side-effect free with respect to its return value, so it is directly unit- and
property-testable. Kernel wiring (``attach`` + event handlers + emissions), improvement tracking, and
unlearning are layered on in later tasks; the class is structured so they slot in without disturbing
the pure pipeline.

Isolation (Property 1 / Req 5.2): this module holds only pure orchestration logic over the plain data
models in :mod:`friday.learning.models` and its sibling collaborators. It MUST NOT import
``friday.memory.controller``, ``friday.memory.runtime``, or any ``friday.competence`` module, and MUST
NOT reference ``FridayMemory``/``MemoryStore`` — like M8 Reflection, it proposes procedural writes only
by emitting ``memory.candidate`` events, never by touching memory directly. No literal application
name, site name, or URL appears here (Axiom 15).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set

from friday.events.event import make_event
from friday.learning.generalization import Generalizer
from friday.learning.models import (
    CompetenceKey,
    LearningStep,
    Principle,
    ValidationStatus,
    VerifiedExperience,
)
from friday.learning.patterns import PatternDiscovery
from friday.learning.validation import LearningValidator

# Neutral competence prior: an unseen (capability, environment) is neither trusted nor distrusted.
# Mirrors the M8 CompetenceModel ``NEUTRAL_PRIOR`` precedent WITHOUT importing it (import boundary,
# Req 5.2) — the pure ingest derives a deterministic baseline/observed pair from the experience's
# own signed ``competence_delta`` so ``observed - baseline`` equals that measured delta.
_NEUTRAL_PRIOR: float = 0.5


class LearningEngine:
    """Ch 15 — orchestrate pattern discovery, generalization, and validated promotion."""

    def __init__(
        self,
        discovery: Optional[PatternDiscovery] = None,
        generalizer: Optional[Generalizer] = None,
        validator: Optional[LearningValidator] = None,
        *,
        min_repetitions: int = 3,
    ) -> None:
        self._discovery = discovery or PatternDiscovery(min_repetitions=min_repetitions)
        self._generalizer = generalizer or Generalizer()
        self._validator = validator or LearningValidator()
        # Kernel handle, set on attach(); emissions are no-ops until then (mirrors M8 Reflection).
        self._kernel: Any = None
        # Per-goal cached (capability, environment) context from competence.updated /
        # memory.integrated so a reflection.completed lacking inline context can still build a
        # VerifiedExperience. Purely engine-owned state; never touches memory (Property 1).
        self._contexts: Dict[str, CompetenceKey] = {}
        # Principles generalized so far, keyed by id. Populated as validated learnings accrue;
        # later tasks (improvement tracking / unlearning / kernel emissions) build on this state.
        self._principles: Dict[str, Principle] = {}
        # Retired principle ids (Ch 15 unlearning): a retired principle stays discoverable for audit
        # but is NEVER proposed for procedural promotion again.
        self._retired: Set[str] = set()
        # Per-key ordered confidence history, populated ONLY from competence.updated evidence
        # (via ``_record_competence``). ``improvement`` reads latest - first from this — it is never
        # fabricated. Ordered by observation (insertion) order.
        self._competence_history: Dict[CompetenceKey, List[float]] = {}

    def ingest(self, experience: VerifiedExperience) -> LearningStep:
        """Fold one verified experience through discover → generalize → validate; return the step.

        Learns ONLY from verified experience (Ch 15.19): an experience whose ``verified`` is not
        ``True`` is dropped and yields an empty :class:`LearningStep` (nothing discovered, generalized,
        or validated). A verified experience is observed by :class:`PatternDiscovery`; until the same
        ``(capability, environment, outcome_signature)`` has recurred at least ``min_repetitions``
        times no pattern emerges and the step stays empty. Once a :class:`DiscoveredPattern` is
        returned it is generalized into a :class:`Principle` and validated against the experience's own
        signed competence signal.

        Deterministic and side-effect free with respect to its return value.
        """

        # Hard gate (Ch 15.19): learn only from verified experience.
        if experience.verified is not True:
            return LearningStep(discovered=None, generalized=None, validation=None)

        # Discover: a pattern only emerges from repeated verified evidence (Ch 15.5).
        pattern = self._discovery.observe(experience)
        if pattern is None:
            return LearningStep(discovered=None, generalized=None, validation=None)

        # Generalize: lift the specific pattern into a transferable principle (Ch 15.6/15.9).
        principle = self._generalizer.generalize(pattern)
        self._principles[principle.id] = principle

        # Validate: promote only after measurable, verified improvement (Ch 15.4). The baseline is
        # the neutral prior; the observed value carries the experience's signed competence delta, so
        # the validator's improvement (observed - baseline) equals that measured delta.
        baseline = _NEUTRAL_PRIOR
        observed = _NEUTRAL_PRIOR + experience.competence_delta
        validation = self._validator.validate(
            principle,
            baseline=baseline,
            observed=observed,
            verified=experience.verified,
        )

        return LearningStep(discovered=pattern, generalized=principle, validation=validation)

    # ------------------------------------------------------------------ #
    # Improvement tracking (Req 1.11) — real, never fabricated.
    # ------------------------------------------------------------------ #
    def _record_competence(self, key: CompetenceKey, confidence: float) -> None:
        """Append one observed confidence for ``key`` in observation order (competence.updated only).

        This is the ONLY writer of competence history. The kernel ``competence.updated`` handler
        (task 2.3) calls it with the payload's ``(capability, environment)`` key and ``confidence``;
        ``improvement`` then reads latest - first from what was actually observed here — nothing is
        derived, inferred, or fabricated.
        """

        self._competence_history.setdefault(key, []).append(confidence)

    def improvement(self, key: CompetenceKey) -> float:
        """Signed measured competence delta for ``key`` since its first observation (Ch 15 / Req 1.11).

        Returns ``0.0`` for an unseen key (never fabricated) and otherwise the signed difference
        between the latest and first observed confidence for that ``(capability, environment)`` key,
        derived only from ``competence.updated`` evidence recorded via :meth:`_record_competence`.
        """

        history = self._competence_history.get(key)
        if not history:
            return 0.0
        return history[-1] - history[0]

    # ------------------------------------------------------------------ #
    # Unlearning (Req 1.10) — retire a decayed validated principle.
    # ------------------------------------------------------------------ #
    def unlearn(self, principle_id: str, reason: str) -> Principle:
        """Retire a validated principle whose confidence dropped below the retire floor (Ch 15 unlearning).

        Confirms the principle's current confidence is at/below the validator's retire floor via
        :meth:`LearningValidator.should_unlearn`, then marks it retired so it is no longer proposed
        for procedural promotion, and returns the retired :class:`Principle`.

        Raises ``KeyError`` if ``principle_id`` is unknown, and ``ValueError`` if the principle's
        confidence has not decayed to/below the retire floor (retiring a still-confident principle
        would be unfounded).
        """

        principle = self._principles[principle_id]  # KeyError on unknown id (existing style).

        if not self._validator.should_unlearn(principle, principle.confidence):
            raise ValueError(
                f"principle {principle_id!r} confidence {principle.confidence:.4f} is above the "
                f"retire floor; refusing to unlearn ({reason})"
            )

        # Mark retired: no longer proposed for procedural promotion (Property 9 / Req 1.10).
        self._retired.add(principle_id)
        # Emit exactly one learning.unlearned when a kernel is attached (Req 1.12 / Property 9).
        self._emit(
            "learning.unlearned",
            {
                "principle_id": principle_id,
                "reason": reason,
                "confidence": float(principle.confidence),
            },
        )
        return principle

    # ------------------------------------------------------------------ #
    # Kernel wiring (Req 1.7/1.8/1.9/1.12/1.13, 5.1/5.2) — subscribe to the M8
    # stream, fold verified experience through ingest(), emit learning events.
    #
    # Every handler reads payload fields defensively via ``.get(...)`` and wraps
    # its body in try/except so a malformed or partial event is skipped WITHOUT
    # raising into the kernel tick loop (Req 1.13). Emissions flow only through
    # ``make_event`` + ``kernel.publish_event`` — the engine never touches memory
    # directly (Property 1); procedural writes are proposed via memory.candidate.
    # ------------------------------------------------------------------ #
    def attach(self, kernel: Any) -> None:
        """Subscribe to reflection.completed / memory.integrated / competence.updated (Ch 52)."""
        self._kernel = kernel
        kernel.subscribe("reflection.completed", self._on_reflection_completed)
        kernel.subscribe("memory.integrated", self._on_memory_integrated)
        kernel.subscribe("competence.updated", self._on_competence_updated)

    def _on_reflection_completed(self, event: Any) -> None:
        """Fold a reflection.completed event into ingest(); emit learning outcomes.

        Builds a :class:`VerifiedExperience` defensively from the payload plus any
        cached ``(capability, environment)`` context. Skips (never raises) when a
        required field is absent (Req 1.13). Only a ``verified is True`` experience
        can produce ``learning.validated`` + a procedural ``memory.candidate``
        (Property 1); ingest itself enforces the same hard gate.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            prediction_error = payload.get("prediction_error")
            if prediction_error is None:
                return

            capability, environment = self._resolve_context(payload, goal_id)
            outcome_signature = payload.get("outcome_signature")
            if not outcome_signature:
                # Derive a stable repetition key from the context + scale when the
                # event carries no explicit signature (defensive; never raises).
                scale = payload.get("scale", "")
                material = f"{capability}\x00{environment}\x00{scale}"
                outcome_signature = hashlib.sha256(material.encode("utf-8")).hexdigest()

            verified = bool(payload.get("verified", False))
            competence_delta = float(payload.get("competence_delta", 0.0))

            experience = VerifiedExperience(
                goal_id=str(goal_id),
                capability=capability,
                environment=environment,
                outcome_signature=str(outcome_signature),
                prediction_error=float(prediction_error),
                verified=verified,
                competence_delta=competence_delta,
                logical_time=int(payload.get("logical_time", self._next_tick())),
                wall_time=float(payload.get("wall_time", 0.0)),
            )

            self._ingest_and_emit(experience)
        except Exception:  # noqa: BLE001 — never raise into the tick loop (Req 1.13)
            return

    def _on_memory_integrated(self, event: Any) -> None:
        """Cache any (capability, environment) context carried by memory.integrated.

        ``memory.integrated`` reports Memory's decision on a candidate; it may
        carry the capability/environment the candidate related to. Caching that
        context lets a later reflection.completed build a full experience. Reads
        defensively; never raises (Req 1.13).
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id") or payload.get("source_goal_id")
            capability = payload.get("capability")
            environment = payload.get("environment")
            if goal_id and (capability is not None or environment is not None):
                cached = self._contexts.get(str(goal_id), ("", ""))
                self._contexts[str(goal_id)] = (
                    str(capability) if capability is not None else cached[0],
                    str(environment) if environment is not None else cached[1],
                )
        except Exception:  # noqa: BLE001 — never raise into the tick loop (Req 1.13)
            return

    def _on_competence_updated(self, event: Any) -> None:
        """Record observed competence per (capability, environment) from competence.updated.

        This is the sole feed for :meth:`improvement` (real, never fabricated). Also
        caches the context so reflection.completed can resolve capability/environment.
        Reads defensively; never raises (Req 1.13).
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            capability = payload.get("capability")
            environment = payload.get("environment")
            confidence = payload.get("confidence")
            if capability is None or environment is None or confidence is None:
                return
            key: CompetenceKey = (str(capability), str(environment))
            self._record_competence(key, float(confidence))
            goal_id = payload.get("goal_id") or payload.get("source_goal_id")
            if goal_id:
                self._contexts[str(goal_id)] = key
        except Exception:  # noqa: BLE001 — never raise into the tick loop (Req 1.13)
            return

    # --- emission helpers --------------------------------------------------
    def _ingest_and_emit(self, experience: VerifiedExperience) -> None:
        """Run the pure pipeline and translate its LearningStep into kernel events."""
        step = self.ingest(experience)

        # A pattern crossing the repetition threshold (Req 1.7 / Property 2).
        if step.discovered is not None:
            self._emit(
                "learning.pattern_discovered",
                {
                    "signature": step.discovered.signature,
                    "support": step.discovered.support,
                    "capability": step.discovered.capability,
                    "environment": step.discovered.environment,
                },
            )

        validation = step.validation
        if validation is None:
            return

        baseline = _NEUTRAL_PRIOR
        observed = _NEUTRAL_PRIOR + experience.competence_delta

        if validation.status is ValidationStatus.VALIDATED:
            # Validated learning (Req 1.8 / Property 3): announce it AND propose a
            # verified procedural memory.candidate — the ONLY way the engine touches
            # memory (Property 1). NEVER emitted for an unverified experience.
            self._emit(
                "learning.validated",
                {
                    "principle_id": validation.principle_id,
                    "improvement": validation.improvement,
                    "baseline": baseline,
                    "observed": observed,
                },
            )
            material = f"{experience.capability}\x00{experience.environment}"
            context_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            principle = self._principles.get(validation.principle_id)
            content = principle.statement if principle is not None else validation.principle_id
            self._emit(
                "memory.candidate",
                {
                    "verified": True,
                    "kind": "pattern",
                    "content": content,
                    "context_hash": context_hash,
                    "competence_delta": float(experience.competence_delta),
                    "capability": experience.capability,
                    "environment": experience.environment,
                },
            )
        elif validation.status is ValidationStatus.REJECTED:
            # Rejected learning (Req 1.9 / Property 3): announce ONLY — no procedural
            # memory.candidate is ever emitted for a rejected learning.
            self._emit(
                "learning.rejected",
                {
                    "principle_id": validation.principle_id,
                    "reason": validation.reason,
                },
            )

    def _resolve_context(self, payload: Dict[str, Any], goal_id: Any) -> CompetenceKey:
        """Best (capability, environment) from the payload, else cached context, else empty."""
        capability = payload.get("capability")
        environment = payload.get("environment")
        cached = self._contexts.get(str(goal_id), ("", ""))
        return (
            str(capability) if capability is not None else cached[0],
            str(environment) if environment is not None else cached[1],
        )

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a learning event through the kernel (no-op until attached)."""
        if self._kernel is None:
            return
        event = make_event(
            event_type=event_type,
            source="learning",
            logical_time=self._next_tick(),
            payload=payload,
        )
        self._kernel.publish_event(event)

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1
