"""M17 — Skill Evolution Pipeline tests.

Feature: m17-skill-evolution

Proves the FAS §A2.5.1 skill-evolution coordinator: an additive, kernel-attached
``SkillEvolutionPipeline`` that consumes the events the learning (M9
``learning.validated``) and reflection (M20 ``reflection.skill``) subsystems already
emit, tracks each skill's stage through the eight normative stages, and emits exactly
one deduplicated ``skill.candidate`` PROPOSAL when a skill carries BOTH a validated
generalization AND a skill-layer candidate signal. It never self-promotes, never
writes memory, and never fabricates competence (Ch 15.19 / the 4th law).

Property tests (Hypothesis, >=100 examples) cover Correctness Properties 1-5 from
design.md. Property tests run against a lightweight fake kernel (fresh, deterministic,
hermetic per example); one integration-style test drives a REAL ``CognitiveKernel``
(confined to pytest ``tmp_path``) to prove the dual-signal candidate emission over the
true event bus.
"""

from __future__ import annotations

import fnmatch
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.learning.skill_pipeline import (
    SkillEvolutionPipeline,
    SkillRecord,
    attach_skill_pipeline,
)
from friday.learning.skill_stage import SkillStage


# ----------------------------------------------------------------- test doubles


class FakeKernel:
    """Minimal kernel mirroring the EventBus surface the pipeline depends on.

    Exposes ``subscribe(pattern, handler)`` (fnmatch dispatch, like the real
    ``EventBus``), ``publish_event(event)`` (persist-free routing), and
    ``health() -> {"tick": int}``. Records every published event so tests can assert
    exactly which event types the pipeline emitted (filtered by ``source``). Fresh per
    example → deterministic, hermetic, no file I/O.
    """

    def __init__(self) -> None:
        self._subs: List[Tuple[str, Any]] = []
        self._tick = 0
        self.published: List[Any] = []

    def subscribe(self, pattern: str, handler: Any) -> str:
        self._subs.append((pattern, handler))
        return f"sub-{len(self._subs)}"

    def publish_event(self, event: Any) -> None:
        self._tick = max(self._tick, int(getattr(event, "logical_time", 0)))
        self.published.append(event)
        for pattern, handler in list(self._subs):
            if fnmatch.fnmatch(event.event_type, pattern):
                handler(event)

    def health(self) -> Dict[str, Any]:
        return {"tick": self._tick}

    # test helpers ---------------------------------------------------------
    def emitted_by_pipeline(self) -> List[Any]:
        """Events emitted by the pipeline itself (source=skill_pipeline)."""
        return [
            e for e in self.published if getattr(e, "source", "") == "skill_pipeline"
        ]

    def types_of(self, event_type: str) -> List[Any]:
        return [e for e in self.published if e.event_type == event_type]


# ----------------------------------------------------------- event builders


def _tick(kernel: Any) -> int:
    return int(kernel.health().get("tick", 0)) + 1


def _validated_event(
    kernel: Any,
    *,
    capability: str,
    environment: str = "",
    principle_id: str = "p-1",
    improvement: float = 0.5,
    baseline: float = 0.4,
    observed: float = 0.6,
) -> Any:
    """Build a synthetic M9 ``learning.validated`` event (source=test)."""
    payload: Dict[str, Any] = {
        "principle_id": principle_id,
        "improvement": improvement,
        "baseline": baseline,
        "observed": observed,
        "capability": capability,
        "environment": environment,
    }
    return make_event(
        event_type="learning.validated",
        source="test",
        logical_time=_tick(kernel),
        payload=payload,
    )


