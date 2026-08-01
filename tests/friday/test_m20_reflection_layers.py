"""M20 — Reflection v2 (Layered Reflection) tests.

Feature: m20-reflection-v2

Proves the five-layer taxonomy plus the three higher **consumer** layers
(Long-Term, Skill, Architectural) that subscribe to the existing engine's
``reflection.completed`` stream, build bounded aggregates, and emit JSON-safe
``reflection.*`` PROPOSAL events — never memory writes, never raising into the bus
(Reflection proposes; Memory decides, Ch 13.16 / 14.8).

Property tests (Hypothesis, >=100 examples) cover Correctness Properties 1-6 from
design.md. Property tests run against a lightweight fake kernel (fresh, deterministic,
hermetic per example); the integration-style Property 6 test drives a REAL
``CognitiveKernel`` (confined to pytest ``tmp_path``) to prove the existing
``ReflectionEngine`` outputs are byte-identical with the higher layers attached.
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

from friday.cognition.reflection import (
    ReflectionEngine,
    ReflectionLayer,
    ReflectionScale,
)
from friday.cognition.reflection_layers import (
    ArchitecturalReflector,
    LongTermReflector,
    ReflectionLayers,
    SkillReflector,
    attach_reflection_layers,
)
from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel


# ----------------------------------------------------------------- test doubles


class FakeKernel:
    """Minimal kernel mirroring the EventBus surface the layers depend on.

    Exposes ``subscribe(pattern, handler)`` (fnmatch dispatch, like the real
    ``EventBus``), ``publish_event(event)`` (persist-free routing), and
    ``health() -> {"tick": int}``. Records every published event so tests can
    assert exactly which event types a layer emitted (filtered by ``source``).
    Fresh per example → deterministic, hermetic, no file I/O.
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
    def emitted_by_reflection(self) -> List[Any]:
        """Events emitted by the reflection layers themselves (source=reflection)."""
        return [e for e in self.published if getattr(e, "source", "") == "reflection"]

    def types_of(self, event_type: str) -> List[Any]:
        return [e for e in self.published if e.event_type == event_type]


def _reflection_event(
    kernel: Any,
    *,
    goal_id: str = "g",
    scale: str = "task",
    prediction_error: float = 0.0,
    calibration: float = 0.0,
    capability: str = "",
    environment: str = "",
    verified: Optional[bool] = None,
) -> Any:
    """Build a synthetic ``reflection.completed`` event (source=test)."""
    payload: Dict[str, Any] = {
        "goal_id": goal_id,
        "scale": scale,
        "prediction_error": prediction_error,
        "calibration": calibration,
        "capability": capability,
        "environment": environment,
    }
    if verified is not None:
        payload["verified"] = verified
    tick = int(kernel.health().get("tick", 0)) + 1
    return make_event(
        event_type="reflection.completed",
        source="test",
        logical_time=tick,
        payload=payload,
    )


def _publish_reflection(kernel: Any, **kwargs: Any) -> None:
    kernel.publish_event(_reflection_event(kernel, **kwargs))


# =============================================================== Property 1


def test_p1_taxonomy_structure_static():
    # Feature: m20-reflection-v2, Property 1: exactly five members in the normative
    # immediate->architectural order, ordinals strictly increasing 0..4, every value
    # JSON-serializes. Validates: Requirements 1.1, 1.3
    members = list(ReflectionLayer)
    assert [m.name for m in members] == [
        "IMMEDIATE",
        "SESSION",
        "LONG_TERM",
        "SKILL",
        "ARCHITECTURAL",
    ]
    assert [m.ordinal for m in members] == [0, 1, 2, 3, 4]
    # Strictly increasing ordinals.
    ordinals = [m.ordinal for m in members]
    assert all(a < b for a, b in zip(ordinals, ordinals[1:]))


