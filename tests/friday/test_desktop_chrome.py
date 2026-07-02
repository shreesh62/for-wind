"""Tests for DesktopChromeController — operating visible Chrome like a human.

Mocks pyautogui and screen/OCR so no real window/keyboard I/O happens.
Proves the duck-typed surface matches BrowserController and that actions
dispatch the right keystrokes.
"""

from __future__ import annotations

import sys
import types

import pytest

from friday.actions.desktop_chrome import DesktopChromeController


class FakeWin:
    def __init__(self):
        self.isMinimized = False
        self.activated = False
    def restore(self):
        self.isMinimized = False
    def activate(self):
        self.activated = True


@pytest.fixture
def fake_pyautogui(monkeypatch):
    calls = {"hotkey": [], "typewrite": [], "press": []}
    mod = types.ModuleType("pyautogui")
    mod.getWindowsWithTitle = lambda t: [FakeWin()]
    mod.hotkey = lambda *a: calls["hotkey"].append(a)
    mod.typewrite = lambda text, interval=0: calls["typewrite"].append(text)
    mod.press = lambda k: calls["press"].append(k)
    monkeypatch.setitem(sys.modules, "pyautogui", mod)
    return calls


class TestDuckTypedSurface:
    def test_has_browser_controller_methods(self):
        c = DesktopChromeController()
        for attr in ("available", "navigate", "search_web", "read_text",
                     "current_url", "click", "type_text", "get_links"):
            assert hasattr(c, attr)


class TestAvailability:
    def test_available_true_when_window_exists(self, fake_pyautogui):
        assert DesktopChromeController().available is True

    def test_available_false_when_no_window(self, monkeypatch):
        mod = types.ModuleType("pyautogui")
        mod.getWindowsWithTitle = lambda t: []
        monkeypatch.setitem(sys.modules, "pyautogui", mod)
        assert DesktopChromeController().available is False


class TestNavigate:
    def test_navigate_drives_address_bar(self, fake_pyautogui, monkeypatch):
        monkeypatch.setattr(
            "friday.actions.desktop_chrome.time.sleep", lambda *_: None
        )
        c = DesktopChromeController()
        c.start()
        res = c.navigate("https://instagram.com")
        assert res["ok"] is True
        assert res["mode"] == "desktop"
        # Ctrl+L to focus the omnibox, then the URL typed, then Enter
        assert ("ctrl", "l") in fake_pyautogui["hotkey"]
        assert "https://instagram.com" in fake_pyautogui["typewrite"]
        assert "enter" in fake_pyautogui["press"]
        assert c.current_url() == "https://instagram.com"


class TestSearch:
    def test_search_opens_tab_and_reads_screen(self, fake_pyautogui, monkeypatch):
        monkeypatch.setattr(
            "friday.actions.desktop_chrome.time.sleep", lambda *_: None
        )
        c = DesktopChromeController()
        c.start()
        monkeypatch.setattr(c, "_read_screen_text", lambda max_chars=5000: "results text")
        res = c.search_web("best laptop")
        assert res["ok"] is True
        assert res["text"] == "results text"
        assert ("ctrl", "t") in fake_pyautogui["hotkey"]


class TestHonestLimits:
    def test_click_without_ocr_fails_gracefully(self, monkeypatch):
        """If OCR is unavailable, click reports an honest failure (no blind click)."""
        c = DesktopChromeController()

        class _NoOCR:
            available = False
            def extract_regions(self, img): return []
        class _FakeScreen:
            def grab(self): return type("S", (), {"image": object()})()
        c._ocr = _NoOCR()
        c._screen = _FakeScreen()
        res = c.click("Login")
        assert res["ok"] is False
        assert "ocr" in res["error"].lower()

    def test_get_links_empty_without_dom(self):
        assert DesktopChromeController().get_links() == []


class TestOcrClick:
    def test_click_finds_text_via_ocr_and_clicks(self, fake_pyautogui, monkeypatch):
        """Click locates the element by OCR and clicks its center."""
        from friday.perception.types import OCRRegion, BoundingBox

        c = DesktopChromeController()

        class _OCR:
            available = True
            def extract_regions(self, img):
                return [OCRRegion(text="Messages", bbox=BoundingBox(x=100, y=200, width=80, height=20), confidence=0.9)]
        class _Screen:
            def grab(self): return type("S", (), {"image": object()})()
        c._ocr = _OCR()
        c._screen = _Screen()

        clicked = {}
        import sys
        sys.modules["pyautogui"].click = lambda x, y: clicked.update({"x": x, "y": y})
        monkeypatch.setattr("friday.actions.desktop_chrome.time.sleep", lambda *_: None)

        res = c.click("Messages")
        assert res["ok"] is True
        assert res["mode"] == "desktop_ocr"
        # center of (100,200,80,20) = (140, 210)
        assert clicked["x"] == 140 and clicked["y"] == 210

    def test_click_text_not_on_screen_fails(self, fake_pyautogui, monkeypatch):
        from friday.perception.types import OCRRegion, BoundingBox
        c = DesktopChromeController()
        class _OCR:
            available = True
            def extract_regions(self, img):
                return [OCRRegion(text="Something else", bbox=BoundingBox(x=0, y=0, width=10, height=10), confidence=0.9)]
        class _Screen:
            def grab(self): return type("S", (), {"image": object()})()
        c._ocr = _OCR()
        c._screen = _Screen()
        res = c.click("Messages")
        assert res["ok"] is False
        assert "not found" in res["error"].lower()


