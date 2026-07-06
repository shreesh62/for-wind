"""Ch 30 — clipboard read/write with bounded history.

Enables copy/paste-based data transfer between environments as a general,
app-agnostic transport. History is bounded (oldest evicted) and returned
newest-first.

Under ``FRIDAY_DRY_RUN=1`` the OS clipboard is mocked with an in-memory
buffer so no real clipboard I/O occurs during tests. When not in dry-run,
a real clipboard backend is attempted via a lazy import (``pyperclip`` or
``win32clipboard``) and falls back to the in-memory buffer if unavailable —
this manager never crashes on a missing backend.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

from friday.actions.result import ActionEvidence, ActionResult


@dataclass
class ClipboardEntry:
    """A single recorded clipboard write."""

    text: str
    timestamp: float


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"


class ClipboardManager:
    """Ch 30 — clipboard read/write with bounded history."""

    def __init__(self, history_limit: int = 25) -> None:
        self._history_limit = max(0, history_limit)
        self._history: List[ClipboardEntry] = []  # oldest-first internally
        self._buffer: Optional[str] = None  # in-memory clipboard backing

    # --- backend ---------------------------------------------------------

    def _read_backend(self) -> Optional[str]:
        """Read the OS clipboard, or the in-memory buffer under DRY_RUN."""
        if _is_dry_run():
            return self._buffer
        try:  # pragma: no cover - real OS path, not exercised under DRY_RUN
            import pyperclip  # type: ignore

            return pyperclip.paste()
        except Exception:
            pass
        try:  # pragma: no cover - real OS path
            import win32clipboard  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                data = win32clipboard.GetClipboardData()
            finally:
                win32clipboard.CloseClipboard()
            return data
        except Exception:
            pass
        # Backend unavailable — fall back to in-memory buffer.
        return self._buffer

    def _write_backend(self, text: str) -> None:
        """Write to the OS clipboard, or the in-memory buffer under DRY_RUN."""
        # Always keep the in-memory buffer in sync as a fallback.
        self._buffer = text
        if _is_dry_run():
            return
        try:  # pragma: no cover - real OS path, not exercised under DRY_RUN
            import pyperclip  # type: ignore

            pyperclip.copy(text)
            return
        except Exception:
            pass
        try:  # pragma: no cover - real OS path
            import win32clipboard  # type: ignore

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            # Never crash — in-memory buffer already holds the value.
            pass

    # --- public API ------------------------------------------------------

    def read(self) -> Optional[str]:
        """Return the current clipboard contents, or ``None`` if empty."""
        return self._read_backend()

    def write(self, text: str) -> ActionResult:
        """Write ``text`` to the clipboard and record a history entry."""
        self._write_backend(text)
        entry = ClipboardEntry(text=text, timestamp=time.time())
        self._history.append(entry)
        # Evict oldest beyond the limit.
        if self._history_limit >= 0 and len(self._history) > self._history_limit:
            overflow = len(self._history) - self._history_limit
            self._history = self._history[overflow:]
        evidence = ActionEvidence(
            state_changed=True,
            text_appeared=text,
            raw={"history_len": len(self._history)},
        )
        return ActionResult.success(
            action="copy",
            target="clipboard",
            message="clipboard write recorded",
            evidence=evidence,
        )

    def history(self) -> List[ClipboardEntry]:
        """History newest-first, length ``<= history_limit``."""
        return list(reversed(self._history))

    def clear_history(self) -> None:
        """Drop all recorded history entries."""
        self._history.clear()