@settings(max_examples=100)
@given(idx=st.integers(min_value=0, max_value=4))
def test_p1_ordinal_matches_declaration_and_value_json(idx):
    # Feature: m20-reflection-v2, Property 1: for any member, its ordinal equals its
    # declaration index and its .value round-trips through json.dumps.
    # Validates: Requirements 1.1, 1.3
    members = list(ReflectionLayer)
    assert len(members) == 5
    member = members[idx]
    assert member.ordinal == idx
    # .value is JSON-serializable and survives a round-trip.
    assert json.loads(json.dumps(member.value)) == member.value
    assert isinstance(member.value, str)


# =============================================================== Property 2


@settings(max_examples=150)
@given(
    errors=st.lists(
        st.floats(min_value=0.6, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=20,
    ),
    cap=st.sampled_from(["research", "browse", "plan"]),
    env=st.sampled_from(["web", "local", "sim"]),
)
def test_p2_longterm_crossing_threshold_emits(errors, cap, env):
    # Feature: m20-reflection-v2, Property 2: a (capability, environment) stream whose
    # mean prediction error stays above the threshold over >= min_samples emits
    # reflection.longterm proposal(s) with the correct payload; the window stays
    # bounded. Validates: Requirements 2.1, 2.2, 2.3
    kernel = FakeKernel()
    reflector = LongTermReflector(window=5, min_samples=3, error_threshold=0.5)
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.longterm", lambda e: seen.append(e))

    for err in errors:
        _publish_reflection(
            kernel, prediction_error=err, calibration=0.5, capability=cap, environment=env
        )

    # High-error stream over >= min_samples => at least one adverse-trend proposal.
    assert seen, "expected a reflection.longterm proposal for a high-error stream"
    for e in seen:
        p = dict(e.payload)
        assert p["capability"] == cap
        assert p["environment"] == env
        assert p["mean_error"] >= 0.5 - 1e-9  # crossed the configured bound
        assert p["sample_count"] >= 3
        assert p["sample_count"] <= 5  # bounded by the window
        json.dumps(p)  # JSON-safe payload (must not raise)

    # Aggregate never exceeds the window bound.
    trend = reflector.trend(cap, env)
    assert trend["sample_count"] <= 5
    assert trend["sample_count"] == min(len(errors), 5)


@settings(max_examples=150)
@given(
    errors=st.lists(
        st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=20,
    ),
)
def test_p2_longterm_below_threshold_emits_none(errors):
    # Feature: m20-reflection-v2, Property 2: a stream staying below the error
    # threshold emits no proposals. Validates: Requirements 2.1, 2.2
    kernel = FakeKernel()
    reflector = LongTermReflector(window=50, min_samples=3, error_threshold=0.5)
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.longterm", lambda e: seen.append(e))

    for err in errors:
        _publish_reflection(kernel, prediction_error=err, capability="c", environment="e")

    assert seen == []


@settings(max_examples=100)
@given(count=st.integers(min_value=1, max_value=60), window=st.integers(min_value=1, max_value=10))
def test_p2_window_strictly_bounded(count, window):
    # Feature: m20-reflection-v2, Property 2: the internal window never exceeds its
    # configured bound regardless of stream length. Validates: Requirements 2.3
    kernel = FakeKernel()
    reflector = LongTermReflector(window=window, min_samples=1, error_threshold=2.0)
    reflector.attach(kernel)
    for _ in range(count):
        _publish_reflection(kernel, prediction_error=0.9, capability="c", environment="e")
    trend = reflector.trend("c", "e")
    assert trend["sample_count"] <= window
    assert trend["sample_count"] == min(count, window)


# =============================================================== Property 3


@settings(max_examples=150)
@given(
    errors=st.lists(
        st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=20,
    ),
    cap=st.sampled_from(["research", "code", "plan"]),
)
def test_p3_skill_verified_low_error_emits_candidate(errors, cap):
    # Feature: m20-reflection-v2, Property 3: a capability accumulating verified
    # low-error experience triggers a reflection.skill candidate proposal, summaries()
    # reports correct counts/rates, and storage stays bounded.
    # Validates: Requirements 3.1, 3.2, 3.3, 3.4
    kernel = FakeKernel()
    reflector = SkillReflector(
        window=10, min_samples=3, verified_threshold=0.7, error_threshold=0.3
    )
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.skill", lambda e: seen.append(e))

    for err in errors:
        _publish_reflection(kernel, prediction_error=err, capability=cap, verified=True)

    assert seen, "expected a reflection.skill candidate for verified low-error stream"
    for e in seen:
        p = dict(e.payload)
        assert p["capability"] == cap
        assert p["candidate"] is True
        assert p["verified_rate"] >= 0.7 - 1e-9
        assert p["mean_error"] <= 0.3 + 1e-9
        json.dumps(p)

    # summaries() reports the correct bounded per-capability aggregate.
    summ = reflector.summaries()
    assert cap in summ
    expected_count = min(len(errors), 10)
    assert summ[cap]["sample_count"] == expected_count
    assert summ[cap]["verified_rate"] == 1.0  # all verified
    assert summ[cap]["mean_error"] <= 0.2 + 1e-9


@settings(max_examples=120)
@given(
    errors=st.lists(
        st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=15,
    ),
)
def test_p3_skill_unverified_emits_none(errors):
    # Feature: m20-reflection-v2, Property 3: low-error but UNVERIFIED experience does
    # not reach the verified-rate threshold, so no candidate is proposed.
    # Validates: Requirements 3.1, 3.2
    kernel = FakeKernel()
    reflector = SkillReflector(
        window=50, min_samples=3, verified_threshold=0.7, error_threshold=0.3
    )
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.skill", lambda e: seen.append(e))
    for err in errors:
        _publish_reflection(kernel, prediction_error=err, capability="c", verified=False)
    assert seen == []
    # summaries still tracks the samples with a 0.0 verified rate.
    summ = reflector.summaries()
    assert summ["c"]["verified_rate"] == 0.0


@settings(max_examples=100)
@given(count=st.integers(min_value=1, max_value=60), window=st.integers(min_value=1, max_value=10))
def test_p3_skill_window_bounded(count, window):
    # Feature: m20-reflection-v2, Property 3: per-capability storage is bounded.
    # Validates: Requirements 3.4
    kernel = FakeKernel()
    reflector = SkillReflector(window=window, min_samples=1)
    reflector.attach(kernel)
    for _ in range(count):
        _publish_reflection(kernel, prediction_error=0.1, capability="c", verified=True)
    assert reflector.summaries()["c"]["sample_count"] == min(count, window)


# =============================================================== Property 4


@settings(max_examples=150)
@given(
    n_caps=st.integers(min_value=2, max_value=5),
    samples_per_cap=st.integers(min_value=3, max_value=6),
    extra_feeds=st.integers(min_value=0, max_value=10),
)
def test_p4_architectural_single_advisory_deduped(n_caps, samples_per_cap, extra_feeds):
    # Feature: m20-reflection-v2, Property 4: crossing the meta-threshold (>=
    # min_capabilities hot capabilities) emits exactly ONE advisory
    # reflection.architectural proposal (dedup latch); continuing to feed hot events
    # does not re-emit; the layer mutates nothing (emits events only).
    # Validates: Requirements 4.1, 4.2
    kernel = FakeKernel()
    reflector = ArchitecturalReflector(
        window=50, min_samples=3, error_threshold=0.5, min_capabilities=2
    )
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.architectural", lambda e: seen.append(e))

    caps = [f"cap{i}" for i in range(n_caps)]
    # Make each capability "hot" (high running mean error over enough samples).
    for cap in caps:
        for _ in range(samples_per_cap):
            _publish_reflection(kernel, prediction_error=0.9, capability=cap)

    assert len(seen) == 1, "expected exactly one advisory proposal on crossing"
    payload = dict(seen[0].payload)
    assert payload["metric"] >= 2
    assert isinstance(payload["capabilities_affected"], list)
    json.dumps(payload)

    # Continuing to feed hot events must NOT re-emit (dedup latch holds).
    for _ in range(extra_feeds):
        _publish_reflection(kernel, prediction_error=0.95, capability=caps[0])
    assert len(seen) == 1

    # No subsystem mutation: the ONLY events the layer emitted are architectural.
    reflection_emitted = kernel.emitted_by_reflection()
    assert reflection_emitted, "layer should have emitted at least the one advisory"
    assert all(e.event_type == "reflection.architectural" for e in reflection_emitted)


@settings(max_examples=100)
@given(samples=st.integers(min_value=3, max_value=15))
def test_p4_architectural_below_threshold_no_emit(samples):
    # Feature: m20-reflection-v2, Property 4: a single hot capability (< min_capabilities)
    # never crosses the meta-threshold. Validates: Requirements 4.1
    kernel = FakeKernel()
    reflector = ArchitecturalReflector(
        window=50, min_samples=3, error_threshold=0.5, min_capabilities=2
    )
    reflector.attach(kernel)
    seen: List[Any] = []
    kernel.subscribe("reflection.architectural", lambda e: seen.append(e))
    for _ in range(samples):
        _publish_reflection(kernel, prediction_error=0.9, capability="only-one")
    assert seen == []


# =============================================================== Property 5


def test_p5_module_does_not_import_memory_competence_recovery():
    # Feature: m20-reflection-v2, Property 5: the layers module never imports
    # memory/competence/recovery (proposes-not-decides isolation). We scan the source
    # text for actual import STATEMENTS (docstring mentions are excluded because they
    # are not `import`/`from` lines). Validates: Requirements 5.1
    import friday.cognition.reflection_layers as mod

    with open(mod.__file__, "r", encoding="utf-8") as fh:
        source = fh.read()

    forbidden = re.compile(
        r"^\s*(?:import|from)\s+friday\.(?:memory|competence|recovery)\b",
        re.MULTILINE,
    )
    matches = forbidden.findall(source)
    assert matches == [], f"forbidden import found: {matches}"
    # Also assert the tell-tale class names are never referenced as code.
    assert re.search(r"\bFridayMemory\b", source) is None
    assert re.search(r"\bMemoryStore\b", source) is None


@settings(max_examples=120)
@given(
    payload=st.one_of(
        st.none(),
        st.just({}),
        st.fixed_dictionaries({"prediction_error": st.just("not-a-number")}),
        st.fixed_dictionaries({"capability": st.integers()}),
        st.dictionaries(
            keys=st.sampled_from(["goal_id", "scale", "prediction_error", "calibration"]),
            values=st.one_of(st.none(), st.text(max_size=5), st.integers()),
            max_size=4,
        ),
    ),
)
def test_p5_malformed_events_never_raise(payload):
    # Feature: m20-reflection-v2, Property 5: malformed/empty reflection.completed
    # events never raise into the bus. Validates: Requirements 2.4, 3.4, 4.3, 6.1
    kernel = FakeKernel()
    attach_reflection_layers(
        kernel, min_samples=3, error_threshold=0.5, min_capabilities=2
    )
    tick = int(kernel.health().get("tick", 0)) + 1
    event = make_event(
        event_type="reflection.completed",
        source="test",
        logical_time=tick,
        payload=payload if isinstance(payload, dict) else None,
    )
    # Must not raise despite malformed payload.
    kernel.publish_event(event)


def test_p5_attach_without_kernel_is_noop():
    # Feature: m20-reflection-v2, Property 5: attach_reflection_layers(None) is a no-op
    # returning a holder of the injected/None layers. Validates: Requirements 6.2, 6.3
    holder = attach_reflection_layers(None)
    assert isinstance(holder, ReflectionLayers)
    assert holder.longterm is None
    assert holder.skill is None
    assert holder.architectural is None

    lt = LongTermReflector()
    sk = SkillReflector()
    arch = ArchitecturalReflector()
    holder2 = attach_reflection_layers(None, longterm=lt, skill=sk, architectural=arch)
    assert holder2.longterm is lt
    assert holder2.skill is sk
    assert holder2.architectural is arch
    # A no-op attach means no kernel was wired into the injected layers.
    assert lt._kernel is None
    assert sk._kernel is None
    assert arch._kernel is None


def test_p5_layers_emit_only_reflection_or_memory_candidate():
    # Feature: m20-reflection-v2, Property 5: the ONLY event types the layers ever emit
    # are reflection.* / memory.candidate. Drive a stream that triggers all three
    # proposals and assert every reflection-sourced event is in the allowed set.
    # Validates: Requirements 5.2, 6.1
    kernel = FakeKernel()
    attach_reflection_layers(
        kernel,
        window=50,
        min_samples=3,
        error_threshold=0.5,
        verified_threshold=0.7,
        min_capabilities=2,
    )

    # Long-term + architectural: two hot capabilities with high error.
    for cap in ("cap-a", "cap-b"):
        for _ in range(4):
            _publish_reflection(
                kernel, prediction_error=0.9, capability=cap, environment="web"
            )
    # Skill: a verified low-error capability. Skill error_threshold is forwarded to 0.5
    # so a mean error <= 0.5 with full verified-rate proposes a candidate.
    for _ in range(4):
        _publish_reflection(
            kernel, prediction_error=0.1, capability="cap-c", verified=True
        )

    emitted = kernel.emitted_by_reflection()
    assert emitted, "expected the layers to emit proposals"
    allowed = {"reflection.longterm", "reflection.skill", "reflection.architectural"}
    for e in emitted:
        assert e.event_type in allowed or e.event_type == "memory.candidate"
        assert e.event_type.startswith("reflection.") or e.event_type == "memory.candidate"
    # We drove all three higher layers; each should have fired at least once.
    kinds = {e.event_type for e in emitted}
    assert "reflection.longterm" in kinds
    assert "reflection.skill" in kinds
    assert "reflection.architectural" in kinds


def test_p5_bus_helper_isolates_layer_attach_failures():
    # Feature: m20-reflection-v2, Property 5: a layer whose attach() explodes must not
    # prevent the others from wiring (degrade safely). Validates: Requirements 6.3
    class BoomLayer:
        def attach(self, kernel):
            raise RuntimeError("attach boom")

    kernel = FakeKernel()
    good = SkillReflector(min_samples=3, verified_threshold=0.7, error_threshold=0.5)
    holder = attach_reflection_layers(kernel, longterm=BoomLayer(), skill=good)
    # The good layer still wired despite the bad one blowing up.
    assert good._kernel is kernel


# =============================================================== Property 6


def _collect_engine_outputs(kernel: CognitiveKernel) -> Tuple[List[Dict], List[Dict]]:
    """Subscribe collectors for the engine's two output event types."""
    candidates: List[Dict] = []
    completeds: List[Dict] = []
    kernel.subscribe("memory.candidate", lambda e: candidates.append(dict(e.payload)))
    kernel.subscribe("reflection.completed", lambda e: completeds.append(dict(e.payload)))
    return candidates, completeds


def _drive_verification(
    kernel: CognitiveKernel,
    *,
    goal_id: str,
    expected: List[str],
    observed: List[str],
    confidence: float,
    satisfied: bool,
    capability: str,
    environment: str,
) -> None:
    tick = int(kernel.health().get("tick", 0)) + 1
    event = make_event(
        event_type="verification.completed",
        source="test",
        logical_time=tick,
        payload={
            "goal_id": goal_id,
            "observed_beliefs": observed,
            "satisfied": satisfied,
            "capability": capability,
            "environment": environment,
            "prediction": {
                "expected_beliefs": expected,
                "confidence": confidence,
                "reversible": True,
            },
        },
    )
    kernel.publish_event(event)


_BELIEF_POOL = ["a", "b", "c", "d", "e"]


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    expected=st.lists(st.sampled_from(_BELIEF_POOL), min_size=0, max_size=5, unique=True),
    observed=st.lists(st.sampled_from(_BELIEF_POOL), min_size=0, max_size=5, unique=True),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    satisfied=st.booleans(),
    capability=st.sampled_from(["research", "browse"]),
    environment=st.sampled_from(["web", "local"]),
)
def test_p6_existing_engine_outputs_unchanged_with_layers(
    tmp_path, expected, observed, confidence, satisfied, capability, environment
):
    # Feature: m20-reflection-v2, Property 6: with the higher layers attached alongside
    # the existing ReflectionEngine, the engine still emits its memory.candidate +
    # reflection.completed outputs identically to a control kernel running only the
    # engine, for the same input. Validates: Requirements 5.3
    goal_id = "g-1"

    # Control kernel: only the engine.
    ctl_path = str(tmp_path / f"ctl_{uuid.uuid4().hex}.jsonl")
    ctl = CognitiveKernel(store_path=ctl_path)
    ctl_engine = ReflectionEngine()
    ctl_engine.attach(ctl)
    ctl_candidates, ctl_completeds = _collect_engine_outputs(ctl)

    # Treatment kernel: the engine PLUS the three higher layers.
    trt_path = str(tmp_path / f"trt_{uuid.uuid4().hex}.jsonl")
    trt = CognitiveKernel(store_path=trt_path)
    trt_engine = ReflectionEngine()
    trt_engine.attach(trt)
    attach_reflection_layers(trt, min_samples=3, min_capabilities=2)
    trt_candidates, trt_completeds = _collect_engine_outputs(trt)

    kwargs = dict(
        goal_id=goal_id,
        expected=expected,
        observed=observed,
        confidence=confidence,
        satisfied=satisfied,
        capability=capability,
        environment=environment,
    )
    _drive_verification(ctl, **kwargs)
    _drive_verification(trt, **kwargs)

    # The engine emits the same number of each output on both kernels.
    assert len(trt_candidates) == len(ctl_candidates)
    assert len(trt_completeds) == len(ctl_completeds)
    # And the payloads are identical (additive layers never alter engine output).
    assert trt_candidates == ctl_candidates
    assert trt_completeds == ctl_completeds


