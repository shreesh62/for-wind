"""M15 — Property-based tests (Hypothesis) for Belief freshness and M15 fields.

Realizes correctness properties 1, 2, 3, 4, 5, 13, and 14 from the M15 design
document (``.kiro/specs/m15-world-model-v2/design.md``) as Hypothesis property
tests over the extended :class:`friday.world.belief.Belief`:

- Property 1  — Freshness correctness (formula, clamp, boundaries, M9 delegation).
- Property 2  — Freshness half-life anchor and monotonicity.
- Property 3  — Freshness determinism (replay-safety).
- Property 4  — Reinforce restores freshness to 1.0.
- Property 5  — refresh_cost is clamped to [0, 1].
- Property 13 — Minimal construction defaults all M15 fields.
- Property 14 — reinforce/contradict preserve M15 fields through replace().

Freshness is a pure numeric function of ``(observed_at, now, half_life_seconds)``
that delegates to the M9 ``KnowledgeAging`` decay curve, so these tests exercise it
directly with no wiring and no clock dependence.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.4, 3.5, 5.3, 5.4, 6.2, 6.3
"""

from __future__ import annotations

import math
from unittest.mock import patch

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from friday.temporal.aging import KnowledgeAging
from friday.world.belief import Belief
from friday.world.provenance import (
    BeliefProvenance,
    RefreshPolicy,
    VerificationStatus,
)


# --------------------------------------------------------------------------- #
# Shared generators (per design "Testing Strategy" / "Generators").
# --------------------------------------------------------------------------- #

# Times: bounded, finite, non-negative (per design generators).
_times = st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False)

# Positive half-lives, plus explicit non-positive (<= 0) cases.
_positive_half_life = st.floats(
    min_value=1e-3, max_value=1e12, allow_nan=False, allow_infinity=False
)
_nonpositive_half_life = st.floats(
    min_value=-1e6, max_value=0.0, allow_nan=False, allow_infinity=False
)
_any_half_life = st.one_of(_positive_half_life, _nonpositive_half_life)

# Deltas spanning negatives (clock skew), zero (boundary), and positives.
_deltas = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False)

_confidence = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_text = st.text(max_size=20)
_refresh_policies = st.sampled_from(list(RefreshPolicy))
_verification_statuses = st.sampled_from(list(VerificationStatus))


def _expected_freshness(observed_at: float, now: float, half_life: float) -> float:
    """Reference clamp of ``0.5 ** ((now - observed_at) / half_life)``.

    Mirrors ``KnowledgeAging.freshness`` arithmetic exactly so the equality checks
    are bit-for-bit, not merely approximate.
    """
    elapsed = now - observed_at
    if elapsed <= 0.0:
        return 1.0
    if half_life <= 0.0:
        return 0.0
    value = 0.5 ** (elapsed / half_life)
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


@st.composite
def _m15_beliefs(draw):
    """Build a Belief with arbitrary (incl. adversarial) M15 field values."""
    observed_at = draw(_times)
    half_life = draw(_positive_half_life)
    ttl = draw(
        st.one_of(
            st.none(),
            st.floats(min_value=-100.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        )
    )
    refresh_cost = draw(
        st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)
    )
    provenance = BeliefProvenance(
        supporting_observations=draw(st.lists(_text, max_size=3)),
        contradicting_observations=draw(st.lists(_text, max_size=3)),
        derivation_chain=draw(st.lists(_text, max_size=3)),
        verification_status=draw(_verification_statuses),
    )
    return Belief(
        description=draw(_text),
        confidence=draw(_confidence),
        source=draw(_text),
        observed_at=observed_at,
        half_life_seconds=half_life,
        ttl_seconds=ttl,
        refresh_policy=draw(_refresh_policies),
        refresh_cost=refresh_cost,
        high_impact=draw(st.booleans()),
        provenance=provenance,
    )