def _skill_event(
    kernel: Any,
    *,
    capability: str,
    sample_count: int = 5,
    mean_error: float = 0.1,
    verified_rate: float = 0.9,
    candidate: bool = True,
    environment: Optional[str] = None,
) -> Any:
    """Build a synthetic M20 ``reflection.skill`` event (source=test).

    Mirrors the real ``SkillReflector`` payload which carries NO ``environment`` field
    (the pipeline defaults it to ""). ``environment`` may be supplied explicitly for
    the generic-keying property test.
    """
    payload: Dict[str, Any] = {
        "capability": capability,
        "sample_count": sample_count,
        "mean_error": mean_error,
        "verified_rate": verified_rate,
        "candidate": candidate,
    }
    if environment is not None:
        payload["environment"] = environment
    return make_event(
        event_type="reflection.skill",
        source="test",
        logical_time=_tick(kernel),
        payload=payload,
    )


def _rejected_event(
    kernel: Any,
    *,
    capability: str,
    environment: str = "",
    principle_id: str = "p-1",
    reason: str = "insufficient-evidence",
) -> Any:
    """Build a synthetic ``learning.rejected`` event (source=test)."""
    payload: Dict[str, Any] = {
        "principle_id": principle_id,
        "reason": reason,
        "capability": capability,
        "environment": environment,
    }
    return make_event(
        event_type="learning.rejected",
        source="test",
        logical_time=_tick(kernel),
        payload=payload,
    )


_LABEL = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=122), min_size=1, max_size=16
)


# =============================================================== Property 1


def test_p1_taxonomy_structure_static():
    # Feature: m17-skill-evolution, Property 1: exactly eight members in the FAS
    # §A2.5.1 order, ordinals strictly increasing 0..7. Validates: Requirements 1.1, 1.2
    members = list(SkillStage)
    assert [m.name for m in members] == [
        "OBSERVATION",
        "EXPERIMENT",
        "REFLECTION",
        "VERIFICATION",
        "COMPILATION",
        "OPTIMIZATION",
        "GENERALIZATION",
        "REGISTRY",
    ]
    assert len(members) == 8
    ordinals = [m.ordinal for m in members]
    assert ordinals == [0, 1, 2, 3, 4, 5, 6, 7]
    # Strictly increasing ordinals.
    assert all(a < b for a, b in zip(ordinals, ordinals[1:]))


@settings(max_examples=100)
@given(idx=st.integers(min_value=0, max_value=7))
def test_p1_ordinal_matches_declaration_and_value_json(idx):
    # Feature: m17-skill-evolution, Property 1: for any member, its ordinal equals its
    # declaration index and its .value round-trips through json.dumps.
    # Validates: Requirements 1.1, 1.2
    members = list(SkillStage)
    assert len(members) == 8
    member = members[idx]
    assert member.ordinal == idx
    # .value is JSON-serializable and survives a round-trip.
    assert json.loads(json.dumps(member.value)) == member.value
    assert isinstance(member.value, str)


# =============================================================== Property 2


@settings(max_examples=100)
@given(cap=_LABEL, env=st.sampled_from(["", "web", "local", "sim"]))
def test_p2_validated_advances_to_generalization(cap, env):
    # Feature: m17-skill-evolution, Property 2: a learning.validated for a skill
    # advances it to at least the GENERALIZATION stage.
    # Validates: Requirements 2.1, 2.3
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_validated_event(kernel, capability=cap, environment=env))

    record = pipe.skill(cap, env)
    reached = SkillStage(record["stage"]).ordinal
    assert reached >= SkillStage.GENERALIZATION.ordinal
    assert record["generalized"] is True


@settings(max_examples=100)
@given(cap=_LABEL)
def test_p2_reflection_skill_sets_candidate_flag(cap):
    # Feature: m17-skill-evolution, Property 2: a reflection.skill sets the candidate
    # flag on the per-skill record (queried via skill(...)).
    # Validates: Requirements 2.1, 2.2
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_skill_event(kernel, capability=cap))

    record = pipe.skill(cap, "")
    assert record["candidate_flag"] is True
    # A reflection.skill alone must NOT fabricate a generalization (verified-only).
    assert record["generalized"] is False


