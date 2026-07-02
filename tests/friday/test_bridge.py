"""Tests for friday.bridge — integration with existing runtime."""

from unittest.mock import MagicMock, patch
import pytest

from friday.bridge import FridayBridge, BridgeConfig, BridgeResult
from friday.router.classifier import ComplexityLevel, RequestMode


class TestFridayBridge:
    """Test the bridge between new friday/ and old Jarvis."""

    def test_init_minimal(self):
        """Bridge initializes without any dependencies."""
        bridge = FridayBridge()
        assert bridge.engine is not None
        assert bridge.router is not None

    def test_question_routes_to_jarvis(self):
        """Questions go through JARVIS mode (fast path)."""
        mock_llm = MagicMock(return_value="Python is great.")

        bridge = FridayBridge(llm_callable=mock_llm)
        result = bridge.process("What is Python?")

        assert isinstance(result, BridgeResult)
        assert result.mode == RequestMode.JARVIS
        assert "Python" in result.response
        mock_llm.assert_called_once()

    def test_action_routes_to_friday(self):
        """Actions go through FRIDAY mode."""
        mock_automation = MagicMock()
        mock_automation.launch_app.return_value = "Chrome opened"

        bridge = FridayBridge(automation_services=mock_automation)
        result = bridge.process("Open Chrome")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_wake_word_jarvis_override(self):
        """JARVIS wake word forces assistant mode."""
        mock_llm = MagicMock(return_value="Sure, let me explain.")

        bridge = FridayBridge(llm_callable=mock_llm)
        result = bridge.process("open chrome", wake_word="jarvis")

        assert result.mode == RequestMode.JARVIS
        mock_llm.assert_called_once()

    def test_wake_word_friday_override(self):
        """FRIDAY wake word forces agent mode."""
        bridge = FridayBridge()
        result = bridge.process("explain python", wake_word="friday")

        assert result.mode == RequestMode.FRIDAY

    def test_legacy_fallback(self):
        """Bridge falls back to legacy LLM when automation unavailable."""
        mock_llm = MagicMock(return_value="I'll try to help.")
        config = BridgeConfig(allow_legacy_fallback=True)

        bridge = FridayBridge(llm_callable=mock_llm, config=config)
        result = bridge.process("Open Chrome")

        # Without automation services, should fallback
        assert result.handled is True

    def test_classification_metadata(self):
        """Result includes classification metadata."""
        bridge = FridayBridge(llm_callable=lambda t: "ok")
        result = bridge.process("What is ML?")

        assert "classification" in result.metadata
        assert result.metadata["classification"]["mode"] == "jarvis"
        assert result.metadata["classification"]["complexity"] == 0

    def test_multi_step_complexity(self):
        """Multi-step commands get correct complexity."""
        bridge = FridayBridge()
        result = bridge.process("Open WhatsApp and send Om hello")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.MULTI_STEP

    def test_complex_goal_complexity(self):
        """Complex goals get level 3."""
        bridge = FridayBridge()
        result = bridge.process("Research laptops and build a spreadsheet")

        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.COMPLEX_GOAL
