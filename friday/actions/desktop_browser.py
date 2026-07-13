"""DesktopBrowserController — operate ANY browser as a generic desktop app.

M23 (Browser as a Generic Desktop Environment): FRIDAY treats Chrome, Edge,
Firefox, Brave, Arc, Electron apps, and future browsers as ordinary desktop
applications. This controller operates whatever window is in the FOREGROUND
through the shared perception stack (Accessibility/UIA -> OCR -> pixels, via
``observe_active_window``) and the Motor System (keyboard + mouse). It contains:

  * NO browser-name checks,
  * NO window-title assumptions (it acts on the active window),
  * NO OCR-only perception (it fuses UIA + OCR),

so the SAME code drives every browser; only measured performance differs, never
correctness (Axiom 15). It exposes the same duck-typed surface as
``BrowserController`` so ``GoalExecutor`` / ``WebAgent`` use it unchanged; the
difference is purely HOW each action is performed (OS-level, not CDP/Playwright).

Navigation uses the universal address-bar focus shortcut (Ctrl+L, standard across
Chromium browsers and Firefox) then types the URL and commits — an affordance
every browser exposes, selected by capability rather than application identity.
Confirmation is honest: results report what was observed, never assumed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class DesktopBrowserController:
    """Operate the active browser window via fused perception + keyboard/mouse.

    Not CDP; there is no DOM. Perception is the fused ``WorldState`` (UIA + OCR +
    pixels) for the foreground window; interaction is keyboard/mouse via pyautogui.
    """

    def __init__(self) -> None:
        self._started = False
        self._last_url = ""
        # The window that was in the foreground when we started — i.e. the target
        # browser (launched/focused by the caller). Re-asserted before each action
        # so keystrokes and screen reads land on the right window. Generic: this is
        # NOT matched by title/name, it is simply "the window we were given".
        self._window = None
        # Lazy, cached perception components (shared across observe calls).
        self._screen = None
        self._ocr = None
        self._desktop = None

    # ------------------------------------------------------------------
    # Lifecycle / availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Available when desktop motor control (pyautogui) is importable.

        Generic: does not require any specific application/window to exist —
        the controller acts on whatever window is in the foreground.
        """
        try:
            import pyautogui  # noqa: F401
            return True
        except Exception:
            return False

    def start(self) -> bool:
        """Begin operating the current foreground window (the target browser).

        Captures the active window so it can be re-focused before each action —
        essential for reliable desktop control (keystrokes/OCR must hit the right
        window). No app-specific focusing / no title match.
        """
        if not self.available:
            return False
        self._started = True
        try:
            import pyautogui
            self._window = pyautogui.getActiveWindow()
        except Exception:
            self._window = None
        return True

    def stop(self) -> None:
        self._started = False

    def _ensure_foreground(self) -> None:
        """Re-assert focus on the target window before an action (best-effort).

        Reliability, not identity: brings back the window we were given so an
        intervening focus change (IDE/terminal) doesn't send our keystrokes or OCR
        to the wrong place. Silent on failure (SetForegroundWindow can be refused).
        """
        win = self._window
        if win is None:
            return
        try:
            if getattr(win, "isMinimized", False):
                win.restore()
            win.activate()
            time.sleep(0.3)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Perception (fused UIA + OCR + pixels for the active window)
    # ------------------------------------------------------------------

    def _window_region(self):
        """(x, y, w, h) of the target window, or None — scopes perception to it."""
        win = self._window
        if win is None:
            return None
        try:
            left = int(getattr(win, "left"))
            top = int(getattr(win, "top"))
            width = int(getattr(win, "width"))
            height = int(getattr(win, "height"))
            if width > 0 and height > 0:
                return (left, top, width, height)
        except Exception:
            pass
        return None

    def _observe_world(self):
        """Return a fused WorldState for the active window, or None on failure."""
        from friday.perception.active_window import observe_active_window
        self._ensure_foreground()  # read/observe the TARGET window, not whatever stole focus
        try:
            return observe_active_window(
                desktop=self._desktop, ocr=self._ocr, screen=self._screen,
                region=self._window_region(),
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Browser-like operations (duck-typed to match BrowserController)
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate by driving the address bar: Ctrl+L, type URL, Enter.

        Ctrl+L focuses the address bar in every mainstream browser (Chromium
        family and Firefox), so this path is browser-agnostic.
        """
        try:
            import pyautogui
            if not self._started and not self.start():
                return {"url": "", "ok": False, "error": "desktop control unavailable"}
            self._ensure_foreground()
            pyautogui.hotkey("ctrl", "l")   # focus address bar (universal)
            time.sleep(0.2)
            pyautogui.typewrite(url, interval=0.01)
            pyautogui.press("enter")
            time.sleep(2.0)                  # allow load
            self._last_url = url
            return {"url": url, "title": "", "ok": True, "mode": "desktop"}
        except Exception as exc:
            return {"url": "", "ok": False, "error": str(exc)}

    def search_web(self, query: str) -> Dict[str, Any]:
        """Open a new tab and search via the address bar (omnibox)."""
        try:
            import pyautogui
            if not self._started and not self.start():
                return {"query": query, "text": "", "links": [], "ok": False,
                        "error": "desktop control unavailable"}
            self._ensure_foreground()
            pyautogui.hotkey("ctrl", "t")    # new tab (universal)
            time.sleep(0.4)
            pyautogui.typewrite(query, interval=0.01)
            pyautogui.press("enter")
            time.sleep(2.5)                  # allow results to load
            text = self.read_text(5000)
            return {"query": query, "text": text, "links": [], "ok": True,
                    "engine": "omnibox", "mode": "desktop"}
        except Exception as exc:
            return {"query": query, "text": "", "links": [], "ok": False, "error": str(exc)}

    def read_text(self, max_chars: int = 4000) -> str:
        """Read the visible window via fused perception (UIA text + OCR)."""
        ws = self._observe_world()
        if ws is None:
            return ""
        try:
            from friday.perception.priority import PerceptionResolver
            text = PerceptionResolver().read_text(ws)
        except Exception:
            text = ws.all_text if ws else ""
        return (text or "")[:max_chars]

    def current_url(self) -> str:
        """Best-effort: without a DOM we return the last URL navigated to."""
        return self._last_url

    def click(self, text: str) -> Dict[str, Any]:
        """Click an element by visible text, resolved semantic-first (UIA>OCR).

        Uses the fused WorldState + PerceptionResolver so a UI-Automation element
        wins over an OCR region when both match — better than OCR-only. Honest:
        only succeeds if the target is found in perception.
        """
        try:
            import pyautogui
            ws = self._observe_world()
            if ws is None:
                return {"clicked": text, "ok": False, "error": "perception unavailable"}
            from friday.perception.priority import PerceptionResolver
            resolved = PerceptionResolver().find_element(ws, text)
            if resolved is None or resolved.bbox is None:
                return {"clicked": text, "ok": False,
                        "error": f"text '{text}' not found in perception"}
            x, y, w, h = resolved.bbox
            cx, cy = int(x + w // 2), int(y + h // 2)
            pyautogui.click(cx, cy)
            time.sleep(0.5)
            return {"clicked": text, "ok": True, "mode": "desktop",
                    "source": resolved.source.value, "coords": [cx, cy]}
        except Exception as exc:
            return {"clicked": text, "ok": False, "error": str(exc)}

    def type_text(self, text: str, selector: Optional[str] = None) -> Dict[str, Any]:
        """Type text into whatever is focused in the active window."""
        try:
            import pyautogui
            if not self._started:
                self.start()
            self._ensure_foreground()
            pyautogui.typewrite(text, interval=0.01)
            return {"typed": text[:50], "ok": True, "mode": "desktop"}
        except Exception as exc:
            return {"typed": text[:50], "ok": False, "error": str(exc)}

    def get_links(self, limit: int = 30) -> List[Dict[str, str]]:
        """No DOM access — cannot enumerate hyperlinks in desktop mode."""
        return []

    # ------------------------------------------------------------------
    # Agentic surface (duck-typed to BrowserController) — lets the generic
    # WebAgent operate the active window over fused perception, no app-specific
    # code. "elements" are fused World Objects (UIA elements ranked above OCR
    # regions) with absolute SCREEN coordinates usable by pyautogui.
    # ------------------------------------------------------------------

    _EDITABLE_CONTROLS = frozenset(
        {"edit", "textbox", "document", "combobox", "input", "textarea"}
    )

    def observe_interactive(self, limit: int = 60) -> Dict[str, Any]:
        """Observe the active window's interactive World Objects (UIA + OCR).

        Returns the same shape as ``BrowserController.observe_interactive`` so the
        WebAgent can reason over it. UI-Automation elements come first (higher
        trust), then OCR regions. Editability is derived from the UIA control type
        (generic), never from application identity.
        """
        ws = self._observe_world()
        if ws is None:
            return {"url": self._last_url, "title": "", "elements": [],
                    "ok": False, "error": "perception unavailable"}
        elements: List[Dict[str, Any]] = []

        for el in ws.ui_elements:
            if el.bbox is None:
                continue
            cx, cy = el.bbox.center
            ctype = (el.control_type or "").lower()
            elements.append({
                "index": len(elements),
                "role": el.control_type or "element",
                "tag": "uia",
                "text": (el.text or "")[:80],
                "editable": ctype in self._EDITABLE_CONTROLS,
                "selector": el.automation_id or "",
                "in_view": True,
                "x": int(cx),
                "y": int(cy),
                "confidence": round(float(el.confidence), 2),
            })
            if len(elements) >= limit:
                break

        if len(elements) < limit:
            for r in ws.ocr_regions:
                cx, cy = r.bbox.center
                text = (r.text or "").strip()
                if not text:
                    continue
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
                if len(elements) >= limit:
                    break

        title = ws.active_window.title if ws.active_window else ""
        return {"url": self._last_url, "title": title, "elements": elements,
                "ok": True, "mode": "desktop"}

    def click_index(self, index: int, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Click the element at `index` by its screen coordinates."""
        el = next((e for e in (elements or []) if e.get("index") == index), None)
        if not el:
            return {"ok": False, "error": f"no element index {index}"}
        try:
            import pyautogui
            before = self.read_text(800)
            pyautogui.click(el["x"], el["y"])
            time.sleep(0.6)
            after = self.read_text(800)
            return {"ok": True, "clicked_index": index, "text": el.get("text", ""),
                    "method": "coords", "changed": after != before}
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
            landed = self.read_text(1500)
            verified = value[:20].lower() in landed.lower() if value else True
            return {"ok": True, "filled_index": index, "value": value[:50],
                    "method": "coords", "verified": verified,
                    "landed": value[:30] if verified else ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def scroll(self, direction: str = "down", amount: int = 600) -> Dict[str, Any]:
        """Scroll the active window via the mouse wheel / Home-End keys."""
        try:
            import pyautogui
            before = self.read_text(800)
            if direction in ("top", "bottom"):
                pyautogui.press("end" if direction == "bottom" else "home")
            else:
                pyautogui.scroll(-amount if direction == "down" else amount)
            time.sleep(0.5)
            after = self.read_text(800)
            return {"ok": True, "direction": direction, "scrolled": after != before}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def press(self, key: str) -> Dict[str, Any]:
        """Press a key or combo (e.g. 'enter', 'ctrl+l') in the active window."""
        try:
            import pyautogui
            if not self._started:
                self.start()
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
        try:
            if self._screen is None:
                from friday.perception.screen import ScreenCapture
                self._screen = ScreenCapture()
            return self._screen.grab()
        except Exception:
            return None

    def viewport_size(self) -> Dict[str, int]:
        """Return the active window's pixel size (for vision coord scaling)."""
        try:
            import pyautogui
            win = pyautogui.getActiveWindow()
            if win is not None:
                return {"width": int(getattr(win, "width", 0)) or 1280,
                        "height": int(getattr(win, "height", 0)) or 800,
                        "device_pixel_ratio": 1.0}
        except Exception:
            pass
        return {"width": 1280, "height": 800, "device_pixel_ratio": 1.0}

    def click_xy(self, x: int, y: int) -> Dict[str, Any]:
        """Click at absolute screen coordinates (vision fallback target)."""
        try:
            import pyautogui
            before = self.read_text(800)
            pyautogui.click(int(x), int(y))
            time.sleep(0.5)
            after = self.read_text(800)
            return {"ok": True, "x": int(x), "y": int(y), "changed": after != before}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
