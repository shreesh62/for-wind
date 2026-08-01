"""M17 — the SkillEvolutionPipeline: formalize FAS §A2.5.1 as a kernel coordinator.

This module is a thin, additive **coordinator** over mechanisms that already exist.
It does NOT re-implement pattern discovery, generalization, promotion, or the
capability lifecycle. It consumes the events those subsystems already emit — M9
``learning.validated`` (a skill has generalized) and M20 ``reflection.skill`` (a
capability accrued verified low-error experience) — tracks each skill's stage, and
when a skill carries BOTH signals it emits a single ``skill.candidate`` **proposal**
offering the skill to the existing M11 evidence-gated ``PromotionPipeline``.

Isolation invariant (Req 4.1/4.2, mirroring the M9/M20 rule): this module MUST NOT
import ``friday.memory.*``, ``friday.competence.*``, or ``friday.evolution.*``, MUST
NOT reference ``FridayMemory``/``MemoryStore``, and MUST NOT call any
lifecycle/promotion API. Its ONLY side effect is emitting ``skill.candidate`` events
via ``kernel.publish_event(make_event(...))``. Every handler is defensive and never
raises into the event bus (A2.14.2): it catches narrowly and degrades to a no-op;
``BaseException`` (e.g. cancellation) is allowed to propagate.

The consumed payloads are read defensively (fields may be absent → skip, never raise):

- ``learning.validated`` (from :class:`friday.learning.engine.LearningEngine`) carries
  ``{principle_id, improvement, baseline, observed}`` — it does NOT currently carry
  ``capability``/``environment``, so both are read via ``.get(...)`` and default to "".
- ``reflection.skill`` (from :class:`friday.cognition.reflection_layers.SkillReflector`)
  carries ``{capability, sample_count, mean_error, verified_rate, candidate}`` — it has
  ``capability`` but NOT ``environment`` (defaults to "").
- ``learning.rejected`` carries ``{principle_id, reason}``.

A skill is keyed only by generic ``(capability, environment)`` strings — no
application/site/window identity ever appears here (Axiom 15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from friday.events.event import make_event
from friday.learning.skill_stage import SkillStage

# Snapshot key separator for the ``skills()`` projection (a non-printable unit
# separator keeps the flattened "capability\x1fenvironment" key unambiguous).
_KEY_SEP = "\x1f"


@dataclass
class SkillRecord:
    """Per-skill state keyed by ``(capability, environment)`` (Design C2).

    Tracks the highest stage reached plus the signals seen: ``generalized`` (a
    ``learning.validated`` was observed), ``candidate_flag`` (a ``reflection.skill``
    was observed), ``emitted`` (the ``skill.candidate`` dedup latch), and a small
    JSON-safe ``evidence`` summary drawn from the ``reflection.skill`` payload.
    """

    stage: SkillStage = SkillStage.OBSERVATION
    generalized: bool = False
    candidate_flag: bool = False
    emitted: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe projection (stage rendered as its ``.value``)."""
        return {
            "stage": self.stage.value,
            "generalized": bool(self.generalized),
            "candidate_flag": bool(self.candidate_flag),
            "emitted": bool(self.emitted),
            "evidence": dict(self.evidence),
        }


