"""Windows accessibility monitoring utilities."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from ctypes import WinDLL, create_unicode_buffer
from ctypes import byref
from ctypes import wintypes
from typing import Dict, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


class WindowsAccessibilityUnavailable(RuntimeError):
    """Raised when attempting to use Windows-only accessibility features on unsupported systems."""


@dataclass
class WindowSnapshot:
    """Represents a lightweight snapshot of the current foreground window."""

    title: str
    handle: int
    class_name: str
    pid: int | None = None
    process: str | None = None
    bounding_rect: tuple[int, int, int, int] | None = None

    def describe(self) -> str:
        parts = []
        if self.title:
            parts.append(f"Window: {self.title}")
        if self.class_name:
            parts.append(f"Class: {self.class_name}")
        return " | ".join(parts) if parts else "Unknown window"


class WindowsAccessibilityMonitor:
    """Utility class that reads foreground window information via Win32 APIs."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise WindowsAccessibilityUnavailable("Windows accessibility APIs are only available on Windows systems.")

        self.user32 = WinDLL("user32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowTextLengthW.restype = wintypes.INT
        self.user32.GetWindowTextW.restype = wintypes.INT
        self.user32.GetClassNameW.restype = wintypes.INT
        try:
            self.user32.GetWindowRect.restype = wintypes.BOOL
        except Exception:
            pass
        try:
            self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        except Exception:
            pass

    def get_foreground_window_snapshot(self) -> Optional[WindowSnapshot]:
        """Return details about the currently focused window, if any."""

        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None

        title_length = self.user32.GetWindowTextLengthW(hwnd)
        title_buffer = create_unicode_buffer(title_length + 1)
        self.user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)

        class_buffer = create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, class_buffer, 256)

        rect_val: tuple[int, int, int, int] | None = None
        try:
            rect = wintypes.RECT()
            ok = False
            try:
                ok = bool(self.user32.GetWindowRect(hwnd, byref(rect)))
            except Exception:
                ok = False
            if ok:
                rect_val = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            rect_val = None

        pid_val: int | None = None
        proc_name: str | None = None
        try:
            pid = wintypes.DWORD(0)
            try:
                self.user32.GetWindowThreadProcessId(hwnd, byref(pid))
                pid_val = int(pid.value) if pid.value else None
            except Exception:
                pid_val = None
        except Exception:
            pid_val = None

        if pid_val is not None and psutil is not None:
            try:
                p = psutil.Process(pid_val)
                proc_name = (p.name() or "").strip() or None
            except Exception:
                proc_name = None

        return WindowSnapshot(
            title=title_buffer.value.strip(),
            handle=hwnd,
            class_name=class_buffer.value.strip(),
            pid=pid_val,
            process=proc_name,
            bounding_rect=rect_val,
        )

    def snapshot_as_context(self) -> Optional[str]:
        """Return a human-readable description for inclusion in prompts."""

        snapshot = self.get_foreground_window_snapshot()
        if not snapshot:
            return None
        return snapshot.describe()

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Return snapshot details as a dict for logging or UI consumption."""

        snapshot = self.get_foreground_window_snapshot()
        if not snapshot:
            return {"title": None, "handle": None, "class_name": None}
        return {
            "title": snapshot.title,
            "handle": str(snapshot.handle),
            "class_name": snapshot.class_name,
            "pid": str(snapshot.pid) if snapshot.pid is not None else None,
            "process": snapshot.process,
            "bounding_rect": str(snapshot.bounding_rect) if snapshot.bounding_rect is not None else None,
        }
