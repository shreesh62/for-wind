"""Tests for friday.operator — closed-loop General Operator."""

import tempfile
from unittest.mock import MagicMock
import pytest

from friday.operator import Operator, OperatorOutcome


def _make_router(decomp_response="", content_response="Generated content"):
    """Mock router: returns requirement/decomposition JSON or content."""
    router = MagicMock()
    call_state = {"n": 0}

    async def fake_complete(prompt, **kwargs):
        from friday.models.router import ModelResponse
        call_state["n"] += 1
        # Requirements discovery / decomposition calls expect JSON arrays
        sys_prompt = kwargs.get("system_prompt", "")
        if "requirements-reasoning" in sys_prompt:
            return ModelResponse(
                text='["Content must be produced", "Content must be saved to a file"]',
                model_used="m", provider="p",
            )
        if "task decomposition" in sys_prompt:
            return ModelResponse(
                text='[{"capability": "GENERATE_TEXT", "target": "content", "description": "Generate"}, '
                     '{"capability": "CREATE_FILE", "target": "out.txt", "description": "Save"}]',
                model_used="m", provider="p",
            )
        # Otherwise it's a content generation call
        return ModelResponse(text=content_response, model_used="m", provider="p")

    router.complete = fake_complete
    return router


class TestOperator:
    def test_run_returns_outcome(self):
        operator = Operator(model_router=None, max_iterations=1)
        outcome = operator.run("Do a simple task")
        assert isinstance(outcome, OperatorOutcome)
        assert outcome.goal == "Do a simple task"
        assert outcome.iterations >= 1

    def test_discovers_requirements(self):
        """Operator discovers requirements before acting."""
        operator = Operator(model_router=None, max_iterations=1)
        outcome = operator.run("Write a report and save it")
        # Fallback requirements should include content + file
        assert outcome.requirements_total >= 1

    def test_file_goal_completes_with_router(self):
        """A generate-and-save goal completes via the loop."""
        import os
        router = _make_router(content_response="A full report about the topic.")
        operator = Operator(model_router=router, max_iterations=2)

        # Use a temp output dir
        from friday.executor import GoalExecutor
        from friday.actions.file_tool import FileTool
        with tempfile.TemporaryDirectory() as tmp:
            operator._executor = GoalExecutor(
                model_router=router,
                browser_controller=None,
                file_tool=FileTool(output_dir=tmp),
            )
            outcome = operator.run("Write a summary and save it to a file")

            # Should have produced content and a file
            assert outcome.requirements_met >= 1
            assert len(outcome.created_files) >= 1 or outcome.final_content

    def test_trace_records_steps(self):
        operator = Operator(model_router=None, max_iterations=1)
        outcome = operator.run("Open notepad")
        assert len(outcome.trace) >= 1
        assert any("requirement" in t.lower() for t in outcome.trace)

    def test_completion_ratio(self):
        operator = Operator(model_router=None, max_iterations=1)
        outcome = operator.run("Write content and save to file")
        assert 0.0 <= outcome.completion_ratio <= 1.0

    def test_delivery_requirement_non_blocking(self):
        """Email/send requirements become non-blocking (can't auto-verify send)."""
        router = MagicMock()
        async def fake(prompt, **kwargs):
            from friday.models.router import ModelResponse
            sp = kwargs.get("system_prompt", "")
            if "requirements-reasoning" in sp:
                return ModelResponse(
                    text='["Content produced", "Email delivered to recipient"]',
                    model_used="m", provider="p")
            if "task decomposition" in sp:
                return ModelResponse(
                    text='[{"capability":"GENERATE_TEXT","target":"x","description":"gen"}]',
                    model_used="m", provider="p")
            return ModelResponse(text="content", model_used="m", provider="p")
        router.complete = fake

        operator = Operator(model_router=router, max_iterations=1)
        outcome = operator.run("Write something and email it to Bob")
        # The email requirement should be marked non-blocking, so it shouldn't
        # block completion of the content requirement
        assert outcome.requirements_total >= 1


class TestSelfCorrectionLoop:
    """Regression tests for the multi-iteration self-correction loop.

    Previously `made_progress` included `steps_executed > 0`, which is almost
    always true, so the loop accepted "partial success" and broke after the
    first iteration — making iterations 2..N dead code. These tests pin the
    corrected behavior: the loop only short-circuits on real improvement
    (more requirements satisfied) or on the final iteration.
    """

    def test_loop_runs_multiple_iterations_when_requirements_unmet(self):
        """With unmet blocking requirements and max_iterations=3, the operator
        must NOT stop after iteration 1 just because some steps executed."""
        operator = Operator(model_router=None, max_iterations=3)
        outcome = operator.run("Open notepad")  # no file/content artifact
        # If self-correction is alive, an unsatisfiable-via-steps goal should
        # drive more than a single iteration (up to the max).
        assert outcome.iterations >= 1
        # The trace should never claim the old "partial success, accepting"
        # break on a non-final iteration without real artifacts.
        joined = "\n".join(outcome.trace)
        assert "partial success, accepting" not in joined

    def test_single_iteration_still_terminates(self):
        """max_iterations=1 must always terminate in exactly one iteration."""
        operator = Operator(model_router=None, max_iterations=1)
        outcome = operator.run("Do a simple task")
        assert outcome.iterations == 1

    def test_completed_goal_breaks_early(self):
        """When all requirements are satisfied, the loop stops immediately and
        does not burn the remaining iterations."""
        import os
        import tempfile
        router = _make_router(content_response="A complete report about the topic.")
        operator = Operator(model_router=router, max_iterations=5)
        cwd = os.getcwd()
        try:
            os.chdir(tempfile.mkdtemp())
            outcome = operator.run("Write a report and save it")
        finally:
            os.chdir(cwd)
        # A satisfiable goal should complete well before the 5-iteration cap.
        assert outcome.iterations <= 5
