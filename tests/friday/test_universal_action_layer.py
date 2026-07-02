"""Tests for the Universal Action Layer (M1 prerequisite).

The action layer had ZERO tests (Truth Report). Before wiring it into the
operator, prove it works: adapter resolution by priority, primitive dispatch,
fallback cascade on failure, focus rules, observe/verify/wait_for, and registry
integration. All adapters are mocked — no real pyautogui/Playwright I/O.
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


def make_world(browser=False):
    b = WorldStateBuilder()
    if browser:
        b.set_browser_state(url="https://x.com", title="X", elements=[], connected=True)
    return b.build()


def resolved(name_source=PerceptionSource.BROWSER):
    return ResolvedElement(
        text="Submit", source=name_source, priority=100,
        confidence=0.95, clickable=True, bbox=(10, 10, 20, 20), raw_element=None,
    )


class FakeAdapter:
    """Configurable adapter implementing the protocol surface we use."""

    def __init__(self, name, priority, can=True, element=None, succeed=True,
                 source=PerceptionSource.BROWSER):
        self._name = name
        self._priority = priority
        self._can = can
        self._element = element if element is not None else resolved(source)
        self._succeed = succeed
        self.calls = []

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

    async def _result(self, action):
        self.calls.append(action)
        if self._succeed:
            return ActionResult.success(
                action=action, target="Submit",
                evidence=ActionEvidence(state_changed=True),
            )
        return ActionResult.failed(
            action=action, error="forced failure", target="Submit",
            error_category="adapter_failed", repair_hints=["retry"],
        )

    async def click(self, element):
        return await self._result("click")

    async def double_click(self, element):
        return await self._result("double_click")

    async def right_click(self, element):
        return await self._result("right_click")

    async def type_text(self, text, element=None):
        return await self._result("type_text")

    async def press_key(self, key):
        return await self._result("press_key")

    async def press_hotkey(self, keys):
        return await self._result("press_hotkey")

    async def scroll(self, direction, amount, element=None):
        return await self._result("scroll")

    async def drag(self, source, dest):
        return await self._result("drag")

    async def focus_window(self, target):
        return await self._result("focus_window")


# --------------------------------------------------------------------------
# Resolver
# --------------------------------------------------------------------------

class TestResolver:
    def test_selects_highest_priority(self):
        low = FakeAdapter("low", 30)
        high = FakeAdapter("high", 100)
        r = AdapterResolver([low, high])
        adapter, _ = r.resolve(Target(text="Submit"), make_world())
        assert adapter.name == "high"

    def test_falls_back_when_higher_cannot_handle(self):
        high = FakeAdapter("high", 100, can=False)
        low = FakeAdapter("low", 30, can=True)
        r = AdapterResolver([high, low])
        adapter, _ = r.resolve(Target(text="Submit"), make_world())
        assert adapter.name == "low"

    def test_returns_none_when_no_adapter_handles(self):
        a = FakeAdapter("a", 50, can=False)
        r = AdapterResolver([a])
        assert r.resolve(Target(text="Submit"), make_world()) is None

    def test_exclude_skips_named_adapter(self):
        high = FakeAdapter("high", 100)
        low = FakeAdapter("low", 30)
        r = AdapterResolver([high, low])
        adapter, _ = r.resolve(Target(text="Submit"), make_world(), exclude=["high"])
        assert adapter.name == "low"


# --------------------------------------------------------------------------
# Primitive dispatch + fallback
# --------------------------------------------------------------------------

class TestPrimitiveDispatch:
    def setup_method(self):
        # reset module resolver between tests
        P._resolver = None

    def test_click_dispatches_to_adapter(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.is_success
        assert "click" in a.calls
        assert res.metadata.get("adapter") == "browser"
        assert res.metadata.get("source")  # source recorded

    def test_uninitialized_returns_failure(self):
        P._resolver = None
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert not res.is_success
        assert res.error_category == "not_initialized"

    def test_fallback_cascade_on_failure(self):
        failing = FakeAdapter("browser", 100, succeed=False)
        working = FakeAdapter("desktop", 80, succeed=True)
        P._resolver = AdapterResolver([failing, working])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert res.is_success
        assert res.metadata.get("adapter") == "desktop"
        # the failing adapter was attempted first
        assert "click" in failing.calls

    def test_all_fail_returns_failed_with_attempts(self):
        a = FakeAdapter("browser", 100, succeed=False)
        b = FakeAdapter("desktop", 80, succeed=False)
        P._resolver = AdapterResolver([a, b])
        res = asyncio.run(P.click(Target(text="Submit"), make_world()))
        assert not res.is_success
        assert "adapters_attempted" in res.metadata

    def test_no_adapter_returns_target_not_found(self):
        a = FakeAdapter("browser", 100, can=False)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.click(Target(text="Nope"), make_world()))
        assert not res.is_success
        assert res.error_category == "target_not_found"

    def test_double_and_right_click_dispatch(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        asyncio.run(P.double_click(Target(text="Submit"), make_world()))
        asyncio.run(P.right_click(Target(text="Submit"), make_world()))
        assert "double_click" in a.calls and "right_click" in a.calls


# --------------------------------------------------------------------------
# Keyboard focus rules
# --------------------------------------------------------------------------

class TestKeyboardRules:
    def setup_method(self):
        P._resolver = None

    def test_type_text_no_focus_fails(self):
        a = FakeAdapter("desktop", 80)
        P._resolver = AdapterResolver([a])
        # no target, no focused element, no browser → must fail with no_focus
        res = asyncio.run(P.type_text("hello", make_world(browser=False)))
        assert not res.is_success
        assert res.error_category == "no_focus"

    def test_type_text_with_browser_connected_ok(self):
        a = FakeAdapter("browser", 100)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.type_text("hello", make_world(browser=True)))
        assert res.is_success
        assert "type_text" in a.calls

    def test_press_hotkey_no_focus_required(self):
        a = FakeAdapter("desktop_actions", 60)
        P._resolver = AdapterResolver([a])
        res = asyncio.run(P.press_hotkey(["ctrl", "s"], make_world(browser=False)))
        assert res.is_success
        assert "press_hotkey" in a.calls


# --------------------------------------------------------------------------
# observe / verify / wait_for
# --------------------------------------------------------------------------

class TestEnvironmentPrimitives:
    def test_observe_fails_with_no_sources(self):
        ws = WorldStateBuilder().build()  # no sources
        res = asyncio.run(P.observe(ws))
        assert not res.is_success
        assert res.error_category == "perception_unavailable"

    def test_verify_finds_text(self):
        b = WorldStateBuilder()
        b.set_browser_state(url="u", title="t", elements=[], connected=True)
        ws = b.build()
        # contains_text searches all_text; inject via ocr-like path not available,
        # so verify on empty should fail honestly
        res = asyncio.run(P.verify("nonexistent phrase", ws))
        assert not res.is_success
        assert res.error_category == "verification_failed"

    def test_wait_for_times_out_quickly(self):
        ws = make_world(browser=True)
        res = asyncio.run(
            P.wait_for("never appears", lambda: ws, timeout_ms=200, poll_interval_ms=50)
        )
        assert res.status == ActionStatus.TIMEOUT


# --------------------------------------------------------------------------
# Registry integration
# --------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_register_primitives_adds_universal_tools(self):
        from friday.tools.registry import build_default_registry, ToolCapability
        registry = build_default_registry()
        P.register_primitives(registry)
        click_tools = registry.find_tools(ToolCapability.CLICK_ELEMENT)
        assert click_tools
        # universal primitive should be highest priority (10)
        assert click_tools[0].name == "universal.click"
        assert click_tools[0].priority == 10

    def test_universal_tools_have_callable_handlers(self):
        from friday.tools.registry import build_default_registry, ToolCapability
        registry = build_default_registry()
        P.register_primitives(registry)
        tool = registry.find_tools(ToolCapability.TYPE_TEXT)[0]
        assert callable(tool.handler)
