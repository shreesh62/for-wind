"""Browser Access Strategy — choose HOW to operate the browser for a goal.

The browser is just one environment. When FRIDAY cannot get CDP control of the
user's real profile, it should NOT fail and should NOT silently use a clean
profile that lacks the user's logins. Instead it picks the best available path,
falling back to operating the already-open Chrome window like a human would
(desktop control: UIA + vision + keyboard + mouse).

Decision matrix:

  CDP already reachable
      -> CDP_REUSE            (attach to the running debug session; best)

  Chrome NOT running, profile configured
      -> CDP_LAUNCH          (launch user's profile with --remote-debugging-port,
                              then attach via CDP; full control + logins)

  Chrome running WITHOUT debug port (profile locked):
      task needs the user's logins / specific profile
        -> DESKTOP_CONTROL   (operate the visible Chrome window via desktop
                              automation — the user's real session, no relaunch)
      task does NOT need the user's profile
        -> CDP_DEDICATED     (spin a dedicated debug profile for clean,
                              fully-controllable automation)

This module only DECIDES. Execution uses existing components:
  - CDP_*       -> BrowserController (Playwright over CDP)
  - DESKTOP_*   -> Universal Action Layer desktop/vision adapters

M23 (Browser as a Generic Desktop Environment): the DESKTOP pipeline is the
canonical, primary path. CDP is an OPTIONAL optimization, enabled only when
FRIDAY_ENABLE_CDP is truthy. With the flag off (default), every goal resolves to
DESKTOP_CONTROL and the browser is operated as a generic desktop application —
no CDP/Playwright dependency for correctness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


def cdp_optimization_enabled() -> bool:
    """Whether the optional CDP acceleration plugin is enabled (M23).

    Default OFF: the desktop pipeline is canonical. Set FRIDAY_ENABLE_CDP=1 to
    let the strategy resolver prefer CDP when it is available. This same switch
    is the milestone's rollback control (re-enables CDP-first behavior).
    """
    return os.environ.get("FRIDAY_ENABLE_CDP", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


class BrowserMode(str, Enum):
    CDP_REUSE = "cdp_reuse"            # attach to existing debug session
    CDP_LAUNCH = "cdp_launch"         # launch user's profile + attach
    CDP_DEDICATED = "cdp_dedicated"   # dedicated clean debug profile
    DESKTOP_CONTROL = "desktop_control"  # operate visible Chrome like a human


# Keywords that imply the goal needs the user's logged-in session / identity.
_LOGIN_SIGNALS = (
    "my ", "instagram", "insta", "dm", "gmail", "email", "inbox", "whatsapp",
    "messages", "account", "profile", "logged in", "my feed", "my posts",
    "facebook", "twitter", "linkedin", "youtube studio", "drive", "calendar",
    "order", "my orders", "cart", "bank", "subscription", "notifications",
    "send a message", "reply", "post ", "upload",
)


def goal_needs_user_session(goal_text: str) -> bool:
    """Heuristic: does this goal require the user's real logged-in profile?

    Conservative — when a goal references personal/account surfaces, assume it
    needs the user's session (so FRIDAY won't use a clean profile that lacks
    their logins).
    """
    if not goal_text:
        return False
    g = goal_text.lower()
    return any(sig in g for sig in _LOGIN_SIGNALS)


@dataclass
class BrowserStrategy:
    """The resolved approach for operating the browser for a goal."""

    mode: BrowserMode
    reason: str
    needs_user_session: bool
    profile_display_name: Optional[str] = None
    profile_directory: Optional[str] = None
    user_data_dir: Optional[str] = None

    @property
    def uses_cdp(self) -> bool:
        return self.mode in (
            BrowserMode.CDP_REUSE, BrowserMode.CDP_LAUNCH, BrowserMode.CDP_DEDICATED,
        )

    @property
    def uses_desktop(self) -> bool:
        return self.mode == BrowserMode.DESKTOP_CONTROL


def resolve_browser_strategy(
    goal_text: str = "",
    port: int = 9222,
    *,
    cdp_reachable_fn=None,
    chrome_running_fn=None,
    cdp_enabled_fn=None,
) -> BrowserStrategy:
    """Decide how FRIDAY should operate the browser for this goal.

    Args:
        goal_text: the goal, used to judge whether the user's session is needed.
        port: CDP debug port.
        cdp_reachable_fn / chrome_running_fn / cdp_enabled_fn: injectable for testing.

    M23: unless the CDP optimization is enabled (FRIDAY_ENABLE_CDP), the result is
    always DESKTOP_CONTROL — the desktop pipeline is the primary path. When CDP is
    enabled, the historical decision matrix (reuse/launch/dedicated/desktop) applies.

    Never raises. Returns a BrowserStrategy.
    """
    from friday.actions.chrome_launcher import (
        cdp_reachable as _cdp, chrome_running_without_debug as _running,
    )
    from friday.config.browser_config import resolve_browser_choice

    cdp_reachable_fn = cdp_reachable_fn or _cdp
    chrome_running_fn = chrome_running_fn or _running
    cdp_enabled_fn = cdp_enabled_fn or cdp_optimization_enabled

    needs_session = goal_needs_user_session(goal_text)
    choice = resolve_browser_choice(use_dedicated_if_unset=True)

    # M23: the desktop pipeline is canonical. CDP is opt-in — when it is not
    # enabled, always operate the browser as a generic desktop application.
    if not cdp_enabled_fn():
        return BrowserStrategy(
            mode=BrowserMode.DESKTOP_CONTROL,
            reason="Desktop pipeline is the primary path; CDP optimization "
                   "disabled (set FRIDAY_ENABLE_CDP=1 to enable CDP acceleration)",
            needs_user_session=needs_session,
            profile_display_name=choice.display_name,
        )

    # --- CDP optimization enabled: historical decision matrix ---
    # 1. A debug session is already up — just reuse it (best case).
    if cdp_reachable_fn(port):
        return BrowserStrategy(
            mode=BrowserMode.CDP_REUSE,
            reason="CDP already reachable — attaching to the running session",
            needs_user_session=needs_session,
            profile_display_name=choice.display_name,
            profile_directory=choice.profile_directory,
            user_data_dir=choice.user_data_dir,
        )

    chrome_locked = chrome_running_fn(port)

    # 2. Chrome not running — we can launch the user's real profile cleanly.
    if not chrome_locked:
        return BrowserStrategy(
            mode=BrowserMode.CDP_LAUNCH,
            reason="Chrome closed — launching your profile with the debug port",
            needs_user_session=needs_session,
            profile_display_name=choice.display_name,
            profile_directory=choice.profile_directory,
            user_data_dir=choice.user_data_dir,
        )

    # 3. Chrome IS running without debug → the user's profile is locked.
    if needs_session:
        # Must use the user's real, logged-in session → operate it as a human.
        return BrowserStrategy(
            mode=BrowserMode.DESKTOP_CONTROL,
            reason="Your Chrome is open (profile locked) and this task needs "
                   "your logins — operating the visible Chrome via desktop "
                   "control (UIA/vision/keyboard) instead of relaunching",
            needs_user_session=True,
            profile_display_name=choice.display_name,
        )

    # 4. Task doesn't need the user's session → clean dedicated profile is fine.
    return BrowserStrategy(
        mode=BrowserMode.CDP_DEDICATED,
        reason="Your Chrome is open and this task does not need your logins — "
               "using a dedicated debug profile for clean automation",
        needs_user_session=False,
        profile_display_name="FRIDAY (dedicated)",
        profile_directory="Default",
    )
