"""Browser factory — pick and build the right controller for a goal.

Bridges the DECISION layer (browser_strategy.resolve_browser_strategy) to the
EXECUTION layer. Both controllers expose the SAME duck-typed surface
(observe_interactive / click_index / fill_index / scroll / press / navigate /
screenshot_image / viewport_size / click_xy / current_url), so whatever this
returns can be handed to GoalExecutor or WebAgent unchanged.

Modes:
  CDP_REUSE / CDP_LAUNCH / CDP_DEDICATED -> BrowserController over CDP
      (launches the right profile or a dedicated debug profile first)
  DESKTOP_CONTROL                        -> DesktopChromeController
      (operates the user's already-open Chrome via OCR + vision + keyboard;
       used when the signed-in profile blocks CDP, e.g. Google Sync)

Never raises — returns (controller_or_None, strategy). The controller is
already started() when returned successfully.
"""

from __future__ import annotations

from typing import Optional, Tuple

from friday.actions.browser_strategy import resolve_browser_strategy, BrowserMode


def build_browser_for_goal(
    goal_text: str = "",
    port: int = 9222,
    *,
    require_real_chrome: bool = True,
):
    """Resolve the strategy for `goal_text` and return a STARTED controller.

    Returns (controller, strategy). controller is None if nothing could be
    brought up (caller should degrade gracefully / report honestly).
    """
    strategy = resolve_browser_strategy(goal_text, port=port)

    if strategy.mode == BrowserMode.DESKTOP_CONTROL:
        controller = _build_desktop_controller()
        return controller, strategy

    # All CDP modes: ensure the debug port is live, then attach.
    controller = _build_cdp_controller(strategy, port=port,
                                       require_real_chrome=require_real_chrome)
    if controller is None and strategy.needs_user_session:
        # CDP could not be established for a session-needing goal — fall back
        # to operating the visible Chrome like a human (honest last resort).
        controller = _build_desktop_controller()
    return controller, strategy


def _build_desktop_controller():
    """Build + focus a DesktopChromeController if a Chrome window exists."""
    try:
        from friday.actions.desktop_chrome import DesktopChromeController
        c = DesktopChromeController()
        if not c.available:
            return None
        c.start()  # focus the window so keystrokes land
        return c
    except Exception:
        return None


def _build_cdp_controller(strategy, port: int, require_real_chrome: bool):
    """Ensure CDP is up for the resolved strategy, then return a controller."""
    try:
        from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
        from friday.actions.browser_controller import BrowserController

        if not cdp_reachable(port):
            if strategy.mode == BrowserMode.CDP_DEDICATED:
                launch = ensure_chrome_debug(port=port, force_dedicated=True)
            elif strategy.mode == BrowserMode.CDP_LAUNCH:
                launch = ensure_chrome_debug(
                    port=port,
                    user_data_dir=strategy.user_data_dir,
                    profile_directory=strategy.profile_directory,
                    allow_dedicated_profile=False,
                )
            else:  # CDP_REUSE but not reachable -> best effort dedicated
                launch = ensure_chrome_debug(port=port, force_dedicated=True)
            if not launch.ok:
                return None

        controller = BrowserController(
            remote_debug_port=port, require_real_chrome=require_real_chrome
        )
        if not controller.start():
            return None
        return controller
    except Exception:
        return None
