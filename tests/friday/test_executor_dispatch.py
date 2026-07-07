"""TD-5 — Characterization tests for GoalExecutor dispatch (Ch 16/22).

Pins the EXACT observable behavior of every `_execute_step` capability branch
BEFORE the dispatch is refactored from an implicit if/elif ladder into an
explicit, data-driven dispatch table. These tests are the safety net: they must
pass identically before and after the refactor, guaranteeing zero behavior
change (the refactor is mechanical, not semantic).

All tests run under FRIDAY_DRY_RUN=1 so no external actions occur; the DRY-RUN
guard branch is itself characterized.

Validates: TD-5 (registry-shaped dispatch), Requirements — behavior preservation.
"""

from __future__ import annotations

import os

os.environ["FRIDAY_DRY_RUN"] = "1"  # force dry-run for the whole module

import tempfile
import types
from unittest.mock import MagicMock

import pytest

from friday.executor import ExecutionContext, GoalExecutor
from friday.planner.operator_planner import OperatorStep
from friday.planner.decomposer import TaskStatus
from friday.tools.registry import ToolCapability


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _step(cap, target="x", description="step"):
    return OperatorStep(
        capability=cap,
        tool_name="t",
        target=target,
        description=description,
        status=TaskStatus.PENDING,
        order=0,
    )


def _executor(tmp_dir=None, **kw):
    from friday.actions.file_tool import FileTool
    return GoalExecutor(file_tool=FileTool(output_dir=tmp_dir) if tmp_dir else None, **kw)


# --------------------------------------------------------------------------- #
# DRY-RUN guard — visible/external capabilities are blocked with a marker string
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "cap",
    [
        ToolCapability.OPEN_APPLICATION,
        ToolCapability.NAVIGATE_URL,
        ToolCapability.SEARCH_WEB,
        ToolCapability.EXTRACT_WEB_CONTENT,
        ToolCapability.READ_DOM,
        ToolCapability.READ_SCREEN,
        ToolCapability.CLICK_ELEMENT,
        ToolCapability.TYPE_TEXT,
        ToolCapability.SWITCH_WINDOW,
    ],
)
def test_dry_run_blocks_visible_actions(cap):
    ex = _executor()
    ctx = ExecutionContext(goal="g")
    out = ex._execute_step(_step(cap, "tgt"), ctx)
    assert out.startswith("[DRY-RUN] Would execute")
    assert cap.value in out


# --------------------------------------------------------------------------- #
# Local (non-visible) capabilities still execute under dry-run
# --------------------------------------------------------------------------- #
def test_generate_text_produces_content_and_evidence():
    router = MagicMock()
    router.complete = MagicMock()
    # _generate uses the model router via an async path; stub it to a known value.
    ex = _executor(model_router=None)  # no router → deterministic fallback content
    ctx = ExecutionContext(goal="write about cats")
    out = ex._execute_step(_step(ToolCapability.GENERATE_TEXT, "cats"), ctx)
    assert out.startswith("Generated ")
    assert ctx.generated_content  # content was stored
    from friday.verification.evidence_law import EvidenceKind
    assert ctx.evidence.has(EvidenceKind.GENERATED_CONTENT)


def test_create_file_writes_real_file(tmp_dir):
    ex = _executor(tmp_dir=tmp_dir)
    ctx = ExecutionContext(goal="make a file")
    ctx.generated_content = "hello world content"
    out = ex._execute_step(_step(ToolCapability.CREATE_FILE, "notes.txt"), ctx)
    assert out.startswith("Created file:")
    assert ctx.created_files
    from friday.verification.evidence_law import EvidenceKind
    assert ctx.evidence.has(EvidenceKind.FILE_ARTIFACT)


def test_edit_file_without_prior_file_is_noop_message(tmp_dir):
    ex = _executor(tmp_dir=tmp_dir)
    ctx = ExecutionContext(goal="edit")
    out = ex._execute_step(_step(ToolCapability.EDIT_FILE, "x"), ctx)
    assert out == "No file to edit"


def test_run_command_is_gated():
    ex = _executor()
    ctx = ExecutionContext(goal="run")
    out = ex._execute_step(_step(ToolCapability.RUN_COMMAND, "ls"), ctx)
    assert "gated for safety" in out


def test_verify_result_returns_check_message():
    ex = _executor()
    ctx = ExecutionContext(goal="v")
    out = ex._execute_step(_step(ToolCapability.VERIFY_RESULT, "x"), ctx)
    assert out == "Intermediate check passed"


def test_unknown_capability_falls_through_to_description():
    ex = _executor()
    ctx = ExecutionContext(goal="g")
    # SCROLL is a real ToolCapability with no dedicated branch → fallback path.
    step = _step(ToolCapability.SCROLL, "x", description="scrolling step")
    out = ex._execute_step(step, ctx)
    assert out == "Executed: scrolling step"


def test_navigate_without_url_or_browser_launches_app(tmp_dir, monkeypatch):
    # Not dry-run for this one path: temporarily disable dry-run to hit the
    # real navigate branch with a bare app name (no URL, no browser) → SystemActions.
    ex = _executor(tmp_dir=tmp_dir)
    ex._dry_run = False  # exercise the real branch deterministically
    launched = {}

    class FakeResult:
        is_success = True
        message = "launched notepad"

    import friday.actions.system as system_mod
    monkeypatch.setattr(system_mod.SystemActions, "launch_app", lambda self, t: FakeResult())

    ctx = ExecutionContext(goal="open notepad")
    out = ex._execute_step(_step(ToolCapability.OPEN_APPLICATION, "notepad"), ctx)
    assert out == "launched notepad"
