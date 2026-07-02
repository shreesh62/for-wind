"""M3 tests — Goal immutability and lifecycle state machine."""

import pytest

from friday.goals.goal import Goal, GoalState, IllegalTransition


def test_goal_text_immutable():
    """Axiom: goals are immutable; strategies are disposable."""
    goal = Goal("send the report")
    with pytest.raises(AttributeError):
        goal.text = "different goal"
    with pytest.raises(AttributeError):
        goal.id = "other"


def test_constraints_copy_not_shared():
    goal = Goal("g", constraints={"deadline": "friday"})
    goal.constraints["deadline"] = "never"
    assert goal.constraints == {"deadline": "friday"}


def test_happy_path_lifecycle():
    goal = Goal("g")
    assert goal.state is GoalState.CREATED
    goal.activate()
    goal.suspend()
    goal.resume()
    goal.block()
    goal.resume()
    goal.complete()
    assert goal.state is GoalState.COMPLETED
    assert goal.terminal
    assert len(goal.history) == 6


def test_illegal_transitions_rejected():
    goal = Goal("g")
    with pytest.raises(IllegalTransition):
        goal.complete()  # created -> completed is illegal
    goal.activate()
    goal.complete()
    with pytest.raises(IllegalTransition):
        goal.activate()  # terminal states are final


def test_failure_records_reason():
    goal = Goal("g")
    goal.activate()
    goal.fail(reason="element not found")
    assert goal.state is GoalState.FAILED
    assert goal.failure_reason == "element not found"


def test_serialization_roundtrip():
    goal = Goal("g", constraints={"k": 1}, parent_id="p1")
    goal.activate()
    goal.suspend()
    restored = Goal.from_dict(goal.to_dict())
    assert restored.id == goal.id
    assert restored.text == goal.text
    assert restored.constraints == {"k": 1}
    assert restored.parent_id == "p1"
    assert restored.state is GoalState.SUSPENDED
    assert restored.history == goal.history