def test_p6_engine_still_emits_reflection_completed_with_layers(tmp_path):
    # Feature: m20-reflection-v2, Property 6: a concrete end-to-end check that the
    # engine's reflection.completed + memory.candidate still fire with layers attached.
    # Validates: Requirements 5.3
    kernel = CognitiveKernel(store_path=str(tmp_path / "p6.jsonl"))
    engine = ReflectionEngine()
    engine.attach(kernel)
    attach_reflection_layers(kernel)
    candidates, completeds = _collect_engine_outputs(kernel)

    _drive_verification(
        kernel,
        goal_id="g-9",
        expected=["a", "b"],
        observed=["a", "b"],
        confidence=0.8,
        satisfied=True,
        capability="research",
        environment="web",
    )
    assert len(candidates) == 1
    assert len(completeds) == 1
    assert completeds[0]["goal_id"] == "g-9"
    assert completeds[0]["prediction_error"] == 0.0  # perfect prediction


# ----------------------------------------------------- ReflectionScale untouched


def test_reflection_scale_unchanged():
    # Feature: m20-reflection-v2: the additive ReflectionLayer taxonomy leaves the
    # pre-existing four-scale enum intact. Validates: Requirements 1.2, 5.3
    assert [s.value for s in ReflectionScale] == ["micro", "task", "goal", "session"]
