"""Ch 30 — session/power state observation and safe restore.

This manager is read-mostly: it observes session/power state (lock detection,
idle/active) and can safely restore a previously captured working set of
windows. State-changing verbs (``lock``) are high-risk and gated behind an
explicit ``allow_session_control`` flag — locking a user's session is
destructive and must never happen implicitly.

Under ``FRIDAY_DRY_RUN=1`` power/lock queries are mocked: ``power_state``
returns ``ACTIVE`` and ``is_locked`` returns ``False`` so tests never touch
real OS session APIs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from friday.actions.result import ActionEvidence, ActionResult


class PowerState(str, Enum):
    """Coarse session/power state."""

    ACTIVE = "active"
    IDLE = "idle"
    LOCKED = "locked"
    UNKNOWN = "unknown"


@dataclass
class SessionSnapshot:
    """A capture of the working set for later restore.

    ``windows`` holds lightweight per-window descriptors (title, geometry);
    ``focused`` is the title of the focused window, if any.
    """

    windows: List[dict] = field(default_factory=list)
    focused: Optional[str] = None
    captured_at: float = 0.0


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"


class SessionManager:
    """Ch 30 — session/power state observation and safe restore."""

    def __init__(self, allow_session_control: bool = False) -> None:
        self._allow_session_control = allow_session_control

    # --- observation -----------------------------------------------------

    def power_state(self) -> PowerState:
        """Return the current power state. ACTIVE under DRY_RUN."""
        if _is_dry_run():
            return PowerState.ACTIVE
        try:  # pragma: no cover - real OS path, not exercised under DRY_RUN
            import ctypes  # type: ignore

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            # A locked workstation has no accessible foreground window.
            hwnd = user32.GetForegroundWindow()
            if hwnd == 0:
                return PowerState.LOCKED
            return PowerState.ACTIVE
        except Exception:
            return PowerState.UNKNOWN

    def is_locked(self) -> bool:
        """Whether the workstation is locked. False under DRY_RUN."""
        if _is_dry_run():
            return False
        return self.power_state() == PowerState.LOCKED

    def snapshot(self) -> SessionSnapshot:
        """Capture the current working set of windows and focus."""
        windows: List[dict] = []
        focused: Optional[str] = None
        if not _is_dry_run():
            try:  # pragma: no cover - real OS path
                import pygetwindow  # type: ignore

                for win in pygetwindow.getAllWindows():
                    if not win.title:
                        continue
                    windows.append(
                        {
                            "title": win.title,
                            "x": win.left,
                            "y": win.top,
                            "width": win.width,
                            "height": win.height,
                        }
                    )
                    if getattr(win, "isActive", False):
                        focused = win.title
            except Exception:
                pass
        return SessionSnapshot(
            windows=windows,
            focused=focused,
            captured_at=time.time(),
        )

    # --- state-changing verbs -------------------------------------------

    def restore(self, snapshot: SessionSnapshot) -> ActionResult:
        """Re-focus and reposition only the windows recorded in ``snapshot``."""
        restored: List[str] = []
        if not _is_dry_run():
            try:  # pragma: no cover - real OS path
                import pygetwindow  # type: ignore

                for spec in snapshot.windows:
                    title = spec.get("title", "")
                    if not title:
                        continue
                    matches = pygetwindow.getWindowsWithTitle(title)
                    if not matches:
                        continue
                    win = matches[0]
                    try:
                        win.moveTo(spec.get("x", win.left), spec.get("y", win.top))
                        win.resizeTo(
                            spec.get("width", win.width),
                            spec.get("height", win.height),
                        )
                        restored.append(title)
                    except Exception:
                        continue
                if snapshot.focused:
                    focus_matches = pygetwindow.getWindowsWithTitle(snapshot.focused)
                    if focus_matches:
                        try:
                            focus_matches[0].activate()
                        except Exception:
                            pass
            except Exception:
                pass
        else:
            restored = [
                spec.get("title", "")
                for spec in snapshot.windows
                if spec.get("title")
            ]

        evidence = ActionEvidence(
            state_changed=bool(restored),
            window_changed=bool(restored),
            focus_changed=snapshot.focused is not None,
            raw={"restored": restored},
        )
        return ActionResult.success(
            action="restore",
            target="session",
            message=f"restored {len(restored)} window(s)",
            evidence=evidence,
        )

    def lock(self) -> ActionResult:
        """Lock the workstation. HIGH-RISK — gated by ``allow_session_control``.

        When session control is disabled this returns ``ActionResult.blocked``
        and applies no state change whatsoever.
        """
        if not self._allow_session_control:
            return ActionResult.blocked(
                action="lock",
                reason="session_control_disabled",
                target="session",
            )
        if _is_dry_run():
            return ActionResult.success(
                action="lock",
                target="session",
                message="lock (dry-run, no-op)",
                evidence=ActionEvidence(state_changed=True, raw={"dry_run": True}),
            )
        try:  # pragma: no cover - real OS path
            import ctypes  # type: ignore

            ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            return ActionResult.success(
                action="lock",
                target="session",
                message="workstation locked",
                evidence=ActionEvidence(state_changed=True),
            )
        except Exception as exc:  # pragma: no cover - real OS path
            return ActionResult.failed(
                action="lock",
                error=str(exc),
                target="session",
            )
