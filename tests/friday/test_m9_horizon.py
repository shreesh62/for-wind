"""Tests for friday.horizon.planner — LongHorizonPlanner roadmap operations (M9 task 6.2).

Covers the roadmap operations: define_project, next_actionable, advance (verification
gated), and revise_roadmap. Asserts the immutable Project.vision outcome (Axiom 1) is
never mutated across a roadmap revision while the milestone structure evolves.
"""

import json
import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.horizon.planner import (  # noqa: E402
    LongHorizonPlanner,
    Milestone,
    Project,
    RoadmapRevision,
)


def _project() -> Project:
    return Project(
        id="proj-1",
        vision="an immutable long-horizon outcome",
        milestones=(
            Milestone(id="m1", text="first"),
            Milestone(id="m2", text="second", prerequisites=("m1",)),
            Milestone(id="m3", text="third", prerequisites=("m2",)),
        ),
    )


def test_define_project_returns_id_and_registers() -> None:
    planner = LongHorizonPlanner()
    project_id = planner.define_project(_project())
    assert project_id == "proj-1"
    assert planner.next_actionable("proj-1") is not None


def test_next_actionable_returns_first_unblocked_milestone() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(_project())
    nxt = planner.next_actionable("proj-1")
    assert nxt is not None and nxt.id == "m1"


def test_next_actionable_respects_prerequisites() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(_project())
    # m1 not reached yet -> m2/m3 are blocked, m1 is actionable.
    planner.advance("proj-1", "m1", verified=True)
    nxt = planner.next_actionable("proj-1")
    assert nxt is not None and nxt.id == "m2"


def test_next_actionable_none_when_all_reached() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(_project())
    planner.advance("proj-1", "m1", verified=True)
    planner.advance("proj-1", "m2", verified=True)
    planner.advance("proj-1", "m3", verified=True)
    assert planner.next_actionable("proj-1") is None


def test_advance_only_marks_reached_when_verified() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(_project())
    # Verification point has not passed -> unchanged, milestone stays unreached.
    unchanged = planner.advance("proj-1", "m1", verified=False)
    assert all(not m.reached for m in unchanged.milestones)

    advanced = planner.advance("proj-1", "m1", verified=True)
    reached = {m.id for m in advanced.milestones if m.reached}
    assert reached == {"m1"}


def test_advance_builds_new_immutable_instances() -> None:
    planner = LongHorizonPlanner()
    original = _project()
    planner.define_project(original)
    advanced = planner.advance("proj-1", "m1", verified=True)
    # Original frozen instances are untouched.
    assert advanced is not original
    assert all(not m.reached for m in original.milestones)


def test_revise_roadmap_evolves_milestones_but_keeps_vision() -> None:
    planner = LongHorizonPlanner()
    original = _project()
    planner.define_project(original)

    revision = RoadmapRevision(
        add=(Milestone(id="m4", text="fourth", prerequisites=("m3",)),),
        remove=("m3",),
    )
    revised = planner.revise_roadmap("proj-1", revision)

    milestone_ids = [m.id for m in revised.milestones]
    # Milestone structure evolved: m3 dropped, m4 appended.
    assert "m3" not in milestone_ids
    assert "m4" in milestone_ids
    assert milestone_ids != [m.id for m in original.milestones]

    # The immutable vision outcome is unchanged (Axiom 1).
    assert revised.vision == original.vision == "an immutable long-horizon outcome"


# --- Task 6.6: checkpoint/restore persistence (Ch 42.6) ---------------------


def test_restore_from_truncated_state_defaults_to_empty_and_invents_nothing() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(_project())

    # Truncated / partial states must never raise and must never invent roadmaps,
    # goal ids, or milestones.
    for truncated in (
        {},
        {"projects": []},
        {"projects": None},
        {"projects": [{}]},  # entry missing an id -> skipped, not invented
        {"projects": [{"vision": "no id here"}]},
        None,
        "not a dict",
    ):
        planner.restore(truncated)  # type: ignore[arg-type]
        assert planner.checkpoint() == {"projects": []}
        assert planner.next_actionable("proj-1") is None