@settings(max_examples=100)
@given(
    max_skills=st.integers(min_value=1, max_value=8),
    n_caps=st.integers(min_value=1, max_value=40),
)
def test_p2_store_never_exceeds_max_skills(max_skills, n_caps):
    # Feature: m17-skill-evolution, Property 2: the per-skill store is bounded (oldest
    # evicted) so memory never grows without limit. Validates: Requirements 2.2, 2.4
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline(max_skills=max_skills)
    pipe.attach(kernel)

    for i in range(n_caps):
        kernel.publish_event(_skill_event(kernel, capability=f"cap-{i}"))

    assert len(pipe.skills()) <= max_skills
    assert len(pipe.skills()) == min(n_caps, max_skills)


@settings(max_examples=150)
@given(
    payload=st.one_of(
        st.none(),
        st.just({}),
        st.fixed_dictionaries({"capability": st.just(""), "environment": st.just("")}),
        st.dictionaries(
            keys=st.sampled_from(
                ["principle_id", "improvement", "baseline", "observed", "reason",
                 "sample_count", "mean_error", "verified_rate", "candidate"]
            ),
            values=st.one_of(st.none(), st.text(max_size=5), st.integers(), st.booleans()),
            max_size=5,
        ),
    ),
    event_type=st.sampled_from(
        ["learning.validated", "reflection.skill", "learning.rejected"]
    ),
)
def test_p2_malformed_events_never_raise_and_create_no_junk(payload, event_type):
    # Feature: m17-skill-evolution, Property 2: malformed/empty events (no usable
    # capability/environment identity) never raise into the bus and never create junk
    # records. Validates: Requirements 2.4
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    event = make_event(
        event_type=event_type,
        source="test",
        logical_time=_tick(kernel),
        payload=payload if isinstance(payload, dict) else None,
    )
    # Must not raise despite malformed payload.
    kernel.publish_event(event)

    # No usable identity → no records created.
    assert pipe.skills() == {}


# =============================================================== Property 3


@settings(max_examples=120)
@given(cap=_LABEL)
def test_p3_dual_signal_validated_then_skill_emits_once(cap):
    # Feature: m17-skill-evolution, Property 3: learning.validated THEN reflection.skill
    # for the same (capability, "") emits exactly one skill.candidate; re-delivering
    # either signal does not re-emit. Validates: Requirements 3.1, 3.2, 3.3
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    # Only one signal so far → no candidate yet.
    assert kernel.types_of("skill.candidate") == []

    kernel.publish_event(_skill_event(kernel, capability=cap))
    emitted = kernel.types_of("skill.candidate")
    assert len(emitted) == 1

    payload = dict(emitted[0].payload)
    assert payload["capability"] == cap
    assert payload["environment"] == ""
    assert payload["generalized"] is True
    assert payload["candidate_flag"] is True
    assert "evidence" in payload
    json.dumps(payload)  # JSON-safe

    # Dedup: re-delivering either signal must NOT re-emit.
    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    kernel.publish_event(_skill_event(kernel, capability=cap))
    assert len(kernel.types_of("skill.candidate")) == 1


@settings(max_examples=120)
@given(cap=_LABEL)
def test_p3_dual_signal_skill_then_validated_emits_once(cap):
    # Feature: m17-skill-evolution, Property 3: reverse ordering — reflection.skill THEN
    # learning.validated also emits exactly one candidate (order-independent).
    # Validates: Requirements 3.1, 3.2, 3.3
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_skill_event(kernel, capability=cap))
    assert kernel.types_of("skill.candidate") == []

    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    emitted = kernel.types_of("skill.candidate")
    assert len(emitted) == 1

    payload = dict(emitted[0].payload)
    assert payload["capability"] == cap
    assert payload["environment"] == ""
    assert payload["evidence"]  # evidence recorded from the reflection.skill payload
    json.dumps(payload)

    # Dedup holds under the reverse ordering too.
    kernel.publish_event(_skill_event(kernel, capability=cap))
    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    assert len(kernel.types_of("skill.candidate")) == 1


