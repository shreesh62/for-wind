"""M5 tests — IntentAnalyzer wired to the kernel event log."""

from friday.intent.analyzer import IntentAnalyzer
from friday.intent.classifier import ProblemClass
from friday.kernel.kernel import CognitiveKernel


def _wired(tmp_path):
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    analyzer = IntentAnalyzer()
    analyzer.attach(kernel)
    return kernel, analyzer


def test_goal_creation_produces_intent_and_classification(tmp_path):
    kernel, analyzer = _wired(tmp_path)
    goal_id = kernel.submit_goal("research the best flight prices")
    result = analyzer.for_goal(goal_id)
    assert result is not None
    intent, classification = result
    assert intent.objective == "research the best flight prices"
    assert classification.primary is ProblemClass.INFORMATION_GATHERING


def test_events_published_with_causal_chain(tmp_path):
    kernel, analyzer = _wired(tmp_path)
    seen = {}
    kernel.subscribe("intent.analyzed", lambda e: seen.setdefault("intent", e))
    kernel.subscribe("goal.classified", lambda e: seen.setdefault("classified", e))
    goal_id = kernel.submit_goal("email the notes to sam")
    assert seen["intent"].payload["goal_id"] == goal_id
    assert seen["classified"].payload["primary"] == "communication"
    # Causality: both trace back to the goal.created event.
    goal_events = [e for e in kernel._store.replay() if e.event_type == "goal.created"]
    assert seen["intent"].parent_id == goal_events[0].id
    assert seen["intent"].correlation_id == goal_events[0].correlation_id


def test_vague_goal_flags_clarification(tmp_path):
    kernel, analyzer = _wired(tmp_path)
    goal_id = kernel.submit_goal("do something about the files")
    intent, _ = analyzer.for_goal(goal_id)
    assert intent.requires_clarification
    assert intent.clarification_questions


def test_complexity_scales_with_structure():
    analyzer = IntentAnalyzer()
    simple = analyzer.analyze("open notepad")
    compound = analyzer.analyze(
        "research prices and write a summary then email it to the team"
    )
    assert compound.complexity > simple.complexity


def test_whitespace_normalized():
    intent = IntentAnalyzer().analyze("  open   the\tfile  ")
    assert intent.objective == "open the file"
