"""Operator ↔ memory wiring.

The Operator ran the full goal pipeline without touching memory at all, so the
agent had no continuity between tasks: preferences and prior facts were re-derived
every run and completed goals were never recorded. These tests pin the two seams
(recall before planning, record after) and the fail-safe behavior.
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import tempfile

import pytest

from friday.operator import Operator


class _FakeContext:
    def __init__(self, text):
        self._text = text

    def to_prompt_string(self, max_length: int = 2000):
        return self._text[:max_length]


class _FakeMemory:
    """Duck-typed stand-in recording how the Operator used it."""

    def __init__(self, context_text="user prefers markdown output", explode=False):
        self._context_text = context_text
        self._explode = explode
        self.context_queries = []
        self.active_goals = []
        self.episodes = []
        self.completed = 0

    def get_context(self, query=""):
        if self._explode:
            raise RuntimeError("memory backend down")
        self.context_queries.append(query)
        return _FakeContext(self._context_text)

    def set_active_goal(self, text, steps=0):
        self.active_goals.append(text)

    def record_episode(self, episode):
        self.episodes.append(episode)

    def complete_goal(self):
        self.completed += 1


def _operator(memory=None):
    # No model_router: discovery/planning use their deterministic fallbacks, so the
    # test exercises the wiring without any network call.
    return Operator(model_router=None, max_iterations=1, memory=memory)


# --------------------------------------------------------------------------- #
# Recall
# --------------------------------------------------------------------------- #
def test_operator_recalls_context_for_the_goal():
    memory = _FakeMemory()
    outcome = _operator(memory).run("write a short note")
    assert memory.context_queries == ["write a short note"]
    assert any("Recalled" in line for line in outcome.trace)


def test_operator_marks_the_goal_active():
    memory = _FakeMemory()
    _operator(memory).run("write a short note")
    assert memory.active_goals == ["write a short note"]


def test_recall_failure_degrades_instead_of_failing_the_goal():
    memory = _FakeMemory(explode=True)
    outcome = _operator(memory).run("write a short note")
    # The goal still ran; memory is advisory.
    assert outcome.goal == "write a short note"
    assert any("No memory context" in line for line in outcome.trace)


def test_operator_without_memory_still_works():
    outcome = _operator(None).run("write a short note")
    assert outcome.goal == "write a short note"
    assert any("No memory context" in line for line in outcome.trace)


def test_recalled_context_reaches_requirements_discovery():
    """Recall is useless if it never gets to the reasoning steps."""
    seen = {}

    class _RecordingOperator(Operator):
        def __init__(self, memory):
            super().__init__(model_router=None, max_iterations=1, memory=memory)
            original = self._discovery.discover

            def _spy(goal, memory_context="", *a, **kw):
                seen["discovery"] = memory_context
                return original(goal, memory_context)

            self._discovery.discover = _spy

    _RecordingOperator(_FakeMemory("prefers markdown")).run("write a note")
    assert "prefers markdown" in seen.get("discovery", "")


def test_recalled_context_reaches_the_planner():
    seen = {}

    class _RecordingOperator(Operator):
        def __init__(self, memory):
            super().__init__(model_router=None, max_iterations=1, memory=memory)
            original = self._planner.plan

            def _spy(goal_text, env_state=None, memory_context="", *a, **kw):
                seen["planner"] = memory_context
                return original(goal_text, env_state, memory_context)

            self._planner.plan = _spy

    _RecordingOperator(_FakeMemory("prefers markdown")).run("write a note")
    assert "prefers markdown" in seen.get("planner", "")


# --------------------------------------------------------------------------- #
# Record
# --------------------------------------------------------------------------- #
def test_operator_records_the_outcome():
    memory = _FakeMemory()
    outcome = _operator(memory).run("write a short note")
    assert len(memory.episodes) == 1
    episode = memory.episodes[0]
    assert episode["goal"] == "write a short note"
    assert episode["completed"] == outcome.completed


def test_recording_failure_does_not_fail_the_goal():
    class _BadRecorder(_FakeMemory):
        def record_episode(self, episode):
            raise RuntimeError("disk full")

    outcome = _operator(_BadRecorder()).run("write a short note")
    assert outcome.goal == "write a short note"


# --------------------------------------------------------------------------- #
# FridayMemory provides a real recording path
# --------------------------------------------------------------------------- #
def test_friday_memory_records_a_goal_episode():
    from friday.memory import FridayMemory

    with tempfile.TemporaryDirectory() as data_dir:
        memory = FridayMemory(data_dir=data_dir)
        assert memory.episodic.total_episodes == 0
        memory.record_episode({
            "goal": "research something",
            "summary": "done",
            "completed": True,
            "created_files": ["out.txt"],
        })
        assert memory.episodic.total_episodes == 1
        episode = memory.episodic.recent(5)[0]
        assert episode.user_text == "research something"
        assert episode.action_success is True
        assert "out.txt" in episode.assistant_response


def test_operator_records_into_real_friday_memory():
    """End-to-end: the production memory object is a valid Operator collaborator."""
    from friday.memory import FridayMemory

    with tempfile.TemporaryDirectory() as data_dir:
        memory = FridayMemory(data_dir=data_dir)
        before = memory.episodic.total_episodes
        _operator(memory).run("write a short note")
        assert memory.episodic.total_episodes == before + 1
        assert memory.episodic.recent(1)[0].user_text == "write a short note"


def test_a_recorded_goal_is_recallable_by_the_next_run():
    """Continuity: the whole point is that goal N+1 can see goal N."""
    from friday.memory import FridayMemory

    with tempfile.TemporaryDirectory() as data_dir:
        memory = FridayMemory(data_dir=data_dir)
        _operator(memory).run("research quantum computing")
        context = memory.get_context("quantum computing").to_prompt_string()
        assert "quantum" in context.lower(), (
            f"prior goal not visible in recalled context: {context[:200]!r}"
        )