class SkillEvolutionPipeline:
    """Coordinate skill maturation from existing events; propose promotion candidates.

    Attaches to a kernel, consumes ``learning.validated`` + ``reflection.skill`` (and
    observes ``learning.rejected``), maintains a bounded per-``(capability,
    environment)`` store, and emits exactly one deduplicated ``skill.candidate``
    proposal when a skill carries BOTH a validated generalization AND a skill-layer
    candidate signal. It never self-promotes, never writes memory, and never
    fabricates competence (Req 4.1/4.2).
    """

    def __init__(self, *, max_skills: int = 500) -> None:
        self._kernel: Any = None
        self._max_skills = max(1, int(max_skills))
        # Insertion-ordered store (plain dict is insertion-ordered) keyed by
        # (capability, environment); bounded — oldest evicted beyond the cap.
        self._skills: Dict[Tuple[str, str], SkillRecord] = {}

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #
    def attach(self, kernel: Any) -> None:
        """Subscribe to the maturation signals (no-op without a kernel)."""
        if kernel is None:
            return
        self._kernel = kernel
        kernel.subscribe("learning.validated", self._on_validated)
        kernel.subscribe("reflection.skill", self._on_skill)
        kernel.subscribe("learning.rejected", self._on_rejected)

    # ------------------------------------------------------------------ #
    # Store helpers
    # ------------------------------------------------------------------ #
    def _key(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        """Resolve a ``(capability, environment)`` key defensively from a payload.

        Both fields are read via ``.get(...)`` and coerced to strings; ``environment``
        defaults to "" (the ``reflection.skill`` payload has no environment).
        """
        capability = str(payload.get("capability", "") or "")
        environment = str(payload.get("environment", "") or "")
        return (capability, environment)

    def _get_or_create(self, key: Tuple[str, str]) -> SkillRecord:
        """Return the record for ``key``, creating (and bounding) it if new."""
        record = self._skills.get(key)
        if record is not None:
            return record
        # New key: enforce the cap by evicting the oldest inserted entry first.
        if len(self._skills) >= self._max_skills:
            oldest = next(iter(self._skills))
            self._skills.pop(oldest, None)
        record = SkillRecord()
        self._skills[key] = record
        return record

    # ------------------------------------------------------------------ #
    # Handlers — defensive; never raise into the bus (A2.14.2).
    # ------------------------------------------------------------------ #
    def _on_validated(self, event: Any) -> None:
        """A ``learning.validated`` → mark generalized; advance to ≥ GENERALIZATION."""
        try:
            payload = self._payload_of(event)
            key = self._key(payload)
            if not self._has_identity(key):
                return  # no usable identity → skip, never create junk.
            record = self._get_or_create(key)
            record.generalized = True
            self._advance(record, SkillStage.GENERALIZATION)
            self._maybe_emit(key, record)
        except Exception:  # noqa: BLE001 — handlers never raise into the bus (A2.14.2)
            return

    def _on_skill(self, event: Any) -> None:
        """A ``reflection.skill`` → set the candidate flag + record evidence summary.

        Does NOT set ``generalized`` — the skill signal alone must not fabricate a
        generalization (verified-only; Req 4.3).
        """
        try:
            payload = self._payload_of(event)
            key = self._key(payload)
            if not self._has_identity(key):
                return  # no usable identity → skip, never create junk.
            record = self._get_or_create(key)
            record.candidate_flag = True
            record.evidence = self._evidence_of(payload)
            self._maybe_emit(key, record)
        except Exception:  # noqa: BLE001 — handlers never raise into the bus (A2.14.2)
            return

    def _on_rejected(self, event: Any) -> None:
        """A ``learning.rejected`` disqualifies a skill: clear ``generalized`` (Req 4.3).

        Only touches an EXISTING record (a rejection never creates one) and never
        emits.
        """
        try:
            payload = self._payload_of(event)
            key = self._key(payload)
            record = self._skills.get(key)
            if record is not None:
                record.generalized = False
        except Exception:  # noqa: BLE001 — handlers never raise into the bus (A2.14.2)
            return

    # ------------------------------------------------------------------ #
    # Emission
    # ------------------------------------------------------------------ #
    def _maybe_emit(self, key: Tuple[str, str], record: SkillRecord) -> None:
        """Emit one ``skill.candidate`` when both signals are present (dedup latch)."""
        if not (record.generalized and record.candidate_flag and not record.emitted):
            return
        capability, environment = key
        payload = {
            "capability": capability,
            "environment": environment,
            "stage": record.stage.value,
            "generalized": True,
            "candidate_flag": True,
            "evidence": dict(record.evidence),
        }
        if self._emit("skill.candidate", payload):
            # Dedup latch (Req 3.1): only latch once the emission actually happened,
            # then advance the skill to the registry stage (offered for promotion).
            record.emitted = True
            self._advance(record, SkillStage.REGISTRY)

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Publish an event through the kernel; return True if it was published."""
        if self._kernel is None:
            return False
        event = make_event(
            event_type=event_type,
            source="skill_pipeline",
            logical_time=self._next_tick(),
            payload=payload,
        )
        self._kernel.publish_event(event)
        return True

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def skill(self, capability: str, environment: str = "") -> Dict[str, Any]:
        """Return the record for a skill as a JSON-safe dict (default if unseen)."""
        key = (str(capability or ""), str(environment or ""))
        record = self._skills.get(key)
        if record is None:
            return SkillRecord().to_dict()
        return record.to_dict()

    def skills(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot mapping ``"capability\\x1fenvironment"`` → record dict."""
        return {
            f"{cap}{_KEY_SEP}{env}": record.to_dict()
            for (cap, env), record in self._skills.items()
        }

    # ------------------------------------------------------------------ #
    # Small pure helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _payload_of(event: Any) -> Dict[str, Any]:
        """Return the event payload as a plain dict, defensively (never raises)."""
        payload = getattr(event, "payload", None)
        if isinstance(payload, dict):
            return payload
        try:
            return dict(payload) if payload else {}
        except Exception:  # noqa: BLE001 — malformed payload → treat as empty
            return {}

    @staticmethod
    def _has_identity(key: Tuple[str, str]) -> bool:
        """True when the skill key carries a usable identity (not both empty)."""
        return bool(key[0]) or bool(key[1])

    @staticmethod
    def _evidence_of(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a small JSON-safe evidence summary from a ``reflection.skill`` payload."""
        evidence: Dict[str, Any] = {}
        for source_key in ("mean_error", "verified_rate", "sample_count"):
            if source_key in payload:
                value = payload.get(source_key)
                try:
                    evidence[source_key] = (
                        int(value) if source_key == "sample_count" else float(value)
                    )
                except Exception:  # noqa: BLE001 — non-numeric evidence is skipped
                    continue
        return evidence

    @staticmethod
    def _advance(record: SkillRecord, target: SkillStage) -> None:
        """Advance ``record.stage`` toward ``target`` (only increase, never regress)."""
        if target.ordinal > record.stage.ordinal:
            record.stage = target


def attach_skill_pipeline(
    kernel: Any,
    *,
    pipeline: "SkillEvolutionPipeline | None" = None,
    **kwargs: Any,
) -> SkillEvolutionPipeline:
    """Attach a :class:`SkillEvolutionPipeline` to ``kernel`` (reusable wiring helper).

    Mirrors :func:`friday.cognition.reflection_layers.attach_reflection_layers`:
    constructs or reuses a pipeline, attaches it (isolating any attach exception so a
    wiring failure never crashes bootstrap), and returns it. Inert without a kernel
    (returns the given/fresh pipeline without attaching). ``**kwargs`` are forwarded
    only to a freshly-constructed pipeline (unknown kwargs are ignored).
    """
    pipe = pipeline if pipeline is not None else _make_pipeline(kwargs)
    if kernel is None:
        # Inert holder: return without attaching.
        return pipe
    try:
        pipe.attach(kernel)
    except Exception:  # noqa: BLE001 — a wiring failure must never crash bootstrap
        pass
    return pipe


def _make_pipeline(kwargs: Dict[str, Any]) -> SkillEvolutionPipeline:
    """Construct a pipeline forwarding only the kwargs it accepts (ignore the rest)."""
    try:
        import inspect

        accepted = set(inspect.signature(SkillEvolutionPipeline.__init__).parameters) - {"self"}
        accepted_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
        return SkillEvolutionPipeline(**accepted_kwargs)
    except Exception:  # noqa: BLE001 — defensive: fall back to defaults
        return SkillEvolutionPipeline()
