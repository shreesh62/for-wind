"""M4 tests — CandidateAction and PredictedOutcome."""

import dataclasses

import pytest

from friday.deliberation.candidate import CandidateAction, PredictedOutcome


def test_candidate_is_immutable():
    candidate = CandidateAction.build(
        "search for info", "search_web", "g1", ["info gathered"]
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.description = "other"


def test_every_candidate_has_a_prediction():
    """Axiom: observation precedes action; every action has a predicted outcome."""
    candidate = CandidateAction.build(
        "open the document", "open_file", "g1", ["document visible"], confidence=0.8
    )
    assert candidate.prediction.expected_beliefs == ("document visible",)
    assert candidate.prediction.confidence == 0.8


def test_prediction_confidence_clamped():
    assert PredictedOutcome(expected_beliefs=(), confidence=2.0).confidence == 1.0
    assert PredictedOutcome(expected_beliefs=(), confidence=-1.0).confidence == 0.0
