"""Integration tests — end-to-end validation of the full FRIDAY pipeline.

These tests wire together all components (bridge, router, memory, models)
and verify the system works as a whole without mocks.

Requires: NVIDIA_API_KEY or GROQ_API_KEY in .env for LLM tests.
Non-LLM tests work without API keys.
"""

import os
import tempfile

import pytest

from friday.bridge import FridayBridge, BridgeConfig, BridgeResult
from friday.memory import FridayMemory
from friday.models.router import ModelRouter, ModelCapability
from friday.router.classifier import RequestMode, ComplexityLevel
from friday.planner import GoalParser, TaskDecomposer
from friday.perception.world_state import WorldStateBuilder
from friday.perception.types import BoundingBox, BrowserElement, UIElement, WindowInfo
from friday.perception.priority import PerceptionResolver
from friday.verification import ActionVerifier, VerificationVerdict
from friday.core import FridayEngine, EngineConfig


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestFullPipeline:
    """Test the complete request → route → plan → result pipeline."""

    def test_question_goes_fast_path(self, tmp_dir):
        """Level 0 questions skip planner/engine entirely."""
        memory = FridayMemory(data_dir=tmp_dir)
        bridge = FridayBridge(
            llm_callable=lambda text: "Python is a programming language.",
        )

        result = bridge.process("What is Python?")

        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION
        assert "Python" in result.response

    def test_action_triggers_friday_mode(self, tmp_dir):
        """Level 1 actions route through FRIDAY engine."""
        bridge = FridayBridge(
            llm_callable=lambda text: "Opened Chrome.",
        )

        result = bridge.process("Open Chrome")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_multi_step_detected(self):
        """Multi-step commands get level 2."""
        bridge = FridayBridge()
        result = bridge.process("Open WhatsApp and send Om hello")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.MULTI_STEP

    def test_complex_goal_detected(self):
        """Complex goals get level 3."""
        bridge = FridayBridge()
        result = bridge.process("Research laptops and build a spreadsheet comparing them")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.COMPLEX_GOAL

    def test_wake_word_override(self):
        """Wake word forces mode regardless of content."""
        bridge = FridayBridge(llm_callable=lambda t: "Sure!")

        # "Open chrome" would normally be FRIDAY, but jarvis override
        result = bridge.process("open chrome", wake_word="jarvis")
        assert result.mode == RequestMode.JARVIS

        # "explain python" would normally be JARVIS, but friday override
        result = bridge.process("explain python", wake_word="friday")
        assert result.mode == RequestMode.FRIDAY


class TestMemoryIntegration:
    """Test memory records interactions end-to-end."""

    def test_interactions_recorded(self, tmp_dir):
        """Bridge records interactions to memory."""
        memory = FridayMemory(data_dir=tmp_dir)
        bridge = FridayBridge(llm_callable=lambda t: "Hello!")

        # Wire memory recording manually (in main.py this is automatic)
        result = bridge.process("Hi there")
        memory.record_turn(
            "Hi there", result.response,
            mode=result.mode.value,
            complexity=int(result.complexity),
        )

        assert memory.episodic.total_episodes == 1
        assert memory.working.turn_count == 1

    def test_memory_context_for_follow_up(self, tmp_dir):
        """Memory provides context for subsequent requests."""
        memory = FridayMemory(data_dir=tmp_dir)
        memory.record_turn("My name is Shreesh", "Nice to meet you, Shreesh!")

        context = memory.get_context("Shreesh")
        assert len(context.relevant_episodes) >= 1
        prompt = context.to_prompt_string()
        assert "Shreesh" in prompt


class TestPlannerIntegration:
    """Test goal parsing → task decomposition → plan execution."""

    def test_multi_step_produces_plan(self):
        """Multi-step goal decomposes into executable steps."""
        parser = GoalParser()
        decomposer = TaskDecomposer()

        goal = parser.parse("Open WhatsApp and send Om hello")
        assert goal.is_multi_step

        plan = decomposer.decompose(goal)
        assert plan.total_steps >= 2
        assert not plan.is_complete

        # Simulate execution
        for _ in range(plan.total_steps):
            step = plan.advance()
            if step:
                plan.complete_current("Done")

        assert plan.is_complete
        assert plan.progress == 1.0


class TestPerceptionPriority:
    """Test semantic-first resolution in realistic scenarios."""

    def test_browser_page_prefers_dom(self):
        """On a browser page, DOM elements beat OCR."""
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(title="Chrome", process_name="chrome.exe", pid=1))
        builder.set_browser_state(
            url="https://google.com",
            title="Google",
            elements=[
                BrowserElement(tag="input", text="Search", role="searchbox", clickable=True),
                BrowserElement(tag="button", text="Google Search", role="button", clickable=True),
            ],
        )
        builder.add_ocr_regions([])  # No OCR needed
        state = builder.build()

        resolver = PerceptionResolver()
        element = resolver.find_element(state, "Google Search", clickable_only=True)

        assert element is not None
        assert element.is_semantic is True
        assert element.source.value == "browser"

    def test_desktop_app_uses_uia(self):
        """For desktop apps, UIA provides semantic understanding."""
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(title="Notepad", process_name="notepad.exe", pid=2))
        builder.add_ui_elements([
            UIElement(text="File", control_type="MenuItem", bbox=BoundingBox(x=0, y=0, width=40, height=20)),
            UIElement(text="Edit", control_type="MenuItem", bbox=BoundingBox(x=40, y=0, width=40, height=20)),
            UIElement(text="Help", control_type="MenuItem", bbox=BoundingBox(x=80, y=0, width=40, height=20)),
        ])
        state = builder.build()

        resolver = PerceptionResolver()
        element = resolver.find_element(state, "File", clickable_only=True)

        assert element is not None
        assert element.is_semantic is True
        assert element.clickable is True

    def test_semantic_coverage_reported(self):
        """Perception quality correctly reports semantic vs visual coverage."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="a", text="Home", role="link", clickable=True)],
        )
        state = builder.build()

        resolver = PerceptionResolver()
        quality = resolver.get_perception_quality(state)

        assert quality["has_browser_dom"] is True
        assert quality["semantic_coverage"] == 1.0


class TestVerificationIntegration:
    """Test verification produces meaningful verdicts."""

    def test_navigation_verified(self):
        """URL change is verified as navigation success."""
        before = WorldStateBuilder()
        before.set_window_info(WindowInfo(title="Chrome", process_name="chrome.exe", pid=1))
        before.set_browser_state(url="https://google.com", title="Google", elements=[])
        before_state = before.build()

        after = WorldStateBuilder()
        after.set_window_info(WindowInfo(title="Chrome", process_name="chrome.exe", pid=1))
        after.set_browser_state(url="https://github.com", title="GitHub", elements=[])
        after_state = after.build()

        verifier = ActionVerifier()
        result = verifier.verify("navigate", "github.com", before_state, after_state)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.evidence.url_changed is True

    def test_no_change_unverified(self):
        """No state change results in UNVERIFIED verdict."""
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(title="App", process_name="app.exe", pid=1))
        builder.set_screenshot_hash("same_hash")
        state = builder.build()

        verifier = ActionVerifier()
        result = verifier.verify("click", "button", state, state)

        assert result.verdict == VerificationVerdict.UNVERIFIED
