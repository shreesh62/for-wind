"""Tests for friday.memory — multi-tier memory system."""

import os
import tempfile
import time
import pytest

from friday.memory.interfaces import MemoryEntry, MemoryTier
from friday.memory.stores import JSONFileStore
from friday.memory.working import WorkingMemory, ActiveGoal
from friday.memory.episodic import EpisodicMemory, Episode
from friday.memory.procedural import ProceduralMemory, ActionPattern, RepairOutcome
from friday.memory.controller import FridayMemory


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestJSONFileStore:
    """Test the JSON file-backed store."""

    def test_store_and_retrieve(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/test.json")
        entry = MemoryEntry(
            content="Python is a programming language",
            tier=MemoryTier.SEMANTIC,
            tags=["programming"],
        )
        entry_id = store.store(entry)

        results = store.retrieve("python programming")
        assert len(results) >= 1
        assert "Python" in results[0].content

    def test_retrieve_by_relevance(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/test.json")
        store.store(MemoryEntry(content="cats are cute animals", tier=MemoryTier.SEMANTIC))
        store.store(MemoryEntry(content="python is a snake", tier=MemoryTier.SEMANTIC))
        store.store(MemoryEntry(content="python programming language", tier=MemoryTier.SEMANTIC))

        results = store.retrieve("python", top_k=2)
        assert len(results) == 2
        assert all("python" in r.content.lower() for r in results)

    def test_delete(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/test.json")
        entry_id = store.store(MemoryEntry(content="deleteme", tier=MemoryTier.WORKING))

        assert store.count() == 1
        assert store.delete(entry_id) is True
        assert store.count() == 0

    def test_list_recent(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/test.json")
        store.store(MemoryEntry(content="first", tier=MemoryTier.EPISODIC, timestamp=1.0))
        store.store(MemoryEntry(content="second", tier=MemoryTier.EPISODIC, timestamp=2.0))
        store.store(MemoryEntry(content="third", tier=MemoryTier.EPISODIC, timestamp=3.0))

        recent = store.list_recent(limit=2)
        assert len(recent) == 2
        assert recent[0].content == "third"

    def test_persistence(self, tmp_dir):
        path = f"{tmp_dir}/persist.json"
        store1 = JSONFileStore(path)
        store1.store(MemoryEntry(content="persist this", tier=MemoryTier.SEMANTIC))

        # New instance should load from file
        store2 = JSONFileStore(path)
        assert store2.count() == 1
        results = store2.retrieve("persist")
        assert len(results) == 1

    def test_bounded_growth(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/bounded.json", max_entries=5)
        for i in range(10):
            store.store(MemoryEntry(content=f"entry {i}", tier=MemoryTier.WORKING))

        assert store.count() == 5  # Oldest pruned

    def test_expired_entries_excluded(self, tmp_dir):
        store = JSONFileStore(f"{tmp_dir}/expire.json")
        store.store(MemoryEntry(
            content="expired", tier=MemoryTier.WORKING,
            expires_at=time.time() - 100,  # Already expired
        ))
        store.store(MemoryEntry(content="valid", tier=MemoryTier.WORKING))

        results = store.retrieve("expired")
        assert len(results) == 0  # Expired entries excluded


class TestWorkingMemory:
    """Test volatile working memory."""

    def test_add_turn(self):
        wm = WorkingMemory()
        wm.add_turn("hello", "hi there")
        assert wm.turn_count == 1

    def test_max_turns(self):
        wm = WorkingMemory(max_turns=3)
        for i in range(5):
            wm.add_turn(f"msg {i}", f"resp {i}")
        assert wm.turn_count == 3

    def test_active_goal(self):
        wm = WorkingMemory()
        wm.set_goal(ActiveGoal(text="Open Chrome", steps_total=2))
        assert wm.active_goal is not None
        assert wm.active_goal.text == "Open Chrome"

    def test_context_for_llm(self):
        wm = WorkingMemory()
        wm.add_turn("What is Python?", "Python is a language.")
        wm.set_goal(ActiveGoal(text="Research task"))

        ctx = wm.get_context_for_llm()
        assert "Python" in ctx
        assert "Research" in ctx

    def test_reset(self):
        wm = WorkingMemory()
        wm.add_turn("test", "test")
        wm.set_goal(ActiveGoal(text="goal"))
        wm.reset()
        assert wm.turn_count == 0
        assert wm.active_goal is None


class TestEpisodicMemory:
    """Test persistent episodic memory."""

    def test_record_and_recall(self, tmp_dir):
        em = EpisodicMemory(f"{tmp_dir}/episodic.json")
        em.record(Episode(
            user_text="Open Chrome",
            assistant_response="Chrome opened.",
            mode="friday",
            action_success=True,
        ))

        results = em.recall("chrome")
        assert len(results) >= 1
        assert "Chrome" in results[0].user_text

    def test_recent(self, tmp_dir):
        em = EpisodicMemory(f"{tmp_dir}/episodic.json")
        em.record(Episode(user_text="first", assistant_response="r1"))
        em.record(Episode(user_text="second", assistant_response="r2"))

        recent = em.recent(limit=1)
        assert len(recent) == 1
        assert recent[0].user_text == "second"

    def test_success_rate(self, tmp_dir):
        em = EpisodicMemory(f"{tmp_dir}/episodic.json")
        em.record(Episode(user_text="a", assistant_response="b", action_success=True))
        em.record(Episode(user_text="c", assistant_response="d", action_success=True))
        em.record(Episode(user_text="e", assistant_response="f", action_success=False))

        rate = em.get_success_rate()
        assert abs(rate - 0.667) < 0.01

    def test_total_episodes(self, tmp_dir):
        em = EpisodicMemory(f"{tmp_dir}/episodic.json")
        em.record(Episode(user_text="a", assistant_response="b"))
        em.record(Episode(user_text="c", assistant_response="d"))
        assert em.total_episodes == 2


class TestProceduralMemory:
    """Test learned pattern memory."""

    def test_record_and_suggest(self, tmp_dir):
        pm = ProceduralMemory(f"{tmp_dir}/proc.json")
        pm.record_success(ActionPattern(
            action_type="click",
            target_description="Submit button",
            context_hash="ctx123",
            steps=["find_element", "scroll_to", "click"],
        ))

        suggestion = pm.suggest_strategy("click", "ctx123")
        assert suggestion is not None
        assert "click" in suggestion

    def test_repair_suggestion(self, tmp_dir):
        pm = ProceduralMemory(f"{tmp_dir}/proc.json")
        pm.record_repair(RepairOutcome(
            failure_type="element_not_found",
            repair_strategy="scroll_down",
            succeeded=True,
            action_type="click",
        ))

        repair = pm.suggest_repair("element_not_found", "click")
        assert repair == "scroll_down"

    def test_statistics(self, tmp_dir):
        pm = ProceduralMemory(f"{tmp_dir}/proc.json")
        pm.record_success(ActionPattern(
            action_type="navigate",
            target_description="Google",
            context_hash="h1",
            steps=["open_browser"],
        ))

        stats = pm.get_statistics()
        assert stats["total_patterns"] >= 1


class TestFridayMemory:
    """Test the unified memory controller."""

    def test_record_turn(self, tmp_dir):
        mem = FridayMemory(data_dir=tmp_dir)
        mem.record_turn("Hello", "Hi there!", mode="jarvis")

        assert mem.working.turn_count == 1
        assert mem.episodic.total_episodes == 1

    def test_get_context(self, tmp_dir):
        mem = FridayMemory(data_dir=tmp_dir)
        mem.record_turn("Open Chrome", "Done.", mode="friday", action_success=True)

        ctx = mem.get_context("chrome")
        assert ctx.working_context != ""
        assert len(ctx.relevant_episodes) >= 1

    def test_goal_lifecycle(self, tmp_dir):
        mem = FridayMemory(data_dir=tmp_dir)
        mem.set_active_goal("Research laptops", steps=5)
        assert mem.working.active_goal is not None

        mem.update_goal_progress(3)
        assert mem.working.active_goal.steps_completed == 3

        mem.complete_goal()
        assert mem.working.active_goal is None

    def test_statistics(self, tmp_dir):
        mem = FridayMemory(data_dir=tmp_dir)
        mem.record_turn("test", "ok")

        stats = mem.get_statistics()
        assert "working" in stats
        assert "episodic" in stats
        assert "procedural" in stats

    def test_reset_session(self, tmp_dir):
        mem = FridayMemory(data_dir=tmp_dir)
        mem.record_turn("hello", "hi")
        mem.set_active_goal("goal")

        mem.reset_session()
        assert mem.working.turn_count == 0
        # Episodic persists across sessions
        assert mem.episodic.total_episodes == 1
