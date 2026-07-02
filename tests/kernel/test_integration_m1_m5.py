"""End-to-end integration — one goal flowing through M1-M5 subsystems.

goal.created -> IntentAnalyzer (intent.analyzed, goal.classified)
             -> GoalManager (graph)
             -> Deliberator (deliberation.decision)
All on the kernel's durable event log, with the kernel as the only coupling.
"""

from friday.deliberation.candidate import CandidateAction
from friday.deliberation.deliberator import Deliberator
from friday.goals.goal import GoalState
from friday.goals.manager import GoalManager
from friday.intent.analyzer import IntentAnalyzer
from friday.intent.classifier import ProblemClass
from friday.kernel.kernel import CognitiveKernel


def test_goal_flows_through_all_subsystems(tmp_path):
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    analyzer = IntentAnalyzer()
    manager = GoalManager()
    deliberator = Deliberator()
    analyzer.attach(kernel)
    manager.attach(kernel)
    deliberator.attach(kernel)

    goal_id = kernel.submit_goal("research flight prices and email the summary")

    # Intent + classification produced.
    intent, classification = analyzer.for_goal(goal_id)
    assert classification.primary in (
        ProblemClass.INFORMATION_GATHERING,
        ProblemClass.COMMUNICATION,
    )
    assert intent.complexity > 0

    # Goal mirrored into the graph and ready.
    goal = manager.graph.get(goal_id)
    assert goal is not None
    assert goal in manager.ready_goals()

    # Deliberation over candidates derived from the classification.
    candidates = [
        CandidateAction.build(
            "gather flight prices", "search_web", goal_id,
            ["flight prices known"], confidence=0.8,
        ),
        CandidateAction.build(
            "guess prices from memory", "recall", goal_id,
            ["flight prices known"], confidence=0.2,
        ),
    ]
    record = deliberator.decide(goal_id, candidates)
    assert record.chosen_id == candidates[0].id

    # Complete the goal; everything is durable on one event log.
    manager.set_state(goal_id, GoalState.ACTIVE)
    manager.set_state(goal_id, GoalState.COMPLETED)
    types = {e.event_type for e in kernel._store.replay()}
    assert {
        "goal.created",
        "intent.analyzed",
        "goal.classified",
        "deliberation.decision",
        "goal.state_changed",
    } <= types