@settings(max_examples=100)
@given(cap=_LABEL, which=st.sampled_from(["validated", "skill"]))
def test_p3_single_signal_never_emits(cap, which):
    # Feature: m17-skill-evolution, Property 3: neither signal alone emits a candidate.
    # Validates: Requirements 3.1
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    if which == "validated":
        for _ in range(3):
            kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    else:
        for _ in range(3):
            kernel.publish_event(_skill_event(kernel, capability=cap))

    assert kernel.types_of("skill.candidate") == []


# =============================================================== Property 4


def test_p4_module_does_not_import_memory_competence_evolution():
    # Feature: m17-skill-evolution, Property 4: the pipeline module never imports
    # memory/competence/evolution and never references FridayMemory/MemoryStore as code
    # (proposes-not-decides isolation; docstring mentions are excluded because they are
    # not import lines). Validates: Requirements 4.1, 4.2
    import friday.learning.skill_pipeline as mod

    with open(mod.__file__, "r", encoding="utf-8") as fh:
        source = fh.read()

    forbidden = re.compile(
        r"^\s*(?:import|from)\s+friday\.(?:memory|competence|evolution)\b",
        re.MULTILINE,
    )
    matches = forbidden.findall(source)
    assert matches == [], f"forbidden import found: {matches}"
    # Strip docstrings/comments before scanning for tell-tale class names as code.
    code_lines = [
        ln for ln in source.splitlines() if not ln.lstrip().startswith("#")
    ]
    # Remove triple-quoted docstring blocks so a documentation mention doesn't trip us.
    stripped = re.sub(r'""".*?"""', "", "\n".join(code_lines), flags=re.DOTALL)
    assert re.search(r"\bFridayMemory\b", stripped) is None
    assert re.search(r"\bMemoryStore\b", stripped) is None


@settings(max_examples=100)
@given(cap=_LABEL, extra=st.integers(min_value=0, max_value=6))
def test_p4_only_emitted_event_type_is_skill_candidate(cap, extra):
    # Feature: m17-skill-evolution, Property 4: driving a full both-signals stream, the
    # ONLY event type the pipeline emits (source=skill_pipeline) is skill.candidate.
    # Validates: Requirements 4.2, 5.2
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    kernel.publish_event(_skill_event(kernel, capability=cap))
    for _ in range(extra):
        kernel.publish_event(_skill_event(kernel, capability=cap))
        kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))

    emitted = kernel.emitted_by_pipeline()
    assert emitted, "pipeline should have emitted at least one candidate"
    assert all(e.event_type == "skill.candidate" for e in emitted)


@settings(max_examples=100)
@given(cap=_LABEL)
def test_p4_rejected_clears_generalized_blocks_candidate(cap):
    # Feature: m17-skill-evolution, Property 4: a learning.rejected after a
    # learning.validated (before any reflection.skill) clears the generalized flag, so a
    # later reflection.skill does NOT trigger a candidate (verified-only).
    # Validates: Requirements 4.3
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    kernel.publish_event(_validated_event(kernel, capability=cap, environment=""))
    kernel.publish_event(_rejected_event(kernel, capability=cap, environment=""))
    kernel.publish_event(_skill_event(kernel, capability=cap))

    assert kernel.types_of("skill.candidate") == []
    record = pipe.skill(cap, "")
    assert record["generalized"] is False
    assert record["candidate_flag"] is True
    assert record["emitted"] is False


def test_p4_attach_without_kernel_is_noop():
    # Feature: m17-skill-evolution, Property 4: attach_skill_pipeline(None) returns a
    # pipeline without attaching (its _kernel stays None). Validates: Requirements 5.2
    pipe = attach_skill_pipeline(None)
    assert isinstance(pipe, SkillEvolutionPipeline)
    assert pipe._kernel is None

    injected = SkillEvolutionPipeline(max_skills=3)
    pipe2 = attach_skill_pipeline(None, pipeline=injected)
    assert pipe2 is injected
    assert pipe2._kernel is None


