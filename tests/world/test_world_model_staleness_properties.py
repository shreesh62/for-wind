"""M15 — Property-based tests (Hypothesis) for the WorldModel staleness sweep.

Realizes correctness properties 6, 7, 8, and 9 from the M15 design document
(``.kiro/specs/m15-world-model-v2/design.md``) as Hypothesis property tests over
:meth:`friday.world.world_model.WorldModel.stale_beliefs`:

- Property 6 — Stale classification (TTL, freshness threshold, non-positive TTL).
- Property 7 — Non-expiring TTL beliefs are stale only by freshness decay.
- Property 8 — Hard expiry outranks staleness.
- Property 9 — Staleness sweep is idempotent and order-stable (no cached freshness).

Populating the WorldModel
-------------------------
The public ``ingest``/``observation.received`` path can only construct beliefs with
the M15 field DEFAULTS (``ttl_seconds=None``, ``high_impact=False``,
``half_life_seconds=86400.0``), so it cannot exercise the staleness classification
that depends on those fields. To drive the sweep across the full input space we
inject fully-specified ``Belief`` instances directly into the authoritative belief
collection ``WorldModel._fusion._beliefs_by_key`` — the exact same collection that
``stale_beliefs`` iterates over (``self._fusion.beliefs``). Each belief is stored
under a unique string key. No production code is modified.

Every WorldModel is built with NO kernel attached, so the ``belief.stale_flagged``
emission for high-impact stale beliefs is a silent no-op and the sweep still returns
its results — detection never depends on a live bus.

Expected results are computed by mirroring the WorldModel's own classification logic
against each belief's ``freshness(now)`` (the real, pure method) and its TTL/expiry,
using a known, explicitly-set ``staleness_threshold``.

Validates: Requirements 2.2, 2.7, 2.8, 4.1, 4.2, 4.3, 4.7, 6.4
"""

from __future__ import annotations

from typing import List, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.world.belief import Belief
from friday.world.world_model import WorldModel

# Known, explicit staleness threshold used throughout so assertions mirror a fixed value.
THRESHOLD = 0.1


# --------------------------------------------------------------------------- #
# Shared generators.
# --------------------------------------------------------------------------- #

_times = st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False)
_positive_half_life = st.floats(
    min_value=1e-3, max_value=1e12, allow_nan=False, allow_infinity=False
)
_text = st.text(max_size=12)

# ttl spanning None (non-expiring), non-positive (<= 0 => instantly stale), and positive.
_ttl = st.one_of(
    st.none(),
    st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1e-3, max_value=1e9, allow_nan=False, allow_infinity=False),
)


@st.composite
def _belief(draw, *, ttl=_ttl, expires=True):
    """Build a Belief with arbitrary M15-relevant fields.

    ``ttl`` selects the ttl strategy (overridable per-property); ``expires`` toggles
    whether a hard ``expires_at`` may be set.
    """
    observed_at = draw(_times)
    expires_at: Optional[float] = None
    if expires:
        expires_at = draw(
            st.one_of(
                st.none(),
                st.floats(
                    min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False
                ),
            )
        )
    return Belief(
        description=draw(_text),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
        source=draw(_text),
        observed_at=observed_at,
        expires_at=expires_at,
        half_life_seconds=draw(_positive_half_life),
        ttl_seconds=draw(ttl),
        high_impact=draw(st.booleans()),
    )


def _populate(beliefs: List[Belief], threshold: float = THRESHOLD) -> WorldModel:
    """Inject beliefs directly into the WorldModel's authoritative belief store.

    Bypasses ``ingest`` (which cannot set M15 fields) by writing into
    ``_fusion._beliefs_by_key`` under unique keys. No kernel is attached, so any
    high-impact emission during the sweep is a silent no-op.
    """
    wm = WorldModel(staleness_threshold=threshold)
    for index, belief in enumerate(beliefs):
        wm._fusion._beliefs_by_key[str(index)] = belief
    return wm


def _expected_stale_ids(beliefs: List[Belief], now: float, threshold: float) -> set:
    """Mirror WorldModel.stale_beliefs classification, returning the set of stale ids.

    Hard expiry outranks staleness (Req 2.8); otherwise stale when TTL is exceeded
    (Req 2.2/4.7) OR freshness has decayed below the threshold (Req 4.1).
    """
    expected = set()
    for belief in beliefs:
        if belief.expires_at is not None and now >= belief.expires_at:
            continue  # hard-expired => neither stale nor flagged
        ttl_exceeded = (
            belief.ttl_seconds is not None
            and (now - belief.observed_at) > belief.ttl_seconds
        )
        if ttl_exceeded or belief.freshness(now) < threshold:
            expected.add(belief.id)
    return expected


