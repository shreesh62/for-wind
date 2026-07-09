"""M15 — Property-based tests (Hypothesis) for the provenance pure cores.

Realizes correctness properties 10 and 12 from the M15 design document
(``.kiro/specs/m15-world-model-v2/design.md``) as Hypothesis property tests over
the pure, domain-agnostic helpers in ``friday/world/provenance.py``:

- ``derive_verification_status`` — the verification-status derivation rule.
- ``build_derivation_chain`` — the ordered, acyclic, bounded derivation chain.

Both helpers are pure functions of their inputs (no I/O, no clock, no kernel), so
these tests exercise them directly with no wiring.

Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7, 3.8
"""

from __future__ import annotations

from typing import List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.world.belief import Belief
from friday.world.provenance import (
    MAX_DERIVATION_CHAIN,
    BeliefProvenance,
    RefreshPolicy,
    VerificationStatus,
    build_derivation_chain,
    derive_verification_status,
)


# --------------------------------------------------------------------------- #
# Shared generators — synthetic, domain-agnostic (Axiom 15).
# --------------------------------------------------------------------------- #

# Observation ids are opaque strings; a small pool guarantees collisions,
# duplicates, and (for chains) overlap with the deriving belief's own id.
_ID_POOL = ["a", "b", "c", "d", "e", "f", "g", "h", "own", "x1", "x2", "x3"]
_ids = st.lists(st.sampled_from(_ID_POOL), max_size=8)
_statuses = st.sampled_from(list(VerificationStatus))


# --------------------------------------------------------------------------- #
# Property 10 — Verification status derivation rule
# Feature: m15-world-model-v2, Property 10: Verification status derivation rule
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(supporting=_ids, contradicting=_ids, current=_statuses)
def test_property_10_verification_status_contradicted_iff_rule(
    supporting: List[str],
    contradicting: List[str],
    current: VerificationStatus,
):
    """Property 10: derived status is CONTRADICTED iff contradicting is non-empty
    AND supporting is empty.

    Universally quantified over random supporting / contradicting id lists and the
    current status. The 'if' direction holds unconditionally; the 'only if'
    direction is expressed relative to ``current`` because the rule never overrides
    an already-CONTRADICTED state that the evidence does not re-derive.

    Validates: Requirements 3.6
    """
    result = derive_verification_status(supporting, contradicting, current)

    if contradicting and not supporting:
        # Contradiction with no corroboration always derives CONTRADICTED.
        assert result == VerificationStatus.CONTRADICTED
    else:
        # Otherwise the result is CONTRADICTED only if it already was.
        assert (result == VerificationStatus.CONTRADICTED) == (
            current == VerificationStatus.CONTRADICTED
        )


@settings(max_examples=100)
@given(supporting=st.lists(st.sampled_from(_ID_POOL), min_size=1, max_size=8), contradicting=_ids)
def test_property_10_supporting_promotes_unverified_to_verified(
    supporting: List[str],
    contradicting: List[str],
):
    """Property 10: adding a supporting observation to a previously UNVERIFIED
    belief yields VERIFIED.

    For any non-empty supporting list and any contradicting list, deriving from an
    UNVERIFIED state promotes the belief to VERIFIED (independent support confirms
    it; the CONTRADICTED branch cannot fire because supporting is non-empty).

    Validates: Requirements 3.3
    """
    result = derive_verification_status(
        supporting, contradicting, VerificationStatus.UNVERIFIED
    )
    assert result == VerificationStatus.VERIFIED


# --------------------------------------------------------------------------- #
# Property 12 — Derivation chain is an ordered DAG bounded to 20
# Feature: m15-world-model-v2, Property 12: Derivation chain is an ordered DAG bounded to 20
# --------------------------------------------------------------------------- #

