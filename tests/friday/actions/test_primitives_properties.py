"""Property-based tests for the Universal Action Layer primitives.

Feature: universal-action-layer

This module verifies correctness Properties 5-19 from the design document
using Hypothesis. The AdapterResolver properties (1-4) belong to task 8.3 and
live alongside these if/when added.

SAFETY: These tests NEVER touch real I/O. Every adapter used here is an
in-memory fake (RecordingAdapter) that records the calls it receives and
returns canned ActionResult objects. No pyautogui / Playwright / window calls
are made. FRIDAY_DRY_RUN=1 is also enforced by the test session conftest.

All primitives are async; each property drives them through asyncio.run() so
no pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import friday.actions.primitives as primitives
from friday.actions.adapters.resolver import AdapterResolver
from friday.actions.primitives import (
    click,
    double_click,
    drag,
    press_hotkey,
    press_key,
    register_primitives,
    right_click,
    scroll,
    switch_window,
    type_text,
    verify,
    wait_for,
)
from friday.actions.result import ActionEvidence, ActionResult, ActionStatus
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BoundingBox, OCRRegion, PerceptionSource
from friday.perception.world_state import WorldState, WorldStateBuilder


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class RecordingAdapter:
    """In-memory fake adapter that records calls and returns canned results.

    Satisfies AdapterProtocol structurally. Never performs real I/O.
    """

    def __init__(
        self,
        name: str,
        priority: int,
        *,
        can: bool = True,
        element: Optional[ResolvedElement] = None,
        succeed: bool = True,
        window_changed: bool = False,
    ) -> None:
        self._name = name
        self._priority = priority
        self._can = can
        self._succeed = succeed
        self._window_changed = window_changed
        # Default resolved element (semantic UIA) if none supplied.
        self._element = element or ResolvedElement(
            text="el",
            source=PerceptionSource.UIA,
            priority=priority,
            confidence=0.9,
            clickable=True,
            bbox=(10, 10, 20, 20),
        )
        self.calls: List[tuple] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        return self._can

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        if not self._can:
            return None
        return self._element

    # -- result helpers --
    def _ok(self, action: str, target: str = "", **ev) -> ActionResult:
        return ActionResult.success(
            action=action,
            target=target,
            evidence=ActionEvidence(state_changed=True, **ev),
        )

    def _fail(self, action: str, target: str = "") -> ActionResult:
        return ActionResult.failed(
            action=action,
            target=target,
            error="recorded failure",
            error_category="adapter_failed",
            repair_hints=["retry"],
        )

    # -- async action methods --
    async def click(self, element: ResolvedElement) -> ActionResult:
        self.calls.append(("click", element))
        return self._ok("click", element.text) if self._succeed else self._fail("click", element.text)

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        self.calls.append(("double_click", element))
        return self._ok("double_click", element.text) if self._succeed else self._fail("double_click")

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        self.calls.append(("right_click", element))
        return self._ok("right_click", element.text) if self._succeed else self._fail("right_click")

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        self.calls.append(("type_text", text, element))
        return self._ok("type_text", text) if self._succeed else self._fail("type_text", text)

    async def press_key(self, key: str) -> ActionResult:
        self.calls.append(("press_key", key))
        return self._ok("press_key", key) if self._succeed else self._fail("press_key", key)

    async def press_hotkey(self, keys: List[str]) -> ActionResult:
        self.calls.append(("press_hotkey", list(keys)))
        return self._ok("press_hotkey", "+".join(keys)) if self._succeed else self._fail("press_hotkey")

    async def scroll(
        self, direction: str, amount: int, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        self.calls.append(("scroll", direction, amount, element))
        return self._ok("scroll") if self._succeed else self._fail("scroll")

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        self.calls.append(("drag", source, dest))
        return self._ok("drag") if self._succeed else self._fail("drag")

    async def focus_window(self, target: Target) -> ActionResult:
        self.calls.append(("focus_window", target))
        if self._succeed:
            return self._ok("focus_window", target.window_title, window_changed=True)
        return self._fail("focus_window", target.window_title)


def _set_resolver(adapters: List[RecordingAdapter]) -> None:
    """Install a resolver with the given fake adapters on the primitives module."""
    primitives._resolver = AdapterResolver(adapters)


def _empty_world() -> WorldState:
    return WorldStateBuilder().build()


def _world_with_text(text: str) -> WorldState:
    region = OCRRegion(text=text, bbox=BoundingBox(0, 0, 10, 10), confidence=0.9)
    return WorldStateBuilder().add_ocr_regions([region]).build()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_lower = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=15,
)

_VALID_STATUSES = set(ActionStatus)

_SEMANTIC_SOURCES = st.sampled_from(
    [PerceptionSource.BROWSER, PerceptionSource.UIA]
)


@st.composite
def targets(draw):
    """Generate a valid Target with at least a text identifier."""
    text = draw(_lower)
    role = draw(st.sampled_from(["button", "link", "textbox", ""]))
    return Target(text=text, role=role)


COMMON = dict(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ===========================================================================
# Property 5: Semantic-First Execution
# Validates: Requirements 3.3
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), source=_SEMANTIC_SOURCES)
def test_property_5_semantic_first_execution(target, source):
    """For a Target resolving to a semantic source, the element passed to the
    adapter has is_semantic == True and the recorded source is semantic."""
    element = ResolvedElement(
        text=target.text,
        source=source,
        priority=100 if source == PerceptionSource.BROWSER else 80,
        confidence=0.95,
        clickable=True,
        bbox=(5, 5, 10, 10),
    )
    adapter = RecordingAdapter("semantic", 100, element=element, succeed=True)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert result.is_success
    # The element dispatched to the adapter came from a semantic source.
    dispatched = adapter.calls[0][1]
    assert dispatched.is_semantic is True
    assert result.metadata["source"] == source.value


# ===========================================================================
# Property 6: Source Recorded in Metadata
# Validates: Requirements 3.5
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), source=st.sampled_from(list(PerceptionSource)))
def test_property_6_source_recorded_in_metadata(target, source):
    """Any successfully completed invocation records the resolved element's
    perception source in ActionResult.metadata['source']."""
    element = ResolvedElement(
        text=target.text,
        source=source,
        priority=50,
        confidence=0.8,
        bbox=(0, 0, 4, 4),
    )
    adapter = RecordingAdapter("any", 70, element=element, succeed=True)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert result.is_success
    assert "source" in result.metadata
    assert result.metadata["source"] == source.value


# ===========================================================================
# Property 7: Re-Routing on Adapter Failure
# Validates: Requirements 4.1, 4.2
# ===========================================================================

@settings(**COMMON)
@given(target=targets())
def test_property_7_rerouting_on_adapter_failure(target):
    """When the highest-priority adapter fails, resolution re-runs with it
    excluded and a lower-priority adapter executes the action."""
    high = RecordingAdapter("high", 100, succeed=False)
    low = RecordingAdapter("low", 50, succeed=True)
    _set_resolver([high, low])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    # First adapter was attempted, then the lower one succeeded.
    assert any(c[0] == "click" for c in high.calls)
    assert any(c[0] == "click" for c in low.calls)
    assert result.is_success
    assert result.metadata["adapter"] == "low"


# ===========================================================================
# Property 8: ActionResult Contract Invariant
# Validates: Requirements 5.1, 13.1
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), can=st.booleans(), succeed=st.booleans())
def test_property_8_actionresult_contract_invariant(target, can, succeed):
    """Every invocation returns an ActionResult with a valid status and a
    non-empty action_type, regardless of outcome."""
    adapter = RecordingAdapter("a", 80, can=can, succeed=succeed)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert isinstance(result, ActionResult)
    assert result.status in _VALID_STATUSES
    assert result.action_type != ""


# ===========================================================================
# Property 9: Success Implies Evidence
# Validates: Requirements 5.2
# ===========================================================================

@settings(**COMMON)
@given(target=targets())
def test_property_9_success_implies_evidence(target):
    """A state-changing primitive returning SUCCESS carries evidence."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    for prim in (click, double_click, right_click):
        result = asyncio.run(prim(target, _empty_world(), timeout_ms=5000))
        assert result.is_success
        assert result.evidence.has_evidence is True