# =============================================================== Property 5


@settings(max_examples=150)
@given(cap=_LABEL, env=_LABEL)
def test_p5_generic_keying_dual_signal_one_candidate(cap, env):
    # Feature: m17-skill-evolution, Property 5: skills are keyed only by generic
    # (capability, environment) strings; the dual-signal → one-candidate behavior is
    # identical regardless of the arbitrary label text (Axiom 15).
    # Validates: Requirements 4.4
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    # Both signals share the same arbitrary (capability, environment).
    kernel.publish_event(
        _validated_event(kernel, capability=cap, environment=env)
    )
    kernel.publish_event(
        _skill_event(kernel, capability=cap, environment=env)
    )

    emitted = kernel.types_of("skill.candidate")
    assert len(emitted) == 1
    payload = dict(emitted[0].payload)
    assert payload["capability"] == cap
    assert payload["environment"] == env
    json.dumps(payload)

    # Dedup holds for arbitrary labels too.
    kernel.publish_event(_skill_event(kernel, capability=cap, environment=env))
    assert len(kernel.types_of("skill.candidate")) == 1


@settings(max_examples=100)
@given(cap=_LABEL, env1=_LABEL, env2=_LABEL)
def test_p5_distinct_environments_are_distinct_skills(cap, env1, env2):
    # Feature: m17-skill-evolution, Property 5: the same capability under two DIFFERENT
    # environment labels are distinct skills — a full dual signal on one environment
    # does not emit a candidate for the other. Validates: Requirements 4.4
    if env1 == env2:
        return  # only meaningful for distinct environment labels
    kernel = FakeKernel()
    pipe = SkillEvolutionPipeline()
    pipe.attach(kernel)

    # Complete both signals for env1 only; env2 gets a single signal.
    kernel.publish_event(_validated_event(kernel, capability=cap, environment=env1))
    kernel.publish_event(_skill_event(kernel, capability=cap, environment=env1))
    kernel.publish_event(_skill_event(kernel, capability=cap, environment=env2))

    emitted = [dict(e.payload) for e in kernel.types_of("skill.candidate")]
    assert len(emitted) == 1
    assert emitted[0]["environment"] == env1
    # The env2 skill saw only one signal → not a candidate.
    assert pipe.skill(cap, env2)["emitted"] is False


# =============================================================== Integration


def test_integration_real_kernel_dual_signal_emits_one_candidate(tmp_path):
    # Feature: m17-skill-evolution, Property 3: end-to-end over a REAL CognitiveKernel
    # (confined to tmp_path) — both signals for the same skill emit exactly one JSON-safe
    # skill.candidate on the true event bus. Validates: Requirements 3.1, 3.2, 5.1
    kernel = CognitiveKernel(store_path=str(tmp_path / f"m17_{uuid.uuid4().hex}.jsonl"))
    pipe = attach_skill_pipeline(kernel)
    assert pipe._kernel is kernel

    candidates: List[Dict[str, Any]] = []
    kernel.subscribe("skill.candidate", lambda e: candidates.append(dict(e.payload)))

    kernel.publish_event(_validated_event(kernel, capability="research", environment=""))
    assert candidates == []  # single signal → nothing yet
    kernel.publish_event(_skill_event(kernel, capability="research"))

    assert len(candidates) == 1
    payload = candidates[0]
    assert payload["capability"] == "research"
    assert payload["environment"] == ""
    assert payload["generalized"] is True
    assert payload["candidate_flag"] is True
    json.dumps(payload)  # replay-safe / JSON-serializable

    # The pipeline query reflects the emitted, registry-advanced skill.
    record = pipe.skill("research", "")
    assert record["emitted"] is True
    assert SkillStage(record["stage"]).ordinal >= SkillStage.GENERALIZATION.ordinal