# Adversarial parent chains: ids overlap with own_id (self-reference attempts),
# repeat across parents (duplicate attempts), and can individually exceed the
# MAX_DERIVATION_CHAIN bound (oversized ancestries).
_parent_chain = st.lists(st.sampled_from(_ID_POOL), max_size=25)
_parent_entry = st.tuples(_parent_chain, st.sampled_from(_ID_POOL))
_parent_chains_and_ids = st.lists(_parent_entry, max_size=6)


@settings(max_examples=200)
@given(
    parent_chains_and_ids=_parent_chains_and_ids,
    own_id=st.sampled_from(_ID_POOL),
)
def test_property_12_derivation_chain_ordered_dag_bounded(
    parent_chains_and_ids: List[Tuple[List[str], str]],
    own_id: str,
):
    """Property 12: the derived chain never contains own_id, has no duplicates,
    is bounded to MAX_DERIVATION_CHAIN, and preserves root-to-parent order.

    Inputs are adversarial by construction: parent chains draw from a small id pool
    shared with ``own_id`` (forcing self-reference attempts), repeat ids across
    parents (duplicate attempts), and can individually exceed 20 entries (oversized
    ancestries).

    Validates: Requirements 3.1, 3.2, 3.7, 3.8
    """
    result = build_derivation_chain(parent_chains_and_ids, own_id)

    # (Req 3.7) No self-reference: a belief is never in its own ancestry.
    assert own_id not in result

    # (Req 3.2) No cycles/duplicates: every id appears at most once.
    assert len(result) == len(set(result))

    # (Req 3.1, 3.8) Bounded to MAX_DERIVATION_CHAIN.
    assert len(result) <= MAX_DERIVATION_CHAIN

    # Flatten the raw input the same way the chain is built (each parent's chain
    # followed by its id), dropping own_id, to reason about first-seen order.
    raw = [
        belief_id
        for chain, parent_id in parent_chains_and_ids
        for belief_id in list(chain) + [parent_id]
        if belief_id != own_id
    ]
    first_index = {}
    for i, belief_id in enumerate(raw):
        first_index.setdefault(belief_id, i)

    # Every retained id came from the input.
    assert all(belief_id in first_index for belief_id in result)

    # (root -> immediate parent) order preserved: adjacent retained ids keep their
    # first-seen ordering from the flattened input.
    for earlier, later in zip(result, result[1:]):
        assert first_index[earlier] < first_index[later]


# --------------------------------------------------------------------------- #
# Property 11 — Observation add appends, mirrors legacy fields, updates status
# Feature: m15-world-model-v2, Property 11: Observation add appends, mirrors legacy fields, updates status
# --------------------------------------------------------------------------- #

# A belief generator spanning the provenance state space: pre-existing supporting /
# contradicting observation ids (mirrored into the legacy evidence lists so the
# starting point is internally consistent) and any starting verification_status.
_obs_ids = st.lists(st.sampled_from(_ID_POOL), max_size=5)


@st.composite
def _beliefs(draw) -> Belief:
    """Build a Belief with a randomized (but internally consistent) provenance.

    Domain-agnostic (Axiom 15): descriptions/sources are opaque synthetic strings.
    The legacy evidence lists are seeded to mirror the provenance observation lists
    so the starting belief matches the invariant the add-methods maintain.
    """
    supporting = draw(_obs_ids)
    contradicting = draw(_obs_ids)
    status = draw(_statuses)
    prov = BeliefProvenance(
        supporting_observations=list(supporting),
        contradicting_observations=list(contradicting),
        verification_status=status,
    )
    return Belief(
        description=draw(st.text(max_size=12)),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
        source=draw(st.sampled_from(["sensor_a", "sensor_b", "runtime"])),
        supporting_evidence=list(supporting),
        contradicting_evidence=list(contradicting),
        provenance=prov,
    )


