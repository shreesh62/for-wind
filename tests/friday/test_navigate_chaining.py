"""Regression tests for search->navigate URL chaining in the executor.

A "navigate/open page" step whose target is not a resolvable URL (e.g. an LLM
planner placeholder like "<extracted URL>") must navigate to a REAL url already
gathered by a prior search/research step — recording NAVIGATION evidence —
instead of trying to launch the placeholder as a desktop app. This closes the
browser.navigate_and_read competence gap (NAVIGATION was never recorded for the
vague "open a page about a topic" goal). General mechanism, no site-specific
logic (Axiom 15). Hermetic: a fake browser, no LLM, no live network.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from friday.executor import GoalExecutor, ExecutionContext
from friday.tools.registry import ToolCapability
from friday.verification.evidence_law import EvidenceKind


def test_placeholder_navigate_chains_to_gathered_source_url():
    """No resolvable URL + a gathered SOURCE_URL -> navigate to it, record NAVIGATION."""
    fake = MagicMock()
    fake.available = True
    fake.navigate.return_value = {"ok": True, "url": "https://example.com/page"}
    fake.read_text.return_value = "real page text"

    ex = GoalExecutor(browser_controller=fake)
    ctx = ExecutionContext(goal="open the page about the topic and read it")
    ctx.evidence.add_source_url("https://example.com/page")  # from a prior search

    msg = ex._dispatch_navigate("<extracted URL>", ToolCapability.NAVIGATE_URL, ctx)

    fake.navigate.assert_called_once_with("https://example.com/page")
    assert "Navigated to gathered source" in msg
    nav = ex_evidence_kind(ctx, EvidenceKind.NAVIGATION)
    assert nav and any("example.com/page" in (a.detail or "") for a in nav)
    # The gathered URL is marked navigated (guards against re-navigation loops).
    assert "https://example.com/page" in ctx.navigated_urls


def test_placeholder_navigate_without_sources_does_not_call_navigate():
    """No resolvable URL and NO gathered sources -> fall back to launch (no nav call)."""
    fake = MagicMock()
    fake.available = True

    ex = GoalExecutor(browser_controller=fake)
    ctx = ExecutionContext(goal="open notepad")

    # 'notepad' is a bare app name -> _target_to_url is None -> no gathered URLs
    # -> must NOT call browser.navigate (falls through to the launch path).
    msg = ex._dispatch_navigate("notepad", ToolCapability.NAVIGATE_URL, ctx)

    fake.navigate.assert_not_called()
    assert isinstance(msg, str)


def test_already_navigated_gathered_url_is_not_renavigated():
    """A gathered URL already in navigated_urls is skipped (no re-nav loop)."""
    fake = MagicMock()
    fake.available = True
    fake.navigate.return_value = {"ok": True, "url": "https://example.com/a"}

    ex = GoalExecutor(browser_controller=fake)
    ctx = ExecutionContext(goal="open the page")
    ctx.evidence.add_source_url("https://example.com/a")
    ctx.navigated_urls.append("https://example.com/a")  # already visited

    ex._dispatch_navigate("<extracted URL>", ToolCapability.NAVIGATE_URL, ctx)

    fake.navigate.assert_not_called()


def ex_evidence_kind(ctx, kind):
    return ctx.evidence.of_kind(kind)