# ===========================================================================
# Property 10: Failure Implies Error Category and Repair Hints
# Validates: Requirements 5.3
# ===========================================================================

@settings(**COMMON)
@given(target=targets())
def test_property_10_failure_implies_category_and_hints(target):
    """A FAILED result always has a non-None error_category and >=1 hint."""
    # No adapter can handle -> resolution exhaustion -> FAILED.
    adapter = RecordingAdapter("a", 80, can=False)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert result.status == ActionStatus.FAILED
    assert result.error_category is not None
    assert len(result.repair_hints) >= 1


# ===========================================================================
# Property 11: Timing Fields Populated
# Validates: Requirements 5.4
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), succeed=st.booleans(), can=st.booleans())
def test_property_11_timing_fields_populated(target, succeed, can):
    """started_at > 0 and duration_ms >= 0 for any invocation."""
    adapter = RecordingAdapter("a", 80, can=can, succeed=succeed)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert result.started_at > 0
    assert result.duration_ms >= 0


# ===========================================================================
# Property 12: Timeout Biconditional
# Validates: Requirements 5.5, 5.6, 8.4
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), timeout_ms=st.sampled_from([0, 5000]))
def test_property_12_timeout_biconditional(target, timeout_ms):
    """Status is TIMEOUT exactly when the time bound is already exhausted.

    timeout_ms == 0 means the budget is immediately exceeded (TIMEOUT);
    a generous budget with a fast adapter completes without TIMEOUT.
    """
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    result = asyncio.run(click(target, _empty_world(), timeout_ms=timeout_ms))

    if timeout_ms == 0:
        assert result.status == ActionStatus.TIMEOUT
        assert result.duration_ms >= 0
    else:
        assert result.status != ActionStatus.TIMEOUT


