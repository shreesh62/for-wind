"""Unit tests for BrowserAdapter (Task 3.2).

Exercises BrowserAdapter against a fully faked BrowserController. No real
browser, Playwright session, or I/O ever occurs: the controller is replaced
with a stub that records calls and returns canned values. The adapter's
`_submit()`-based methods pass real coroutines, so the fake controller closes
them to avoid "coroutine was never awaited" warnings.

Coverage:
- name / priority properties
- can_handle (connected + hint, not connected, no hint)
- resolve_element by selector / text / role, and miss
- click delegation (success + failure dict + exception)
- type_text delegation (with/without selector element)
- double_click / right_click / press_key / press_hotkey / scroll / drag
  dispatch through the controller
- focus_window always fails
- evidence captures URL before/after

Validates: Requirements 2.1, 5.1, 5.2, 13.3
"""

from __future__ import annotations

import asyncio

import pytest

from friday.actions.adapters.browser import BrowserAdapter
from friday.actions.result import ActionResult, ActionStatus
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import (
    BoundingBox,
    BrowserElement,
    PerceptionSource,
)
from friday.perception.world_state import WorldStateBuilder


# ---------------------------------------------------------------------------
# Fake BrowserController
# ---------------------------------------------------------------------------

class FakePage:
    """Minimal placeholder for the Playwright page attribute."""

    def get_by_text(self, *args, **kwargs):  # pragma: no cover - never awaited
        raise AssertionError("page should not be driven directly in tests")


class FakeController:
    """Records calls and returns canned values; never touches a real browser.

    `_submit` accepts the coroutine the adapter builds, closes it (so no
    "never awaited" warning is emitted), records that a submit happened, and
    returns a canned value.
    """

    def __init__(
        self,
        *,
        urls=None,
        click_result=None,
        type_result=None,
        raise_on_click=False,
    ):
        # urls is an iterable of values returned by successive current_url()
        self._urls = list(urls) if urls is not None else ["https://example.com"]
        self._url_idx = 0
        self._click_result = click_result if click_result is not None else {"ok": True}
        self._type_result = type_result if type_result is not None else {"ok": True}
        self._raise_on_click = raise_on_click
        self._page = FakePage()

        self.click_calls = []
        self.type_calls = []
        self.submit_count = 0

    def current_url(self) -> str:
        # Return successive urls; clamp to last once exhausted.
        if self._url_idx < len(self._urls):
            url = self._urls[self._url_idx]
            self._url_idx += 1
        else:
            url = self._urls[-1] if self._urls else ""
        return url

    def click(self, text: str):
        self.click_calls.append(text)
        if self._raise_on_click:
            raise RuntimeError("browser crashed")
        return self._click_result

    def type_text(self, text: str, selector=None):
        self.type_calls.append((text, selector))
        return self._type_result

    def _submit(self, coro):
        self.submit_count += 1
        # Close the coroutine so it is not flagged as "never awaited".
        if asyncio.iscoroutine(coro):
            coro.close()
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_browser_element(
    text="Submit", selector="#submit", role="button", clickable=True
):
    return BrowserElement(
        tag="button",
        text=text,
        role=role,
        clickable=clickable,
        bbox=BoundingBox(10, 20, 30, 40),
        selector=selector,
    )


def make_world(connected=True, elements=None):
    b = WorldStateBuilder()
    b.set_browser_state(
        url="https://example.com",
        title="Example",
        elements=elements if elements is not None else [],
        connected=connected,
    )
    return b.build()


def resolved(text="Submit", raw=None, bbox=(10, 20, 30, 40)):
    return ResolvedElement(
        text=text,
        source=PerceptionSource.BROWSER,
        priority=100,
        confidence=0.95,
        clickable=True,
        bbox=bbox,
        raw_element=raw,
    )


# ---------------------------------------------------------------------------
# Identity properties
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_name_is_browser(self):
        adapter = BrowserAdapter(FakeController())
        assert adapter.name == "browser"

    def test_priority_is_100(self):
        adapter = BrowserAdapter(FakeController())
        assert adapter.priority == 100


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_true_when_connected_and_text(self):
        adapter = BrowserAdapter(FakeController())
        assert adapter.can_handle(Target(text="Submit"), make_world(connected=True))

    def test_true_when_connected_and_selector(self):
        adapter = BrowserAdapter(FakeController())
        assert adapter.can_handle(Target(selector="#x"), make_world(connected=True))

    def test_true_when_connected_and_role(self):
        adapter = BrowserAdapter(FakeController())
        assert adapter.can_handle(Target(role="button"), make_world(connected=True))

    def test_false_when_not_connected(self):
        adapter = BrowserAdapter(FakeController())
        assert not adapter.can_handle(Target(text="Submit"), make_world(connected=False))

    def test_false_when_no_hint(self):
        adapter = BrowserAdapter(FakeController())
        # coordinates-only target has no text/selector/role
        ws = make_world(connected=True)
        assert not adapter.can_handle(Target(coordinates=(5, 5)), ws)


# ---------------------------------------------------------------------------
# resolve_element
# ---------------------------------------------------------------------------

