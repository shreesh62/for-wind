"""M3 tests — GoalGraph decomposition, dependencies, readiness."""

import pytest

from friday.goals.goal import Goal, GoalState
from friday.goals.graph import GoalGraph


def _active(text, **kw):
    goal = Goal(text, **kw)
    goal.activate()
    return goal


def test_add_and_get():
    graph = GoalGraph()
    goal = Goal("root")
    graph.add(goal)
    assert graph.get(goal.id) is goal
    assert len(graph) == 1
    with pytest.raises(ValueError):
        graph.add(goal)


def test_children_require_known_parent():
    graph = GoalGraph()
    with pytest.raises(ValueError):
        graph.add(Goal("orphan", parent_id="missing"))


def test_decomposition_tracking():
    graph = GoalGraph()
    root = Goal("root")
    graph.add(root)
    child_a = _active("a", parent_id=root.id)
    child_b = _active("b", parent_id=root.id)
    graph.add(child_a)
    graph.add(child_b)
    assert {c.id for c in graph.children(root.id)} == {child_a.id, child_b.id}
    assert not graph.decomposition_complete(root.id)
    child_a.complete()
    child_b.complete()
    assert graph.decomposition_complete(root.id)


def test_ready_respects_dependencies():
    graph = GoalGraph()
    first = _active("first")
    second = _active("second")
    graph.add(first)
    graph.add(second)
    graph.add_dependency(second.id, first.id)
    assert {g.id for g in graph.ready()} == {first.id}
    first.complete()
    assert {g.id for g in graph.ready()} == {second.id}


def test_dependency_cycle_rejected():
    graph = GoalGraph()
    a, b, c = Goal("a"), Goal("b"), Goal("c")
    for g in (a, b, c):
        graph.add(g)
    graph.add_dependency(b.id, a.id)
    graph.add_dependency(c.id, b.id)
    with pytest.raises(ValueError):
        graph.add_dependency(a.id, c.id)


def test_suspended_goals_not_ready():
    graph = GoalGraph()
    goal = _active("g")
    graph.add(goal)
    goal.suspend()
    assert graph.ready() == []


def test_roots():
    graph = GoalGraph()
    root = Goal("root")
    graph.add(root)
    graph.add(Goal("child", parent_id=root.id))
    assert [g.id for g in graph.roots()] == [root.id]


def test_graph_serialization_roundtrip():
    graph = GoalGraph()
    root = Goal("root")
    graph.add(root)
    child = _active("child", parent_id=root.id)
    graph.add(child)
    dep = Goal("dep")
    graph.add(dep)
    graph.add_dependency(child.id, dep.id)

    restored = GoalGraph.from_dict(graph.to_dict())
    assert len(restored) == 3
    assert restored.get(child.id).state is GoalState.ACTIVE
    assert {c.id for c in restored.children(root.id)} == {child.id}
    dep_restored = restored.get(dep.id)
    assert {g.id for g in restored.ready()} >= {dep_restored.id}