# --------------------------------------------------------------------------- #
# Property 1 — Freshness correctness (formula, clamp, boundaries, M9 delegation)
# Feature: m15-world-model-v2, Property 1: Freshness correctness (formula, clamp, boundaries, M9 delegation)
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(observed_at=_times, half_life=_any_half_life, delta=_deltas)
def test_property_1_freshness_correctness(observed_at, half_life, delta):
    """Property 1: freshness equals the M9 curve, is clamped to [0, 1], is 1.0 when
    now <= observed_at, matches the clamped half-life formula otherwise, and is 0.0
    for a non-positive half-life once time has advanced.

    Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.7
    """
    now = observed_at + delta
    belief = Belief(
        description="b",
        confidence=0.5,
        source="s",
        observed_at=observed_at,
        half_life_seconds=half_life,
    )
    result = belief.freshness(now)

    # (Req 1.5) Delegation: identical to the single M9 decay-curve implementation.
    aging = KnowledgeAging(half_life_seconds=half_life)
    assert result == aging.freshness(observed_at, now)

    # (Req 1.1) Always within the closed interval [0, 1].
    assert 0.0 <= result <= 1.0

    # (Req 1.4) Freshest (1.0) at or before the observation instant.
    if now <= observed_at:
        assert result == 1.0

    # (Req 1.2, 1.7) Otherwise equals the clamped half-life formula bit-for-bit.
    assert result == _expected_freshness(observed_at, now, half_life)

    # (Req 1.7) Non-positive half-life => stale immediately once time advances.
    if half_life <= 0.0 and now > observed_at:
        assert result == 0.0


# --------------------------------------------------------------------------- #
# Property 2 — Freshness half-life anchor and monotonicity
# Feature: m15-world-model-v2, Property 2: Freshness half-life anchor and monotonicity
# --------------------------------------------------------------------------- #

# Constrained ranges so observed_at + half_life keeps float precision at the anchor.
_anchor_times = st.floats(
    min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False
)
_anchor_half_life = st.floats(
    min_value=1e-2, max_value=1e6, allow_nan=False, allow_infinity=False
)


@settings(max_examples=200)
@given(observed_at=_anchor_times, half_life=_anchor_half_life, d1=_deltas, d2=_deltas)
def test_property_2_half_life_anchor_and_monotonicity(observed_at, half_life, d1, d2):
    """Property 2: freshness at one half-life is 0.5 (within epsilon), and freshness
    is monotonically non-increasing as ``now`` advances.

    Validates: Requirements 1.3
    """
    belief = Belief(
        description="b",
        confidence=0.5,
        source="s",
        observed_at=observed_at,
        half_life_seconds=half_life,
    )

    # Anchor: at exactly one half-life the freshness is 0.5 within float epsilon.
    at_half_life = belief.freshness(observed_at + half_life)
    assert math.isclose(at_half_life, 0.5, rel_tol=1e-6, abs_tol=1e-6)

    # Monotonicity: for t1 <= t2, freshness(t1) >= freshness(t2).
    t1 = observed_at + min(d1, d2)
    t2 = observed_at + max(d1, d2)
    f1 = belief.freshness(t1)
    f2 = belief.freshness(t2)
    assert f1 >= f2 - 1e-9


# --------------------------------------------------------------------------- #
# Property 3 — Freshness determinism (replay-safety)
# Feature: m15-world-model-v2, Property 3: Freshness determinism (replay-safety)
# --------------------------------------------------------------------------- #
@settings(max_examples=100)
@given(observed_at=_times, half_life=_positive_half_life, delta=_deltas)
def test_property_3_freshness_determinism(observed_at, half_life, delta):
    """Property 3: for fixed (observed_at, now, half_life) every invocation returns a
    bit-identical float, independent of call count, and freshness never reads a clock.

    Validates: Requirements 1.8, 6.2, 6.3
    """
    now = observed_at + delta
    belief = Belief(
        description="b",
        confidence=0.5,
        source="s",
        observed_at=observed_at,
        half_life_seconds=half_life,
    )

    # Repeated invocations are bit-identical.
    first = belief.freshness(now)
    for _ in range(25):
        assert belief.freshness(now) == first

    # A second belief with the same inputs yields the same value.
    twin = Belief(
        description="other",
        confidence=0.9,
        source="other",
        observed_at=observed_at,
        half_life_seconds=half_life,
    )
    assert twin.freshness(now) == first

    # No wall-clock access: freshness must succeed even if time.time() would raise.
    with patch("time.time", side_effect=AssertionError("clock accessed")):
        assert belief.freshness(now) == first