class TestResolveElement:
    def test_finds_by_selector_exact(self):
        adapter = BrowserAdapter(FakeController())
        elem = make_browser_element(text="Go", selector="#submit")
        ws = make_world(elements=[elem])
        res = adapter.resolve_element(Target(selector="#submit"), ws)
        assert res is not None
        assert res.source == PerceptionSource.BROWSER
        assert res.priority == 100
        assert res.confidence == 0.95
        assert res.raw_element is elem

    def test_finds_by_text_case_insensitive(self):
        adapter = BrowserAdapter(FakeController())
        elem = make_browser_element(text="Submit Form")
        ws = make_world(elements=[elem])
        res = adapter.resolve_element(Target(text="submit form"), ws)
        assert res is not None
        assert res.text == "Submit Form"

    def test_finds_by_role(self):
        adapter = BrowserAdapter(FakeController())
        elem = make_browser_element(text="Anything", selector="", role="link")
        ws = make_world(elements=[elem])
        res = adapter.resolve_element(Target(role="link"), ws)
        assert res is not None
        assert res.raw_element is elem

    def test_returns_bbox_tuple(self):
        adapter = BrowserAdapter(FakeController())
        elem = make_browser_element()
        ws = make_world(elements=[elem])
        res = adapter.resolve_element(Target(selector="#submit"), ws)
        assert res.bbox == (10, 20, 30, 40)

    def test_returns_none_when_no_match(self):
        adapter = BrowserAdapter(FakeController())
        ws = make_world(elements=[make_browser_element(text="Submit")])
        res = adapter.resolve_element(Target(text="Nonexistent"), ws)
        assert res is None


# ---------------------------------------------------------------------------
# click
# ---------------------------------------------------------------------------

class TestClick:
    def test_click_success_delegates_to_controller(self):
        ctrl = FakeController(click_result={"ok": True})
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.click(resolved(text="Submit")))
        assert isinstance(res, ActionResult)
        assert res.is_success
        assert res.action_type == "click"
        assert ctrl.click_calls == ["Submit"]

    def test_click_failure_dict_returns_failed(self):
        ctrl = FakeController(click_result={"ok": False, "error": "no element"})
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.click(resolved()))
        assert not res.is_success
        assert res.status == ActionStatus.FAILED
        assert res.error_category == "adapter_failed"
        assert res.error == "no element"
        assert res.repair_hints

    def test_click_exception_returns_browser_unavailable(self):
        ctrl = FakeController(raise_on_click=True)
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.click(resolved()))
        assert not res.is_success
        assert res.error_category == "browser_unavailable"
        assert "browser crashed" in res.error

    def test_click_evidence_captures_url_change(self):
        ctrl = FakeController(urls=["https://a.com", "https://b.com"])
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.click(resolved()))
        assert res.is_success
        assert res.evidence.before_hash == "https://a.com"
        assert res.evidence.after_hash == "https://b.com"
        assert res.evidence.url_changed is True
        assert res.evidence.state_changed is True

    def test_click_evidence_no_url_change(self):
        ctrl = FakeController(urls=["https://same.com", "https://same.com"])
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.click(resolved()))
        assert res.evidence.url_changed is False
        assert res.evidence.state_changed is False


# ---------------------------------------------------------------------------
# type_text
# ---------------------------------------------------------------------------

class TestTypeText:
    def test_type_text_success_without_element(self):
        ctrl = FakeController(type_result={"ok": True})
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.type_text("hello"))
        assert res.is_success
        assert ctrl.type_calls == [("hello", None)]

    def test_type_text_uses_selector_from_element(self):
        ctrl = FakeController(type_result={"ok": True})
        adapter = BrowserAdapter(ctrl)
        raw = make_browser_element(text="Field", selector="#email")
        res = asyncio.run(adapter.type_text("a@b.com", resolved(text="Field", raw=raw)))
        assert res.is_success
        assert ctrl.type_calls == [("a@b.com", "#email")]

    def test_type_text_failure_dict_returns_failed(self):
        ctrl = FakeController(type_result={"ok": False, "error": "no field"})
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.type_text("hello"))
        assert not res.is_success
        assert res.error_category == "adapter_failed"
        assert res.error == "no field"


# ---------------------------------------------------------------------------
# Playwright-backed methods dispatch via _submit
# ---------------------------------------------------------------------------

class TestSubmitBackedMethods:
    def test_double_click_dispatches_submit(self):
        ctrl = FakeController()
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.double_click(resolved()))
        assert res.is_success
        assert res.action_type == "double_click"
        assert ctrl.submit_count == 1

    def test_right_click_dispatches_submit(self):
        ctrl = FakeController()
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.right_click(resolved()))
        assert res.is_success
        assert res.action_type == "right_click"
        assert ctrl.submit_count == 1

    def test_press_key_dispatches_submit(self):
        ctrl = FakeController()
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.press_key("Enter"))
        assert res.is_success
        assert res.action_type == "press_key"
        assert res.target == "Enter"
        assert ctrl.submit_count == 1

    def test_press_hotkey_joins_keys(self):
        ctrl = FakeController()
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.press_hotkey(["ctrl", "s"]))
        assert res.is_success
        assert res.action_type == "press_hotkey"
        assert res.target == "ctrl+s"
        assert ctrl.submit_count == 1

    def test_scroll_marks_state_changed(self):
        ctrl = FakeController(urls=["https://same.com", "https://same.com"])
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.scroll("down", 3))
        assert res.is_success
        assert res.action_type == "scroll"
        # scroll always sets state_changed even when URL is unchanged
        assert res.evidence.state_changed is True

    def test_drag_dispatches_submit_and_marks_state_changed(self):
        ctrl = FakeController()
        adapter = BrowserAdapter(ctrl)
        res = asyncio.run(adapter.drag(resolved(text="A"), resolved(text="B")))
        assert res.is_success
        assert res.action_type == "drag"
        assert res.evidence.state_changed is True
        assert ctrl.submit_count == 1


# ---------------------------------------------------------------------------
# focus_window
# ---------------------------------------------------------------------------

class TestFocusWindow:
    def test_focus_window_always_fails(self):
        adapter = BrowserAdapter(FakeController())
        res = asyncio.run(adapter.focus_window(Target(window_title="Notepad")))
        assert not res.is_success
        assert res.status == ActionStatus.FAILED
        assert res.error_category == "adapter_failed"
        assert res.repair_hints
