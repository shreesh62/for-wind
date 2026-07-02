"""Environment perception — what's already running, open, available.

Per ADR-020: Every task begins with observation. FRIDAY must know
what applications, windows, tabs, and files are already available
before deciding what to do. Skip unnecessary work. Reuse existing state.

This module observes the full machine environment:
- Running processes / applications
- Open windows (titles, apps)
- Browser tabs (if connected)
- Active sessions (logged-in state)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


@dataclass
class RunningApp:
    """A running application."""

    name: str
    pid: int
    window_title: str = ""
    is_foreground: bool = False


@dataclass
class OpenWindow:
    """An open window on the desktop."""

    title: str
    app_name: str = ""
    is_minimized: bool = False
    is_foreground: bool = False


@dataclass
class BrowserTab:
    """A browser tab (when connected via DevTools)."""

    url: str
    title: str
    active: bool = False


@dataclass
class EnvironmentState:
    """Complete environment snapshot — what's already available.

    The planner uses this to decide:
    - Is the needed app already open? (reuse it)
    - Is the target tab already open? (switch to it)
    - Is the file already open? (don't reopen)
    - What's the fastest path to the goal?
    """

    timestamp: float = 0.0
    running_apps: List[RunningApp] = field(default_factory=list)
    open_windows: List[OpenWindow] = field(default_factory=list)
    browser_tabs: List[BrowserTab] = field(default_factory=list)
    foreground_window: Optional[str] = None
    foreground_app: Optional[str] = None

    def is_app_running(self, app_name: str) -> bool:
        """Check if an app is currently running."""
        target = app_name.lower()
        return any(target in app.name.lower() for app in self.running_apps)

    def is_window_open(self, title_substring: str) -> bool:
        """Check if a window with the given title is open."""
        target = title_substring.lower()
        return any(target in w.title.lower() for w in self.open_windows)

    def find_window(self, title_substring: str) -> Optional[OpenWindow]:
        """Find a window by title substring."""
        target = title_substring.lower()
        for w in self.open_windows:
            if target in w.title.lower():
                return w
        return None

    def is_tab_open(self, url_substring: str) -> bool:
        """Check if a browser tab with the URL is already open."""
        target = url_substring.lower()
        return any(target in tab.url.lower() for tab in self.browser_tabs)

    def find_tab(self, url_or_title: str) -> Optional[BrowserTab]:
        """Find a browser tab by URL or title."""
        target = url_or_title.lower()
        for tab in self.browser_tabs:
            if target in tab.url.lower() or target in tab.title.lower():
                return tab
        return None

    def get_reusable_state(self, goal_keywords: List[str]) -> Dict[str, bool]:
        """Determine what's already available for a given goal.

        Returns a dict of what can be reused vs needs opening.
        """
        state = {}
        for kw in goal_keywords:
            kw_lower = kw.lower()
            state[f"app_{kw}_running"] = self.is_app_running(kw)
            state[f"window_{kw}_open"] = self.is_window_open(kw)
            state[f"tab_{kw}_open"] = self.is_tab_open(kw)
        return state


class EnvironmentObserver:
    """Observes the full machine environment.

    Call snapshot() to get the current EnvironmentState.
    The planner uses this BEFORE deciding actions — observe reality first.

    Usage:
        observer = EnvironmentObserver()
        env = observer.snapshot()

        if env.is_app_running("chrome"):
            # Chrome already open — just switch to it
            if env.is_tab_open("instagram"):
                # Instagram tab exists — switch to it directly
                # Skip: open Chrome, navigate to Instagram
    """

    def __init__(self, browser_session=None) -> None:
        """Initialize with optional browser session for tab info."""
        self._browser_session = browser_session

    def snapshot(self) -> EnvironmentState:
        """Capture the current environment state."""
        env = EnvironmentState(timestamp=time.time())

        # Get running apps
        env.running_apps = self._get_running_apps()

        # Get open windows
        env.open_windows = self._get_open_windows()

        # Determine foreground
        if env.open_windows:
            fg = next((w for w in env.open_windows if w.is_foreground), None)
            if fg:
                env.foreground_window = fg.title
                env.foreground_app = fg.app_name

        # Browser tabs (if session connected)
        # This would use DevTools CDP to list all tabs
        # Deferred to when browser session is connected

        return env

    def _get_running_apps(self) -> List[RunningApp]:
        """Get list of running user applications."""
        if not PSUTIL_AVAILABLE:
            return []

        apps = []
        seen = set()
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    name = proc.info['name'] or ""
                    if not name or name in seen:
                        continue
                    # Filter to user-facing apps (skip system processes)
                    if self._is_user_app(name):
                        seen.add(name)
                        apps.append(RunningApp(
                            name=name,
                            pid=proc.info['pid'],
                        ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return apps

    def _get_open_windows(self) -> List[OpenWindow]:
        """Get all open windows with titles."""
        if not PYAUTOGUI_AVAILABLE:
            return []

        windows = []
        try:
            for win in pyautogui.getAllWindows():
                if win.title and len(win.title.strip()) > 0:
                    windows.append(OpenWindow(
                        title=win.title,
                        is_minimized=win.isMinimized if hasattr(win, 'isMinimized') else False,
                        is_foreground=win.isActive if hasattr(win, 'isActive') else False,
                    ))
        except Exception:
            pass
        return windows

    def _is_user_app(self, name: str) -> bool:
        """Filter to user-facing applications."""
        user_apps = {
            "chrome.exe", "firefox.exe", "msedge.exe",
            "notepad.exe", "code.exe", "explorer.exe",
            "spotify.exe", "discord.exe", "slack.exe",
            "winword.exe", "excel.exe", "powerpnt.exe",
            "windowsterminal.exe", "wt.exe", "cmd.exe",
            "python.exe", "calc.exe", "mspaint.exe",
            "outlook.exe", "teams.exe",
        }
        return name.lower() in user_apps
