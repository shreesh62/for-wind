"""Unit tests for AdapterResolver.

Task 8.2 — exercises `friday/actions/adapters/resolver.py` through a set of
self-contained in-memory fake adapters. No real I/O occurs: each fake adapter
only implements the resolution surface the resolver touches (`name`,
`priority`, `can_handle`, `resolve_element`).

Coverage:
- priority ordering is descending after construction
- highest-priority handler is selected when several can handle
- lower-priority adapter selected when higher ones cannot handle
- adapters that can_handle but resolve None are skipped
- exclusion set re-routes past named adapters
- empty adapter list / no match returns None
- deterministic ordering across equivalent constructions

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

from friday.actions.adapters.resolver import AdapterResolver
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import PerceptionSource
from friday.perception.world_state import WorldState, WorldStateBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_world() -> WorldState:
    """A minimal WorldState; the fake adapters ignore its contents."""
    return WorldStateBuilder().build()


def make_element(name: str, priority: int) -> ResolvedElement:
    """A canned ResolvedElement tagged with the adapter name for assertions."""
    return ResolvedElement(
        text=name,
        source=PerceptionSource.BROWSER,
        priority=priority,
        confidence=0.9,
        clickable=True,
        bbox=(0, 0, 10, 10),
        raw_element=None,
    )


class FakeAdapter:
    """In-memory adapter exposing only the resolver-facing surface.

    Args:
        name: unique identifier used for exclusion + assertions.
        priority: resolution priority (higher = preferred).
        can: value returned by can_handle.
        resolves: when False, resolve_element returns None even if can_handle
                  is True (simulates an adapter that matches but fails to
                  locate the element).
    """

    def __init__(self, name: str, priority: int, *, can: bool = True, resolves: bool = True):
        self._name = name
        self._priority = priority
        self._can = can
        self._resolves = resolves
        self.can_handle_calls = 0
        self.resolve_calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def can_handle(self, target, world_state) -> bool:
        self.can_handle_calls += 1
        return self._can

    def resolve_element(self, target, world_state):
        self.resolve_calls += 1
        if self._can and self._resolves:
            return make_element(self._name, self._priority)
        return None


# ---------------------------------------------------------------------------
# Construction / ordering
# ---------------------------------------------------------------------------

class TestOrdering:
    def test_constructor_sorts_adapters_by_priority_descending(self):
        low = FakeAdapter("vision", 30)
        high = FakeAdapter("browser", 100)
        mid = FakeAdapter("desktop", 80)
        resolver = AdapterResolver([low, high, mid])
        priorities = [a.priority for a in resolver._adapters]
        assert priorities == [100, 80, 30]

    def test_ordering_is_deterministic_across_input_orderings(self):
        adapters_a = [
            FakeAdapter("a", 30),
            FakeAdapter("b", 100),
            FakeAdapter("c", 80),
            FakeAdapter("d", 60),
        ]
        adapters_b = [
            FakeAdapter("b", 100),
            FakeAdapter("d", 60),
            FakeAdapter("a", 30),
            FakeAdapter("c", 80),
        ]
        order_a = [a.priority for a in AdapterResolver(adapters_a)._adapters]
        order_b = [a.priority for a in AdapterResolver(adapters_b)._adapters]
        assert order_a == order_b == [100, 80, 60, 30]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestResolve:
    def test_highest_priority_handler_selected_when_multiple_can_handle(self):
        high = FakeAdapter("browser", 100)
        mid = FakeAdapter("desktop", 80)
        low = FakeAdapter("vision", 30)
        resolver = AdapterResolver([mid, low, high])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is not None
        adapter, element = result
        assert adapter.name == "browser"
        assert element.text == "browser"

    def test_lower_priority_selected_when_higher_cannot_handle(self):
        high = FakeAdapter("browser", 100, can=False)
        mid = FakeAdapter("desktop", 80, can=True)
        resolver = AdapterResolver([high, mid])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is not None
        adapter, _ = result
        assert adapter.name == "desktop"
        # higher-priority adapter was consulted but did not resolve
        assert high.resolve_calls == 0

    def test_skips_adapter_that_can_handle_but_resolves_none(self):
        # browser claims it can handle but fails to locate the element
        high = FakeAdapter("browser", 100, can=True, resolves=False)
        mid = FakeAdapter("desktop", 80, can=True, resolves=True)
        resolver = AdapterResolver([high, mid])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is not None
        adapter, _ = result
        assert adapter.name == "desktop"
        # the higher-priority adapter did attempt resolution
        assert high.resolve_calls == 1

    def test_returns_none_when_no_adapter_can_handle(self):
        a = FakeAdapter("browser", 100, can=False)
        b = FakeAdapter("desktop", 80, can=False)
        resolver = AdapterResolver([a, b])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is None

    def test_returns_none_when_all_handlers_resolve_none(self):
        a = FakeAdapter("browser", 100, can=True, resolves=False)
        b = FakeAdapter("desktop", 80, can=True, resolves=False)
        resolver = AdapterResolver([a, b])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is None

    def test_empty_adapter_list_returns_none(self):
        resolver = AdapterResolver([])
        result = resolver.resolve(Target(text="Submit"), make_world())
        assert result is None


# ---------------------------------------------------------------------------
# Exclusion / re-routing
# ---------------------------------------------------------------------------

class TestExclusion:
    def test_exclusion_skips_named_adapter_and_reroutes(self):
        high = FakeAdapter("browser", 100)
        mid = FakeAdapter("desktop", 80)
        resolver = AdapterResolver([high, mid])
        result = resolver.resolve(
            Target(text="Submit"), make_world(), exclude=["browser"]
        )
        assert result is not None
        adapter, _ = result
        assert adapter.name == "desktop"
        # excluded adapter is never consulted
        assert high.can_handle_calls == 0
        assert high.resolve_calls == 0

    def test_exclusion_of_all_handlers_returns_none(self):
        high = FakeAdapter("browser", 100)
        mid = FakeAdapter("desktop", 80)
        resolver = AdapterResolver([high, mid])
        result = resolver.resolve(
            Target(text="Submit"), make_world(), exclude=["browser", "desktop"]
        )
        assert result is None

    def test_empty_exclusion_behaves_like_no_exclusion(self):
        high = FakeAdapter("browser", 100)
        mid = FakeAdapter("desktop", 80)
        resolver = AdapterResolver([high, mid])
        result = resolver.resolve(Target(text="Submit"), make_world(), exclude=[])
        assert result is not None
        adapter, _ = result
        assert adapter.name == "browser"

    def test_exclusion_reroutes_through_multiple_failed_adapters(self):
        a = FakeAdapter("browser", 100)
        b = FakeAdapter("desktop", 80)
        c = FakeAdapter("vision", 30)
        resolver = AdapterResolver([a, b, c])
        result = resolver.resolve(
            Target(text="Submit"), make_world(), exclude=["browser", "desktop"]
        )
        assert result is not None
        adapter, _ = result
        assert adapter.name == "vision"


# ---------------------------------------------------------------------------
# Candidate retention regardless of world state
# ---------------------------------------------------------------------------

class TestCandidateRetention:
    def test_all_adapters_retained_after_construction(self):
        names = ["browser", "desktop", "desktop_actions", "vision"]
        adapters = [
            FakeAdapter("browser", 100),
            FakeAdapter("desktop", 80),
            FakeAdapter("desktop_actions", 60),
            FakeAdapter("vision", 30),
        ]
        resolver = AdapterResolver(adapters)
        retained = [a.name for a in resolver._adapters]
        assert sorted(retained) == sorted(names)
