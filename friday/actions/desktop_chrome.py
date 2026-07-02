"""DesktopChromeController — operate the ALREADY-OPEN Chrome like a human.

Used when the user's Chrome is open (profile locked) and the task needs their
real logged-in session, so CDP control of that profile isn't possible. Instead
of failing or using a clean profile, FRIDAY drives the visible Chrome window
with desktop control: focus the window, drive the address bar / search with the
keyboard, and read the screen via OCR + screenshot.

It deliberately exposes the SAME duck-typed surface as BrowserController
(`available`, `navigate`, `search_web`, `read_text`, `current_url`, `click`,
`type_text`) so the existing GoalExecutor can use it unchanged. The difference
is purely in HOW each action is performed (OS-level, not Playwright/CDP).

Semantic-first is not possible without the DOM here, so this is the human-like
fallback per ADR-014's last resort: vision/OCR + keyboard. It is honest about
what it can and cannot confirm.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class DesktopChromeController:
    """Operate the visible Chrome window via keyboard + screen reading.

    This is NOT CDP. There is no DOM. Actions use pyautogui hotkeys and the
    screen is read via OCR. Confirmation is best-effort (screenshot/OCR), so
    results report what was actually observed, not assumed.
    """

    def __init__(self, window_title_hint: str = "Chrome") -> None:
        self._title_hint = window_title_hint
        self._focused = False
        self._last_url = ""
        # Lazy perception components
        self._screen = None
        self._ocr = None

    # ------------------------------------------------------------------
    # Lifecycle / availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Available if a Chrome window exists and pyautogui works."""
        try:
            import pyautogui
            wins = pyautogui.getWindowsWithTitle(self._title_hint)
            return len(wins) > 0
        except Exception:
            return False

    def start(self) -> bool:
        """Focus the Chrome window so subsequent keystrokes land there."""
        return self._focus_chrome()

    def stop(self) -> None:
        self._focused = False

    def _focus_chrome(self) -> bool:
        try:
            import pyautogui
            wins = pyautogui.getWindowsWithTitle(self._title_hint)
            if not wins:
                return False
            win = wins[0]
            if getattr(win, "isMinimized", False):
                win.restore()
            win.activate()
            time.sleep(0.4)
            self._focused = True
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Perception helpers
    # ------------------------------------------------------------------

    def _read_screen_text(self, max_chars: int = 4000) -> str:
        """Capture the screen and OCR it to text (best-effort)."""
        try:
            if self._screen is None:
                from friday.perception.screen import ScreenCapture
                self._screen = ScreenCapture()
            if self._ocr is None:
                from friday.perception.ocr import OCREngine
                self._ocr = OCREngine()
            shot = self._screen.grab()
            if shot is None or not self._ocr.available:
                return ""
            text = self._ocr.extract_text(shot.image) or ""
            return text[:max_chars]
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Browser-like operations (duck-typed to match BrowserController)
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate by driving the address bar: Ctrl+L, type URL, Enter."""
        try:
            import pyautogui
            if not self._focused and not self._focus_chrome():
                return {"url": "", "ok": False, "error": "Chrome window not found"}
            pyautogui.hotkey("ctrl", "l")     # focus address bar
            time.sleep(0.2)
            pyautogui.typewrite(url, interval=0.01)
            pyautogui.press("enter")
            time.sleep(2.0)                    # allow load
            self._last_url = url
            return {"url": url, "title": "", "ok": True, "mode": "desktop"}
        except Exception as exc:
            return {"url": "", "ok": False, "error": str(exc)}

    def search_web(self, query: str) -> Dict[str, Any]:
        """Open a new tab and search via the address bar (omnibox)."""
        try:
            import pyautogui
            if not self._focused and not self._focus_chrome():
                return {"query": query, "text": "", "links": [], "ok": False,
                        "error": "Chrome window not found"}
            pyautogui.hotkey("ctrl", "t")      # new tab
            time.sleep(0.4)
            pyautogui.typewrite(query, interval=0.01)
            pyautogui.press("enter")
            time.sleep(2.5)                    # allow results to load
            text = self._read_screen_text(max_chars=5000)
            return {"query": query, "text": text, "links": [], "ok": True,
                    "engine": "omnibox", "mode": "desktop"}
        except Exception as exc:
            return {"query": query, "text": "", "links": [], "ok": False, "error": str(exc)}

    def read_text(self, max_chars: int = 4000) -> str:
        """Read the visible page via screenshot + OCR."""
        if not self._focused:
            self._focus_chrome()
        return self._read_screen_text(max_chars=max_chars)

    def current_url(self) -> str:
        """Best-effort: we cannot read the omnibox reliably without DOM.

        Returns the last URL we navigated to (honest: may be stale).
        """
        return self._last_url

    def click(self, text: str) -> Dict[str, Any]:
        """Click an element by visible text using screen OCR coordinates.

        Captures the screen, OCRs it to find the text region, and clicks its
        center. This is the human-like fallback (vision + mouse) for when DOM
        control isn't available. Honest: only succeeds if the text is found
        on screen via OCR.
        """
        try:
            import pyautogui
            if self._screen is None:
                from friday.perception.screen import ScreenCapture
                self._screen = ScreenCapture()
            if self._ocr is None:
                from friday.perception.ocr import OCREngine
                self._ocr = OCREngine()

            if not self._ocr.available:
                return {"clicked": text, "ok": False,
                        "error": "OCR unavailable; cannot locate element on screen"}

            shot = self._screen.grab()
            if shot is None:
                return {"clicked": text, "ok": False, "error": "screen capture failed"}

            regions = self._ocr.extract_regions(shot.image)
            target_lower = text.lower()
            match = None
            for r in regions:
                if target_lower in r.text.lower():
                    match = r
                    break
            if match is None:
                return {"clicked": text, "ok": False,
                        "error": f"text '{text}' not found on screen via OCR"}

            cx, cy = match.bbox.center
            pyautogui.click(cx, cy)
            time.sleep(0.5)
            return {"clicked": text, "ok": True, "mode": "desktop_ocr",
                    "coords": [cx, cy]}
        except Exception as exc:
            return {"clicked": text, "ok": False, "error": str(exc)}

    def type_text(self, text: str, selector: Optional[str] = None) -> Dict[str, Any]:
        """Type into whatever is focused in Chrome."""
        try:
            import pyautogui
            if not self._focused:
                self._focus_chrome()
            pyautogui.typewrite(text, interval=0.01)
            return {"typed": text[:50], "ok": True, "mode": "desktop"}
        except Exception as exc:
            return {"typed": text[:50], "ok": False, "error": str(exc)}

    def get_links(self, limit: int = 30) -> List[Dict[str, str]]:
        """No DOM access — cannot enumerate links in desktop mode."""
        return []

    # ------------------------------------------------------------------
    # Agentic surface (duck-typed to BrowserController) — lets the SAME
    # generic WebAgent operate the visible Chrome via OCR + vision + mouse,
    # with NO site-specific code. DOM is unavailable here, so "elements" are
    # OCR text regions and actions use absolute screen coordinates.
    # ------------------------------------------------------------------

    def _ensure_perception(self) -> bool:
        """Lazy-init screen capture + OCR. Returns True if both are usable."""
        try:
            if self._screen is None:
                from friday.perception.screen import ScreenCapture
                self._screen = ScreenCapture()
            if self._ocr is None:
                from friday.perception.ocr import OCREngine
                self._ocr = OCREngine()
            return self._screen.available and self._ocr.available
        except Exception:
            return False

    def observe_interactive(self, limit: int = 60) -> Dict[str, Any]:
        """Observe the visible Chrome via OCR — generic, no hardcoding.

        Returns the same shape as BrowserController.observe_interactive so the
        WebAgent can reason over it. Each element is an OCR text region with an
        index and absolute SCREEN coordinates (x, y) usable directly by
        pyautogui. Editability is unknown without a DOM, so it is inferred
        heuristically (short label near a box) and left False by default; the
        agent can still click a field by its label then type.
        """
        if not self._focused:
            self._focus_chrome()
        if not self._ensure_perception():
            return {"url": self._last_url, "title": "", "elements": [],
                    "ok": False, "error": "screen/OCR unavailable"}
        shot = self._screen.grab()
        if shot is None:
            return {"url": self._last_url, "title": "", "elements": [],
                    "ok": False, "error": "screen capture failed"}
        regions = self._ocr.extract_regions(shot.image)
        elements: List[Dict[str, Any]] = []
        for i, r in enumerate(regions[:limit]):
            text = (r.text or "").strip()
            if not text:
                continue
            cx, cy = r.bbox.center
            elements.append({
                "index": len(elements),
                "role": "text",
                "tag": "ocr",
                "text": text[:80],
                "editable": False,
                "selector": "",
                "in_view": True,
                "x": int(cx),
                "y": int(cy),
                "confidence": round(float(r.confidence), 2),
            })
        return {"url": self._last_url, "title": "", "elements": elements,
                "ok": True, "mode": "desktop_ocr"}

    def click_index(self, index: int, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Click the OCR element at `index` by its screen coordinates."""
        el = next((e for e in (elements or []) if e.get("index") == index), None)
        if not el:
            return {"ok": False, "error": f"no element index {index}"}
        try:
            import pyautogui
            before = self._read_screen_text(800)
            pyautogui.click(el["x"], el["y"])
            time.sleep(0.6)
            after = self._read_screen_text(800)
            return {"ok": True, "clicked_index": index, "text": el.get("text", ""),
                    "method": "ocr_coords", "changed": after != before}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def fill_index(self, index: int, value: str,
                   elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Click the field at `index`, clear it, and type `value`."""
        el = next((e for e in (elements or []) if e.get("index") == index), None)
        if not el:
            return {"ok": False, "error": f"no element index {index}"}
        try:
            import pyautogui
            pyautogui.click(el["x"], el["y"])
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("delete")
            pyautogui.typewrite(value, interval=0.02)
            time.sleep(0.3)
            # Best-effort verification via OCR of the surrounding area.
            landed = self._read_screen_text(1500)
            verified = value[:20].lower() in landed.lower() if value else True
            return {"ok": True, "filled_index": index, "value": value[:50],
                    "method": "ocr_coords", "verified": verified,
                    "landed": value[:30] if verified else ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def scroll(self, direction: str = "down", amount: int = 600) -> Dict[str, Any]:
        """Scroll the page via the mouse wheel (pyautogui)."""
        try:
            import pyautogui
            before = self._read_screen_text(800)
            clicks = -amount if direction == "down" else amount
            if direction in ("top", "bottom"):
                # Approximate: Home/End keys after focusing the page body.
                pyautogui.press("end" if direction == "bottom" else "home")
            else:
                pyautogui.scroll(clicks)
            time.sleep(0.5)
            after = self._read_screen_text(800)
            return {"ok": True, "direction": direction, "scrolled": after != before}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def press(self, key: str) -> Dict[str, Any]:
        """Press a key (Enter/Tab/etc.) in the focused Chrome."""
        try:
            import pyautogui
            if not self._focused:
                self._focus_chrome()
            # Support simple combos like "ctrl+l".
            if "+" in key:
                pyautogui.hotkey(*[k.strip() for k in key.split("+")])
            else:
                pyautogui.press(key)
            time.sleep(0.3)
            return {"ok": True, "key": key}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def screenshot_image(self):
        """Return a Screenshot (PIL image) for the vision fallback."""
        if not self._ensure_perception():
            return None
        try:
            return self._screen.grab()
        except Exception:
            return None

    def viewport_size(self) -> Dict[str, int]:
        """Return the Chrome window pixel size (for vision coord scaling)."""
        try:
            import pyautogui
            wins = pyautogui.getWindowsWithTitle(self._title_hint)
            if wins:
                w = wins[0]
                return {"width": int(getattr(w, "width", 0)) or 1280,
                        "height": int(getattr(w, "height", 0)) or 800,
                        "device_pixel_ratio": 1.0}
        except Exception:
            pass
        return {"width": 1280, "height": 800, "device_pixel_ratio": 1.0}

    def click_xy(self, x: int, y: int) -> Dict[str, Any]:
        """Click at absolute screen coordinates (vision fallback target)."""
        try:
            import pyautogui
            before = self._read_screen_text(800)
            pyautogui.click(int(x), int(y))
            time.sleep(0.5)
            after = self._read_screen_text(800)
            return {"ok": True, "x": int(x), "y": int(y), "changed": after != before}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