# --------------------------------------------------------------------------- #
# Property 6 — Stale classification (TTL, freshness threshold, non-positive TTL)
# Feature: m15-world-model-v2, Property 6: Stale classification (TTL, freshness threshold, non-positive TTL)
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(beliefs=st.lists(_belief(), min_size=0, max_size=8), now=_times)
def test_property_6_stale_classification(beliefs, now):
    """Property 6: stale_beliefs(now) contains exactly the beliefs that are (a) not
    hard-expired and (b) either have a non-None ttl with age > ttl, or freshness(now)
    strictly below the configured staleness_threshold. Non-positive TTL beliefs are
    stale for now > observed_at, and stale high_impact beliefs are included.

    Validates: Requirements 2.2, 4.1, 4.3, 4.7
    """
    wm = _populate(beliefs, THRESHOLD)
    result = wm.stale_beliefs(now)
    result_ids = {b.id for b in result}

    expected_ids = _expected_stale_ids(beliefs, now, THRESHOLD)
    assert result_ids == expected_ids

    # Every returned belief genuinely satisfies the stale predicate at `now`.
    for belief in result:
        assert not (belief.expires_at is not None and now >= belief.expires_at)
        ttl_exceeded = (
            belief.ttl_seconds is not None
            and (now - belief.observed_at) > belief.ttl_seconds
        )
        assert ttl_exceeded or belief.freshness(now) < THRESHOLD

    # ttl_seconds <= 0 with now > observed_at and no hard expiry => always included.
    for belief in beliefs:
        if (
            belief.ttl_seconds is not None
            and belief.ttl_seconds <= 0
            and now > belief.observed_at
            and not (belief.expires_at is not None and now >= belief.expires_at)
        ):
            assert belief.id in result_ids

    # Stale high_impact beliefs are included in the results (Req 4.3).
    for belief in beliefs:
        if belief.id in expected_ids and belief.high_impact:
            assert belief.id in result_ids


# --------------------------------------------------------------------------- #
# Property 7 — Non-expiring TTL beliefs are stale only by freshness decay
# Feature: m15-world-model-v2, Property 7: Non-expiring TTL beliefs are stale only by freshness decay
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(
    beliefs=st.lists(_belief(ttl=st.none(), expires=False), min_size=0, max_size=8),
    now=_times,
)
def test_property_7_non_expiring_ttl_freshness_only(beliefs, now):
    """Property 7: for beliefs with ttl_seconds is None (and no hard expiry), the
    belief is absent from stale_beliefs(now) exactly when freshness(now) >= threshold
    and present exactly when freshness(now) < threshold.

    Validates: Requirements 2.7
    """
    wm = _populate(beliefs, THRESHOLD)
    result_ids = {b.id for b in wm.stale_beliefs(now)}

    for belief in beliefs:
        assert belief.ttl_seconds is None  # generator invariant
        if belief.freshness(now) < THRESHOLD:
            assert belief.id in result_ids
        else:
            assert belief.id not in result_ids


# --------------------------------------------------------------------------- #
# Property 8 — Hard expiry outranks staleness
# Feature: m15-world-model-v2, Property 8: Hard expiry outranks staleness
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(
    observed_at=st.floats(
        min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
    ),
    age=st.floats(min_value=1e-3, max_value=1e9, allow_nan=False, allow_infinity=False),
    expiry_frac=st.floats(min_value=0.0, max_value=1.0),
    half_life=_positive_half_life,
    high_impact=st.booleans(),
)
def test_property_8_hard_expiry_outranks_staleness(
    observed_at, age, expiry_frac, half_life, high_impact
):
    """Property 8: a belief whose expires_at is exceeded at now is treated as expired,
    not stale — it is NOT in stale_beliefs(now) even when its TTL is also exceeded.

    Validates: Requirements 2.8
    """
    now = observed_at + age
    # Place expires_at within (observed_at, now] so it is hard-expired at now.
    expires_at = observed_at + expiry_frac * age
    # TTL of 0 => also exceeded for any now > observed_at, so staleness would fire
    # were it not for the expiry precedence.
    belief = Belief(
        description="b",
        confidence=0.5,
        source="s",
        observed_at=observed_at,
        expires_at=expires_at,
        half_life_seconds=half_life,
        ttl_seconds=0.0,
        high_impact=high_impact,
    )
    wm = _populate([belief], THRESHOLD)
    result_ids = {b.id for b in wm.stale_beliefs(now)}

    # Sanity: the belief IS hard-expired at now, and WOULD be stale by TTL otherwise.
    assert now >= expires_at
    assert (now - observed_at) > belief.ttl_seconds
    # Expiry precedence: absent from the stale results regardless of refresh policy.
    assert belief.id not in result_ids


# --------------------------------------------------------------------------- #
# Property 9 — Staleness sweep is idempotent and order-stable (no cached freshness)
# Feature: m15-world-model-v2, Property 9: Staleness sweep is idempotent and order-stable (no cached freshness)
# --------------------------------------------------------------------------- #
@settings(max_examples=100)
@given(
    beliefs=st.lists(_belief(), min_size=0, max_size=8),
    now=_times,
    other_nows=st.lists(_times, min_size=0, max_size=4),
)
def test_property_9_sweep_idempotent_and_order_stable(beliefs, now, other_nows):
    """Property 9: for a fixed belief set and now, stale_beliefs(now) called N >= 2
    times returns lists with the same elements in the same order, and interleaving
    calls at other now values does not change the result at the original now
    (freshness is recomputed, never cached).

    Validates: Requirements 4.2, 6.4
    """
    wm = _populate(beliefs, THRESHOLD)

    baseline = [b.id for b in wm.stale_beliefs(now)]

    # Idempotent: N >= 2 repeated calls are identical in elements AND order.
    for _ in range(3):
        assert [b.id for b in wm.stale_beliefs(now)] == baseline

    # Interleave sweeps at other `now` values; they must not perturb the original.
    for other in other_nows:
        wm.stale_beliefs(other)
        assert [b.id for b in wm.stale_beliefs(now)] == baseline

    # Result is sorted by the stable key (observed_at, id).
    by_id = {b.id: b for b in beliefs}
    keys = [(by_id[bid].observed_at, bid) for bid in baseline]
    assert keys == sorted(keys)