def test_full_checkpoint_restore_round_trips_goal_ids_states_and_milestones() -> None:
    planner = LongHorizonPlanner()
    planner.define_project(
        Project(
            id="proj-1",
            vision="an immutable long-horizon outcome",
            milestones=(
                Milestone(id="m1", text="first", goal_ids=("g1", "g2")),
                Milestone(id="m2", text="second", goal_ids=("g3",), prerequisites=("m1",)),
                Milestone(id="m3", text="third", prerequisites=("m2",)),
            ),
        )
    )
    planner.define_project(
        Project(id="proj-2", vision="another outcome", milestones=())
    )
    # Reach a milestone so reached-state must survive the round-trip.
    planner.advance("proj-1", "m1", verified=True)

    state = planner.checkpoint()

    # State is JSON-serializable and round-trips through JSON cleanly.
    assert json.loads(json.dumps(state)) == state

    restored = LongHorizonPlanner()
    restored.restore(state)

    # Identical checkpoint content after restore.
    assert restored.checkpoint() == state

    def _summary(p: LongHorizonPlanner) -> dict:
        out = {}
        for raw in p.checkpoint()["projects"]:
            out[raw["id"]] = {
                m["id"]: (tuple(m["goal_ids"]), m["reached"])
                for m in raw["milestones"]
            }
        return out

    # Identical goal ids, reached milestones across the restart boundary.
    assert _summary(restored) == _summary(planner)
    assert _summary(restored)["proj-1"]["m1"] == (("g1", "g2"), True)
    assert _summary(restored)["proj-1"]["m2"][1] is False

    # The immutable vision outcome also survives (Axiom 1).
    assert restored.next_actionable("proj-1").id == "m2"


# --- Task 6.4: kernel wiring (attach + emissions) ---------------------------

import fnmatch  # noqa: E402
from typing import Any, List, Tuple  # noqa: E402

from friday.events.event import Event, make_event  # noqa: E402


class _FakeKernel:
    """Minimal kernel double: records subscriptions and published events."""

    def __init__(self, tick: int = 0) -> None:
        self.published: List[Event] = []
        self.subscriptions: List[Tuple[str, Any]] = []
        self._tick = tick

    def subscribe(self, pattern: str, handler: Any) -> str:
        self.subscriptions.append((pattern, handler))
        return f"sub-{len(self.subscriptions)}"

    def publish_event(self, event: Event) -> None:
        self.published.append(event)
        for pattern, handler in list(self.subscriptions):
            if fnmatch.fnmatch(event.event_type, pattern):
                handler(event)

    def health(self) -> dict:
        return {"tick": self._tick}


def test_attach_subscribes_to_goal_and_checkpoint_events() -> None:
    planner = LongHorizonPlanner()
    kernel = _FakeKernel()
    planner.attach(kernel)

    patterns = {pattern for pattern, _ in kernel.subscriptions}
    assert patterns == {"goal.created", "goal.state_changed", "kernel.checkpoint"}


def test_advance_emits_milestone_reached_and_project_advanced() -> None:
    planner = LongHorizonPlanner()
    kernel = _FakeKernel(tick=7)
    planner.attach(kernel)
    planner.define_project(_project())

    planner.advance("proj-1", "m1", verified=True)

    reached = [e for e in kernel.published if e.event_type == "horizon.milestone_reached"]
    advanced = [e for e in kernel.published if e.event_type == "horizon.project_advanced"]
    assert len(reached) == 1 and len(advanced) == 1

    assert reached[0].source == "horizon"
    assert reached[0].payload["project_id"] == "proj-1"
    assert reached[0].payload["milestone_id"] == "m1"
    assert reached[0].payload["verified"] is True

    # next_actionable after reaching m1 is m2.
    assert advanced[0].source == "horizon"
    assert advanced[0].payload["project_id"] == "proj-1"
    assert advanced[0].payload["next_milestone_id"] == "m2"


def test_advance_project_advanced_next_is_none_when_all_reached() -> None:
    planner = LongHorizonPlanner()
    kernel = _FakeKernel()
    planner.attach(kernel)
    planner.define_project(_project())

    planner.advance("proj-1", "m1", verified=True)
    planner.advance("proj-1", "m2", verified=True)
    planner.advance("proj-1", "m3", verified=True)

    advanced = [e for e in kernel.published if e.event_type == "horizon.project_advanced"]
    # Last advance leaves no actionable milestone -> next_milestone_id is None.
    assert advanced[-1].payload["next_milestone_id"] is None


def test_advance_does_not_emit_when_not_verified() -> None:
    planner = LongHorizonPlanner()
    kernel = _FakeKernel()
    planner.attach(kernel)
    planner.define_project(_project())

    planner.advance("proj-1", "m1", verified=False)
    assert kernel.published == []


def test_advance_is_pure_operation_without_kernel() -> None:
    # No attach: advance still marks reached and never raises (pure operation).
    planner = LongHorizonPlanner()
    planner.define_project(_project())
    advanced = planner.advance("proj-1", "m1", verified=True)
    assert {m.id for m in advanced.milestones if m.reached} == {"m1"}


def test_handlers_never_raise_on_malformed_events() -> None:
    planner = LongHorizonPlanner()
    kernel = _FakeKernel()
    planner.attach(kernel)

    class _Bad:
        payload = None

    for _pattern, handler in kernel.subscriptions:
        handler(_Bad())  # must not raise
        handler(make_event("goal.created", "test", 1, payload={}))  # must not raise