# ===========================================================================
# Property 13: Verify Condition Evaluation
# Validates: Requirements 7.2, 7.3
# ===========================================================================

@settings(**COMMON)
@given(base=_lower, present=st.booleans())
def test_property_13_verify_condition_evaluation(base, present):
    """verify returns SUCCESS iff the condition text is present in the state."""
    world = _world_with_text(base)
    if present:
        condition = base  # exact substring -> contained
    else:
        condition = base + "Q"  # longer than base -> cannot be a substring

    result = asyncio.run(verify(condition, world))

    if present:
        assert result.status == ActionStatus.SUCCESS
    else:
        assert result.status == ActionStatus.FAILED
        assert result.error_category == "verification_failed"


# ===========================================================================
# Property 14: Wait Polling Terminates Correctly
# Validates: Requirements 8.1, 8.2, 8.3, 8.4
# ===========================================================================

@settings(max_examples=25, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(base=_lower, will_meet=st.booleans())
def test_property_14_wait_polling_terminates(base, will_meet):
    """wait_for returns SUCCESS if the condition becomes true before timeout,
    TIMEOUT otherwise."""
    if will_meet:
        world = _world_with_text(base)
        result = asyncio.run(
            wait_for(base, lambda: world, timeout_ms=500, poll_interval_ms=10)
        )
        assert result.status == ActionStatus.SUCCESS
    else:
        world = _world_with_text(base)
        missing = base + "Q"
        result = asyncio.run(
            wait_for(missing, lambda: world, timeout_ms=40, poll_interval_ms=10)
        )
        assert result.status == ActionStatus.TIMEOUT


# ===========================================================================
# Property 15: Pointer Dispatch Correctness
# Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
# ===========================================================================

@settings(**COMMON)
@given(target=targets())
def test_property_15_pointer_dispatch_click_variants(target):
    """click/double_click/right_click each dispatch exactly their own call."""
    for prim, expected in (
        (click, "click"),
        (double_click, "double_click"),
        (right_click, "right_click"),
    ):
        adapter = RecordingAdapter("a", 80, succeed=True)
        _set_resolver([adapter])
        asyncio.run(prim(target, _empty_world(), timeout_ms=5000))
        dispatched = [c[0] for c in adapter.calls]
        assert dispatched == [expected]


@settings(**COMMON)
@given(
    direction=st.sampled_from(["up", "down", "left", "right"]),
    amount=st.integers(min_value=1, max_value=20),
)
def test_property_15_scroll_dispatch(direction, amount):
    """scroll dispatches scroll with the exact direction and amount."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    asyncio.run(scroll(direction, amount, _empty_world(), timeout_ms=5000))

    scroll_calls = [c for c in adapter.calls if c[0] == "scroll"]
    assert len(scroll_calls) == 1
    assert scroll_calls[0][1] == direction
    assert scroll_calls[0][2] == amount


@settings(**COMMON)
@given(src=_lower, dst=_lower)
def test_property_15_drag_dispatch(src, dst):
    """drag dispatches a single drag with both resolved source and dest."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    asyncio.run(
        drag(Target(text=src), Target(text=dst), _empty_world(), timeout_ms=5000)
    )

    drag_calls = [c for c in adapter.calls if c[0] == "drag"]
    assert len(drag_calls) == 1
    assert isinstance(drag_calls[0][1], ResolvedElement)
    assert isinstance(drag_calls[0][2], ResolvedElement)


