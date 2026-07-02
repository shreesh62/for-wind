"""Tests for friday.router — request classification and routing."""

import pytest

from friday.router.classifier import (
    ClassificationResult,
    ComplexityLevel,
    RequestClassifier,
    RequestMode,
)
from friday.router.request_router import RequestRouter, RouteResult


class TestRequestClassifier:
    """Test intent classification and complexity detection."""

    def setup_method(self):
        self.classifier = RequestClassifier()

    # --- Level 0: Simple Questions (JARVIS) ---

    def test_question_what(self):
        result = self.classifier.classify("What is Python?")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_question_how(self):
        result = self.classifier.classify("How do decorators work?")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_question_explain(self):
        result = self.classifier.classify("Explain Memory OS architecture")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_question_mark(self):
        result = self.classifier.classify("Is FastAPI better than Flask?")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_question_help_understand(self):
        result = self.classifier.classify("Help me understand async await")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_question_compare(self):
        result = self.classifier.classify("Compare Groq and NVIDIA?")
        assert result.mode == RequestMode.JARVIS
        assert result.complexity == ComplexityLevel.SIMPLE_QUESTION

    def test_conversational_default(self):
        result = self.classifier.classify("Thanks for the help")
        assert result.mode == RequestMode.JARVIS

    # --- Level 1: Simple Actions (FRIDAY) ---

    def test_open_app(self):
        result = self.classifier.classify("Open Chrome")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_open_spotify(self):
        result = self.classifier.classify("Open Spotify")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_launch_app(self):
        result = self.classifier.classify("Launch terminal")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_play_music(self):
        result = self.classifier.classify("Play some music")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    def test_screenshot(self):
        result = self.classifier.classify("Take a screenshot")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.SIMPLE_ACTION

    # --- Level 2: Multi-Step (FRIDAY) ---

    def test_open_and_send(self):
        result = self.classifier.classify("Open WhatsApp and send Om a message")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.MULTI_STEP

    def test_search_and_click(self):
        result = self.classifier.classify("Search for laptops and then click the first result")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.MULTI_STEP

    def test_navigate_then_download(self):
        result = self.classifier.classify("Navigate to Gmail and download the latest attachment")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.MULTI_STEP

    # --- Level 3: Complex Goals (FRIDAY) ---

    def test_research_task(self):
        result = self.classifier.classify("Research the best laptops under 1 lakh and build a spreadsheet")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.COMPLEX_GOAL

    def test_download_all(self):
        result = self.classifier.classify("Download all invoices from this month and summarize them")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.COMPLEX_GOAL

    def test_automate_workflow(self):
        result = self.classifier.classify("Automate sending weekly reports to the team")
        assert result.mode == RequestMode.FRIDAY
        assert result.complexity == ComplexityLevel.COMPLEX_GOAL

    # --- Wake Word Overrides ---

    def test_friday_wake_word_forces_agent(self):
        result = self.classifier.classify("send Om the report", wake_word="friday")
        assert result.mode == RequestMode.FRIDAY
        assert result.confidence >= 0.9
        assert result.wake_word_override == "friday"

    def test_jarvis_wake_word_forces_assistant(self):
        result = self.classifier.classify("open chrome", wake_word="jarvis")
        assert result.mode == RequestMode.JARVIS
        assert result.confidence >= 0.9
        assert result.wake_word_override == "jarvis"

    # --- Confidence ---

    def test_high_confidence_on_clear_question(self):
        result = self.classifier.classify("What time is it?")
        assert result.confidence >= 0.8

    def test_high_confidence_on_clear_action(self):
        result = self.classifier.classify("Open Chrome")
        assert result.confidence >= 0.8

    # --- Edge Cases ---

    def test_empty_string(self):
        result = self.classifier.classify("")
        assert result.mode == RequestMode.JARVIS  # Default

    def test_single_word(self):
        result = self.classifier.classify("hello")
        assert result.mode == RequestMode.JARVIS


class TestRequestRouter:
    """Test request routing to mode handlers."""

    def test_routes_question_to_jarvis(self):
        """Questions go to JARVIS handler."""
        jarvis_called = [False]

        def jarvis_handler(text, ctx):
            jarvis_called[0] = True
            return "Python is a programming language."

        router = RequestRouter(jarvis_handler=jarvis_handler)
        result = router.route("What is Python?")

        assert result.mode == RequestMode.JARVIS
        assert result.is_conversation is True
        assert jarvis_called[0] is True
        assert "programming" in result.response

    def test_routes_action_to_friday(self):
        """Actions go to FRIDAY handler."""
        friday_called = [False]

        def friday_handler(text, ctx, level):
            friday_called[0] = True
            return "Chrome opened"

        router = RequestRouter(friday_handler=friday_handler)
        result = router.route("Open Chrome")

        assert result.mode == RequestMode.FRIDAY
        assert result.is_action is True
        assert friday_called[0] is True

    def test_friday_handler_receives_complexity(self):
        """FRIDAY handler receives complexity level."""
        received_level = [None]

        def friday_handler(text, ctx, level):
            received_level[0] = level
            return "done"

        router = RequestRouter(friday_handler=friday_handler)
        router.route("Open WhatsApp and send Om hello")

        assert received_level[0] == ComplexityLevel.MULTI_STEP

    def test_wake_word_override(self):
        """Wake word overrides classification."""
        jarvis_handler = lambda t, c: "response"
        friday_handler = lambda t, c, l: "action"

        router = RequestRouter(
            jarvis_handler=jarvis_handler,
            friday_handler=friday_handler,
        )

        # "open chrome" would normally go to FRIDAY, but jarvis wake word forces assistant
        result = router.route("open chrome", wake_word="jarvis")
        assert result.mode == RequestMode.JARVIS

    def test_handler_exception_graceful(self):
        """Router handles handler exceptions gracefully."""
        def bad_handler(text, ctx):
            raise RuntimeError("LLM down")

        router = RequestRouter(jarvis_handler=bad_handler)
        result = router.route("Hello")

        assert "error" in result.response.lower()

    def test_no_handler_returns_empty(self):
        """Router works without handlers (returns empty response)."""
        router = RequestRouter()
        result = router.route("Hello")

        assert result.mode == RequestMode.JARVIS
        assert result.response == ""

    def test_context_passed_to_handler(self):
        """Context dict is passed to handlers."""
        received_ctx = [None]

        def handler(text, ctx):
            received_ctx[0] = ctx
            return "ok"

        router = RequestRouter(jarvis_handler=handler)
        router.route("Hello", context={"memory": "some context"})

        assert received_ctx[0] == {"memory": "some context"}
