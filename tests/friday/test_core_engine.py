"""Tests for friday.core — FridayEngine (Observe → Act → Verify loop)."""

from unittest.mock import MagicMock, patch
import pytest

from friday.core import FridayEngine, EngineConfig
from friday.actions.result import ActionResult, ActionStatus
from friday.perception.types import BoundingBox, UIElement, WindowInfo
from friday.perception.world_state import WorldState, WorldStateBuilder


def _make_state(title="App", url=None, ui_texts=None, screenshot_hash="h"):
    builder = WorldStateBuilder()
    builder.set_window_info(WindowInfo(title=title, process_name="app.exe", pid=1))
    builder.set_screenshot_hash(screenshot_hash)
    if url:
        builder.set_browser_state(url=url, title=title, elements=[], connected=True)
    if ui_texts:
        elements = [
            UIElement(text=t, control_type="Button",
                     bbox=BoundingBox(x=0, y=0, width=50, height=25))
            for t in ui_texts
        ]
        builder.add_ui_elements(elements)
    return builder.build()


class TestFridayEngine:
    """Test the core cognitive engine."""

    def test_init_without_state_cache(self):
        """Engine initializes without state cache."""
        engine = FridayEngine()
        assert engine.verifier is not None

    def test_execute_verified_success(self):
        """Engine reports verified success when state changes."""
        engine = FridayEngine()

        before = _make_state(url="https://a.com", screenshot_hash="h1")
        after = _make_state(url="https://b.com", screenshot_hash="h2")

        # Mock perception to return controlled states
        call_count = [0]
        def mock_perceive():
            call_count[0] += 1
            return before if call_count[0] == 1 else after

        engine.perceive = mock_perceive

        result = engine.execute_verified(
            action_fn=lambda: "clicked",
            action_type="navigate",
            target="b.com",
            expected={"url": "b.com"},
        )

        assert result.is_success is True
        assert result.verified is True
        assert result.evidence.url_changed is True

    def test_execute_verified_failure(self):
        """Engine reports failure when action raises exception."""
        engine = FridayEngine()

        # Mock perception
        state = _make_state()
        engine.perceive = lambda: state

        result = engine.execute_verified(
            action_fn=lambda: (_ for _ in ()).throw(RuntimeError("Element not found")),
            action_type="click",
            target="button",
        )

        assert result.is_success is False
        assert result.status == ActionStatus.FAILED
        assert "Element not found" in result.error

    def test_execute_verified_needs_repair(self):
        """Engine reports needs_repair when no state change detected."""
        config = EngineConfig(allow_unverified_success=False)
        engine = FridayEngine(config=config)

        # Same state before and after
        state = _make_state(screenshot_hash="same")
        engine.perceive = lambda: state

        result = engine.execute_verified(
            action_fn=lambda: "done",
            action_type="click",
            target="button",
        )

        assert result.status == ActionStatus.NEEDS_REPAIR
        assert result.needs_repair is True

    def test_execute_verified_allows_unverified_when_configured(self):
        """Engine allows unverified success when configured."""
        config = EngineConfig(allow_unverified_success=True)
        engine = FridayEngine(config=config)

        state = _make_state(screenshot_hash="same")
        engine.perceive = lambda: state

        result = engine.execute_verified(
            action_fn=lambda: "done",
            action_type="click",
            target="button",
        )

        assert result.is_success is True

    def test_execute_with_repair_retries(self):
        """Engine retries actions with repair function."""
        config = EngineConfig(max_repair_attempts=3, allow_unverified_success=False)
        engine = FridayEngine(config=config)

        # First two perceives show no change, third shows change
        call_count = [0]
        def mock_perceive():
            call_count[0] += 1
            if call_count[0] <= 4:  # before+after for first 2 attempts
                return _make_state(screenshot_hash="same")
            else:
                return _make_state(screenshot_hash="changed", url="https://new.com")

        engine.perceive = mock_perceive

        repair_calls = [0]
        def mock_repair(result):
            repair_calls[0] += 1

        result = engine.execute_with_repair(
            action_fn=lambda: "click",
            action_type="navigate",
            target="new page",
            repair_fn=mock_repair,
        )

        # After repairs, should eventually succeed or exhaust attempts
        assert repair_calls[0] >= 1

    def test_execute_without_perception(self):
        """Engine returns success without perception when unavailable."""
        engine = FridayEngine()
        engine.perceive = lambda: (_ for _ in ()).throw(Exception("No perception"))

        result = engine.execute_verified(
            action_fn=lambda: "done",
            action_type="click",
            target="button",
        )

        # Without perception, returns unverified success (legacy fallback)
        assert result.is_success is True
        assert result.verified is False

    def test_execute_skip_perception(self):
        """Engine can skip perception for testing."""
        engine = FridayEngine()

        result = engine.execute_verified(
            action_fn=lambda: "result",
            action_type="test_action",
            target="test",
            skip_perception=True,
        )

        assert result.is_success is True
        assert "perception unavailable" in result.message

    def test_action_timing(self):
        """Engine records action timing."""
        engine = FridayEngine()
        state = _make_state()
        engine.perceive = lambda: state

        import time

        def slow_action():
            time.sleep(0.02)
            return "done"

        result = engine.execute_verified(
            action_fn=slow_action,
            action_type="test",
            target="slow",
        )

        assert result.duration_ms >= 15  # At least 15ms (allowing some variance)
