"""Tests for DesktopBrowserController — operate ANY browser as a desktop app.

Mocks pyautogui and injects fake fused-perception sensors so no real
window/keyboard/screen I/O happens. Proves the duck-typed surface matches
BrowserController and that actions dispatch browser-agnostic keystrokes.
"""

from __future__ import annotations

import sys
import types

import pytest

from friday.actions.desktop_browser import DesktopBrowserController
from friday.perception.types import BoundingBox, OCRRegion, UIElement, WindowInfo


@pytest.fixture
def fake_pyautogui(monkeypatch):
    calls = {"hotkey": [], "typewrite": [], "press": [], "click": [], "scroll": []}
    mod = types.ModuleType("pyautogui")
    mod.hotkey = lambda *a: calls["hotkey"].append(a)
    mod.typewrite = lambda text, interval=0: calls["typewrite"].append(text)
    mod.press = lambda k: calls["press"].append(k)
    mod.click = lambda x, y: calls["click"].append((x, y))
    mod.scroll = lambda n: calls["scroll"].append(n)
    mod.getActiveWindow = lambda: None
    monkeypatch.setitem(sys.modules, "pyautogui", mod)
    monkeypatch.setattr("friday.actions.desktop_browser.time.sleep", lambda *_: None)
    return calls


class _FakeDesktop:
    def __init__(self, elements, window=None):
        self._elements = elements
        self._window = window or WindowInfo(title="Any App", process_name="x", pid=1)

    def get_active_window(self):
        return self._window

    def get_ui_elements(self):
        return list(self._elements)

    def get_cursor_position(self):
        return (0, 0)

    def get_focused_element(self):
        return None


class _FakeOCR:
    def __init__(self, regions):
        self._regions = regions
        self.available = True

    def extract_regions(self, image, min_confidence=None):
        return list(self._regions)


class _FakeScreen:
    def grab(self):
        return type("S", (), {"image": object(), "pixel_hash": "h"})()


class TestDuckTypedSurface:
    def test_has_browser_controller_methods(self):
        c = DesktopBrowserController()
        for attr in ("available", "start", "stop", "navigate", "search_web",
                     "read_text", "current_url", "click", "type_text", "get_links",
                     "observe_interactive", "click_index", "fill_index", "scroll",
                     "press", "screenshot_image", "viewport_size", "click_xy"):
            assert hasattr(c, attr), f"missing {attr}"


class TestAvailability:
    def test_available_true_when_pyautogui_importable(self, fake_pyautogui):
        assert DesktopBrowserController().available is True

    def test_available_does_not_require_a_titled_window(self, monkeypatch):
        # A pyautogui WITHOUT getWindowsWithTitle still yields available=True:
        # the controller acts on the active window, not a named one.
        mod = types.ModuleType("pyautogui")
        monkeypatch.setitem(sys.modules, "pyautogui", mod)
        assert DesktopBrowserController().available is True


class TestNavigate:
    def test_navigate_drives_address_bar(self, fake_pyautogui):
        c = DesktopBrowserController()
        c.start()
        res = c.navigate("https://example.com")
        assert res["ok"] is True and res["mode"] == "desktop"
        assert ("ctrl", "l") in fake_pyautogui["hotkey"]
        assert "https://example.com" in fake_pyautogui["typewrite"]
        assert "enter" in fake_pyautogui["press"]
        assert c.current_url() == "https://example.com"


