"""Actions layer — all actuators with verified outcomes.

Every action in FRIDAY returns an ActionResult. No action may report
success without evidence. The verification layer consumes ActionResults
to confirm outcomes match expectations.

Subsystems:
- SystemActions: app launch, window management, file operations
- Desktop actions (Win32, UIA, pyautogui) — future module
- Browser actions (Playwright, DevTools) — future module
"""

from friday.actions.result import ActionResult, ActionStatus, ActionEvidence, ActionTimer
from friday.actions.system import SystemActions
from friday.actions.browser import BrowserActions

__all__ = [
    "ActionResult",
    "ActionStatus",
    "ActionEvidence",
    "ActionTimer",
    "SystemActions",
    "BrowserActions",
]
