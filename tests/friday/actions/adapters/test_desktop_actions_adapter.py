"""Unit tests for DesktopActionsAdapter (Task 5.2).

DesktopActionsAdapter is the OS-level / coordinate-based fallback adapter
(priority 60). It sits between DesktopAdapter (UIA, 80) and VisionAdapter
(OCR/pixel, 30). It handles explicit coordinates, window management, and
OS-level hotkeys (e.g. Ctrl+S, Alt+Tab) when no UIA element is available.

All desktop I/O is mocked: the module-level ``pyautogui`` is replaced with a
MagicMock recorder so NO real mouse/keyboard/window action ever occurs.
FRIDAY_DRY_RUN=1 is additionally enforced by conftest.

Coverage:
- name / priority properties
- can_handle: coordinates, window_title, OS-level (no semantic hint),
  and False for semantic-only targets (text/role/selector)
- resolve_element: coordinate path, window_title via world_state / pyautogui /
  placeholder, OS-level generic element, and None for semantic-only targets
- pointer actions (click / double_click / right_click) at resolved coordinates
- keyboard actions (type_text / press_key / press_hotkey) dispatch
- scroll at element center and screen-center fallback, down negation
- drag dispatches mouseDown/moveTo/mouseUp
- focus_window activates a match, restores minimized, fails when no match
- failure paths return ActionResult.failed with adapter_failed category

Validates: Requirements 2.1, 4.4, 5.1
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import friday.actions.adapters.desktop_actions as desktop_actions_mod
from friday.actions.adapters.desktop_actions import DesktopActionsAdapter
from friday.actions.result import ActionResult, ActionStatus
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import PerceptionSource, WindowInfo
from friday.perception.world_state import WorldStateBuilder


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_world(window_title=None):
    """Build a WorldState, optionally with an active window."""
    builder = WorldStateBuilder()
    if window_title is not None:
        builder.set_window_info(
            WindowInfo(title=window_title, process_name="app.exe", pid=1234)
        )
    return builder.build()


def coord_element(x=300, y=400, text="(300, 400)"):
    """A ResolvedElement located at explicit coordinates (1x1 bbox)."""
    return ResolvedElement(
        text=text,
        source=PerceptionSource.UIA,
        priority=60,
        confidence=1.0,
        clickable=True,
        bbox=(x, y, 1, 1),
        raw_element=None,
    )


@pytest.fixture
def fake_pyautogui(monkeypatch):
    """Replace the module-level pyautogui with a MagicMock recorder."""
    fake = MagicMock(name="pyautogui")
    fake.size.return_value = (1920, 1080)
    fake.getWindowsWithTitle.return_value = []
    monkeypatch.setattr(desktop_actions_mod, "pyautogui", fake)
    return fake


@pytest.fixture
def adapter():
    return DesktopActionsAdapter()


# ---------------------------------------------------------------------------
# Identity properties
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_name_is_desktop_actions(self, adapter):
        assert adapter.name == "desktop_actions"

    def test_priority_is_60(self, adapter):
        assert adapter.priority == 60


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_true_for_coordinates(self, adapter):
        world = make_world()
        assert adapter.can_handle(Target(coordinates=(100, 200)), world) is True

    def test_true_for_window_title(self, adapter):
        world = make_world()
        assert adapter.can_handle(Target(window_title="Notepad"), world) is True

    def test_false_for_text_only(self, adapter):
        world = make_world()
        assert adapter.can_handle(Target(text="Submit"), world) is False

    def test_false_for_role_only(self, adapter):
        world = make_world()
        assert adapter.can_handle(Target(role="button"), world) is False

    def test_false_for_selector_only(self, adapter):
        world = make_world()
        assert adapter.can_handle(Target(selector="#submit"), world) is False


# ---------------------------------------------------------------------------
# resolve_element
# ---------------------------------------------------------------------------

class TestResolveElement:
    def test_coordinates_produce_element_with_bbox(self, adapter):
        world = make_world()
        result = adapter.resolve_element(Target(coordinates=(300, 400)), world)
        assert result is not None
        assert result.source == PerceptionSource.UIA
        assert result.priority == 60
        assert result.bbox == (300, 400, 1, 1)

    def test_window_title_matches_active_window(self, adapter):
        world = make_world(window_title="Notepad - Untitled")
        result = adapter.resolve_element(Target(window_title="Notepad"), world)
        assert result is not None
        assert result.text == "Notepad - Untitled"
        assert result.confidence == 0.9

    def test_window_title_via_pyautogui(self, adapter, fake_pyautogui):
        win = MagicMock()
        win.title = "Calculator"
        win.left, win.top, win.width, win.height = 5, 6, 700, 500
        fake_pyautogui.getWindowsWithTitle.return_value = [win]
        world = make_world()  # no active window in world_state
        result = adapter.resolve_element(Target(window_title="Calculator"), world)
        assert result is not None
        assert result.text == "Calculator"
        assert result.bbox == (5, 6, 700, 500)

    def test_window_title_placeholder_when_not_found(self, adapter, fake_pyautogui):
        fake_pyautogui.getWindowsWithTitle.return_value = []
        world = make_world()
        result = adapter.resolve_element(Target(window_title="Ghost"), world)
        assert result is not None
        assert result.text == "Ghost"
        assert result.confidence == 0.5

    def test_semantic_only_target_returns_none(self, adapter):
        world = make_world()
        assert adapter.resolve_element(Target(text="Submit"), world) is None


# ---------------------------------------------------------------------------
# Pointer actions
# ---------------------------------------------------------------------------

class TestPointerActions:
    def test_click_at_coordinates(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.click(coord_element(x=300, y=400)))
        assert res.is_success
        assert res.action_type == "click"
        # center of (300, 400, 1, 1) = (300 + 0, 400 + 0) = (300, 400)
        fake_pyautogui.click.assert_called_once_with(300, 400)

    def test_double_click_dispatches(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.double_click(coord_element(x=10, y=20)))
        assert res.is_success
        fake_pyautogui.doubleClick.assert_called_once_with(10, 20)

    def test_right_click_dispatches(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.right_click(coord_element(x=10, y=20)))
        assert res.is_success
        fake_pyautogui.rightClick.assert_called_once_with(10, 20)

    def test_click_without_bbox_fails(self, adapter, fake_pyautogui):
        # An element with no bbox cannot yield coordinates.
        elem = ResolvedElement(
            text="no_coords",
            source=PerceptionSource.UIA,
            priority=60,
            confidence=0.7,
            clickable=False,
            bbox=None,
            raw_element=None,
        )
        res = asyncio.run(adapter.click(elem))
        assert not res.is_success
        assert res.status == ActionStatus.FAILED
        assert res.error_category == "adapter_failed"

    def test_click_failure_returns_failed_result(self, adapter, fake_pyautogui):
        fake_pyautogui.click.side_effect = RuntimeError("boom")
        res = asyncio.run(adapter.click(coord_element()))
        assert not res.is_success
        assert res.error_category == "adapter_failed"
        assert res.repair_hints


# ---------------------------------------------------------------------------
# Keyboard actions
# ---------------------------------------------------------------------------

class TestKeyboardActions:
    def test_type_text_dispatches(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.type_text("hello"))
        assert res.is_success
        fake_pyautogui.write.assert_called_once_with("hello")

    def test_press_key_dispatches(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.press_key("enter"))
        assert res.is_success
        fake_pyautogui.press.assert_called_once_with("enter")

    def test_press_hotkey_dispatches_combo(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.press_hotkey(["ctrl", "s"]))
        assert res.is_success
        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "s")
        assert res.target == "ctrl+s"

    def test_press_hotkey_three_keys(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.press_hotkey(["ctrl", "shift", "esc"]))
        assert res.is_success
        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "shift", "esc")
        assert res.target == "ctrl+shift+esc"

    def test_press_hotkey_failure_returns_failed(self, adapter, fake_pyautogui):
        fake_pyautogui.hotkey.side_effect = RuntimeError("nope")
        res = asyncio.run(adapter.press_hotkey(["ctrl", "s"]))
        assert not res.is_success
        assert res.error_category == "adapter_failed"

    def test_press_key_failure_returns_failed(self, adapter, fake_pyautogui):
        fake_pyautogui.press.side_effect = RuntimeError("nope")
        res = asyncio.run(adapter.press_key("enter"))
        assert not res.is_success
        assert res.error_category == "adapter_failed"


# ---------------------------------------------------------------------------
# scroll
# ---------------------------------------------------------------------------

class TestScroll:
    def test_scroll_at_element_center(self, adapter, fake_pyautogui):
        elem = ResolvedElement(
            text="region",
            source=PerceptionSource.UIA,
            priority=60,
            confidence=1.0,
            clickable=False,
            bbox=(100, 100, 40, 40),
            raw_element=None,
        )
        res = asyncio.run(adapter.scroll("up", 3, element=elem))
        assert res.is_success
        fake_pyautogui.scroll.assert_called_once_with(3, x=120, y=120)

    def test_scroll_down_negates_amount(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.scroll("down", 5))
        assert res.is_success
        # screen center for (1920, 1080) = (960, 540)
        fake_pyautogui.scroll.assert_called_once_with(-5, x=960, y=540)

    def test_scroll_failure_returns_failed(self, adapter, fake_pyautogui):
        fake_pyautogui.scroll.side_effect = RuntimeError("boom")
        res = asyncio.run(adapter.scroll("up", 2))
        assert not res.is_success
        assert res.error_category == "adapter_failed"


# ---------------------------------------------------------------------------
# drag
# ---------------------------------------------------------------------------

class TestDrag:
    def test_drag_dispatches_down_move_up(self, adapter, fake_pyautogui):
        src = coord_element(x=0, y=0, text="A")
        dst = coord_element(x=100, y=60, text="B")
        res = asyncio.run(adapter.drag(src, dst))
        assert res.is_success
        fake_pyautogui.mouseDown.assert_called_once()
        fake_pyautogui.mouseUp.assert_called_once()
        # moveTo called for both source and destination
        assert fake_pyautogui.moveTo.call_count == 2
        assert res.target == "A -> B"


# ---------------------------------------------------------------------------
# focus_window
# ---------------------------------------------------------------------------

class TestFocusWindow:
    def test_focus_window_activates_match(self, adapter, fake_pyautogui):
        window = MagicMock(name="window")
        window.isMinimized = False
        window.title = "Notepad"
        fake_pyautogui.getWindowsWithTitle.return_value = [window]
        res = asyncio.run(adapter.focus_window(Target(window_title="Notepad")))
        assert res.is_success
        assert res.evidence.window_changed is True
        window.activate.assert_called_once()

    def test_focus_window_restores_minimized(self, adapter, fake_pyautogui):
        window = MagicMock(name="window")
        window.isMinimized = True
        window.title = "Notepad"
        fake_pyautogui.getWindowsWithTitle.return_value = [window]
        res = asyncio.run(adapter.focus_window(Target(window_title="Notepad")))
        assert res.is_success
        window.restore.assert_called_once()
        window.activate.assert_called_once()

    def test_focus_window_no_match_fails(self, adapter, fake_pyautogui):
        fake_pyautogui.getWindowsWithTitle.return_value = []
        res = asyncio.run(adapter.focus_window(Target(window_title="Missing")))
        assert not res.is_success
        assert res.error_category == "window_not_found"
        assert res.repair_hints


# ---------------------------------------------------------------------------
# Contract invariant
# ---------------------------------------------------------------------------

class TestContract:
    def test_actions_return_actionresult(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.click(coord_element()))
        assert isinstance(res, ActionResult)
        assert isinstance(res.status, ActionStatus)