class TestObserveInteractive:
    def test_uia_elements_rank_before_ocr(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop(
            [UIElement(text="Search", control_type="Edit",
                       bbox=BoundingBox(10, 20, 40, 10))]
        )
        c._ocr = _FakeOCR([OCRRegion(text="Footer", bbox=BoundingBox(5, 500, 60, 10),
                                     confidence=0.8)])
        c._screen = _FakeScreen()
        snap = c.observe_interactive()
        assert snap["ok"] is True
        assert len(snap["elements"]) == 2
        first = snap["elements"][0]
        assert first["tag"] == "uia" and first["text"] == "Search"
        assert first["editable"] is True         # Edit control is editable
        assert first["x"] == 30 and first["y"] == 25  # center of (10,20,40,10)
        assert snap["elements"][1]["tag"] == "ocr"


class TestClickSemanticFirst:
    def test_click_resolves_uia_and_clicks_center(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop(
            [UIElement(text="Login", control_type="Button",
                       bbox=BoundingBox(100, 200, 80, 20))]
        )
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        res = c.click("Login")
        assert res["ok"] is True and res["source"] == "uia"
        assert (140, 210) in fake_pyautogui["click"]  # center of (100,200,80,20)

    def test_click_not_found_fails_honestly(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop([])
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        res = c.click("Nonexistent")
        assert res["ok"] is False and "not found" in res["error"].lower()


class TestBrowserFactory:
    def test_desktop_mode_builds_desktop_browser_controller(self, monkeypatch):
        import friday.actions.browser_factory as bf
        from friday.actions.browser_strategy import BrowserStrategy, BrowserMode

        strat = BrowserStrategy(mode=BrowserMode.DESKTOP_CONTROL,
                                reason="locked profile", needs_user_session=True)
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

        strat = BrowserStrategy(mode=BrowserMode.CDP_LAUNCH, reason="closed",
                                needs_user_session=True)
        monkeypatch.setattr(bf, "resolve_browser_strategy", lambda *a, **k: strat)
        monkeypatch.setattr(bf, "_build_cdp_controller", lambda *a, **k: None)
        sentinel = object()
        monkeypatch.setattr(bf, "_build_desktop_controller", lambda: sentinel)

        ctrl, strategy = bf.build_browser_for_goal("open my gmail")
        assert ctrl is sentinel


class TestSearch:
    def test_search_opens_tab_and_reads_screen(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop([UIElement(text="results", control_type="Text",
                                             bbox=BoundingBox(0, 0, 10, 10))])
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        c.start()
        res = c.search_web("best laptop")
        assert res["ok"] is True and res["engine"] == "omnibox"
        assert ("ctrl", "t") in fake_pyautogui["hotkey"]
        assert "best laptop" in fake_pyautogui["typewrite"]
        assert "enter" in fake_pyautogui["press"]


class TestKeyboardAndScroll:
    def test_press_single_key(self, fake_pyautogui):
        c = DesktopBrowserController()
        c.start()
        assert c.press("enter")["ok"] is True
        assert "enter" in fake_pyautogui["press"]

    def test_press_combo_uses_hotkey(self, fake_pyautogui):
        c = DesktopBrowserController()
        c.start()
        assert c.press("ctrl+l")["ok"] is True
        assert ("ctrl", "l") in fake_pyautogui["hotkey"]

    def test_scroll_down_uses_negative_wheel(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop([])
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        res = c.scroll("down", amount=600)
        assert res["ok"] is True
        assert -600 in fake_pyautogui["scroll"]

    def test_type_text_types(self, fake_pyautogui):
        c = DesktopBrowserController()
        c.start()
        res = c.type_text("hello")
        assert res["ok"] is True
        assert "hello" in fake_pyautogui["typewrite"]


class TestIndexOps:
    def test_click_index_clicks_at_coords(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop([])
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        els = [{"index": 0, "text": "Compose", "x": 30, "y": 25}]
        res = c.click_index(0, els)
        assert res["ok"] is True and (30, 25) in fake_pyautogui["click"]

    def test_click_index_unknown_index_errors(self):
        c = DesktopBrowserController()
        res = c.click_index(99, [{"index": 0, "text": "x", "x": 1, "y": 1}])
        assert res["ok"] is False and "no element index" in res["error"]

    def test_fill_index_types_value(self, fake_pyautogui):
        c = DesktopBrowserController()
        c._desktop = _FakeDesktop([])
        c._ocr = _FakeOCR([])
        c._screen = _FakeScreen()
        els = [{"index": 0, "text": "Search", "x": 10, "y": 10}]
        res = c.fill_index(0, "query", els)
        assert res["ok"] is True and "query" in fake_pyautogui["typewrite"]


class TestViewportAndUrl:
    def test_viewport_size_from_active_window(self, monkeypatch):
        mod = types.ModuleType("pyautogui")
        mod.getActiveWindow = lambda: type("W", (), {"width": 1600, "height": 900})()
        monkeypatch.setitem(sys.modules, "pyautogui", mod)
        vs = DesktopBrowserController().viewport_size()
        assert vs["width"] == 1600 and vs["height"] == 900

    def test_current_url_defaults_empty(self):
        assert DesktopBrowserController().current_url() == ""

    def test_get_links_empty_without_dom(self):
        assert DesktopBrowserController().get_links() == []
