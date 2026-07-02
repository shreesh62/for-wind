"""M2 tests — Belief confidence, decay, reinforcement, contradiction."""

import time

from hypothesis import given, strategies as st

from friday.world.belief import Belief


def test_decay_reduces_confidence_over_time():
    """M2 criterion: belief confidence < 1.0 after 10s of decay."""
    belief = Belief(description="x", confidence=1.0, source="test")
    decayed = belief.decay(rate=0.01, now=belief.observed_at + 10.0)
    assert decayed.confidence < 1.0
    assert abs(decayed.confidence - 0.9) < 1e-6


def test_decay_never_negative():
    belief = Belief(description="x", confidence=0.1, source="test")
    decayed = belief.decay(rate=1.0, now=belief.observed_at + 100.0)
    assert decayed.confidence == 0.0


def test_decay_returns_new_belief():
    belief = Belief(description="x", confidence=1.0, source="test")
    decayed = belief.decay(rate=0.01, now=belief.observed_at + 5.0)
    assert belief.confidence == 1.0
    assert decayed is not belief


def test_reinforce_raises_confidence():
    belief = Belief(description="x", confidence=0.6, source="a")
    stronger = belief.reinforce(0.6, evidence_id="e1")
    assert stronger.confidence > belief.confidence
    assert "e1" in stronger.supporting_evidence


def test_contradict_lowers_confidence():
    """M2 criterion: contradictory observations lower confidence, not raise it."""
    belief = Belief(description="x", confidence=0.9, source="a")
    weaker = belief.contradict(0.8, evidence_id="e2")
    assert weaker.confidence < belief.confidence
    assert "e2" in weaker.contradicting_evidence


def test_expiry():
    belief = Belief(
        description="x", confidence=1.0, source="a", expires_at=time.time() - 1
    )
    assert belief.expired


def test_confidence_clamped():
    assert Belief(description="x", confidence=5.0, source="a").confidence == 1.0
    assert Belief(description="x", confidence=-1.0, source="a").confidence == 0.0


@given(
    conf=st.floats(min_value=0.0, max_value=1.0),
    other=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_reinforce_never_lowers_and_contradict_never_raises(conf, other):
    belief = Belief(description="x", confidence=conf, source="a")
    assert belief.reinforce(other).confidence >= conf - 1e-9
    assert belief.contradict(other).confidence <= conf + 1e-9
