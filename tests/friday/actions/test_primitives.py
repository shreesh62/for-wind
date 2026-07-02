"""Unit tests for the Universal Action Layer primitives.

Task 12.1 — exercises every primitive in `friday/actions/primitives.py`
through a fully mocked adapter + resolver stack. No real pyautogui /
Playwright I/O occurs: every adapter here is a fake that records calls and
returns canned ActionResults.

Coverage:
- click happy path / re-routing / total failure
- type_text focus rules
- press_hotkey dispatch
- switch_window window_changed evidence
- observe with empty WorldState
- verify met / unmet conditions
- wait_for success-before-timeout and timeout
- generic timeout behaviour
- metadata source + adapter name on success

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.1, 9.6, 10.4, 11.1, 11.3
"""

from __future__ import annotations

import asyncio

import pytest

from friday.actions import primitives as P
from friday.actions.target import Target
from friday.actions.result import ActionResult, ActionEvidence, ActionStatus
from friday.actions.adapters.resolver import AdapterResolver
from friday.perception.priority import ResolvedElement
from friday.perception.types import PerceptionSource
from friday.perception.world_state import WorldStateBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_world(browser: bool = False):
    """Build a minimal WorldState, optionally with a connected browser."""
    b = WorldStateBuilder()
    if browser:
        b.set_browser_state(
            url="https://example.com", title="Example", elements=[], connected=True
        )
    return b.build()


def resolved(source=PerceptionSource.BROWSER):
    """A canned ResolvedElement for the fake adapter to return."""
    return ResolvedElement(
        text="Submit",
        source=source,
        priority=100,
        confidence=0.95,
        clickable=True,
        bbox=(10, 10, 20, 20),
        raw_element=None,
    )