# ===========================================================================
# Property 16: Keyboard Dispatch Correctness
# Validates: Requirements 10.1, 10.2, 10.3
# ===========================================================================

@settings(**COMMON)
@given(text=_lower)
def test_property_16_type_text_dispatch(text):
    """type_text passes the exact text to the adapter."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    asyncio.run(type_text(text, _empty_world(), target=Target(text="field")))

    type_calls = [c for c in adapter.calls if c[0] == "type_text"]
    assert len(type_calls) == 1
    assert type_calls[0][1] == text


@settings(**COMMON)
@given(key=st.sampled_from(["enter", "tab", "escape", "a", "f5"]))
def test_property_16_press_key_dispatch(key):
    """press_key passes the exact key to the adapter (focus present)."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])
    # browser_connected satisfies the focus precondition.
    world = WorldStateBuilder().set_browser_state(
        url="http://x", title="t", elements=[], connected=True
    ).build()

    asyncio.run(press_key(key, world))

    key_calls = [c for c in adapter.calls if c[0] == "press_key"]
    assert len(key_calls) == 1
    assert key_calls[0][1] == key


@settings(**COMMON)
@given(keys=st.lists(st.sampled_from(["ctrl", "alt", "shift", "s", "a"]),
                     min_size=1, max_size=3))
def test_property_16_press_hotkey_dispatch(keys):
    """press_hotkey passes the exact key list to the adapter."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    asyncio.run(press_hotkey(keys, _empty_world()))

    hk_calls = [c for c in adapter.calls if c[0] == "press_hotkey"]
    assert len(hk_calls) == 1
    assert hk_calls[0][1] == list(keys)


# ===========================================================================
# Property 17: No Focus Means Keyboard Fails
# Validates: Requirements 10.4
# ===========================================================================

@settings(**COMMON)
@given(text=_lower)
def test_property_17_no_focus_keyboard_fails(text):
    """type_text with no focus and no target fails with a focus repair hint."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])
    # No focused_element, browser not connected, no target.
    world = _empty_world()

    result = asyncio.run(type_text(text, world))

    assert result.status == ActionStatus.FAILED
    assert result.error_category == "no_focus"
    assert any("focus" in hint for hint in result.repair_hints)


