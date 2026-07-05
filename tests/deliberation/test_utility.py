"""M4 tests — UtilityFunction scoring and ranking."""

from hypothesis import given, strategies as st

from friday.deliberation.candidate import CandidateAction, PredictedOutcome
from friday.deliberation.utility import UtilityFunction


def _candidate(confidence=0.8, value=1.0, cost=0.1, risk=0.0, reversible=True, desc="c"):
    return CandidateAction(
        description=desc,
        capability="capability",
        goal_id="g1",
        prediction=PredictedOutcome(
            expected_beliefs=("done",), confidence=confidence, reversible=reversible
        ),
        expected_value=value,
        cost=cost,
        risk=risk,
    )


def test_higher_confidence_wins():
    utility = UtilityFunction()
    sure = _candidate(confidence=0.9, desc="sure")
    risky = _candidate(confidence=0.3, desc="unsure")
    assert utility.best([risky, sure]).description == "sure"


def test_risk_and_cost_penalized():
    utility = UtilityFunction()
    cheap_safe = _candidate(cost=0.1, risk=0.0, desc="safe")
    costly_risky = _candidate(cost=0.5, risk=0.4, desc="risky")
    assert utility.best([costly_risky, cheap_safe]).description == "safe"


def test_irreversible_actions_penalized():
    utility = UtilityFunction()
    reversible = _candidate(confidence=0.6, desc="undoable")
    irreversible = _candidate(confidence=0.8, reversible=False, desc="permanent")
    assert utility.best([irreversible, reversible]).description == "undoable"


def test_best_returns_none_below_threshold():
    utility = UtilityFunction()
    hopeless = _candidate(confidence=0.1, value=0.5, cost=0.5, risk=0.5)
    assert utility.best([hopeless], min_utility=0.0) is None


def test_rank_orders_descending():
    utility = UtilityFunction()
    ranked = utility.rank(
        [_candidate(confidence=c, desc=str(c)) for c in (0.2, 0.9, 0.5)]
    )
    scores = [u for _, u in ranked]
    assert scores == sorted(scores, reverse=True)


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0),
    cost=st.floats(min_value=0.0, max_value=1.0),
    risk=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_utility_bounded(confidence, cost, risk):
    utility = UtilityFunction()
    score = utility.score(_candidate(confidence=confidence, cost=cost, risk=risk))
    assert -2.0 <= score <= 1.0
