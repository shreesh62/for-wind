"""Ch 30 — window enumeration and control (wraps SystemActions + pyautogui).

The ``WindowManager`` enumerates, focuses, launches, resizes, moves, minimizes,
and restores windows. It wraps the live-verified ``SystemActions`` (for
``launch_app``, ``focus_window``, and ``list_windows``) and uses
``pyautogui.getWindowsWithTitle`` for geometry operations. ``SystemActions`` is
injected and wrapped — never modified.

Every window operation returns an ``ActionResult`` whose ``ActionEvidence``
reports ``window_changed`` on success. ``launch`` and ``focus`` take the
application name / window title from the call arguments; there is no hardcoded
application identifier anywhere in this manager.

Under ``FRIDAY_DRY_RUN=1`` the ``pyautogui`` window backend typically returns
nothing, so enumeration yields an empty list and geometry operations report a
``window_not_found`` failure — no real OS window manipulation occurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.system import SystemActions


@dataclass
class WindowInfo:
    """Lightweight descriptor of an open window.

    Distinct from ``friday.perception.types.WindowInfo`` (which is a
    process-centric perception signal requiring a ``process_name``/``pid``);
    here we only need geometry and focus for window-management operations.
    """

    title: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    is_active: bool = False


def _get_windows_with_title(title_substring: str) -> list:
    """Return pyautogui windows matching ``title_substring`` (``[]`` on error).

    Wrapped in try/except so a missing/failed ``pyautogui`` backend (as under
    ``FRIDAY_DRY_RUN=1``) yields an empty list rather than raising.
    """
    try:
        import pyautogui  # type: ignore

        return list(pyautogui.getWindowsWithTitle(title_substring) or [])
    except Exception:
        return []


def _get_all_windows() -> list:
    """Return all pyautogui windows (``[]`` on error)."""
    try:
        import pyautogui  # type: ignore

        return list(pyautogui.getAllWindows() or [])
    except Exception:
        return []


class WindowManager:
    """Ch 30 — window enumeration and control (wraps SystemActions + pyautogui)."""

    def __init__(self, system_actions: Optional[SystemActions] = None) -> None:
        self._system_actions = system_actions or SystemActions()

    # --- enumeration -----------------------------------------------------

    def enumerate(self) -> List[WindowInfo]:
        """Enumerate all open windows as ``WindowInfo``.

        Titles come from ``SystemActions.list_windows()``; geometry/focus are
        enriched from the pyautogui window handle when available. Under
        DRY_RUN this typically returns an empty list.
        """
        titles = self._system_actions.list_windows()
        infos: List[WindowInfo] = []
        for title in titles:
            info = WindowInfo(title=title)
            matches = _get_windows_with_title(title)
            if matches:
                win = matches[0]
                info = _window_info_from_handle(title, win)
            infos.append(info)
        return infos

    def active_window(self) -> Optional[WindowInfo]:
        """Return the currently active window, or ``None`` if none/unknown."""
        try:
            import pyautogui  # type: ignore

            win = pyautogui.getActiveWindow()
        except Exception:
            win = None
        if win is None:
            return None
        title = getattr(win, "title", "") or ""
        info = _window_info_from_handle(title, win)
        info.is_active = True
        return info

    # --- delegated verbs (wrap SystemActions) ---------------------------

    def focus(self, title_substring: str) -> ActionResult:
        """Bring a window to the foreground by title match.

        Delegates to ``SystemActions.focus_window``; the title comes from the
        call argument, never a hardcoded identifier. Ensures the returned
        evidence reports ``window_changed`` on success.
        """
        result = self._system_actions.focus_window(title_substring)
        if result.is_success:
            result.evidence.window_changed = True
        return result

    def launch(self, app_name: str) -> ActionResult:
        """Launch an application by name.

        Delegates to ``SystemActions.launch_app``; the app name comes from the
        call argument, never a hardcoded identifier. Ensures the returned
        evidence reports ``window_changed`` on success.
        """
        result = self._system_actions.launch_app(app_name)
        if result.is_success:
            result.evidence.window_changed = True
        return result

    # --- geometry verbs (wrap pyautogui window handles) -----------------

    def resize(self, title_substring: str, w: int, h: int) -> ActionResult:
        """Resize the first window matching ``title_substring`` to ``w`` x ``h``."""
        return self._geometry_op(
            action="resize",
            title_substring=title_substring,
            op=lambda win: win.resizeTo(w, h),
            raw={"width": w, "height": h},
        )

    def move(self, title_substring: str, x: int, y: int) -> ActionResult:
        """Move the first window matching ``title_substring`` to ``(x, y)``."""
        return self._geometry_op(
            action="move",
            title_substring=title_substring,
            op=lambda win: win.moveTo(x, y),
            raw={"x": x, "y": y},
        )

    def minimize(self, title_substring: str) -> ActionResult:
        """Minimize the first window matching ``title_substring``."""
        return self._geometry_op(
            action="minimize",
            title_substring=title_substring,
            op=lambda win: win.minimize(),
            raw={},
        )

    def restore(self, title_substring: str) -> ActionResult:
        """Restore the first window matching ``title_substring``."""
        return self._geometry_op(
            action="restore",
            title_substring=title_substring,
            op=lambda win: win.restore(),
            raw={},
        )

    # --- internal helpers -----------------------------------------------

    def _geometry_op(self, action, title_substring, op, raw) -> ActionResult:
        """Run a pyautogui window geometry op, wrapped in try/except.

        Returns ``ActionResult.failed`` with ``window_not_found`` when no
        window matches (the common DRY_RUN case), and a success carrying
        ``window_changed`` evidence when the op is applied.
        """
        matches = _get_windows_with_title(title_substring)
        if not matches:
            return ActionResult.failed(
                action=action,
                error=f"No window matching '{title_substring}'",
                target=title_substring,
                error_category="window_not_found",
                repair_hints=["check_app_open", "launch_app_first"],
            )
        win = matches[0]
        try:
            op(win)
        except Exception as exc:
            return ActionResult.failed(
                action=action,
                error=str(exc),
                target=title_substring,
                error_category="window_op_failed",
            )
        return ActionResult.success(
            action=action,
            target=title_substring,
            message=f"{action} applied to '{getattr(win, 'title', title_substring)}'",
            evidence=ActionEvidence(
                window_changed=True,
                state_changed=True,
                raw={"window_title": getattr(win, "title", title_substring), **raw},
            ),
        )


def _window_info_from_handle(title: str, win: object) -> WindowInfo:
    """Build a ``WindowInfo`` from a pyautogui window handle, defensively."""
    return WindowInfo(
        title=title or getattr(win, "title", "") or "",
        x=int(getattr(win, "left", 0) or 0),
        y=int(getattr(win, "top", 0) or 0),
        width=int(getattr(win, "width", 0) or 0),
        height=int(getattr(win, "height", 0) or 0),
        is_active=bool(getattr(win, "isActive", False)),
    )