@settings(max_examples=100)
@given(belief=_beliefs(), observation_id=st.sampled_from(_ID_POOL))
def test_property_11_add_supporting_observation_mirrors_and_updates_status(
    belief: Belief,
    observation_id: str,
):
    """Property 11: add_supporting_observation appends to BOTH provenance and legacy
    fields, follows the derivation rule, and never mutates the original.

    Validates: Requirements 3.4, 3.9
    """
    # Snapshot the original lists to prove non-mutation after the call.
    orig_supporting = list(belief.provenance.supporting_observations)
    orig_contradicting = list(belief.provenance.contradicting_observations)
    orig_legacy_supporting = list(belief.supporting_evidence)
    orig_legacy_contradicting = list(belief.contradicting_evidence)
    orig_status = belief.provenance.verification_status

    result = belief.add_supporting_observation(observation_id)

    # A NEW belief is returned; the original is untouched.
    assert result is not belief
    assert belief.provenance.supporting_observations == orig_supporting
    assert belief.provenance.contradicting_observations == orig_contradicting
    assert belief.supporting_evidence == orig_legacy_supporting
    assert belief.contradicting_evidence == orig_legacy_contradicting
    assert belief.provenance.verification_status == orig_status

    # (Req 3.9) The id is mirrored into BOTH provenance and legacy supporting lists.
    assert observation_id in result.provenance.supporting_observations
    assert observation_id in result.supporting_evidence
    # Append semantics: exactly the original plus the new id, in order.
    assert result.provenance.supporting_observations == orig_supporting + [observation_id]
    assert result.supporting_evidence == orig_legacy_supporting + [observation_id]
    # The contradicting side is carried through unchanged.
    assert result.provenance.contradicting_observations == orig_contradicting

    # (Req 3.3/3.6) verification_status follows the pure derivation rule.
    expected_status = derive_verification_status(
        result.provenance.supporting_observations,
        result.provenance.contradicting_observations,
        orig_status,
    )
    assert result.provenance.verification_status == expected_status

    # Support on an UNVERIFIED belief promotes it to VERIFIED (supporting is now
    # non-empty, so the CONTRADICTED branch cannot fire).
    if orig_status == VerificationStatus.UNVERIFIED:
        assert result.provenance.verification_status == VerificationStatus.VERIFIED


@settings(max_examples=100)
@given(belief=_beliefs(), observation_id=st.sampled_from(_ID_POOL))
def test_property_11_add_contradicting_observation_mirrors_and_updates_status(
    belief: Belief,
    observation_id: str,
):
    """Property 11: add_contradicting_observation appends to BOTH provenance and
    legacy fields, follows the derivation rule, and never mutates the original.

    Validates: Requirements 3.4, 3.9
    """
    orig_supporting = list(belief.provenance.supporting_observations)
    orig_contradicting = list(belief.provenance.contradicting_observations)
    orig_legacy_supporting = list(belief.supporting_evidence)
    orig_legacy_contradicting = list(belief.contradicting_evidence)
    orig_status = belief.provenance.verification_status

    result = belief.add_contradicting_observation(observation_id)

    # A NEW belief is returned; the original is untouched.
    assert result is not belief
    assert belief.provenance.supporting_observations == orig_supporting
    assert belief.provenance.contradicting_observations == orig_contradicting
    assert belief.supporting_evidence == orig_legacy_supporting
    assert belief.contradicting_evidence == orig_legacy_contradicting
    assert belief.provenance.verification_status == orig_status

    # (Req 3.4/3.9) The id is mirrored into BOTH provenance and legacy contradicting lists.
    assert observation_id in result.provenance.contradicting_observations
    assert observation_id in result.contradicting_evidence
    assert result.provenance.contradicting_observations == orig_contradicting + [observation_id]
    assert result.contradicting_evidence == orig_legacy_contradicting + [observation_id]
    # The supporting side is carried through unchanged.
    assert result.provenance.supporting_observations == orig_supporting

    # (Req 3.6) verification_status follows the pure derivation rule.
    expected_status = derive_verification_status(
        result.provenance.supporting_observations,
        result.provenance.contradicting_observations,
        orig_status,
    )
    assert result.provenance.verification_status == expected_status
