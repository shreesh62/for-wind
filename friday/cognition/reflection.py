"""Ch 13 — ReflectionEngine: compare prediction to reality, propose learning.

Reflection proposes; Memory decides (Ch 13.16 / 14.8). This engine NEVER writes
long-term memory directly — it only emits ``memory.candidate`` kernel events. It
subscribes to action/verification/goal events, computes prediction error against
the M4 ``PredictedOutcome``, answers the FAS Ch 13.5 "5 Questions" at four scales
(Ch 13.13), calibrates confidence, and stays purely reactive (never raising into
the kernel tick loop).

Isolation (Property 1 / Req 1.1, 5.2): this module MUST NOT import
``friday.memory.*``, ``friday.competence.*``, or ``friday.recovery.*``, and MUST
NOT reference ``FridayMemory``/``MemoryStore``. The ONLY way it touches memory is
by emitting the ``memory.candidate`` kernel event.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from friday.deliberation.candidate import PredictedOutcome
from friday.events.event import make_event


class ReflectionScale(str, Enum):
    """Ch 13.13 — the four scales at which reflection happens."""

    MICRO = "micro"      # per action
    TASK = "task"        # per task (group of actions)
    GOAL = "goal"        # per goal
    SESSION = "session"  # per session


class ReflectionLayer(str, Enum):
    """FAS §A2.10.1 — the five normative reflection layers, ordered by scope.

    The layers run from the narrowest scope (a single action) to the widest (the
    architecture itself):

        IMMEDIATE → SESSION → LONG_TERM → SKILL → ARCHITECTURAL

    This is the M20 layer taxonomy layered additively on top of the existing
    :class:`ReflectionScale`; it does NOT change any ``ReflectionEngine`` output.

    Mapping to the existing engine's scales (Req 1.2):

    - The engine's per-action / micro reflection (``ReflectionScale.MICRO``) is the
      ``IMMEDIATE`` layer.
    - The engine's per-task / per-goal / per-session reflection
      (``ReflectionScale.TASK`` / ``GOAL`` / ``SESSION``) is the ``SESSION`` layer.
    - ``LONG_TERM``, ``SKILL`` and ``ARCHITECTURAL`` are the three new higher
      consumer layers (M20) that aggregate the ``reflection.completed`` stream.

    A ``str`` enum (like :class:`ReflectionScale`) so ``.value`` is JSON-safe for
    events/logging. Use :attr:`ordinal` to compare scope (Req 1.3).
    """

    IMMEDIATE = "immediate"          # per action (existing micro scale)
    SESSION = "session"              # per goal/session (existing task/goal/session)
    LONG_TERM = "long_term"          # across sessions (M20 consumer)
    SKILL = "skill"                  # per capability (M20 consumer, feeds §A2.5)
    ARCHITECTURAL = "architectural"  # meta / whole-architecture (M20 consumer)

    @property
    def ordinal(self) -> int:
        """0-based index in declaration order (immediate=0 → architectural=4).

        Lets callers compare a layer's scope: a lower ordinal is a narrower scope.
        """
        return list(type(self).__members__.values()).index(self)


@dataclass(frozen=True)
class FiveQuestions:
    """Ch 13.5 — the five reflection questions, as booleans/scores."""

    reality_changed_as_expected: bool      # Q1 did reality change as predicted?
    progress_increased: bool               # Q2 did progress toward the goal increase?
    assumptions_wrong: bool                # Q3 were any assumptions wrong?
    new_knowledge: Tuple[str, ...]         # Q4 what new knowledge was gained?
    should_change_behavior: bool           # Q5 should behavior change next time?


@dataclass(frozen=True)
class ReflectionRecord:
    """Ch 13 — an immutable record of one reflection (audit-grade)."""

    goal_id: str
    scale: ReflectionScale
    capability: str
    environment: str
    predicted_beliefs: Tuple[str, ...]
    observed_beliefs: Tuple[str, ...]
    predicted_confidence: float
    prediction_error: float                # 0..1 — 0 = perfect prediction
    questions: FiveQuestions
    verified: bool                         # was the triggering experience verified?
    calibration_delta: float = 0.0         # signed: predicted_conf - observed_accuracy
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        # Clamp the two bounded scores into [0, 1] (Req 1.2, data-model validation).
        object.__setattr__(
            self, "predicted_confidence", max(0.0, min(1.0, self.predicted_confidence))
        )
        object.__setattr__(
            self, "prediction_error", max(0.0, min(1.0, self.prediction_error))
        )

    def to_candidate_payload(self) -> Dict[str, Any]:
        """Project into a ``memory.candidate`` payload (verified-only downstream gate).

        ``verified`` is copied verbatim so Memory's hard gate (Ch 14.22) sees the
        exact triggering-experience flag. ``kind`` is ``pattern`` when behavior
        should change, otherwise ``turn``. ``competence_delta`` is a small signed
        nudge derived from whether the experience was verified and how large the
        prediction error was.
        """
        should_change = self.questions.should_change_behavior
        kind = "pattern" if should_change else "turn"

        # Small signed competence nudge: reward verified low-error experience,
        # penalize high-error experience. Bounded and evidence-shaped, not an
        # authoritative competence value (that lives in the CompetenceModel).
        if self.verified and self.prediction_error < 0.5:
            competence_delta = 0.05 * (1.0 - self.prediction_error)
        elif self.prediction_error > 0.5:
            competence_delta = -0.05 * self.prediction_error
        else:
            competence_delta = 0.0

        content = (
            f"[{self.scale.value}] capability={self.capability or '-'} "
            f"environment={self.environment or '-'} "
            f"prediction_error={self.prediction_error:.2f} "
            f"verified={self.verified}"
        )

        material = f"{self.capability}\x00{self.environment}"
        context_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()

        return {
            "verified": self.verified,
            "kind": kind,
            "content": content,
            "context_hash": context_hash,
            "competence_delta": float(competence_delta),
            "source_goal_id": self.goal_id,
            "capability": self.capability,
            "environment": self.environment,
        }


class ConfidenceCalibrator:
    """Ch 13 — tracks predicted-confidence vs observed-accuracy over time."""

    def __init__(self) -> None:
        # Each sample is (predicted_confidence in [0,1], accuracy 1.0/0.0).
        self._samples: List[Tuple[float, float]] = []

    def observe(self, predicted_confidence: float, was_accurate: bool) -> None:
        """Record one (predicted_confidence, accuracy) sample."""
        pc = max(0.0, min(1.0, float(predicted_confidence)))
        accuracy = 1.0 if was_accurate else 0.0
        self._samples.append((pc, accuracy))

    @property
    def calibration_error(self) -> float:
        """Mean |predicted_confidence - observed_accuracy|, in [0, 1].

        Returns ``0.0`` when there are no samples.
        """
        if not self._samples:
            return 0.0
        total = sum(abs(pc - accuracy) for pc, accuracy in self._samples)
        error = total / len(self._samples)
        return max(0.0, min(1.0, error))


def _prediction_error(expected: List[str], observed: List[str]) -> float:
    """Jaccard-distance prediction error in [0, 1].

    - Empty expected → 0.0 (nothing predicted, nothing to be wrong about).
    - Exact set match → 0.0.
    - Non-empty expected with ZERO overlap → 1.0.
    - Otherwise 1 - |intersection| / |union| (Jaccard distance), clamped [0, 1].
    """
    expected_set = set(expected)
    observed_set = set(observed)
    if not expected_set:
        return 0.0
    if expected_set == observed_set:
        return 0.0
    intersection = expected_set & observed_set
    if not intersection:
        return 1.0
    union = expected_set | observed_set
    error = 1.0 - (len(intersection) / len(union))
    return max(0.0, min(1.0, error))


class ReflectionEngine:
    """Kernel-driven reflection. Subscribes to events; emits memory candidates."""

    def __init__(self, calibrator: Optional[ConfidenceCalibrator] = None) -> None:
        self._calibrator = calibrator
        self._kernel: Any = None
        # Cache of the last PredictedOutcome seen per goal_id (from action.executed)
        # so a later verification.completed without an inline prediction can reflect.
        self._predictions: Dict[str, PredictedOutcome] = {}
        # Cache of the last (capability, environment) seen per goal_id.
        self._contexts: Dict[str, Tuple[str, str]] = {}

    def attach(self, kernel: Any) -> None:
        """Subscribe to action/verification/goal events (Ch 52 — kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("verification.completed", self._on_verification)
        kernel.subscribe("action.executed", self._on_action)
        kernel.subscribe("goal.state_changed", self._on_goal_state)

    # --- pure core ---------------------------------------------------------
    def reflect(
        self,
        *,
        goal_id: str,
        scale: ReflectionScale,
        prediction: PredictedOutcome,
        observed_beliefs: List[str],
        verified: bool,
        capability: str = "",
        environment: str = "",
    ) -> ReflectionRecord:
        """Pure core: build a ReflectionRecord from a prediction/observation pair.

        Deterministic and side-effect free with respect to its returned record
        (no I/O, no memory writes) so it is directly unit- and property-testable
        under DRY_RUN. The engine's own ``ConfidenceCalibrator`` (if present) is
        updated as engine-owned state, but ``calibration_delta`` is derived from
        the signed formula below — not from calibrator internals — so the record
        stays a pure function of the inputs.
        """
        expected = list(prediction.expected_beliefs)
        observed = list(observed_beliefs)

        error = _prediction_error(expected, observed)

        # Ch 13.5 — the 5 Questions.
        reality_changed_as_expected = error == 0.0
        progress_increased = verified and error < 0.5
        assumptions_wrong = error > 0.5
        new_knowledge = tuple(sorted(set(observed) - set(expected)))[:5]
        should_change_behavior = error > 0.5 or not verified

        questions = FiveQuestions(
            reality_changed_as_expected=reality_changed_as_expected,
            progress_increased=progress_increased,
            assumptions_wrong=assumptions_wrong,
            new_knowledge=new_knowledge,
            should_change_behavior=should_change_behavior,
        )

        predicted_confidence = prediction.confidence

        # Signed calibration delta: predicted confidence minus observed accuracy,
        # where accuracy is 1.0 for a perfect prediction (error 0) else 0.0.
        observed_accuracy = 1.0 if error == 0.0 else 0.0
        calibration_delta = predicted_confidence - observed_accuracy

        # Feed the engine-owned calibrator (mutation of engine state is fine; the
        # returned record is unaffected by calibrator internals).
        if self._calibrator is not None:
            self._calibrator.observe(predicted_confidence, error < 0.5)

        return ReflectionRecord(
            goal_id=goal_id,
            scale=scale,
            capability=capability,
            environment=environment,
            predicted_beliefs=tuple(expected),
            observed_beliefs=tuple(observed),
            predicted_confidence=predicted_confidence,
            prediction_error=error,
            questions=questions,
            verified=verified,
            calibration_delta=calibration_delta,
        )

    # --- event handlers: reflect() then publish memory.candidate -----------
    def _on_verification(self, event: Any) -> None:
        """React to a verification.completed event; reflect and emit a candidate.

        ``verification.completed`` is itself the verification-backed signal, so the
        emitted candidate is ``verified=True`` when the event reports ``satisfied``
        (Ch 13/14 — verified only when the triggering experience was
        verification-backed). Reads all fields defensively; if ``goal_id``,
        prediction, or observed beliefs are absent it skips (never raises).
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            observed_beliefs = payload.get("observed_beliefs")
            if observed_beliefs is None:
                return
            observed_beliefs = list(observed_beliefs)

            capability = payload.get("capability", "")
            environment = payload.get("environment", "")
            # Fall back to cached context from a prior action.executed.
            if not capability and goal_id in self._contexts:
                capability, cached_env = self._contexts[goal_id]
                environment = environment or cached_env
            elif not environment and goal_id in self._contexts:
                environment = self._contexts[goal_id][1]

            prediction = self._extract_prediction(payload, goal_id)
            if prediction is None:
                return

            satisfied = bool(payload.get("satisfied", False))
            # This IS the verification-backed path; the candidate is verified only
            # when the triggering experience was genuinely satisfied.
            verified = satisfied

            record = self.reflect(
                goal_id=goal_id,
                scale=ReflectionScale.TASK,
                prediction=prediction,
                observed_beliefs=observed_beliefs,
                verified=verified,
                capability=capability,
                environment=environment,
            )

            self._emit_candidate(record)
            self._emit_reflection_completed(record)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_action(self, event: Any) -> None:
        """Cache the PredictedOutcome from an action.executed payload by goal_id.

        A later verification.completed can then reflect even if it does not carry
        its own prediction. Caching is the key job here; never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            capability = payload.get("capability", "")
            environment = payload.get("environment", "")
            self._contexts[goal_id] = (capability, environment)

            prediction = self._extract_prediction(payload, goal_id)
            if prediction is not None:
                self._predictions[goal_id] = prediction
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_goal_state(self, event: Any) -> None:
        """Optional GOAL/SESSION-scale reflection hook.

        Minimal by design: skips when there is insufficient data (no cached
        prediction or no observed beliefs on the event). Never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            goal_id = payload.get("goal_id")
            if not goal_id:
                return

            observed_beliefs = payload.get("observed_beliefs")
            if observed_beliefs is None:
                return

            prediction = self._extract_prediction(payload, goal_id)
            if prediction is None:
                return

            capability, environment = self._contexts.get(goal_id, ("", ""))
            record = self.reflect(
                goal_id=goal_id,
                scale=ReflectionScale.GOAL,
                prediction=prediction,
                observed_beliefs=list(observed_beliefs),
                verified=bool(payload.get("satisfied", False)),
                capability=payload.get("capability", capability),
                environment=payload.get("environment", environment),
            )
            self._emit_candidate(record)
            self._emit_reflection_completed(record)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    # --- helpers -----------------------------------------------------------
    def _extract_prediction(
        self, payload: Dict[str, Any], goal_id: str
    ) -> Optional[PredictedOutcome]:
        """Build a PredictedOutcome from the payload, else from the cache.

        The payload's ``prediction`` may be a dict ``{expected_beliefs, confidence,
        reversible}`` or an actual ``PredictedOutcome``. Falls back to the cached
        prediction from a matching action.executed. Returns ``None`` if neither is
        available.
        """
        raw = payload.get("prediction")
        if isinstance(raw, PredictedOutcome):
            return raw
        if isinstance(raw, dict):
            expected = raw.get("expected_beliefs", ())
            confidence = raw.get("confidence", 0.0)
            reversible = raw.get("reversible", True)
            try:
                return PredictedOutcome(
                    expected_beliefs=tuple(expected),
                    confidence=float(confidence),
                    reversible=bool(reversible),
                )
            except Exception:  # noqa: BLE001 — malformed prediction → fall through
                pass
        return self._predictions.get(goal_id)

    def _emit_candidate(self, record: ReflectionRecord) -> None:
        """Publish a ``memory.candidate`` — the ONLY way Reflection touches memory."""
        if self._kernel is None:
            return
        tick = self._next_tick()
        event = make_event(
            event_type="memory.candidate",
            source="reflection",
            logical_time=tick,
            payload=record.to_candidate_payload(),
        )
        self._kernel.publish_event(event)

    def _emit_reflection_completed(self, record: ReflectionRecord) -> None:
        """Publish a ``reflection.completed`` audit event."""
        if self._kernel is None:
            return
        tick = self._next_tick()
        calibration = (
            self._calibrator.calibration_error if self._calibrator is not None else 0.0
        )
        event = make_event(
            event_type="reflection.completed",
            source="reflection",
            logical_time=tick,
            payload={
                "goal_id": record.goal_id,
                "scale": record.scale.value,
                "prediction_error": record.prediction_error,
                "calibration": calibration,
            },
        )
        self._kernel.publish_event(event)

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1
