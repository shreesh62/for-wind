"""Unit tests for DesktopAdapter (Task 4.2).

Exercises the Windows UIA-based DesktopAdapter through a fully mocked
pyautogui. No real mouse/keyboard/window I/O ever occurs: pyautogui is
patched on the adapter module, and FRIDAY_DRY_RUN=1 is enforced by conftest.

Coverage:
- name / priority properties
- can_handle: text match, no match, role + automation_id matching
- resolve_element: source/priority/bbox/clickable, miss returns None, index disambiguation
- click / double_click / right_click dispatch to mocked pyautogui at center coords
- type_text ASCII path (pyautogui.write) and Unicode path (clipboard + ctrl+v)
- press_key / press_hotkey dispatch
- scroll at element center and screen-center fallback, down-direction negation
- drag computes delta and dispatches moveTo + drag
- focus_window activates a matching window, restores when minimized, and
  fails cleanly when no window matches
- failure paths return ActionResult.failed with adapter_failed category

Validates: Requirements 2.1, 5.1, 14.3
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import friday.actions.adapters.desktop as desktop_mod
from friday.actions.adapters.desktop import DesktopAdapter
from friday.actions.result import ActionResult, ActionStatus
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BoundingBox, PerceptionSource, UIElement
from friday.perception.world_state import WorldStateBuilder


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_element(
    text="Submit",
    control_type="button",
    x=100,
    y=200,
    width=40,
    height=20,
    automation_id="",
    confidence=0.9,
):
    """Construct a UIElement with a known bounding box."""
    return UIElement(
        text=text,
        control_type=control_type,
        bbox=BoundingBox(x=x, y=y, width=width, height=height),
        automation_id=automation_id,
        confidence=confidence,
    )


def make_world(elements):
    """Build a WorldState containing the given UI elements."""
    return WorldStateBuilder().add_ui_elements(list(elements)).build()


def resolved_from(element):
    """Wrap a UIElement in a ResolvedElement the way the adapter would."""
    bbox = element.bbox
    return ResolvedElement(
        text=element.text,
        source=PerceptionSource.UIA,
        priority=80,
        confidence=element.confidence,
        clickable=True,
        bbox=(bbox.x, bbox.y, bbox.width, bbox.height),
        raw_element=element,
    )


@pytest.fixture
def fake_pyautogui(monkeypatch):
    """Replace the module-level pyautogui with a MagicMock recorder."""
    fake = MagicMock(name="pyautogui")
    fake.size.return_value = (1920, 1080)
    fake.getWindowsWithTitle.return_value = []
    monkeypatch.setattr(desktop_mod, "pyautogui", fake)
    return fake


@pytest.fixture
def adapter():
    return DesktopAdapter()


# ---------------------------------------------------------------------------
# Identity properties
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_name_is_desktop(self, adapter):
        assert adapter.name == "desktop"

    def test_priority_is_80(self, adapter):
        assert adapter.priority == 80


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_returns_true_when_text_matches(self, adapter):
        world = make_world([make_element(text="Save Document")])
        assert adapter.can_handle(Target(text="save"), world) is True

    def test_returns_false_when_no_match(self, adapter):
        world = make_world([make_element(text="Save Document")])
        assert adapter.can_handle(Target(text="Cancel"), world) is False

    def test_returns_false_for_empty_world(self, adapter):
        world = make_world([])
        assert adapter.can_handle(Target(text="anything"), world) is False

    def test_matches_by_role_only(self, adapter):
        world = make_world([make_element(text="OK", control_type="button")])
        assert adapter.can_handle(Target(role="button"), world) is True

    def test_matches_by_automation_id(self, adapter):
        world = make_world([make_element(text="Field", automation_id="user_input")])
        assert adapter.can_handle(Target(automation_id="user_input"), world) is True


# ---------------------------------------------------------------------------
# resolve_element
# ---------------------------------------------------------------------------

class TestResolveElement:
    def test_returns_resolved_with_uia_source_and_bbox(self, adapter):
        elem = make_element(text="Submit", x=10, y=20, width=30, height=40)
        world = make_world([elem])
        result = adapter.resolve_element(Target(text="Submit"), world)
        assert result is not None
        assert result.source == PerceptionSource.UIA
        assert result.priority == 80
        assert result.bbox == (10, 20, 30, 40)
        assert result.raw_element is elem

    def test_clickable_true_for_button(self, adapter):
        world = make_world([make_element(text="Go", control_type="button")])
        result = adapter.resolve_element(Target(text="Go"), world)
        assert result.clickable is True

    def test_clickable_false_for_text_control(self, adapter):
        world = make_world([make_element(text="Label", control_type="text")])
        result = adapter.resolve_element(Target(text="Label"), world)
        assert result.clickable is False

    def test_returns_none_when_no_match(self, adapter):
        world = make_world([make_element(text="Submit")])
        assert adapter.resolve_element(Target(text="Nope"), world) is None

    def test_index_disambiguation_selects_nth_match(self, adapter):
        first = make_element(text="Item", x=0, y=0)
        second = make_element(text="Item", x=500, y=500)
        world = make_world([first, second])
        result = adapter.resolve_element(Target(text="Item", index=1), world)
        assert result.raw_element is second


# ---------------------------------------------------------------------------
# Pointer actions
# ---------------------------------------------------------------------------

class TestPointerActions:
    def test_click_calls_pyautogui_at_center(self, adapter, fake_pyautogui):
        elem = make_element(x=100, y=200, width=40, height=20)
        res = asyncio.run(adapter.click(resolved_from(elem)))
        assert res.is_success
        assert res.action_type == "click"
        # center = (100 + 40//2, 200 + 20//2) = (120, 210)
        fake_pyautogui.click.assert_called_once_with(120, 210)

    def test_double_click_dispatches(self, adapter, fake_pyautogui):
        elem = make_element(x=10, y=10, width=20, height=20)
        res = asyncio.run(adapter.double_click(resolved_from(elem)))
        assert res.is_success
        fake_pyautogui.doubleClick.assert_called_once_with(20, 20)

    def test_right_click_dispatches(self, adapter, fake_pyautogui):
        elem = make_element(x=10, y=10, width=20, height=20)
        res = asyncio.run(adapter.right_click(resolved_from(elem)))
        assert res.is_success
        fake_pyautogui.rightClick.assert_called_once_with(20, 20)

    def test_click_failure_returns_failed_result(self, adapter, fake_pyautogui):
        fake_pyautogui.click.side_effect = RuntimeError("boom")
        res = asyncio.run(adapter.click(resolved_from(make_element())))
        assert not res.is_success
        assert res.status == ActionStatus.FAILED
        assert res.error_category == "adapter_failed"
        assert res.repair_hints


# ---------------------------------------------------------------------------
# Keyboard actions
# ---------------------------------------------------------------------------

class TestKeyboardActions:
    def test_type_text_ascii_uses_write(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.type_text("hello world"))
        assert res.is_success
        fake_pyautogui.write.assert_called_once_with("hello world", interval=0.02)

    def test_type_text_unicode_uses_clipboard_paste(self, adapter, fake_pyautogui, monkeypatch):
        fake_pyperclip = MagicMock(name="pyperclip")
        monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake_pyperclip)
        res = asyncio.run(adapter.type_text("caf\u00e9"))
        assert res.is_success
        fake_pyperclip.copy.assert_called_once_with("caf\u00e9")
        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "v")
        fake_pyautogui.write.assert_not_called()

    def test_type_text_uses_element_text_as_target(self, adapter, fake_pyautogui):
        elem = resolved_from(make_element(text="Username"))
        res = asyncio.run(adapter.type_text("bob", element=elem))
        assert res.target == "Username"

    def test_press_key_dispatches(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.press_key("enter"))
        assert res.is_success
        fake_pyautogui.press.assert_called_once_with("enter")

    def test_press_hotkey_dispatches_combo(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.press_hotkey(["ctrl", "s"]))
        assert res.is_success
        fake_pyautogui.hotkey.assert_called_once_with("ctrl", "s")
        assert res.target == "ctrl+s"

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
        elem = resolved_from(make_element(x=100, y=100, width=40, height=40))
        res = asyncio.run(adapter.scroll("up", 3, element=elem))
        assert res.is_success
        fake_pyautogui.scroll.assert_called_once_with(3, x=120, y=120)

    def test_scroll_down_negates_amount(self, adapter, fake_pyautogui):
        elem = resolved_from(make_element(x=100, y=100, width=40, height=40))
        res = asyncio.run(adapter.scroll("down", 5, element=elem))
        assert res.is_success
        fake_pyautogui.scroll.assert_called_once_with(-5, x=120, y=120)

    def test_scroll_without_element_uses_screen_center(self, adapter, fake_pyautogui):
        res = asyncio.run(adapter.scroll("up", 2))
        assert res.is_success
        # screen size (1920, 1080) -> center (960, 540)
        fake_pyautogui.scroll.assert_called_once_with(2, x=960, y=540)
        assert res.target == "screen_center"


# ---------------------------------------------------------------------------
# drag
# ---------------------------------------------------------------------------

class TestDrag:
    def test_drag_computes_delta_and_dispatches(self, adapter, fake_pyautogui):
        src = resolved_from(make_element(text="A", x=0, y=0, width=20, height=20))
        dst = resolved_from(make_element(text="B", x=100, y=60, width=20, height=20))
        res = asyncio.run(adapter.drag(src, dst))
        assert res.is_success
        # src center (10, 10), dst center (110, 70) -> delta (100, 60)
        fake_pyautogui.moveTo.assert_called_once_with(10, 10)
        fake_pyautogui.drag.assert_called_once_with(100, 60, duration=0.5)
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
        res = asyncio.run(adapter.click(resolved_from(make_element())))
        assert isinstance(res, ActionResult)
        assert isinstance(res.status, ActionStatus)