class FakeAdapter:
    """Configurable adapter implementing the protocol surface primitives use.

    Records every action method invoked so tests can assert dispatch.
    """

    def __init__(
        self,
        name="browser",
        priority=100,
        *,
        can=True,
        element=None,
        succeed=True,
        source=PerceptionSource.BROWSER,
        delay_ms=0.0,
        window_changed=False,
    ):
        self._name = name
        self._priority = priority
        self._can = can
        self._element = element if element is not None else resolved(source)
        self._succeed = succeed
        self._delay_ms = delay_ms
        self._window_changed = window_changed
        self.calls = []
        self.typed_text = []
        self.pressed_keys = []
        self.hotkeys = []

    @property
    def name(self):
        return self._name

    @property
    def priority(self):
        return self._priority

    def can_handle(self, target, world_state):
        return self._can

    def resolve_element(self, target, world_state):
        return self._element if self._can else None

    async def _result(self, action, *, evidence=None):
        self.calls.append(action)
        if self._delay_ms:
            await asyncio.sleep(self._delay_ms / 1000.0)
        if self._succeed:
            return ActionResult.success(
                action=action,
                target="Submit",
                evidence=evidence or ActionEvidence(state_changed=True),
            )
        return ActionResult.failed(
            action=action,
            error="forced failure",
            target="Submit",
            error_category="adapter_failed",
            repair_hints=["retry"],
        )

    async def click(self, element):
        return await self._result("click")

    async def double_click(self, element):
        return await self._result("double_click")

    async def right_click(self, element):
        return await self._result("right_click")

    async def type_text(self, text, element=None):
        self.typed_text.append(text)
        return await self._result("type_text")

    async def press_key(self, key):
        self.pressed_keys.append(key)
        return await self._result("press_key")

    async def press_hotkey(self, keys):
        self.hotkeys.append(list(keys))
        return await self._result("press_hotkey")

    async def scroll(self, direction, amount, element=None):
        return await self._result("scroll")

    async def drag(self, source, dest):
        return await self._result("drag")

    async def focus_window(self, target):
        return await self._result(
            "focus_window",
            evidence=ActionEvidence(state_changed=True, window_changed=self._window_changed),
        )


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Ensure each test starts and ends with a clean module-level resolver."""
    P._resolver = None
    yield
    P._resolver = None


# ---------------------------------------------------------------------------
# click — dispatch, re-routing, failure
# ---------------------------------------------------------------------------

class TestClick:
    def test_click_happy_path_dispatches_and_succeeds(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.is_success
        assert a.calls == ["click"]

    def test_click_records_source_and_adapter_metadata(self):
        a = FakeAdapter("browser", 100, source=PerceptionSource.BROWSER)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.metadata.get("adapter") == "browser"
        assert res.metadata.get("source") == PerceptionSource.BROWSER.value

    def test_click_reroutes_when_first_adapter_fails(self):
        failing = FakeAdapter("browser", 100, succeed=False)
        working = FakeAdapter("desktop", 80, succeed=True)
        P._resolver = AdapterResolver([failing, working])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.is_success
        assert res.metadata.get("adapter") == "desktop"
        # the higher-priority adapter was attempted first
        assert "click" in failing.calls

    def test_click_all_adapters_fail_returns_failed_with_attempts(self):
        a = FakeAdapter("browser", 100, succeed=False)
        b = FakeAdapter("desktop", 80, succeed=False)
        P._resolver = AdapterResolver([a, b])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert not res.is_success
        attempted = res.metadata.get("adapters_attempted")
        assert attempted is not None
        assert "browser" in attempted and "desktop" in attempted

    def test_click_no_adapter_handles_returns_target_not_found(self):
        a = FakeAdapter("browser", 100, can=False)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Nope"), make_world()))
        assert not res.is_success
        assert res.error_category == "target_not_found"
        assert res.repair_hints  # non-empty

    def test_click_uninitialized_resolver_returns_failure(self):
        P._resolver = None
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert not res.is_success
        assert res.error_category == "not_initialized"

    def test_double_and_right_click_dispatch_correct_methods(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        asyncio.run(P.double_click(Target(text="Submit"), make_world()))
        asyncio.run(P.right_click(Target(text="Submit"), make_world()))
        assert "double_click" in a.calls
        assert "right_click" in a.calls


# ---------------------------------------------------------------------------
# Keyboard primitives — focus rules and dispatch
# ---------------------------------------------------------------------------

class TestKeyboard:
    def test_type_text_no_focus_no_target_fails(self):
        a = FakeAdapter("desktop", 80)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.type_text("hello", make_world(browser=False)))
        assert not res.is_success
        assert res.error_category == "no_focus"
        assert res.repair_hints

    def test_type_text_with_browser_connected_dispatches_text(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.type_text("hello world", make_world(browser=True)))
        assert res.is_success
        assert a.typed_text == ["hello world"]

    def test_type_text_with_explicit_target_dispatches(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(
            P.type_text("abc", make_world(), target=Target(text="Field"))
        )
        assert res.is_success
        assert a.typed_text == ["abc"]

    def test_press_key_no_focus_fails(self):
        a = FakeAdapter("desktop", 80)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.press_key("Enter", make_world(browser=False)))
        assert not res.is_success
        assert res.error_category == "no_focus"

    def test_press_key_with_browser_dispatches(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.press_key("Enter", make_world(browser=True)))
        assert res.is_success
        assert a.pressed_keys == ["Enter"]

    def test_press_hotkey_requires_no_focus_and_dispatches_keys(self):
        a = FakeAdapter("desktop_actions", 60)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.press_hotkey(["ctrl", "s"], make_world(browser=False)))
        assert res.is_success
        assert a.hotkeys == [["ctrl", "s"]]


# ---------------------------------------------------------------------------
# scroll / drag
# ---------------------------------------------------------------------------

class TestPointerMisc:
    def test_scroll_without_target_dispatches(self):
        a = FakeAdapter("desktop_actions", 60)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.scroll("down", 3, make_world()))
        assert res.is_success
        assert "scroll" in a.calls

    def test_drag_dispatches_through_source_adapter(self):
        a = FakeAdapter("desktop", 80)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(
            P.drag(Target(text="A"), Target(text="B"), make_world())
        )
        assert res.is_success
        assert "drag" in a.calls

    def test_drag_uninitialized_returns_failure(self):
        P._resolver = None
        res = asyncio.run(
            P.drag(Target(text="A"), Target(text="B"), make_world())
        )
        assert not res.is_success
        assert res.error_category == "not_initialized"


# ---------------------------------------------------------------------------
# switch_window — window_changed evidence
# ---------------------------------------------------------------------------

class TestSwitchWindow:
    def test_switch_window_success_has_window_changed_evidence(self):
        a = FakeAdapter("desktop", 80, window_changed=True)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(
            P.switch_window(Target(window_title="Notepad"), make_world())
        )
        assert res.is_success
        assert res.evidence.window_changed is True
        assert "focus_window" in a.calls


# ---------------------------------------------------------------------------
# observe
# ---------------------------------------------------------------------------

class TestObserve:
    def test_observe_no_sources_fails(self):
        ws = WorldStateBuilder().build()  # no perception sources
        res = asyncio.run(P.observe(ws))
        assert not res.is_success
        assert res.error_category == "perception_unavailable"

    def test_observe_sources_but_no_data_fails(self):
        # screenshot source registered but no semantic/OCR data
        ws = WorldStateBuilder().set_screenshot_hash("abc123").build()
        res = asyncio.run(P.observe(ws))
        assert not res.is_success
        assert res.error_category == "perception_insufficient"


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_matching_condition_succeeds(self):
        from friday.perception.types import OCRRegion, BoundingBox

        ws = (
            WorldStateBuilder()
            .add_ocr_regions(
                [OCRRegion(text="Login successful", bbox=BoundingBox(0, 0, 10, 10), confidence=0.9)]
            )
            .build()
        )
        res = asyncio.run(P.verify("Login successful", ws))
        assert res.is_success
        assert res.evidence.text_appeared == "Login successful"

    def test_verify_unmet_condition_fails(self):
        ws = make_world(browser=True)
        res = asyncio.run(P.verify("nonexistent phrase", ws))
        assert not res.is_success
        assert res.error_category == "verification_failed"
        assert res.repair_hints


# ---------------------------------------------------------------------------
# wait_for
# ---------------------------------------------------------------------------

class TestWaitFor:
    def test_wait_for_returns_success_when_condition_met(self):
        from friday.perception.types import OCRRegion, BoundingBox

        ws = (
            WorldStateBuilder()
            .add_ocr_regions(
                [OCRRegion(text="Ready", bbox=BoundingBox(0, 0, 10, 10), confidence=0.9)]
            )
            .build()
        )
        res = asyncio.run(
            P.wait_for("Ready", lambda: ws, timeout_ms=1000, poll_interval_ms=50)
        )
        assert res.is_success
        assert res.evidence.text_appeared == "Ready"

    def test_wait_for_times_out_when_condition_never_met(self):
        ws = make_world(browser=True)
        res = asyncio.run(
            P.wait_for("never appears", lambda: ws, timeout_ms=200, poll_interval_ms=50)
        )
        assert res.status == ActionStatus.TIMEOUT
        assert res.duration_ms >= 0


# ---------------------------------------------------------------------------
# timeout behaviour for the generic dispatch path
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_click_times_out_when_elapsed_exceeds_timeout(self):
        # adapter that always fails so the loop keeps retrying / re-checking
        # the timeout. With timeout_ms=0 the very first elapsed check trips.
        a = FakeAdapter("browser", 100, succeed=False)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world(), timeout_ms=0))
        assert res.status == ActionStatus.TIMEOUT


# ---------------------------------------------------------------------------
# metadata + contract invariants on success
# ---------------------------------------------------------------------------

class TestResultContract:
    def test_success_result_populates_timing(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.is_success
        assert res.started_at > 0
        assert res.duration_ms >= 0

    def test_success_result_is_actionresult_with_valid_status(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert isinstance(res, ActionResult)
        assert isinstance(res.status, ActionStatus)
        assert res.action_type == "click"
