"""Tests for friday.planner — goal parser and task decomposer."""

import pytest

from friday.planner.goal_parser import Goal, GoalIntent, GoalParser
from friday.planner.decomposer import TaskDecomposer, TaskPlan, TaskStep, TaskStatus


class TestGoalParser:
    """Test goal parsing from natural language."""

    def setup_method(self):
        self.parser = GoalParser()

    # --- Navigation ---

    def test_open_chrome(self):
        goal = self.parser.parse("Open Chrome")
        assert goal.intent == GoalIntent.NAVIGATE
        assert "chrome" in goal.target.lower()

    def test_go_to_url(self):
        goal = self.parser.parse("Go to https://google.com")
        assert goal.intent == GoalIntent.NAVIGATE
        assert "google" in goal.target

    def test_navigate_to_gmail(self):
        goal = self.parser.parse("Navigate to Gmail")
        assert goal.intent == GoalIntent.NAVIGATE

    def test_launch_terminal(self):
        goal = self.parser.parse("Launch terminal")
        assert goal.intent == GoalIntent.NAVIGATE
        assert "terminal" in goal.target

    # --- Communication ---

    def test_send_message(self):
        goal = self.parser.parse("Send Om a message")
        assert goal.intent == GoalIntent.COMMUNICATE
        assert goal.get_param("recipient") is not None

    def test_message_with_content(self):
        goal = self.parser.parse("Message Rahul saying hey what's up")
        assert goal.intent == GoalIntent.COMMUNICATE
        assert "rahul" in goal.get_param("recipient").lower()

    def test_email(self):
        goal = self.parser.parse("Email the team about the update")
        assert goal.intent == GoalIntent.COMMUNICATE

    # --- Search ---

    def test_search_google(self):
        goal = self.parser.parse("Search for best laptops under 50k")
        assert goal.intent == GoalIntent.SEARCH
        assert goal.get_param("query") is not None
        assert "laptop" in goal.get_param("query")

    def test_find(self):
        goal = self.parser.parse("Find restaurants near me")
        assert goal.intent == GoalIntent.SEARCH

    # --- Create ---

    def test_create_file(self):
        goal = self.parser.parse("Create a new spreadsheet")
        assert goal.intent == GoalIntent.CREATE

    def test_write_document(self):
        goal = self.parser.parse("Write a summary of today's meeting")
        assert goal.intent == GoalIntent.CREATE

    # --- Research ---

    def test_research(self):
        goal = self.parser.parse("Research the best AI frameworks in 2026")
        assert goal.intent == GoalIntent.RESEARCH

    # --- Control ---

    def test_play_music(self):
        goal = self.parser.parse("Play some lo-fi music")
        assert goal.intent == GoalIntent.CONTROL

    # --- Multi-step ---

    def test_multi_step_and(self):
        goal = self.parser.parse("Open WhatsApp and send Om hello")
        assert goal.is_multi_step is True
        assert len(goal.sub_goals) == 2
        assert goal.sub_goals[0].intent == GoalIntent.NAVIGATE

    def test_multi_step_then(self):
        goal = self.parser.parse("Open Chrome then search for Python tutorials")
        assert goal.is_multi_step is True
        assert len(goal.sub_goals) == 2

    def test_step_count(self):
        goal = self.parser.parse("Open WhatsApp and send Om hello")
        assert goal.step_count == 2

    # --- Edge cases ---

    def test_empty_input(self):
        goal = self.parser.parse("")
        assert goal.intent == GoalIntent.UNKNOWN

    def test_unknown_intent(self):
        goal = self.parser.parse("banana")
        assert goal.intent == GoalIntent.UNKNOWN
        assert goal.confidence < 0.5


class TestTaskDecomposer:
    """Test task decomposition from goals."""

    def setup_method(self):
        self.parser = GoalParser()
        self.decomposer = TaskDecomposer()

    def test_navigate_produces_single_step(self):
        goal = self.parser.parse("Open Chrome")
        plan = self.decomposer.decompose(goal)

        assert isinstance(plan, TaskPlan)
        assert plan.total_steps == 1
        assert plan.steps[0].action_type == "open_app"
        assert "chrome" in plan.steps[0].target.lower()

    def test_search_produces_steps(self):
        goal = self.parser.parse("Search for laptops")
        plan = self.decomposer.decompose(goal)

        assert plan.total_steps >= 2  # open browser + type + search
        assert any(s.action_type == "type" for s in plan.steps)

    def test_communicate_produces_steps(self):
        goal = self.parser.parse("Send Om a message saying hello")
        plan = self.decomposer.decompose(goal)

        assert plan.total_steps >= 3  # open app + find chat + type + send
        assert any(s.action_type == "type" for s in plan.steps)

    def test_multi_step_decomposition(self):
        goal = self.parser.parse("Open WhatsApp and send Om hello")
        plan = self.decomposer.decompose(goal)

        assert plan.total_steps >= 2
        # Steps should have dependencies
        if plan.total_steps > 1:
            assert plan.steps[1].depends_on == [0]

    def test_plan_progress_tracking(self):
        goal = self.parser.parse("Open Chrome")
        plan = self.decomposer.decompose(goal)

        assert plan.progress == 0.0
        assert plan.is_complete is False

        step = plan.advance()
        assert step is not None
        assert step.status == TaskStatus.RUNNING

        plan.complete_current("Done")
        assert plan.progress == 1.0
        assert plan.is_complete is True

    def test_plan_failure_tracking(self):
        goal = self.parser.parse("Search for something")
        plan = self.decomposer.decompose(goal)

        plan.advance()
        plan.fail_current("Element not found")

        failed = [s for s in plan.steps if s.status == TaskStatus.FAILED]
        assert len(failed) == 1
        assert "Element not found" in failed[0].result

    def test_next_step(self):
        goal = self.parser.parse("Open Chrome then search for Python")
        plan = self.decomposer.decompose(goal)

        first = plan.next_step
        assert first is not None
        assert first.order == 0

        plan.advance()
        plan.complete_current()

        second = plan.next_step
        assert second is not None
        assert second.order == 1
