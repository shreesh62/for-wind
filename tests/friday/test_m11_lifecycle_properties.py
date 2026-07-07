"""M11 — Property tests for the capability lifecycle and rollback manager.

Exercises ``friday/evolution/lifecycle.py`` and ``friday/evolution/rollback.py``:
- Property 1: ``transition`` succeeds iff ``can_transition(frm, to)``; an illegal
  transition raises ``ValueError`` and leaves ``state_of`` unchanged. The forward
  path DRAFT -> EXPERIMENTAL -> VERIFIED -> STABLE all succeed in order.
- Property 2: an unverified capability (DRAFT/EXPERIMENTAL) is never usable for an
  irreversible action; only VERIFIED and STABLE are.
- Property 6: after ``record_stable(id, A)`` a ``rollback(id)`` returns A; with no
  snapshot ``can_rollback`` is False and ``rollback`` raises ``LookupError``.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green.

Validates: Requirements 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest
from hypothesis import given, settings, strategies as st

from friday.evolution.lifecycle import CapabilityLifecycle, LifecycleState
from friday.evolution.rollback import RollbackManager


# --------------------------------------------------------------------------- #
# Helpers — reach a target state via legal transitions on a fresh lifecycle.
# --------------------------------------------------------------------------- #
_PATHS = {
    LifecycleState.DRAFT: [],
    LifecycleState.EXPERIMENTAL: [LifecycleState.EXPERIMENTAL],
    LifecycleState.VERIFIED: [LifecycleState.EXPERIMENTAL, LifecycleState.VERIFIED],
    LifecycleState.STABLE: [
        LifecycleState.EXPERIMENTAL,
        LifecycleState.VERIFIED,
        LifecycleState.STABLE,
    ],
    LifecycleState.DEPRECATED: [LifecycleState.DEPRECATED],
    LifecycleState.ARCHIVED: [LifecycleState.DEPRECATED, LifecycleState.ARCHIVED],
}


def _lifecycle_in(state: LifecycleState):
    """Return a lifecycle with capability 'c' driven to ``state`` legally."""
    lc = CapabilityLifecycle()
    for step in _PATHS[state]:
        lc.transition("c", step)
    assert lc.state_of("c") == state
    return lc


_states = st.sampled_from(list(LifecycleState))


# --------------------------------------------------------------------------- #
# Property 1: Lifecycle transitions are legal-only
# --------------------------------------------------------------------------- #
@given(frm=_states, to=_states)
@settings(max_examples=100)
def test_property1_transition_legal_only(frm, to):
    """transition succeeds iff can_transition; illegal raises and preserves state."""
    lc = _lifecycle_in(frm)
    legal = lc.can_transition(frm, to)

    if legal:
        assert lc.transition("c", to) == to
        assert lc.state_of("c") == to
    else:
        with pytest.raises(ValueError):
            lc.transition("c", to)
        assert lc.state_of("c") == frm


def test_property1_forward_path_succeeds_in_order():
    """DRAFT -> EXPERIMENTAL -> VERIFIED -> STABLE all succeed on a fresh lifecycle."""
    lc = CapabilityLifecycle()
    assert lc.state_of("c") == LifecycleState.DRAFT
    for nxt in (
        LifecycleState.EXPERIMENTAL,
        LifecycleState.VERIFIED,
        LifecycleState.STABLE,
    ):
        assert lc.transition("c", nxt) == nxt
    assert lc.state_of("c") == LifecycleState.STABLE


# --------------------------------------------------------------------------- #
# Property 2: Unverified capabilities cannot perform irreversible actions
# --------------------------------------------------------------------------- #
@given(state=_states)
@settings(max_examples=50)
def test_property2_irreversible_only_verified_or_stable(state):
    """is_usable_for(id, 'irreversible') is True only for VERIFIED and STABLE."""
    lc = _lifecycle_in(state)
    usable = lc.is_usable_for("c", "irreversible")
    if state in (LifecycleState.VERIFIED, LifecycleState.STABLE):
        assert usable is True
    else:
        assert usable is False


# --------------------------------------------------------------------------- #
# Property 6: Rollback restores the last-known-good snapshot
# --------------------------------------------------------------------------- #
@given(snapshot=st.integers() | st.text() | st.tuples(st.integers()))
@settings(max_examples=50)
def test_property6_rollback_restores_recorded_snapshot(snapshot):
    """record_stable then rollback returns the exact snapshot."""
    mgr = RollbackManager()
    mgr.record_stable("cap.a", snapshot)
    assert mgr.can_rollback("cap.a") is True
    assert mgr.rollback("cap.a") == snapshot


def test_property6_no_snapshot_cannot_rollback_and_raises():
    """With no recorded snapshot, can_rollback is False and rollback raises."""
    mgr = RollbackManager()
    assert mgr.can_rollback("cap.missing") is False
    with pytest.raises(LookupError):
        mgr.rollback("cap.missing")
