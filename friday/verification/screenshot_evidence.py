"""Screenshot evidence — visual proof + stuck-state detection.

Two jobs:
1. Capture real screenshots to disk so the operator has VISUAL evidence of
   what actually happened (not just text claims). Saved under the FRIDAY
   evidence directory with timestamped names.
2. Detect "stuck" states the Truth Report surfaced — most importantly a
   CAPTCHA / "unusual traffic" / verification wall that traps the operator
   in a loop (it kept opening Google captcha tabs and never advanced).

A captcha/verification page is NOT progress. The operator must treat it as a
blocked state, stop re-trying the same path, and surface it honestly rather
than spawning more tabs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Signals that a page is a verification/captcha/block wall, not real content.
_BLOCK_SIGNALS = (
    "captcha",
    "unusual traffic",
    "verify you are human",
    "are you a robot",
    "i'm not a robot",
    "recaptcha",
    "hcaptcha",
    "cloudflare",
    "checking your browser",
    "before you continue",
    "detected unusual",
    "complete the security check",
    "verify it's you",
    "confirm you're not a robot",
)


def _evidence_dir() -> Path:
    """Directory where screenshot evidence is stored."""
    base = os.environ.get("FRIDAY_EVIDENCE_DIR")
    if base:
        d = Path(base)
    else:
        d = Path.home() / ".friday" / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class ScreenshotResult:
    """Outcome of a screenshot capture."""

    path: str = ""
    size: int = 0
    captured: bool = False
    label: str = ""

    @property
    def is_real(self) -> bool:
        return self.captured and self.size > 0


def capture_screenshot(label: str = "", screen_capture=None) -> ScreenshotResult:
    """Capture the screen to a timestamped file and return proof.

    Args:
        label: short label included in the filename (e.g. "after_navigate").
        screen_capture: optional ScreenCapture instance (for injection/tests).

    Returns:
        ScreenshotResult with the saved path and byte size (0 if it failed).
    """
    try:
        if screen_capture is None:
            from friday.perception.screen import ScreenCapture
            screen_capture = ScreenCapture()

        shot = screen_capture.grab()
        if shot is None:
            return ScreenshotResult(captured=False, label=label)

        safe_label = "".join(c for c in label if c.isalnum() or c in ("_", "-"))[:40]
        fname = f"{int(time.time()*1000)}_{safe_label or 'screen'}.png"
        path = _evidence_dir() / fname
        shot.save(str(path))

        size = path.stat().st_size if path.exists() else 0
        return ScreenshotResult(
            path=str(path), size=size, captured=size > 0, label=label,
        )
    except Exception:
        return ScreenshotResult(captured=False, label=label)


def is_blocked_page(page_text: str, url: str = "", title: str = "") -> bool:
    """Detect a captcha / verification / block wall.

    Returns True when the page looks like a verification wall rather than the
    real content the operator was trying to reach. This is the signal to STOP
    re-trying the same path (which previously caused the captcha tab-spam loop).
    """
    haystack = " ".join([page_text or "", url or "", title or ""]).lower()
    if not haystack.strip():
        return False
    return any(sig in haystack for sig in _BLOCK_SIGNALS)


def blocked_reason(page_text: str, url: str = "", title: str = "") -> str:
    """Return the specific block signal matched, for honest reporting."""
    haystack = " ".join([page_text or "", url or "", title or ""]).lower()
    for sig in _BLOCK_SIGNALS:
        if sig in haystack:
            return f"verification/captcha wall detected ('{sig}')"
    return ""
