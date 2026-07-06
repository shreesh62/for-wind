"""M8 — Property-based tests (Hypothesis) for reflection/memory/competence/recovery.

Realizes the 8 correctness properties from the M8 design document
(``.kiro/specs/m8-reflection-memory-competence/design.md``) as Hypothesis
property tests. Every test runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O
or external surface is ever touched.

Each test carries its design property number and a ``Validates: Requirements``
annotation in its docstring.
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.cognition import ReflectionEngine, ReflectionScale
from friday.competence.model import CompetenceModel, NEUTRAL_PRIOR
from friday.deliberation.candidate import PredictedOutcome
from friday.memory.runtime import MemoryDecision, MemoryRuntime
from friday.recovery import RecoveryEngine, RecoveryLevel
from friday.verification.evidence_law import ExecutionEvidence


# --------------------------------------------------------------------------- #
# Helpers / strategies
# --------------------------------------------------------------------------- #

_beliefs = st.lists(st.text(min_size=1, max_size=8), min_size=0, max_size=6)
_confidence = st.floats(min_value=0.0, max_value=1.0)


def _reflect(engine: ReflectionEngine, expected: List[str], observed: List[str],
             *, confidence: float = 0.5, verified: bool = True):
    prediction = PredictedOutcome(expected_beliefs=tuple(expected), confidence=confidence)
    return engine.reflect(
        goal_id="g-1",
        scale=ReflectionScale.TASK,
        prediction=prediction,
        observed_beliefs=observed,
        verified=verified,
        capability="cap",
        environment="env",
    )


def _is_non_increasing(values: List[float], tol: float = 1e-9) -> bool:
    return all(values[i] + tol >= values[i + 1] for i in range(len(values) - 1))


def _is_non_decreasing(values: List[float], tol: float = 1e-9) -> bool:
    return all(values[i] - tol <= values[i + 1] for i in range(len(values) - 1))


# --------------------------------------------------------------------------- #
# Property 1 — Reflection never writes long-term memory directly
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(expected=_beliefs, observed=_beliefs, confidence=_confidence,
       verified=st.booleans())
def test_property_1_reflection_never_writes_memory(
    expected: List[str], observed: List[str], confidence: float, verified: bool
) -> None:
    """Property 1 — a ReflectionEngine constructed WITHOUT a kernel performs no
    memory writes (it holds no memory store) and ``reflect`` is a pure function
    of its inputs.

    Validates: Requirements 1.1
    """
    engine = ReflectionEngine()  # no kernel attached

    # The engine has no reference to any memory store — the ONLY channel to
    # memory is emitting a kernel event, and no kernel is attached.
    assert engine._kernel is None
    for attr in vars(engine).values():
        assert not isinstance(attr, MemoryRuntime)

    record = _reflect(engine, expected, observed,
                      confidence=confidence, verified=verified)
    from friday.cognition.reflection import ReflectionRecord
    assert isinstance(record, ReflectionRecord)

    # Purity: two identical calls yield equal derived fields (ignore random id).
    engine2 = ReflectionEngine()
    record2 = _reflect(engine2, expected, observed,
                       confidence=confidence, verified=verified)
    assert record.prediction_error == record2.prediction_error
    assert record.questions == record2.questions
    assert record.verified == record2.verified
    assert record.calibration_delta == record2.calibration_delta


# --------------------------------------------------------------------------- #
# Property 8 — Prediction error is a bounded score
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(expected=_beliefs, observed=_beliefs, confidence=_confidence)
def test_property_8_prediction_error_bounded(
    expected: List[str], observed: List[str], confidence: float
) -> None:
    """Property 8 — prediction_error is always in [0, 1]; an exact match is 0.0;
    an empty expected set is 0.0; a non-empty expected set with zero overlap is
    1.0.

    Validates: Requirements 1.2, 1.3, 1.4
    """
    engine = ReflectionEngine()
    error = _reflect(engine, expected, observed, confidence=confidence).prediction_error
    assert 0.0 <= error <= 1.0

    # Exact match → 0.0
    assert _reflect(engine, expected, expected, confidence=confidence).prediction_error == 0.0

    # Empty expected → 0.0
    assert _reflect(engine, [], observed, confidence=confidence).prediction_error == 0.0

    # Non-empty expected with zero overlap → 1.0
    if expected:
        disjoint = [f"__disjoint__{tok}" for tok in expected]
        # Guarantee no accidental overlap with expected.
        assert set(disjoint).isdisjoint(set(expected))
        assert _reflect(engine, expected, disjoint,
                        confidence=confidence).prediction_error == 1.0


# --------------------------------------------------------------------------- #
# Property 2 — Memory candidates integrated only from verified experience
# --------------------------------------------------------------------------- #


_verified_values = st.sampled_from([True, False, None, 1, "true", "True", 0])


@settings(max_examples=50, deadline=None)
@given(verified=_verified_values, has_hash=st.booleans(),
       kind=st.sampled_from(["turn", "pattern", "fact", ""]))
def test_property_2_verified_only_integration(
    verified, has_hash: bool, kind: str
) -> None:
    """Property 2 — a candidate is REJECTED whenever ``verified`` is not exactly
    True; ACCEPT/MERGE only occur when ``verified`` is exactly True (and not
    contradicting).

    Validates: Requirements 2.1
    """
    runtime = MemoryRuntime()
    candidate = {"kind": kind, "content": "x"}
    if verified is not None or True:
        # Only set the key when not "missing"; None models the missing case.
        if verified is not None:
            candidate["verified"] = verified
    if has_hash:
        candidate["context_hash"] = "abc123"

    verdict = runtime.decide(candidate)

    if verified is True:
        assert verdict.decision in (MemoryDecision.ACCEPT, MemoryDecision.MERGE)
    else:
        assert verdict.decision is MemoryDecision.REJECT


# --------------------------------------------------------------------------- #
# Property 7 — Memory never overrides a contradicting observation
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(kind=st.sampled_from(["turn", "pattern", "fact"]),
       has_hash=st.booleans())
def test_property_7_reality_outranks_memory(kind: str, has_hash: bool) -> None:
    """Property 7 — for any candidate (even verified=True), a contradicting
    observation forces REJECT (reality outranks memory).

    Validates: Requirements 2.2
    """
    runtime = MemoryRuntime()
    candidate = {"verified": True, "kind": kind, "content": "x"}
    if has_hash:
        candidate["context_hash"] = "abc123"

    verdict = runtime.decide(candidate, contradicting_observation=True)
    assert verdict.decision is MemoryDecision.REJECT


# --------------------------------------------------------------------------- #
# Property 3 — Competence in [0, 1] and evidence-derived
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(outcomes=st.lists(st.booleans(), min_size=0, max_size=40))
def test_property_3_competence_bounded_and_laplace(outcomes: List[bool]) -> None:
    """Property 3 — confidence stays in [0, 1] and equals the Laplace estimator
    ``(successes + 1) / (attempts + 2)`` derived from recorded outcomes.

    Validates: Requirements 3.1, 3.4
    """
    model = CompetenceModel()
    key = ("cap", "env")
    for success in outcomes:
        model.record_outcome(key, success=success, tick=0)

    attempts = len(outcomes)
    successes = sum(1 for s in outcomes if s)
    expected = (successes + 1) / (attempts + 2)

    confidence = model.confidence(key)
    assert 0.0 <= confidence <= 1.0
    assert abs(confidence - expected) < 1e-9


# --------------------------------------------------------------------------- #
# Property 4 — Competence decay is monotonic toward the neutral prior
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(
    successes=st.integers(min_value=3, max_value=20),
    failures=st.integers(min_value=3, max_value=20),
    ticks=st.lists(st.integers(min_value=0, max_value=2000),
                   min_size=2, max_size=12),
)
def test_property_4_decay_monotonic(
    successes: int, failures: int, ticks: List[int]
) -> None:
    """Property 4 — without new evidence, effective_confidence decays monotonically
    toward the neutral prior: non-increasing from above, non-decreasing from below,
    always in [0, 1].

    Validates: Requirements 3.2
    """
    sorted_ticks = sorted(ticks)

    # Above-prior case: several successes push confidence above 0.5.
    above = CompetenceModel(decay_half_life_ticks=100)
    key = ("cap", "env")
    for _ in range(successes):
        above.record_outcome(key, success=True, tick=0)
    assert above.confidence(key) > 0.5

    above_seq = [above.effective_confidence(key, t) for t in sorted_ticks]
    assert all(0.0 <= v <= 1.0 for v in above_seq)
    assert _is_non_increasing(above_seq)
    assert all(v >= NEUTRAL_PRIOR - 1e-9 for v in above_seq)

    # Below-prior case: several failures push confidence below 0.5.
    below = CompetenceModel(decay_half_life_ticks=100)
    for _ in range(failures):
        below.record_outcome(key, success=False, tick=0)
    assert below.confidence(key) < 0.5

    below_seq = [below.effective_confidence(key, t) for t in sorted_ticks]
    assert all(0.0 <= v <= 1.0 for v in below_seq)
    assert _is_non_decreasing(below_seq)
    assert all(v <= NEUTRAL_PRIOR + 1e-9 for v in below_seq)


# --------------------------------------------------------------------------- #
# Property 6 — Irreversible-action confidence gate is monotonic
# --------------------------------------------------------------------------- #


def test_property_6a_risk_gate_monotonic() -> None:
    """Property 6 (a) — RISK_CONFIDENCE_GATE is non-decreasing across
    [observe, reversible, modify, irreversible].

    Validates: Requirements 3.6, 4.2, 4.3
    """
    gate = CompetenceModel.RISK_CONFIDENCE_GATE
    order = ["observe", "reversible", "modify", "irreversible"]
    values = [gate[k] for k in order]
    assert _is_non_decreasing(values)


@settings(max_examples=50, deadline=None)
@given(
    competence=st.floats(min_value=0.0, max_value=0.849),
    goal_id=st.text(min_size=1, max_size=16),
)
def test_property_6b_irreversible_escalates(competence: float, goal_id: str) -> None:
    """Property 6 (b) — required confidence for an irreversible action is at least
    that for a reversible one, and an irreversible failure below the 0.85 floor
    escalates to HUMAN with no chosen alternative.

    Validates: Requirements 3.6, 4.2, 4.3
    """
    engine = RecoveryEngine()
    assert (engine._required_confidence(reversible=False)
            >= engine._required_confidence(reversible=True))

    plan = engine.recover(
        goal_id=goal_id,
        requirement="research X",
        evidence=ExecutionEvidence(),
        reversible=False,
        competence=competence,
    )
    assert plan.chosen is None
    assert plan.level >= RecoveryLevel.HUMAN


# --------------------------------------------------------------------------- #
# Property 5 — Recovery preserves the goal id
# --------------------------------------------------------------------------- #


@settings(max_examples=50, deadline=None)
@given(
    goal_id=st.text(min_size=1, max_size=24),
    reversible=st.booleans(),
    blocked=st.booleans(),
    competence=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_5_recovery_preserves_goal_id(
    goal_id: str, reversible: bool, blocked: bool, competence: float
) -> None:
    """Property 5 — recovery preserves the goal id verbatim, both on the plan and
    in its serialized payload.

    Validates: Requirements 4.1
    """
    engine = RecoveryEngine()
    plan = engine.recover(
        goal_id=goal_id,
        requirement="research X",
        evidence=ExecutionEvidence(),
        reversible=reversible,
        blocked=blocked,
        competence=competence,
    )
    assert plan.goal_id == goal_id
    assert plan.to_payload()["goal_id"] == goal_id