# ===========================================================================
# Property 18: Switch Window Success Evidence
# Validates: Requirements 11.1, 11.2
# ===========================================================================

@settings(**COMMON)
@given(title=_lower)
def test_property_18_switch_window_success_evidence(title):
    """A successful switch_window carries window_changed evidence."""
    adapter = RecordingAdapter("a", 80, succeed=True)
    _set_resolver([adapter])

    result = asyncio.run(
        switch_window(Target(window_title=title), _empty_world(), timeout_ms=5000)
    )

    assert result.is_success
    assert result.evidence.window_changed is True


# ===========================================================================
# Property 19: Registry Discoverability
# Validates: Requirements 12.2
# ===========================================================================

def test_property_19_registry_discoverability():
    """Querying the registry for each primitive capability returns the
    universal primitive whose handler is the primitive function."""
    from friday.tools.registry import ToolCapability, ToolRegistry

    registry = ToolRegistry()
    register_primitives(registry)

    expected = {
        ToolCapability.CLICK_ELEMENT: click,
        ToolCapability.TYPE_TEXT: type_text,
        ToolCapability.SCROLL: scroll,
        ToolCapability.SWITCH_WINDOW: switch_window,
        ToolCapability.VERIFY_RESULT: verify,
    }

    for capability, handler in expected.items():
        tools = registry.find_tools(capability)
        assert tools, f"no tool found for {capability}"
        top = tools[0]
        assert top.name.startswith("universal.")
        assert top.handler is handler


# ===========================================================================
# AdapterResolver properties (Properties 1-4)
#
# These exercise friday.actions.adapters.resolver.AdapterResolver directly,
# plus the primitive-level exhaustion behaviour for Property 4. They reuse the
# in-memory RecordingAdapter test double defined above; no real I/O occurs.
# ===========================================================================


