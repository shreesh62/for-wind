"""M25 — PreferenceResolver: the preference resolution pipeline coordinator.

A kernel-attached coordinator that resolves ``DecisionPoint``s by querying
existing Preference Memory via the Retrieval Router, evaluating contextual
confidence + reversibility + freshness, and either applying a preference
autonomously or escalating to the user. Emits ``decision.resolved`` and
``preference.*`` lifecycle events.

Isolation invariant (Axiom 15 / Requirement 9):
- This module MUST NOT import application-specific modules.
- It imports ONLY: ``friday.events.event``, ``friday.memory.interfaces``,
  ``friday.deliberation.decision_point``, math, logging, and stdlib.
- Collaborators (preference_memory, retrieval_router, cognitive_state,
  failure_memory) are accessed through the interfaces passed at ``attach`` time.
- Its ONLY persistence side effect is calling
  ``preference_memory.record_preference(...)`` (the existing API).
- Its ONLY bus side effects are emitting ``decision.resolved`` and ``preference.*``
  events via ``kernel.publish_event(make_event(...))``.

Error handling (A2.14.2):
- Every handler catches narrowly, degrades to a no-op, never raises into the bus.
- ``BaseException`` (KeyboardInterrupt/SystemExit) propagates.
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Dict, Optional

from friday.deliberation.decision_point import DecisionPoint
from friday.events.event import make_event
from friday.memory.interfaces import MemoryTier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C3 — compute_preference_confidence (pure function)
# ---------------------------------------------------------------------------

def compute_preference_confidence(
    *,
    source_type: str,
    reuse_count: int,
    correction_count: int,
    recency_days: float,
    contradiction_count: int,
) -> float:
    """Return empirical confidence in [0, 1]. Pure and deterministic.

    Never LLM-asserted. Monotonically decreasing in corrections and contradictions.
    """
    base = {"explicit": 0.9, "repeated": 0.6, "inferred": 0.5}.get(source_type, 0.5)
    reuse_boost = min(0.3, math.log2(max(1, reuse_count) + 1) * 0.05)
    correction_penalty = correction_count * 0.15
    contradiction_penalty = contradiction_count * 0.2
    recency_decay = recency_days / 180.0  # half-year half-life
    raw = base + reuse_boost - correction_penalty - contradiction_penalty - recency_decay
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# C4 — contains_secret_material (pure function)
# ---------------------------------------------------------------------------

_SECRET_PREFIXES = ("sk-", "ghp_", "gho_", "glpat-", "xoxb-", "xoxp-", "Bearer ")
_PEM_MARKERS = ("-----BEGIN",)
_VAULT_RE = re.compile(r"^vault://")


def _shannon_entropy(s: str) -> float:
    """Compute Shannon entropy (bits per character) for a string."""
    if not s:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def contains_secret_material(value: Any) -> bool:
    """Return True if ``value`` looks like secret material (conservative).

    Checks: known prefixes (sk-, ghp_, gho_, glpat-, xoxb-, xoxp-, Bearer),
    base64 blocks >= 20 chars with entropy > 4.0 bits/char, PEM markers.
    Vault references (``vault://...``) are explicitly ALLOWED (opaque refs).
    """
    if not isinstance(value, str):
        return False
    if _VAULT_RE.match(value):
        return False  # vault references are identity refs, not secrets
    for prefix in _SECRET_PREFIXES:
        if value.startswith(prefix):
            return True
    # PEM markers
    for marker in _PEM_MARKERS:
        if marker in value:
            return True
    # High-entropy base64 blocks >= 20 chars
    # Match continuous base64-safe characters
    b64_pattern = re.compile(r"[A-Za-z0-9+/=]{20,}")
    for match in b64_pattern.finditer(value):
        block = match.group()
        if _shannon_entropy(block) > 4.0:
            return True
    return False


# Keep backward compat alias used internally
_is_secret_material = contains_secret_material


# ---------------------------------------------------------------------------
# C2 — PreferenceResolver
# ---------------------------------------------------------------------------

class PreferenceResolver:
    """Coordinate the preference resolution pipeline over existing subsystems.

    Resolves ``DecisionPoint``s via contextual preference recall + confidence +
    reversibility gating; emits ``decision.resolved`` + ``preference.*`` lifecycle
    events. Never raises into the bus.
    """

    def __init__(
        self,
        *,
        autonomous_threshold: float = 0.75,
        ask_threshold: float = 0.4,
    ) -> None:
        self._autonomous_threshold = float(autonomous_threshold)
        self._ask_threshold = float(ask_threshold)
        self._kernel: Any = None
        self._preference_memory: Any = None
        self._retrieval_router: Any = None
        self._cognitive_state: Any = None
        self._failure_memory: Any = None
        self._resolving: bool = False  # re-entry guard

    # ------------------------------------------------------------------ attach

    def attach(
        self,
        kernel: Any,
        *,
        preference_memory: Any = None,
        retrieval_router: Any = None,
        cognitive_state: Any = None,
        failure_memory: Any = None,
    ) -> None:
        """Store collaborator references; subscribe to ``decision.required``.

        No-op if kernel is None. Defensive — never raises into bootstrap.
        """
        if kernel is None:
            return
        self._kernel = kernel
        self._preference_memory = preference_memory
        self._retrieval_router = retrieval_router
        self._cognitive_state = cognitive_state
        self._failure_memory = failure_memory
        try:
            kernel.subscribe("decision.required", self._on_decision_required)
        except Exception:  # noqa: BLE001 — subscribe failure must not crash
            pass

    # ------------------------------------------------------------------ event handler

    def _on_decision_required(self, event: Any) -> None:
        """Handle a decision.required event from the bus. Never raises (A2.14.2)."""
        if self._resolving:
            return  # prevent re-entry from our own emitted events
        try:
            payload = getattr(event, "payload", None)
            if not payload or not isinstance(payload, dict):
                return
            decision_id = payload.get("decision_id", "")
            options = tuple(payload.get("options", ()))
            if not decision_id or not options:
                return
            dp = DecisionPoint(
                decision_id=decision_id,
                goal_context=payload.get("goal_context", ""),
                environment=payload.get("environment", ""),
                options=options,
                risk=float(payload.get("risk", 0.0)),
                reversible=bool(payload.get("reversible", True)),
                category=payload.get("category", ""),
                candidates=tuple(payload.get("candidates", ())),
                metadata=payload.get("metadata"),
            )
            self.resolve_sync(dp)
        except Exception:  # noqa: BLE001 — handlers never raise into the bus
            return

    # ------------------------------------------------------------------ resolution pipeline

    def resolve_sync(self, decision_point: DecisionPoint) -> Dict[str, Any]:
        """Full resolution pipeline (synchronous entry point).

        Stages:
        1. Emit decision.required event.
        2. Query preference memory via retrieval router.
        3. Evaluate candidates: context match × confidence × freshness.
        4. Check failure memory.
        5. Gate: reversibility + confidence + risk → apply / infer / ask.
        6. Consult cognitive_state.should_interrupt if asking.
        7. Emit decision.resolved event.
        8. Return resolution dict.
        """
        dp = decision_point
        self._resolving = True
        try:
            return self._resolve_inner(dp)
        finally:
            self._resolving = False

    def _resolve_inner(self, dp: DecisionPoint) -> Dict[str, Any]:
        """Inner resolution logic (separated for re-entry guard)."""

        # 1. Emit decision.required event.
        self._emit("decision.required", {
            "decision_id": dp.decision_id,
            "goal_context": dp.goal_context,
            "environment": dp.environment,
            "options": list(dp.options),
            "risk": dp.risk,
            "reversible": dp.reversible,
            "category": dp.category,
        })

        # 2. Query: retrieve candidate preferences from memory via router.
        candidates = self._query_preferences(dp)

        # 3. Evaluate: score candidates by context similarity + confidence + freshness.
        best_candidate, best_confidence = self._evaluate_candidates(dp, candidates)

        # 4. Check failure memory for past failures (penalty).
        if self._failure_memory is not None and best_confidence > 0:
            try:
                if self._failure_memory.has_failed_before(dp.decision_id):
                    best_confidence = max(0.0, best_confidence * 0.5)
            except Exception:  # noqa: BLE001 — failure memory unavailable → skip
                pass

        # 5. Gate: decide whether to apply, infer, or ask.
        gate = self._gate_decision(dp, best_confidence)

        # 6. Build result based on gate.
        if gate == "apply" and best_candidate is not None:
            chosen = best_candidate.get("value", "")
            self._try_apply_preference(
                dp.decision_id, chosen,
                reuse_count=int(best_candidate.get("reuse_count", 0)),
                confidence=best_confidence,
            )
            result = self._make_result(
                dp, chosen, best_confidence, source="memory", autonomous=True,
                explanation=self._build_explanation(best_candidate, gate),
            )
        elif gate == "infer" and best_candidate is not None:
            chosen = best_candidate.get("value", "")
            result = self._make_result(
                dp, chosen, best_confidence * 0.8, source="inferred", autonomous=True,
                explanation=self._build_explanation(best_candidate, gate),
            )
        else:
            # "ask" path — check should_interrupt for deferral.
            deferred = False
            if gate == "ask" and self._cognitive_state is not None:
                try:
                    if not self._cognitive_state.should_interrupt(dp.risk):
                        deferred = True
                except Exception:  # noqa: BLE001 — degrade to always-ask
                    pass
            result = self._make_result(
                dp, "", 0.0, source="user_required", autonomous=False,
                needs_user_input=True,
                explanation="Insufficient confidence or high risk; user input required.",
            )
            if deferred:
                result["deferred"] = True

        # 7. Emit decision.resolved event.
        self._emit("decision.resolved", result)

        # 8. Return result.
        return result

    # ------------------------------------------------------------------ query

    def _query_preferences(self, dp: DecisionPoint) -> list:
        """Query the retrieval router (or preference memory directly) for candidates."""
        if self._retrieval_router is not None:
            try:
                items = self._retrieval_router.route(
                    dp.decision_id,
                    tiers={MemoryTier.PREFERENCE},
                    top_k=5,
                )
                return items or []
            except Exception:  # noqa: BLE001 — router failure → try direct
                pass
        # Fallback: query preference memory directly if available.
        if self._preference_memory is not None:
            try:
                items = self._preference_memory.retrieve(dp.decision_id, top_k=5)
                return items or []
            except Exception:  # noqa: BLE001 — memory failure → no candidates
                pass
        return []

    # ------------------------------------------------------------------ evaluate

    def _evaluate_candidates(
        self, dp: DecisionPoint, candidates: list
    ) -> tuple:
        """Score candidates by context similarity × confidence × freshness.

        Returns (best_candidate_metadata_dict | None, best_confidence).
        """
        if not candidates:
            return None, 0.0

        best: Optional[Dict[str, Any]] = None
        best_score = -1.0

        now = time.time()
        for item in candidates:
            meta = getattr(item, "metadata", {}) or {}
            confidence = float(meta.get("confidence", 0.5))
            # Freshness decay: reduce score for very old preferences.
            ts = float(meta.get("last_verified", 0.0) or getattr(item, "timestamp", 0.0) or 0.0)
            age_days = max(0.0, (now - ts) / 86400.0) if ts > 0 else 30.0
            freshness = 1.0 / (1.0 + age_days / 30.0)
            # Context match: heuristic based on scope overlap.
            context_match = self._context_match_score(dp, meta)
            score = confidence * freshness * context_match
            if score > best_score:
                best_score = score
                best = dict(meta)

        final_confidence = min(1.0, max(0.0, best_score)) if best else 0.0
        return best, final_confidence

    def _context_match_score(self, dp: DecisionPoint, meta: Dict[str, Any]) -> float:
        """Simple context similarity between DecisionPoint and a stored preference.

        Returns a value in [0.1, 1.0] — never zero (so a generalized preference
        still contributes).
        """
        scope = str(meta.get("context_scope", ""))
        if not scope:
            return 0.5  # generalized (no scope) → moderate match

        score = 0.1
        if dp.goal_context and dp.goal_context in scope:
            score += 0.3
        if dp.environment and dp.environment in scope:
            score += 0.3
        if dp.category and dp.category in scope:
            score += 0.3
        return min(1.0, score)

    # ------------------------------------------------------------------ gating (C5)

    def _gate_decision(self, dp: DecisionPoint, confidence: float) -> str:
        """Reversibility gating: determine whether to apply, infer, or ask.

        - Reversible + high confidence + low risk → "apply"
        - Irreversible / high risk / low confidence → "ask"
        - Middle ground → "infer"
        """
        if dp.reversible and confidence >= self._autonomous_threshold and dp.risk < 0.3:
            return "apply"
        if not dp.reversible or dp.risk >= 0.7 or confidence < self._ask_threshold:
            return "ask"
        return "infer"

    # ------------------------------------------------------------------ lifecycle

    def learn_preference(
        self,
        decision_id: str,
        chosen: Any,
        *,
        context_scope: str = "",
        preference_class: str = "contextual",
        provenance: str = "explicit",
    ) -> None:
        """Learn a new preference: store + emit ``preference.learned``.

        Rejects secret material (hard boundary — logs warning, does not store).
        """
        if contains_secret_material(chosen):
            logger.warning(
                "preference_resolver: rejecting learn_preference for %r — "
                "value contains secret material", decision_id
            )
            return
        if self._preference_memory is None:
            return
        try:
            self._preference_memory.record_preference(
                key=decision_id,
                value=chosen,
                description=context_scope,
            )
        except Exception:  # noqa: BLE001 — memory failure must not crash
            pass
        self._emit("preference.learned", {
            "key": decision_id,
            "value": chosen,
            "context_scope": context_scope,
            "preference_class": preference_class,
            "confidence": 0.9 if provenance == "explicit" else 0.5,
            "provenance": provenance,
        })

    def apply_preference(
        self,
        decision_id: str,
        chosen: Any,
        *,
        reuse_count: int = 0,
        confidence: float = 0.5,
    ) -> None:
        """Reapply a stored preference: increment reuse_count, emit ``preference.applied``."""
        self._try_apply_preference(decision_id, chosen, reuse_count=reuse_count, confidence=confidence)

    def _try_apply_preference(
        self,
        decision_id: str,
        chosen: Any,
        *,
        reuse_count: int = 0,
        confidence: float = 0.5,
    ) -> None:
        """Internal: re-store with incremented reuse_count; emit ``preference.applied``."""
        if self._preference_memory is None:
            return
        new_reuse = reuse_count + 1
        try:
            self._preference_memory.record_preference(
                key=decision_id,
                value=chosen,
                description=f"Reapplied (reuse_count={new_reuse})",
            )
        except Exception:  # noqa: BLE001 — memory failure must not crash
            pass
        self._emit("preference.applied", {
            "key": decision_id,
            "value": chosen,
            "decision_id": decision_id,
            "reuse_count": new_reuse,
            "confidence": confidence,
        })

    def correct_preference(
        self,
        decision_id: str,
        old_value: Any,
        new_value: Any,
        *,
        context_scope: str = "",
    ) -> None:
        """Correct a preference: refine scope, increment corrections, emit ``preference.corrected``."""
        if contains_secret_material(new_value):
            logger.warning(
                "preference_resolver: rejecting correct_preference for %r — "
                "new_value contains secret material", decision_id
            )
            return
        if self._preference_memory is None:
            return
        existing = None
        try:
            existing = self._preference_memory.get(decision_id)
        except Exception:  # noqa: BLE001
            pass
        corrections = (existing.corrections + 1) if existing else 1
        try:
            self._preference_memory.record_preference(
                key=decision_id,
                value=new_value,
                description=context_scope or (f"Corrected from {old_value!r} (corrections={corrections})"),
            )
        except Exception:  # noqa: BLE001
            pass
        self._emit("preference.corrected", {
            "key": decision_id,
            "old_value": old_value,
            "new_value": new_value,
            "context_scope": context_scope,
            "corrections": corrections,
        })

    def supersede_preference(
        self,
        old_key: str,
        new_key: str,
        new_value: Any,
    ) -> None:
        """Supersede an old preference with a new one; emit ``preference.superseded``."""
        if contains_secret_material(new_value):
            logger.warning(
                "preference_resolver: rejecting supersede_preference — "
                "new_value contains secret material"
            )
            return
        if self._preference_memory is None:
            return
        old_record = None
        try:
            old_record = self._preference_memory.get(old_key)
        except Exception:  # noqa: BLE001
            pass
        if old_record is not None:
            try:
                self._preference_memory.record_preference(
                    key=old_key,
                    value=old_record.value,
                    description=f"Superseded by {new_key}",
                )
            except Exception:  # noqa: BLE001
                pass
        try:
            self._preference_memory.record_preference(
                key=new_key,
                value=new_value,
                description=f"Supersedes {old_key}",
            )
        except Exception:  # noqa: BLE001
            pass
        old_value = old_record.value if old_record else ""
        self._emit("preference.superseded", {
            "key": old_key,
            "old_value": old_value,
            "new_key": new_key,
            "new_value": new_value,
        })

    # ------------------------------------------------------------------ explainability

    def explain(self, decision_id: str) -> Dict[str, Any]:
        """Return a provenance summary for the given decision_id."""
        if self._preference_memory is None:
            return {}
        try:
            record = self._preference_memory.get(decision_id)
        except Exception:  # noqa: BLE001
            return {}
        if record is None:
            return {}
        return {
            "source": record.provenance or "unknown",
            "when_learned": record.timestamp,
            "context": record.context_scope,
            "confidence": record.confidence,
            "reuse_count": record.reuse_count,
            "corrections": record.corrections,
            "last_verified": record.last_verified,
        }

    # ------------------------------------------------------------------ event emission

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Publish a JSON-safe event through the kernel; return True if published."""
        if self._kernel is None:
            return False
        try:
            event = make_event(
                event_type=event_type,
                source="preference_resolver",
                logical_time=self._next_tick(),
                payload=payload,
            )
            self._kernel.publish_event(event)
            return True
        except Exception:  # noqa: BLE001 — emission failure must not crash
            return False

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001
            return 1

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _make_result(
        dp: DecisionPoint,
        chosen: Any,
        confidence: float,
        *,
        source: str = "",
        autonomous: bool = False,
        needs_user_input: bool = False,
        explanation: str = "",
    ) -> Dict[str, Any]:
        """Build a JSON-safe resolution result dict."""
        return {
            "decision_id": dp.decision_id,
            "chosen_option": chosen,
            "confidence": round(float(confidence), 6),
            "source": source,
            "explanation": explanation,
            "autonomous": autonomous,
            "needs_user_input": needs_user_input,
        }

    @staticmethod
    def _build_explanation(candidate_meta: Optional[Dict[str, Any]], gate: str) -> str:
        """Build a human-readable explanation from candidate metadata."""
        if candidate_meta is None:
            return f"Gate decision: {gate}; no candidate matched."
        key = candidate_meta.get("key", "?")
        conf = candidate_meta.get("confidence", 0.0)
        reuse = candidate_meta.get("reuse_count", 0)
        prov = candidate_meta.get("provenance", "unknown")
        return (
            f"Applied preference '{key}' (confidence={conf}, reuse_count={reuse}, "
            f"provenance={prov}, gate={gate})."
        )


# ---------------------------------------------------------------------------
# C7 — Wiring helper (module-level)
# ---------------------------------------------------------------------------

def attach_preference_resolver(
    kernel: Any,
    *,
    resolver: Optional["PreferenceResolver"] = None,
    preference_memory: Any = None,
    retrieval_router: Any = None,
    cognitive_state: Any = None,
    failure_memory: Any = None,
    **kwargs: Any,
) -> PreferenceResolver:
    """Attach a PreferenceResolver to ``kernel`` (reusable wiring helper).

    Mirrors ``attach_skill_pipeline``: constructs or reuses a resolver, attaches it,
    and returns it. Inert without a kernel (returns the given/fresh resolver without
    attaching).
    """
    res = resolver if resolver is not None else _make_resolver(kwargs)
    if kernel is None:
        return res
    try:
        res.attach(
            kernel,
            preference_memory=preference_memory,
            retrieval_router=retrieval_router,
            cognitive_state=cognitive_state,
            failure_memory=failure_memory,
        )
    except Exception:  # noqa: BLE001 — wiring failure must never crash bootstrap
        pass
    return res


def _make_resolver(kwargs: Dict[str, Any]) -> PreferenceResolver:
    """Construct a resolver forwarding only the kwargs it accepts."""
    try:
        import inspect
        accepted = set(inspect.signature(PreferenceResolver.__init__).parameters) - {"self"}
        accepted_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        return PreferenceResolver(**accepted_kwargs)
    except Exception:  # noqa: BLE001 — defensive: fall back to defaults
        return PreferenceResolver()
