"""Tests for the Browser Access Strategy resolver.

Encodes the owner's decision matrix:
- CDP reachable                          -> CDP_REUSE
- Chrome closed                          -> CDP_LAUNCH (user's profile)
- Chrome open (locked) + needs logins    -> DESKTOP_CONTROL (operate visible Chrome)
- Chrome open (locked) + no logins needed -> CDP_DEDICATED (clean profile)
"""

from __future__ import annotations

import pytest

from friday.actions.browser_strategy import (
    BrowserMode,
    goal_needs_user_session,
    resolve_browser_strategy,
)


class TestGoalNeedsSession:
    def test_instagram_dm_needs_session(self):
        assert goal_needs_user_session("check who dmed me on instagram") is True

    def test_my_gmail_needs_session(self):
        assert goal_needs_user_session("read my latest gmail email") is True

    def test_generic_research_does_not(self):
        assert goal_needs_user_session("research best gaming laptops") is False

    def test_empty_is_false(self):
        assert goal_needs_user_session("") is False


class TestStrategyMatrix:
    def test_cdp_reachable_reuses(self):
        s = resolve_browser_strategy(
            "anything",
            cdp_reachable_fn=lambda port: True,
            chrome_running_fn=lambda port: True,
        )
        assert s.mode == BrowserMode.CDP_REUSE
        assert s.uses_cdp

    def test_chrome_closed_launches_user_profile(self):
        s = resolve_browser_strategy(
            "check my instagram dms",
            cdp_reachable_fn=lambda port: False,
            chrome_running_fn=lambda port: False,
        )
        assert s.mode == BrowserMode.CDP_LAUNCH
        assert s.needs_user_session is True

    def test_locked_chrome_with_login_goal_uses_desktop(self):
        s = resolve_browser_strategy(
            "reply to my latest instagram dm",
            cdp_reachable_fn=lambda port: False,
            chrome_running_fn=lambda port: True,
        )
        assert s.mode == BrowserMode.DESKTOP_CONTROL
        assert s.uses_desktop
        assert s.needs_user_session is True

    def test_locked_chrome_no_login_uses_dedicated(self):
        s = resolve_browser_strategy(
            "research best gaming laptops and summarize",
            cdp_reachable_fn=lambda port: False,
            chrome_running_fn=lambda port: True,
        )
        assert s.mode == BrowserMode.CDP_DEDICATED
        assert s.needs_user_session is False
        assert s.uses_cdp

    def test_strategy_always_has_reason(self):
        for goal, cdp, running in [
            ("x", True, True), ("my dm", False, False),
            ("my dm", False, True), ("research x", False, True),
        ]:
            s = resolve_browser_strategy(
                goal, cdp_reachable_fn=lambda p: cdp, chrome_running_fn=lambda p: running
            )
            assert s.reason
            assert isinstance(s.mode, BrowserMode)