@st.composite
def adapter_specs(draw, *, min_size: int = 1, max_size: int = 4,
                  require_one_handler: bool = False):
    """Generate a list of (name, priority, can_handle) adapter specs.

    Priorities are unique so "highest priority" is always unambiguous. Each
    spec also carries a `can` flag controlling whether the adapter can handle
    (and therefore resolve) the target.
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    priorities = draw(
        st.lists(
            st.integers(min_value=1, max_value=200),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    cans = [draw(st.booleans()) for _ in range(n)]
    if require_one_handler and not any(cans):
        # Force at least one adapter that can handle the target.
        cans[draw(st.integers(min_value=0, max_value=n - 1))] = True
    specs = []
    for i, (prio, can) in enumerate(zip(priorities, cans)):
        specs.append((f"adapter_{i}", prio, can))
    return specs


def _build_adapters(specs, *, succeed: bool = True):
    """Materialize RecordingAdapter instances from (name, priority, can) specs."""
    return [
        RecordingAdapter(name, prio, can=can, succeed=succeed)
        for (name, prio, can) in specs
    ]


# Pre-built world states covering browser-only, desktop/ocr, and empty cases.
def _world_variants():
    browser = WorldStateBuilder().set_browser_state(
        url="http://x", title="t", elements=[], connected=True
    ).build()
    ocr = _world_with_text("hello")
    return [_empty_world(), browser, ocr]


# ===========================================================================
# Property 1: Priority Resolution
# Validates: Requirements 1.3, 2.1, 2.2, 3.1, 3.2
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), specs=adapter_specs(require_one_handler=True))
def test_property_1_priority_resolution(target, specs):
    """The resolver selects the highest-priority adapter among those that can
    handle AND resolve a non-None element."""
    adapters = _build_adapters(specs)
    resolver = AdapterResolver(adapters)

    result = resolver.resolve(target, _empty_world())

    # At least one adapter can handle (require_one_handler), so a selection
    # must occur.
    assert result is not None
    selected_adapter, element = result
    assert element is not None

    # Expected winner: highest priority among can_handle == True adapters.
    handlers = [a for a in adapters if a.can_handle(target, _empty_world())]
    expected = max(handlers, key=lambda a: a.priority)
    assert selected_adapter.name == expected.name
    assert selected_adapter.priority == expected.priority


# ===========================================================================
# Property 2: All Adapters Remain Candidates
# Validates: Requirements 2.3
# ===========================================================================

@settings(**COMMON)
@given(
    target=targets(),
    specs=adapter_specs(min_size=2, max_size=4),
    world=st.sampled_from(_world_variants()),
)
def test_property_2_all_adapters_remain_candidates(target, specs, world):
    """No adapter is pruned based on environment: every registered adapter is
    eligible for selection. Verified by making each adapter the sole handler
    in turn and confirming it is selected, regardless of WorldState."""
    names = {name for (name, _prio, _can) in specs}
    # The resolver must retain exactly the registered adapters.
    resolver = AdapterResolver(_build_adapters(specs))
    retained = {a.name for a in resolver._adapters}
    assert retained == names

    # Each adapter, when it is the only one that can handle, must be selectable
    # under any WorldState -> proves none were pruned.
    for idx in range(len(specs)):
        adapters = [
            RecordingAdapter(name, prio, can=(i == idx), succeed=True)
            for i, (name, prio, _can) in enumerate(specs)
        ]
        only_resolver = AdapterResolver(adapters)
        result = only_resolver.resolve(target, world)
        assert result is not None
        assert result[0].name == specs[idx][0]


# ===========================================================================
# Property 3: Fallback to Lower-Priority Adapter
# Validates: Requirements 2.4, 4.3, 4.4
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), high_prio=st.integers(80, 200), gap=st.integers(1, 70))
def test_property_3_fallback_to_lower_priority(target, high_prio, gap):
    """When the highest-priority adapter cannot resolve but a lower-priority
    one can, the resolver selects the lower-priority adapter."""
    low_prio = high_prio - gap
    high = RecordingAdapter("high", high_prio, can=False, succeed=True)
    low = RecordingAdapter("low", low_prio, can=True, succeed=True)
    resolver = AdapterResolver([high, low])

    result = resolver.resolve(target, _empty_world())

    assert result is not None
    selected_adapter, element = result
    assert selected_adapter.name == "low"
    assert element is not None


@settings(**COMMON)
@given(target=targets())
def test_property_3_no_resolution_returns_none(target):
    """When no adapter can resolve the target, resolve() returns None."""
    adapters = [
        RecordingAdapter("a", 100, can=False),
        RecordingAdapter("b", 50, can=False),
    ]
    resolver = AdapterResolver(adapters)

    assert resolver.resolve(target, _empty_world()) is None


# ===========================================================================
# Property 4: Exhaustion Produces FAILED with Attempted Adapters
# Validates: Requirements 2.5, 4.5, 9.6
# ===========================================================================

@settings(**COMMON)
@given(target=targets(), specs=adapter_specs(min_size=2, max_size=4))
def test_property_4_exhaustion_lists_attempted_adapters(target, specs):
    """When every adapter can handle but all fail execution, the primitive
    exhausts them all and returns FAILED, with repair hints present and the
    set of attempted adapters recorded on the result.

    Note: the primitive records attempted adapters in
    metadata['adapters_attempted'] (the concrete contract surface), while
    repair_hints carry generic recovery guidance. Both are asserted here.
    """
    # All adapters can handle but fail -> primitive cascades through them all.
    adapters = [
        RecordingAdapter(name, prio, can=True, succeed=False)
        for (name, prio, _can) in specs
    ]
    _set_resolver(adapters)

    result = asyncio.run(click(target, _empty_world(), timeout_ms=5000))

    assert result.status == ActionStatus.FAILED
    assert result.error_category is not None
    assert len(result.repair_hints) >= 1
    # Every attempted adapter must be recorded on the failed result.
    attempted = set(result.metadata.get("adapters_attempted", []))
    expected = {name for (name, _prio, _can) in specs}
    assert attempted == expected
