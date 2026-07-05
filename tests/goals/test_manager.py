"""M3 tests — GoalManager wired to the kernel event log."""

from friday.goals.goal import GoalState
from friday.goals.manager import GoalManager
from friday.kernel.kernel import CognitiveKernel


def _wired(tmp_path):
    kernel = CognitiveKernel(store_path=str(tmp_path / "s.jsonl"))
    manager = GoalManager()
    manager.attach(kernel)
    return kernel, manager


def test_kernel_goal_mirrors_into_graph(tmp_path):
    kernel, manager = _wired(tmp_path)
    goal_id = kernel.submit_goal("write the report")
    goal = manager.graph.get(goal_id)
    assert goal is not None
    assert goal.text == "write the report"
    assert goal.state is GoalState.CREATED


def test_decompose_publishes_events(tmp_path):
    kernel, manager = _wired(tmp_path)
    seen = []
    kernel.subscribe("goal.decomposed", seen.append)
    goal_id = kernel.submit_goal("plan a trip")
    child_ids = manager.decompose(goal_id, ["book flights", "book hotel"])
    assert len(child_ids) == 2
    assert len(seen) == 2
    assert {e.payload["parent_id"] for e in seen} == {goal_id}


def test_state_changes_are_on_event_log(tmp_path):
    kernel, manager = _wired(tmp_path)
    seen = []
    kernel.subscribe("goal.state_changed", seen.append)
    goal_id = kernel.submit_goal("g")
    manager.set_state(goal_id, GoalState.ACTIVE)
    manager.set_state(goal_id, GoalState.COMPLETED)
    assert [e.payload["state"] for e in seen] == ["active", "completed"]
    # And the events are durable in the store:
    types = [e.event_type for e in kernel._store.replay()]
    assert types.count("goal.state_changed") == 2


def test_parent_auto_completes_when_children_done(tmp_path):
    kernel, manager = _wired(tmp_path)
    parent_id = kernel.submit_goal("parent")
    child_ids = manager.decompose(parent_id, ["a", "b"])
    for child_id in child_ids:
        manager.set_state(child_id, GoalState.ACTIVE)
        manager.set_state(child_id, GoalState.COMPLETED)
    assert manager.graph.get(parent_id).state is GoalState.COMPLETED


def test_checkpoint_restore_roundtrip(tmp_path):
    kernel, manager = _wired(tmp_path)
    goal_id = kernel.submit_goal("persist me")
    manager.set_state(goal_id, GoalState.ACTIVE)
    state = manager.checkpoint()

    fresh = GoalManager()
    fresh.restore(state)
    restored = fresh.graph.get(goal_id)
    assert restored is not None
    assert restored.state is GoalState.ACTIVE
