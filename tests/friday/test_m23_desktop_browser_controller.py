"""M23 — DesktopBrowserController generality property tests.

Feature: m23-browser-generic-desktop-environment

Property 4: the controller exposes the full duck-typed surface and contains NO
browser-name / window-title / OCR-only branch (generic desktop control).
Property 5: navigation is browser-invariant — the same key sequence regardless
of which window/browser is active.
"""

import inspect
import sys
import types

from hypothesis import given, settings
from hypothesis import strategies as st

import friday.actions.desktop_browser as dbmod
from friday.actions.desktop_browser import DesktopBrowserController


_RC1_SURFACE = (
    "available", "start", "stop", "navigate", "search_web", "read_text",
    "current_url", "click", "type_text", "observe_interactive", "click_index",
    "fill_index", "scroll", "press", "screenshot_image", "viewport_size", "click_xy",
)


def test_p4_controller_is_generic_no_browser_specifics():
    # Feature: m23-browser-generic-desktop-environment, Property 4:
    # full surface + no window-title / OCR-only assumptions.
    # Validates: Requirements 2.1, 2.2, 2.4, 2.5
    c = DesktopBrowserController()
    for attr in _RC1_SURFACE:
        assert hasattr(c, attr), f"missing {attr}"

    src = inspect.getsource(dbmod)
    # No window-title targeting API / hints anywhere in the module.
    assert "getWindowsWithTitle" not in src
    assert "window_title" not in src
    assert "title_hint" not in src
    # Fused perception (UIA+OCR+pixels), not OCR-only: uses the shared builder.
    assert "observe_active_window" in src


@settings(max_examples=100)
@given(title=st.text(max_size=24))
def test_p5_navigation_is_browser_invariant(title):
    # Feature: m23-browser-generic-desktop-environment, Property 5:
    # the navigation key sequence is identical regardless of the active window
    # (no per-browser branching). Validates: Requirements 2.3, 2.5
    seq = []
    mod = types.ModuleType("pyautogui")
    mod.hotkey = lambda *a: seq.append(("hotkey",) + a)
    mod.typewrite = lambda text, interval=0: seq.append(("type", text))
    mod.press = lambda k: seq.append(("press", k))
    mod.getActiveWindow = lambda: type("W", (), {"title": title})()

    prev_mod = sys.modules.get("pyautogui")
    prev_sleep = dbmod.time.sleep
    sys.modules["pyautogui"] = mod
    dbmod.time.sleep = lambda *_: None
    try:
        c = DesktopBrowserController()
        c.start()
        c.navigate("https://example.com")
    finally:
        dbmod.time.sleep = prev_sleep
        if prev_mod is not None:
            sys.modules["pyautogui"] = prev_mod
        else:
            sys.modules.pop("pyautogui", None)

    # Exactly: focus address bar (Ctrl+L) -> type URL -> Enter, no matter the window.
    assert seq == [
        ("hotkey", "ctrl", "l"),
        ("type", "https://example.com"),
        ("press", "enter"),
    ]
