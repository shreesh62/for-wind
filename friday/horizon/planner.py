"""Ch 42 — Long-horizon planning data models: Vision > Mission > Project > Milestone > Goal.

Defines the immutable planning records that the ``LongHorizonPlanner`` (tasks
6.2–6.4) operates on. A ``Project`` carries an immutable ``vision`` outcome
(Axiom 1) and an ordered roadmap of ``Milestone`` verification points that may
be evolved through a ``RoadmapRevision`` (Ch 42.4) without ever mutating the
vision. The ``to_dict``/``from_dict`` pair mirrors the M3 ``Goal`` serialization
so roadmaps round-trip cleanly through JSON checkpoints (Ch 42.6).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from friday.events.event import make_event


class HorizonLevel(str, Enum):
    """The Ch 42 planning hierarchy, coarsest (vision) to finest (goal)."""

    VISION = "vision"
    MISSION = "mission"
    PROJECT = "project"
    MILESTONE = "milestone"
    GOAL = "goal"


@dataclass(frozen=True)
class Milestone:
    """A verification point on a roadmap.

    ``goal_ids`` are the M3 goals whose verified completion reaches this
    milestone; ``prerequisites`` are milestone ids that must complete first.
    Both are tuples for immutability.
    """

    id: str
    text: str
    goal_ids: Tuple[str, ...] = ()
    prerequisites: Tuple[str, ...] = ()
    reached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "goal_ids": list(self.goal_ids),
            "prerequisites": list(self.prerequisites),
            "reached": self.reached,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Milestone":
        return cls(
            id=data["id"],
            text=data.get("text", ""),
            goal_ids=tuple(data.get("goal_ids", ())),
            prerequisites=tuple(data.get("prerequisites", ())),
            reached=bool(data.get("reached", False)),
        )


@dataclass(frozen=True)
class Project:
    """A registered project: an immutable ``vision`` plus an ordered roadmap.

    The ``vision`` outcome is immutable (Axiom 1); only the ``milestones``
    structure/state evolves across revisions.
    """

    id: str
    vision: str
    milestones: Tuple[Milestone, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vision": self.vision,
            "milestones": [m.to_dict() for m in self.milestones],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        return cls(
            id=data["id"],
            vision=data.get("vision", ""),
            milestones=tuple(
                Milestone.from_dict(m) for m in data.get("milestones", ())
            ),
        )


@dataclass(frozen=True)
class RoadmapRevision:
    """A dynamic roadmap evolution (Ch 42.4).

    ``add`` appends new milestones; ``remove`` names milestone ids to drop. The
    ``Project.vision`` outcome is never touched by a revision.
    """

    add: Tuple[Milestone, ...] = ()
    remove: Tuple[str, ...] = ()


class LongHorizonPlanner:
    """Ch 42 — Vision>Mission>Project>Milestone>Goal; roadmaps that survive across sessions.

    Owns the Ch 42 planning hierarchy: registers ``Project`` roadmaps, surfaces the
    next actionable ``Milestone`` (the one whose prerequisites are all reached),
    advances milestones ONLY once their verification point passes, and evolves the
    roadmap through a ``RoadmapRevision`` without ever mutating the immutable
    ``Project.vision`` outcome (Axiom 1). ``Project``/``Milestone`` are frozen, so
    every mutation constructs new immutable instances via :func:`dataclasses.replace`.

    Kernel wiring (``attach`` + event emissions), checkpoint/restore persistence, and
    the M3 ``Goal`` outcome integration are layered on in tasks 6.3/6.4; this class
    keeps its roadmap store (``_projects``) open for those additions.
    """

    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}
        self._kernel: Any = None

    # Kernel wiring (Ch 52 — kernel-driven; task 6.4) ------------------------

    def attach(self, kernel: Any) -> None:
        """Subscribe to goal/checkpoint events (Ch 52 — kernel-driven).

        Mirrors the M8 ReflectionEngine attach pattern: stores the kernel and
        subscribes to ``goal.created`` and ``goal.state_changed`` (so the planner
        can react to the goals that back its milestones) plus ``kernel.checkpoint``
        (so roadmap state can be serialized at a session boundary). Emission of
        ``horizon.milestone_reached`` / ``horizon.project_advanced`` happens from
        :meth:`advance` once a milestone's verification point passes.
        """
        self._kernel = kernel
        kernel.subscribe("goal.created", self._on_goal_created)
        kernel.subscribe("goal.state_changed", self._on_goal_state_changed)
        kernel.subscribe("kernel.checkpoint", self._on_kernel_checkpoint)

    def _on_goal_created(self, event: Any) -> None:
        """React to ``goal.created`` (defensive, never raises into the tick loop).

        The planning hierarchy links milestones to M3 goals via ``goal_ids``; this
        handler reads the payload defensively and is a safe no-op when a goal is not
        associated with any registered roadmap. It never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            _ = payload.get("goal_id")
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_goal_state_changed(self, event: Any) -> None:
        """React to ``goal.state_changed`` (defensive, never raises).

        Reads the payload defensively; milestone advancement is driven through
        :meth:`advance` (verification gated), so this handler is a safe no-op when
        the goal is not tied to a roadmap milestone. It never raises.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            _ = payload.get("goal_id")
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_kernel_checkpoint(self, event: Any) -> None:
        """React to ``kernel.checkpoint`` by serializing roadmap state (Ch 42.6).

        Best-effort: computes :meth:`checkpoint` so roadmaps can survive across
        sessions. Kernel-side persistence is not required here — if the kernel does
        not expose a store hook this is a defensive no-op. Never raises into the
        tick loop.
        """
        try:
            _ = self.checkpoint()
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1

    def _emit_advance_events(self, project_id: str, milestone_id: str) -> None:
        """Publish ``horizon.milestone_reached`` / ``horizon.project_advanced``.

        Called from :meth:`advance` only after a milestone's verification point has
        passed AND a kernel is attached. Reads the next actionable milestone
        defensively (may be ``None``). Never raises into the tick loop.
        """
        if self._kernel is None:
            return
        try:
            reached_event = make_event(
                event_type="horizon.milestone_reached",
                source="horizon",
                logical_time=self._next_tick(),
                payload={
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "verified": True,
                },
            )
            self._kernel.publish_event(reached_event)

            nxt = self.next_actionable(project_id)
            next_milestone_id = nxt.id if nxt is not None else None
            advanced_event = make_event(
                event_type="horizon.project_advanced",
                source="horizon",
                logical_time=self._next_tick(),
                payload={
                    "project_id": project_id,
                    "next_milestone_id": next_milestone_id,
                },
            )
            self._kernel.publish_event(advanced_event)
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def define_project(self, project: Project) -> str:
        """Register a Project with its milestone roadmap; returns the project id."""
        self._projects[project.id] = project
        return project.id

    def next_actionable(self, project_id: str) -> Optional[Milestone]:
        """Return the next unreached milestone whose prerequisites are all reached.

        Prerequisites are milestone ids; a prerequisite counts as complete only when
        its milestone is reached. Returns ``None`` when no milestone is currently
        actionable (all reached, or every remaining one still blocked).
        """
        project = self._projects.get(project_id)
        if project is None:
            return None
        reached_ids = {m.id for m in project.milestones if m.reached}
        for milestone in project.milestones:
            if milestone.reached:
                continue
            if all(prereq in reached_ids for prereq in milestone.prerequisites):
                return milestone
        return None

    def advance(self, project_id: str, milestone_id: str, *, verified: bool = False) -> Project:
        """Mark a milestone reached ONLY after its verification point passes.

        The verification signal is modeled by the ``verified`` gate; the kernel-event
        wiring that derives it from verified experience is task 6.4. When ``verified``
        is falsey the roadmap is returned unchanged (the milestone stays unreached).
        Because ``Project``/``Milestone`` are frozen, the reached milestone and its
        owning project are rebuilt as new immutable instances. The immutable
        ``vision`` is preserved by :func:`dataclasses.replace`.
        """
        project = self._projects.get(project_id)
        if project is None:
            raise KeyError(f"unknown project_id: {project_id!r}")
        if not verified:
            return project
        updated_milestones = tuple(
            replace(m, reached=True) if m.id == milestone_id else m
            for m in project.milestones
        )
        if updated_milestones == project.milestones:
            raise KeyError(f"unknown milestone_id: {milestone_id!r}")
        advanced = replace(project, milestones=updated_milestones)
        self._projects[project_id] = advanced
        # Emit only when a milestone was actually marked reached AND a kernel is
        # attached; advance() stays a pure roadmap operation with no kernel.
        self._emit_advance_events(project_id, milestone_id)
        return advanced

    def revise_roadmap(self, project_id: str, revision: RoadmapRevision) -> Project:
        """Evolve the milestone roadmap (Ch 42.4) while keeping the vision unchanged.

        Applies the revision by dropping every milestone named in ``revision.remove``
        and appending ``revision.add``. The immutable ``Project.vision`` outcome is
        never touched (Axiom 1) and no Goal outcome is mutated — only roadmap
        structure evolves. Returns the new immutable ``Project``.
        """
        project = self._projects.get(project_id)
        if project is None:
            raise KeyError(f"unknown project_id: {project_id!r}")
        remove_ids = set(revision.remove)
        kept = tuple(m for m in project.milestones if m.id not in remove_ids)
        revised_milestones = kept + tuple(revision.add)
        revised = replace(project, milestones=revised_milestones)
        self._projects[project_id] = revised
        return revised

    # Persistence (Ch 42.6) — reuses Goal/Project/Milestone serialization -----

    def checkpoint(self) -> Dict[str, Any]:
        """Produce JSON-serializable roadmap state so goals survive across sessions.

        Serializes every registered ``Project`` (with its milestones and the goal
        ids each milestone references) via the existing ``Project.to_dict`` /
        ``Milestone.to_dict`` pair, mirroring the M3 ``Goal.to_dict`` semantics and
        the kernel checkpoint contract rather than re-inventing them. The returned
        dict round-trips cleanly through JSON and is consumed by :meth:`restore`.
        """
        return {"projects": [project.to_dict() for project in self._projects.values()]}

    def restore(self, state: Dict[str, Any]) -> None:
        """Rehydrate roadmaps from checkpoint state (Ch 42.6 — resume months later).

        Restores defensively: a missing/partial/truncated ``state`` yields empty
        roadmaps rather than an error, and no goal ids or milestones are ever
        invented — only what was explicitly serialized by :meth:`checkpoint` is
        rehydrated via ``Project.from_dict`` (which reuses ``Milestone.from_dict``).
        Entries lacking an ``id`` are skipped, since a project cannot be keyed or
        keyed goals reconstructed without one.
        """
        self._projects = {}
        if not isinstance(state, dict):
            return
        raw_projects = state.get("projects")
        if not isinstance(raw_projects, list):
            return
        for raw in raw_projects:
            if not isinstance(raw, dict) or "id" not in raw:
                # Never invent an id/roadmap from partial state; skip the entry.
                continue
            project = Project.from_dict(raw)
            self._projects[project.id] = project
