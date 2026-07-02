"""Tests for friday.executor — GoalExecutor with data flow."""

import tempfile
from unittest.mock import MagicMock
import pytest

from friday.executor import GoalExecutor, ExecutionContext, ExecutionResult
from friday.actions.file_tool import FileTool
from friday.planner.operator_planner import OperatorPlan, OperatorStep
from friday.tools.registry import ToolCapability
from friday.planner.decomposer import TaskStatus


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestExecutionContext:
    def test_add_info_accumulates(self):
        ctx = ExecutionContext(goal="test")
        ctx.add_info("fact 1")
        ctx.add_info("fact 2")
        assert len(ctx.gathered_info) == 2
        assert "fact 1" in ctx.combined_info
        assert "fact 2" in ctx.combined_info

    def test_empty_info_ignored(self):
        ctx = ExecutionContext(goal="test")
        ctx.add_info("")
        ctx.add_info("   ")
        assert len(ctx.gathered_info) == 0


class TestFileTool:
    def test_create_text_file(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        result = tool.create_file("test.txt", "Hello FRIDAY")
        assert result.is_success
        assert "test.txt" in result.target

    def test_create_and_read(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        tool.create_file("data.txt", "content here")
        result = tool.read_file("data.txt")
        assert result.is_success
        assert "content here" in result.message

    def test_read_nonexistent(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        result = tool.read_file("nope.txt")
        assert not result.is_success
        assert result.error_category == "not_found"

    def test_append(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        tool.create_file("log.txt", "line1\n")
        tool.append_file("log.txt", "line2\n")
        result = tool.read_file("log.txt")
        assert "line1" in result.message
        assert "line2" in result.message

    def test_delete(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        tool.create_file("temp.txt", "x")
        result = tool.delete_file("temp.txt")
        assert result.is_success

    def test_html_format(self, tmp_dir):
        tool = FileTool(output_dir=tmp_dir)
        result = tool.create_file("page.html", "Hello\nWorld")
        assert result.is_success
        read = tool.read_file("page.html")
        assert "<p>" in read.message


class TestGoalExecutor:
    def _make_plan(self, capabilities):
        """Build a plan from a list of (capability, target, desc)."""
        plan = OperatorPlan(goal_text="test goal")
        for i, (cap, target, desc) in enumerate(capabilities):
            plan.steps.append(OperatorStep(
                capability=cap, tool_name="x", target=target,
                description=desc, order=i,
            ))
        return plan

    def test_file_creation_flow(self, tmp_dir):
        """Generate content then create file — data flows."""
        # Mock model router that returns content
        router = MagicMock()
        async def fake_complete(prompt, **kwargs):
            from friday.models.router import ModelResponse
            return ModelResponse(text="Generated report content", model_used="m", provider="p")
        router.complete = fake_complete

        executor = GoalExecutor(
            model_router=router,
            browser_controller=None,
            file_tool=FileTool(output_dir=tmp_dir),
        )

        plan = self._make_plan([
            (ToolCapability.GENERATE_TEXT, "write report", "Generate report"),
            (ToolCapability.CREATE_FILE, "report.txt", "Create file"),
        ])

        result = executor.execute_plan(plan, "Create a report")

        assert result.success is True
        assert len(result.created_files) == 1
        assert result.steps_executed == 2

    def test_skipped_steps_counted(self, tmp_dir):
        executor = GoalExecutor(file_tool=FileTool(output_dir=tmp_dir))
        plan = self._make_plan([
            (ToolCapability.OPEN_APPLICATION, "chrome", "Open Chrome"),
        ])
        plan.steps[0].can_skip = True
        plan.steps[0].skip_reason = "already running"

        result = executor.execute_plan(plan, "Open Chrome")
        assert result.steps_skipped == 1
        assert result.steps_executed == 0

    def test_generated_content_feeds_file(self, tmp_dir):
        """Content generated in one step is written by the file step."""
        router = MagicMock()
        async def fake_complete(prompt, **kwargs):
            from friday.models.router import ModelResponse
            return ModelResponse(text="UNIQUE_CONTENT_12345", model_used="m", provider="p")
        router.complete = fake_complete

        ft = FileTool(output_dir=tmp_dir)
        executor = GoalExecutor(model_router=router, file_tool=ft)

        plan = self._make_plan([
            (ToolCapability.GENERATE_TEXT, "content", "Generate"),
            (ToolCapability.CREATE_FILE, "out.txt", "Save"),
        ])
        result = executor.execute_plan(plan, "Generate and save content")

        # Read the created file — should contain the generated content
        assert len(result.created_files) == 1
        read = ft.read_file(result.created_files[0])
        assert "UNIQUE_CONTENT_12345" in read.message

    def test_verify_goal_for_file_task(self, tmp_dir):
        executor = GoalExecutor(file_tool=FileTool(output_dir=tmp_dir))
        ctx = ExecutionContext(goal="create a report file")
        # No files created
        assert executor._verify_goal("create a report file", ctx) is False
        # File created
        ctx.created_files.append("report.txt")
        assert executor._verify_goal("create a report file", ctx) is True

    def test_filename_inference(self, tmp_dir):
        executor = GoalExecutor(file_tool=FileTool(output_dir=tmp_dir))
        ctx = ExecutionContext(goal="create a word report about laptops")
        fname = executor._infer_filename("report", ctx)
        assert fname.endswith(".docx")  # "word" + "report" → docx

    def test_target_to_url(self, tmp_dir):
        executor = GoalExecutor(file_tool=FileTool(output_dir=tmp_dir))
        assert "instagram.com" in executor._target_to_url("instagram")
        assert "youtube.com" in executor._target_to_url("youtube")
        assert executor._target_to_url("notepad") is None  # not a known site


class TestBuildWorldState:
    """Regression tests for `_build_world_state`.

    Previously this always passed `elements=[]`, so BrowserAdapter had nothing
    to resolve against and every primitive click/type silently failed. The fix
    populates live interactive elements via `observe_interactive()`.
    """

    def _fake_browser(self, snap):
        b = MagicMock()
        b.available = True
        b.current_url.return_value = snap.get("url", "")
        b.observe_interactive.return_value = snap
        return b

    def test_world_state_populates_elements_from_observe(self):
        snap = {
            "ok": True,
            "url": "https://example.com",
            "title": "Example",
            "elements": [
                {"index": 0, "role": "button", "tag": "button", "text": "Submit",
                 "editable": False, "selector": "#submit", "in_view": True,
                 "x": 120, "y": 210},
                {"index": 1, "role": "textbox", "tag": "input", "text": "Email",
                 "editable": True, "selector": "#email", "in_view": True,
                 "x": 100, "y": 50},
            ],
        }
        ex = GoalExecutor(browser_controller=self._fake_browser(snap))
        ws = ex._build_world_state()
        assert ws.browser_connected is True
        assert ws.browser_url == "https://example.com"
        # The bug: this list used to always be empty.
        assert len(ws.browser_elements) == 2
        texts = {e.text for e in ws.browser_elements}
        assert "Submit" in texts and "Email" in texts
        # editable -> not clickable; non-editable -> clickable
        by_text = {e.text: e for e in ws.browser_elements}
        assert by_text["Submit"].clickable is True
        assert by_text["Email"].clickable is False
        assert by_text["Submit"].selector == "#submit"
        assert by_text["Submit"].bbox is not None

    def test_world_state_handles_observe_failure_gracefully(self):
        b = MagicMock()
        b.available = True
        b.current_url.return_value = "https://x.com"
        b.observe_interactive.side_effect = RuntimeError("context destroyed")
        ex = GoalExecutor(browser_controller=b)
        ws = ex._build_world_state()
        # Falls back to empty elements but stays connected — no crash.
        assert ws.browser_connected is True
        assert ws.browser_elements == []

    def test_world_state_no_browser_is_empty(self):
        ex = GoalExecutor(browser_controller=None)
        ws = ex._build_world_state()
        assert ws.browser_elements == []
        assert ws.browser_connected is False