# --------------------------------------------------------------------------- #
# Property 4 — Reinforce restores freshness to 1.0
# Feature: m15-world-model-v2, Property 4: Reinforce restores freshness to 1.0
# --------------------------------------------------------------------------- #
@settings(max_examples=100)
@given(
    belief=_m15_beliefs(),
    confidence=_confidence,
    evidence_id=st.one_of(st.none(), _text),
)
def test_property_4_reinforce_restores_freshness(belief, confidence, evidence_id):
    """Property 4: after reinforce, evaluating freshness at the returned belief's own
    observation time yields 1.0.

    reinforce resets observed_at to its observation instant (via time.time()), so
    freshness is evaluated AT that returned observed_at.

    Validates: Requirements 1.6
    """
    reinforced = belief.reinforce(confidence, evidence_id)
    assert reinforced.freshness(reinforced.observed_at) == 1.0


# --------------------------------------------------------------------------- #
# Property 5 — refresh_cost is clamped to [0, 1]
# Feature: m15-world-model-v2, Property 5: refresh_cost is clamped to [0, 1]
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(
    refresh_cost=st.floats(allow_nan=False, allow_infinity=True),
    confidence=_confidence,
)
def test_property_5_refresh_cost_clamped(refresh_cost, confidence):
    """Property 5: for any float refresh_cost at construction, the stored value lies
    in [0, 1] and equals the clamp of the input.

    Validates: Requirements 2.4
    """
    belief = Belief(
        description="b",
        confidence=confidence,
        source="s",
        refresh_cost=refresh_cost,
    )
    assert 0.0 <= belief.refresh_cost <= 1.0
    assert belief.refresh_cost == max(0.0, min(1.0, refresh_cost))


# --------------------------------------------------------------------------- #
# Property 13 — Minimal construction defaults all M15 fields
# Feature: m15-world-model-v2, Property 13: Minimal construction defaults all M15 fields
# --------------------------------------------------------------------------- #
@settings(max_examples=100)
@given(description=_text, confidence=_confidence, source=_text)
def test_property_13_minimal_construction_defaults(description, confidence, source):
    """Property 13: Belief(description, confidence, source) constructs with all M15
    fields at their documented defaults.

    Validates: Requirements 3.5, 5.3
    """
    belief = Belief(description, confidence, source)

    assert belief.half_life_seconds == 86400.0
    assert belief.ttl_seconds is None
    assert belief.refresh_policy == RefreshPolicy.ON_STALE
    assert belief.refresh_cost == 0.0
    assert belief.high_impact is False
    assert isinstance(belief.provenance, BeliefProvenance)
    assert belief.provenance.verification_status == VerificationStatus.UNVERIFIED


# --------------------------------------------------------------------------- #
# Property 14 — reinforce/contradict preserve M15 fields through replace()
# Feature: m15-world-model-v2, Property 14: reinforce/contradict preserve M15 fields through replace()
# --------------------------------------------------------------------------- #
@settings(max_examples=100)
@given(
    belief=_m15_beliefs(),
    confidence=_confidence,
    evidence_id=st.one_of(st.none(), _text),
)
def test_property_14_reinforce_contradict_preserve_m15_fields(
    belief, confidence, evidence_id
):
    """Property 14: reinforce(...) and contradict(...) carry all M15 fields through
    dataclasses.replace() unchanged; only confidence, observed_at/last_updated, and
    the relevant legacy evidence list may change.

    Validates: Requirements 5.4
    """
    reinforced = belief.reinforce(confidence, evidence_id)
    contradicted = belief.contradict(confidence, evidence_id)

    for derived in (reinforced, contradicted):
        assert derived.half_life_seconds == belief.half_life_seconds
        assert derived.ttl_seconds == belief.ttl_seconds
        assert derived.refresh_policy == belief.refresh_policy
        assert derived.refresh_cost == belief.refresh_cost
        assert derived.high_impact == belief.high_impact
        assert derived.provenance == belief.provenance
