"""M4 tests — Deliberator decision records on the kernel event log."""

from friday.deliberation.candidate import CandidateAction
from friday.deliberation.deliberator import Deliberator
from friday.kernel.kernel import CognitiveKernel


def _candidate(desc, confidence, goal_id="g1"):
    return CandidateAction.build(desc, "capability", goal_id, ["done"], confidence=confidence)


def test_decision_chooses_highest_utility():
    deliberator = Deliberator()
    good = _candidate("good", 0.9)
    bad = _candidate("bad", 0.2)
    record = deliberator.decide("g1", [bad, good])
    assert record.chosen_id == good.id
    assert len(record.considered) == 2
    assert "good" in record.reason


def test_no_candidates_is_recorded_inaction():
    record = Deliberator().decide("g1", [])
    assert record.chosen_id is None
    assert record.reason == "no candidates generated"


def test_below_threshold_chooses_inaction():
    deliberator = Deliberator(min_utility=0.5)
    weak = _candidate("weak", 0.3)
    record = deliberator.decide("g1", [weak])
    assert record.chosen_id is None
    assert "inaction" in record.reason


def test_decisions_published_to_kernel_log(tmp_path):
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    deliberator = Deliberator()
    deliberator.attach(kernel)
    seen = []
    kernel.subscribe("deliberation.decision", seen.append)
    record = deliberator.decide("g1", [_candidate("act", 0.9)])
    assert len(seen) == 1
    assert seen[0].payload["decision_id"] == record.id
    assert seen[0].payload["chosen_id"] == record.chosen_id
    # Durable on the event log:
    types = [e.event_type for e in kernel._store.replay()]
    assert "deliberation.decision" in types


def test_decision_history_kept():
    deliberator = Deliberator()
    deliberator.decide("g1", [_candidate("a", 0.9)])
    deliberator.decide("g2", [_candidate("b", 0.9)])
    assert len(deliberator.decisions) == 2