class TestAgenticSurface:
    """The desktop controller exposes the SAME surface the WebAgent uses, so
    the generic agent can operate the visible Chrome via OCR + mouse."""

    def test_has_agentic_methods(self):
        c = DesktopChromeController()
        for attr in ("observe_interactive", "click_index", "fill_index",
                     "scroll", "press", "screenshot_image", "viewport_size",
                     "click_xy"):
            assert hasattr(c, attr), f"missing {attr}"

    def test_observe_interactive_returns_ocr_elements(self, fake_pyautogui, monkeypatch):
        from friday.perception.types import OCRRegion, BoundingBox

        c = DesktopChromeController()
        c._focused = True

        class _Screen:
            available = True
            def grab(self):
                class S: image = object()
                return S()

        class _OCR:
            available = True
            def extract_regions(self, img):
                return [
                    OCRRegion(text="Compose", bbox=BoundingBox(10, 20, 40, 10), confidence=0.9),
                    OCRRegion(text="Inbox", bbox=BoundingBox(10, 60, 40, 10), confidence=0.8),
                ]

        c._screen = _Screen()
        c._ocr = _OCR()
        snap = c.observe_interactive()
        assert snap["ok"] is True
        assert len(snap["elements"]) == 2
        first = snap["elements"][0]
        assert first["text"] == "Compose"
        # center of (10,20,40,10) = (30, 25)
        assert first["x"] == 30 and first["y"] == 25
        assert first["index"] == 0

    def test_observe_interactive_handles_no_perception(self, fake_pyautogui, monkeypatch):
        c = DesktopChromeController()
        c._focused = True
        monkeypatch.setattr(c, "_ensure_perception", lambda: False)
        snap = c.observe_interactive()
        assert snap["ok"] is False
        assert snap["elements"] == []

    def test_click_index_clicks_at_coords(self, monkeypatch):
        clicks = []
        mod = types.ModuleType("pyautogui")
        mod.click = lambda x, y: clicks.append((x, y))
        monkeypatch.setitem(sys.modules, "pyautogui", mod)
        monkeypatch.setattr(
            "friday.actions.desktop_chrome.time.sleep", lambda *_: None)

        c = DesktopChromeController()
        monkeypatch.setattr(c, "_read_screen_text", lambda n=800: "before")
        els = [{"index": 0, "text": "Compose", "x": 30, "y": 25}]
        res = c.click_index(0, els)
        assert res["ok"] is True
        assert (30, 25) in clicks
        assert "changed" in res

    def test_click_index_unknown_index_errors(self):
        c = DesktopChromeController()
        res = c.click_index(99, [{"index": 0, "text": "x", "x": 1, "y": 1}])
        assert res["ok"] is False
        assert "no element index" in res["error"]

    def test_viewport_size_from_window(self, monkeypatch):
        win = FakeWin()
        win.width = 1600
        win.height = 900
        mod = types.ModuleType("pyautogui")
        mod.getWindowsWithTitle = lambda t: [win]
        monkeypatch.setitem(sys.modules, "pyautogui", mod)
        c = DesktopChromeController()
        vs = c.viewport_size()
        assert vs["width"] == 1600 and vs["height"] == 900
        assert vs["device_pixel_ratio"] == 1.0

    def test_press_combo_uses_hotkey(self, fake_pyautogui):
        c = DesktopChromeController()
        c._focused = True
        res = c.press("ctrl+l")
        assert res["ok"] is True
        assert ("ctrl", "l") in fake_pyautogui["hotkey"]


class TestBrowserFactory:
    """The factory wires strategy -> the correct started controller."""

    def test_desktop_mode_builds_desktop_controller(self, monkeypatch):
        import friday.actions.browser_factory as bf
        from friday.actions.browser_strategy import BrowserStrategy, BrowserMode

        strat = BrowserStrategy(
            mode=BrowserMode.DESKTOP_CONTROL, reason="locked profile",
            needs_user_session=True)
        monkeypatch.setattr(bf, "resolve_browser_strategy", lambda *a, **k: strat)

        class _Desktop:
            available = True
            def start(self): return True
        monkeypatch.setattr(bf, "_build_desktop_controller", lambda: _Desktop())

        ctrl, strategy = bf.build_browser_for_goal("reply to my dm")
        assert strategy.mode == BrowserMode.DESKTOP_CONTROL
        assert isinstance(ctrl, _Desktop)

    def test_cdp_failure_for_session_goal_falls_back_to_desktop(self, monkeypatch):
        import friday.actions.browser_factory as bf
        from friday.actions.browser_strategy import BrowserStrategy, BrowserMode

        strat = BrowserStrategy(
            mode=BrowserMode.CDP_LAUNCH, reason="closed",
            needs_user_session=True)
        monkeypatch.setattr(bf, "resolve_browser_strategy", lambda *a, **k: strat)
        monkeypatch.setattr(bf, "_build_cdp_controller", lambda *a, **k: None)
        sentinel = object()
        monkeypatch.setattr(bf, "_build_desktop_controller", lambda: sentinel)

        ctrl, strategy = bf.build_browser_for_goal("open my gmail")
        assert ctrl is sentinel  # fell back to desktop
